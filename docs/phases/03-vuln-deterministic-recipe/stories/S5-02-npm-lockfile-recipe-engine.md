# Story S5-02 — `NpmLockfileRecipeEngine` (production day-1 implementation)

**Step:** Step 5 — Transform ABC consumers, RecipeEngine Protocol, RecipeRegistry, lockfile policy
**Status:** Done — GREEN 2026-05-20 (phase-story-executor; see [`_attempts/S5-02.md`](_attempts/S5-02.md) for the per-AC evidence table, the as-built contract-drift resolutions, and the gate log — 100% branch coverage on `npm_lockfile.py`, full suite + fences + import-linter + pre-commit + docs all green). The prior BLOCKED `apply`-2-tuple-vs-Protocol-conformance contradiction was resolved by [ADR-0014](../ADRs/0014-recipe-engine-surfaces-transform-via-transform-registry.md) + story S5-01b (`TransformRegistry`, GREEN): `apply` returns a bare `RecipeOutcome` and the produced `NpmLockfileTransform` is surfaced via a constructor-injected `TransformRegistry`. See the **Re-execution note** below — it is authoritative and supersedes every conflicting AC / outline / TDD-plan statement elsewhere in this file. Two ACs are environment-gated / deferred (see the attempt log): **AC-Gold-1** runs only where `bwrap` + `npm` are both present (skipped in the default CI matrix; the golden infrastructure ships, the `.after.json` is an authored placeholder pending a real jailed run), and **AC-Plan-3** is N/A — the S6-06 contract-snapshot test + `recipe_outcome.schema.json` do not exist yet (S6-06 is HARDENED, not shipped); the additive `ApplicationPlan` widening is in place for S6-06 to baseline.
**Effort:** L
**Depends on:** S5-01 (`RecipeEngine` Protocol at `transforms/recipe_engine.py` + `ApplicationPlan`), S5-01b (`TransformRegistry` at `transforms/transform_registry.py` — the channel for the produced Transform; GREEN), S1-03 (`outcomes.py` discriminated unions), S1-04 (`Transform` ABC + `TransformProvenance`), S4-01 (`SubprocessJail` Port + `JailedSubprocessSpec` + `JailedSubprocessResult` variant shapes), S4-04 (`SandboxedPath` + `O_NOFOLLOW`; HARDENED — integration TOCTOU AC gates on this story being GREEN at execute-time), S4-05 (`NpmInstallCapability` + `mint()`; HARDENED).
**ADRs honored:** ADR-0009, ADR-0010, ADR-0007, ADR-0006, ADR-0011, ADR-0001 (Phase-5 contract snapshot — `Transform` / `RecipeOutcome` shape pinned), Phase-1 ADR-0007 (`ErrorId` dotted-snake format)

## Re-execution note (2026-05-20 — `codewizard-executer`; un-blocks this story)

This story was `BLOCKED` on 2026-05-20: two acceptance criteria contradicted each other against the landed S5-01 `RecipeEngine.apply(...) -> RecipeOutcome`. [ADR-0014](../ADRs/0014-recipe-engine-surfaces-transform-via-transform-registry.md) resolves the design question and story **S5-01b** (`TransformRegistry`, GREEN) ships the missing component. The **corrected contract below is authoritative** — it supersedes every conflicting statement elsewhere in this file: Validation note #2, Validation note #18, the `apply` return-contract line in the "Convention" block, AC-Apply-1, AC-Surface-2, AC-Surface-4, Implementation outline §5–§7, and **every `outcome, transform = await ...apply(...)` destructure in the TDD plan**.

**Corrected contract (authoritative):**

1. **`apply` returns a bare `RecipeOutcome`** — `async def apply(self, repo: SandboxedPath, plan: ApplicationPlan, capability: NpmInstallCapability) -> RecipeOutcome`. NOT a 2-tuple. This is the as-built S5-01 Protocol surface verbatim (ADR-0001 / ADR-0009 frozen); the harden-pass 2-tuple rewrite is withdrawn.
2. **The constructor takes the registry** — `__init__(self, jail: SubprocessJail, transform_registry: TransformRegistry)` (two args). `TransformRegistry` is imported from `codegenie.transforms.transform_registry`. No other ambient state; no module-level mutable state (the AC-Surface-4 fence is unchanged — it walks `transforms/engines/*.py`, and `transform_registry.py` is not under `engines/`).
3. **The produced `NpmLockfileTransform` is surfaced via the registry.** On the happy path the engine builds the `NpmLockfileTransform`, calls `self._transform_registry.register(transform)`, then returns `Applied(kind="applied", transform_id=transform.transform_id, plugin_id=…, recipe_id=…)`. Non-Applied branches return their `RecipeFailed` / `RecipeNotApplicable` outcome and register nothing.
4. **Tests obtain the Transform by lookup.** Where a TDD-plan test wrote `outcome, transform = await engine.apply(...)`, the corrected form is: `outcome = await engine.apply(...)`; then `transform = transform_registry.get(outcome.transform_id)` — the test constructs the `TransformRegistry`, injects it into the engine, and reads it back. `outcome.transform_id == transform.transform_id` holds by construction.
5. **AC-Surface-2(b) now type-checks** — `_engine: RecipeEngine = NpmLockfileRecipeEngine(jail, transform_registry)` is assignable because `apply`'s return type matches the Protocol exactly.

Nothing else changes: the six-step pipeline, the closed error-id taxonomy, the size/depth caps, the golden round-trip, and the determinism ACs all stand.

## Validation notes (2026-05-19, phase-story-validator)

The original draft carried substantial as-built contract drift that would have BLOCKED the executor on the first import. Every change below was made because the corresponding shape is **already shipped** under `src/codegenie/transforms/` (S1-03 GREEN, S1-04 GREEN), `src/codegenie/plugins/protocols.py` (S2-01 GREEN; S5-01 HARDENED moves it to `transforms/recipe_engine.py`), or `src/codegenie/transforms/sandbox_jail.py` (S4-01 HARDENED).

**Block-grade corrections (the executor would hard-fail without these):**

1. **`RecipeOutcome.Failed(reason=…, exit_code=…, stderr_tail=…)` rewritten to `RecipeFailed(error=RecipeError(error_id="recipe.<…>", message=…, details={…}))`.** Per as-built `src/codegenie/transforms/outcomes.py:222`, `RecipeFailed.error: RecipeError(error_id: ErrorId, message: str, details: dict[str, str|int|bool|float] | None)`. There is no `reason` field, no `exit_code` field, no `stderr_tail` field. Every failure AC now constructs the canonical `RecipeError`; counters and contextual data go in `details`. (Coverage + Consistency findings F1.)
2. **`RecipeOutcome.Applied(transform=NpmLockfileTransform(...))` rewritten to `Applied(transform_id=…, plugin_id=…, recipe_id=…)`.** Per `outcomes.py:189`, the `Applied` variant carries the BLAKE3-hex `transform_id` (lookup key), NOT the Transform instance itself. The `NpmLockfileTransform` *instance* is returned alongside via the `(outcome, transform)` tuple pattern (see new AC-Apply-1) — the recipe engine returns a 2-tuple `(RecipeOutcome, Transform | None)` where the Transform is `None` on every non-Applied branch. The Transform is stashed by the orchestrator (S6-04) keyed by `transform_id`. (Coverage + Consistency F2.)
3. **`RecipePlan(package=…, from_version=…, to_version=…, kind=…)` removed; `ApplicationPlan` widened additively.** S5-01 HARDENED pins the Protocol parameter type to `ApplicationPlan` (per `outcomes.py:174`, currently `summary: str | None = None`). The docstring at `outcomes.py:178` explicitly says the field set widens additively for S5-02. This story now lands the **additive widening** (new optional fields: `package: PackageId | None`, `from_version: str | None`, `to_version: str | None`, `transform_kind: TransformKind | None`) plus a smart-constructor `ApplicationPlan.for_npm_semver_bump(...)` that fills them. Backwards-compatible: every existing `ApplicationPlan(summary=...)` call site keeps working (additive widen, no field removal — Rule 11 + extension by addition). (Consistency F3.)
4. **`Completed(exit_code=0, stdout=b"", stderr=b"")` and bare-arg `TimedOut() / OomKilled() / NetworkDenied()` rewritten to S4-01 shapes.** Per as-built `sandbox_jail.py`, the discriminated-union variants are `Completed(exit_code, stdout_bytes: int, stderr_bytes: int, wall_time_s: float)`, `TimedOut(budget_s, elapsed_s)`, `OomKilled(peak_rss_mib)`, `NetworkDenied(host: str)`, `DiskQuotaExceeded(quota_bytes, bytes_written)`. The `stderr_tail` AC is impossible under this Port (no byte buffer is captured, only counters) and has been **dropped**, replaced with `details={"exit_code": …, "stderr_bytes": …, "wall_time_s": …}` carry-through. (Coverage F4.)
5. **`Transform.files_changed: tuple[SandboxedPath, ...]` (was `list[...]`).** Per `transform.py:94` the as-built type is `tuple`. Test fixtures and the `NpmLockfileTransform` subclass corrected. (Consistency F5.)
6. **All failure `reason` strings rewritten as dotted-snake `error_id` literals.** Phase-1 ADR-0007 mandates `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` and `ErrorId` validates on construction. The taxonomy is enumerated as a module-top closed `Literal` (new AC-Tax-1) following the S1-03 / S4-01 / S1-05 precedent. (Consistency F6.)

**Harden-grade corrections:**

7. **`Result[T, E]` invention removed.** Original "if `codegenie.util.result` exists import from there; else define minimal `_Result`" violates Rule 7 (surface conflicts; don't average) and Rule 2 (simplicity first) — no such kernel exists in the codebase. Replaced with a **private discriminated union of small Pydantic models** (`_PJsonError | _IoError | _NpmError | _LockfileError`, each `frozen=True, extra="forbid"`, all keyed by `kind: Literal["…"]`) the `apply` body `match`-dispatches on. Mirrors the codebase convention from `outcomes.py`. (Design-Patterns F1.)
8. **`spec.env is NpmEnv` rewritten to `spec.env.kind == "npm"` + per-field assertions on the `NpmEnv` payload.** S4-01 HARDENED env is the `JailedEnv = Annotated[NpmEnv | GitEnv, Field(discriminator="kind")]` sum. `NpmEnv.npm_config_ignore_scripts == "true"` is the load-bearing ADR-0007 cross-check (CLI AND env). (Test-Quality F1.)
9. **Error-id Literal taxonomy enumerated + fence-tested.** New module-top `_NpmLockfileErrorId: Literal[...]` + an `_ERROR_IDS: Final[frozenset[ErrorId]]` assertion (mirrors S1-05 `_WARNING_IDS` precedent). AC-Tax-1 pins the set. Adding a new failure mode = new entry in the Literal + new AC; *deleting* one breaks the Phase-3 contract snapshot. (Design-Patterns F2.)
10. **`pyproject.toml` `orjson` dep added explicitly to Files-to-touch + import-linter `forbidden_modules` lists checked.** Arch §C12 names orjson; the dep is currently absent from `pyproject.toml`. The story now lists the dep addition as a load-bearing step and adds an `import_linter` allow-comment so `tests/unit/test_pyproject_fence.py` keeps green. (Consistency F7.)
11. **`O_NOFOLLOW` integration test gated on S4-04 GREEN.** S4-04 is HARDENED (not GREEN) and `SandboxedPath: TypeAlias = pathlib.Path` in `transforms/_forward.py` does not yet enforce `O_NOFOLLOW`. The TOCTOU AC is now split: an **always-run unit AC** asserts that the engine code path opens via `SandboxedPath.open(...)` (AST-walk fence — no raw `os.open` under `transforms/engines/`); a **conditional integration AC** with `pytest.mark.skipif(SandboxedPath is pathlib.Path, reason="S4-04 substitution not yet shipped")` runs the symlink-swap race after S4-04 GREEN. (Test-Quality F2.)
12. **Mutation-test AC made operational.** Original "missing-flag mutation tests cause assertion to fail" rewritten as a parametrized test that monkeypatches `_NPM_INSTALL_CMD` (or constructs a shadowed engine with a shortened tuple via dependency injection of the constant) and asserts the integration test fails for each dropped flag. (Test-Quality F3.)
13. **Pure-helper fence AC added** (AST-walk on `npm_lockfile.py` confirms `_read_package_json` / `_edit_dep_version` / `_max_depth` / `_build_unified_diff` carry no `await`, no `os.*`, no `subprocess`). Mirrors the S1-05 `_no_io_in_pure_helpers` precedent. (Design-Patterns F3.)
14. **Key-order across-edits property AC added** (the original no-op round-trip only proves no-op preservation). New parametrized test edits each dep version in turn and asserts every other byte stays bit-identical (line-diff cardinality ≤ 1). Closes the mutation gap where a re-serialize could re-sort other keys silently. (Test-Quality F4.)
15. **Adversarial repo-content AC added** (§Edge case E20 — NUL bytes in `name`; `PackageId.parse` smart-constructor rejection). (Coverage F1 — edge case coverage.)
16. **Golden-regen guard AC added** (`tests/golden/lockfiles/` changes require a `.regen-justification` sidecar — fence test rejects PRs that modify the byte-equal golden without the sidecar). Implements G4-determinism intent at the human-review boundary. (Test-Quality F5.)
17. **Closed-sum dispatch on JailedSubprocessResult** — added an explicit `assert_never` exhaustiveness AC mirroring S4-01 AC-9. The engine's mapping over `JailedSubprocessResult` variants must compile under mypy-strict; adding a new variant must break the mapping until the engine handles it. (Design-Patterns F4.)
18. **`isinstance(NpmLockfileRecipeEngine(jail), RecipeEngine)` strengthened.** Per S5-01, `RecipeEngine` is `@runtime_checkable` AND mypy structurally typed. AC now asserts both: runtime `isinstance(...)` is True AND a mypy-strict assignment `_engine: RecipeEngine = NpmLockfileRecipeEngine(jail)` type-checks (mirrors S4-01's `_StubJail` Port-proof pattern). (Design-Patterns F5.)

**No `RESCUE` conditions** — the story's goal, scope, and arch-trace are sound. Verdict: **HARDENED**. Full critic dossier at `_validation/S5-02-npm-lockfile-recipe-engine.md`.

---

## Context

`NpmLockfileRecipeEngine` is **the** production day-1 `RecipeEngine` for Phase 3 (ADR-0009 Option C: ship the Protocol with two real implementations from day one). Every Phase 3 npm vulnerability-remediation workflow routes through this engine — the four npm recipes (`NpmLockfileSemverBumpRecipe`, `NpmPeerDepConflictRecipe`, `NpmTransitiveOverridesRecipe`, `NpmMajorBumpRefuseRecipe`, all in S7-02) produce a `RecipePlan` and hand it here. The engine performs the *deterministic* lockfile edit Phase 3 commits to (cardinal goal G4 — byte-identical `Transform.diff_bytes` across 100 Hypothesis runs of `test_transform_determinism`).

The pipeline per `../phase-arch-design.md §C12` is six steps and every parameter matters:

1. Parse `package.json` via `orjson` with a **1 MiB size cap** (rejects oversized inputs before the parser; depth is bounded structurally by `orjson` itself but we add an explicit depth-16 check on the parsed tree for parity with §C11 ingest caps).
2. Edit the affected dep version **in-memory while preserving key order** (this is why we use `orjson` not `json` — `orjson` preserves insertion order; `json` does too in CPython 3.7+ but `orjson` is the production parser, and `option=orjson.OPT_INDENT_2 | OPT_SORT_KEYS=False` is the round-trip pin).
3. Write back through `SandboxedPath` with **`O_NOFOLLOW`** (S4-04) — the TOCTOU defense from §Edge case E12; a symlink swap between the read and write raises `OSError(ELOOP)`, caught and turned into `RecipeOutcome.Failed(filesystem_race)`.
4. Run `SubprocessJail.run(npm install --package-lock-only --ignore-scripts --no-audit --prefer-offline)` — **all four flags are required, not options**:
   - `--package-lock-only` regenerates `package-lock.json` without populating `node_modules` (fast + no postinstall surface).
   - `--ignore-scripts` is the postinstall-canary defense (§Edge case E10); npm has shipped bugs where one of CLI/env was honored and not the other, so S4-05 enforces both `--ignore-scripts` flag AND `npm_config_ignore_scripts=true` env. This story's job is to pass the CLI flag; the env wrapping is `NpmEnv`'s job (S4-01).
   - `--no-audit` suppresses the synchronous network call to the npm audit endpoint (deterministic, offline-respecting).
   - `--prefer-offline` instructs npm to consult its on-disk cache before egress (warm-cache determinism; cold-cache still hits `registry.npmjs.org` under the `RegistryAllowlist`).
5. Parse the new lockfile (`package-lock.json` v3 — npm v7+) with caps **32 MiB / depth 24** — lockfiles are larger and deeper than `package.json`; npm v1 lockfiles fail-fast with `LockfileVersionUnsupported` per §Edge case E1.
6. Return `RecipeOutcome.Applied(NpmLockfileTransform(...))` — the `NpmLockfileTransform` concrete subclass of `Transform` (ABC from S1-04) carries `diff_bytes` (the unified diff of `package.json` + `package-lock.json` before/after), `files_changed: list[SandboxedPath]`, and `provenance: TransformProvenance` (plugin id, recipe id, version, applied-at, capability-use event id).

The engine is **pure-Python at every step except `npm install`** — no shelling out to `npm` for the parse / edit / re-parse. This is the determinism contract: a `json.loads` round-trip of two side-by-side `package.json` files produces byte-identical edits regardless of whether `npm` is installed; only the lockfile regeneration uses npm, and that's deterministic given a fixed warm cache + `--prefer-offline`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C12` — the six-step pipeline; this story implements it verbatim.
  - `../phase-arch-design.md §Scenario A` (lines 309–340) — the engine's role in the happy-path sequence.
  - `../phase-arch-design.md §Edge cases E1, E10, E11, E12, E14` — lockfile v1 rejection, postinstall canary, `cve_delta` introduction, symlink TOCTOU, lockfile depth bomb.
  - `../phase-arch-design.md §Data model` — `Transform` ABC, `NpmLockfileTransform(Transform)`, `TransformProvenance`.
  - `../phase-arch-design.md §Defaults` — time budget for `npm install --package-lock-only` is 60 s (the value `JailedSubprocessSpec.time_budget_s` will carry from this engine).
- **Phase ADRs:**
  - `../ADRs/0009-recipe-engine-protocol-with-two-implementations-day-1.md` — ADR-0009 — this story's engine is one of the two day-1 implementations.
  - `../ADRs/0007-run-npm-install-and-npm-test-in-phase3-jail.md` — ADR-0007 — `npm install` MUST run inside `SubprocessJail`; `--ignore-scripts` enforcement at CLI AND env.
  - `../ADRs/0006-hexagonal-subprocessjail-port-bwrap-sandbox-exec.md` — ADR-0006 — `SubprocessJail` Port; `JailedSubprocessSpec` typed env + network policy.
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — ADR-0010 — `RecipeOutcome` discriminated union; `TransformId = blake3(diff_bytes)`; `PackageId.parse` smart constructor.
  - `../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — ADR-0011 — `SandboxedPath.open()` is always `O_NOFOLLOW`.
- **Source design:**
  - `../final-design.md §Synthesis ledger row "Default recipe engine"` (score 15/15).
- **High-level impl:**
  - `../High-level-impl.md §Step 5 — Features delivered` bullet 3 (`engines/npm_lockfile.py`); `Done criteria` lines 1 + 5 (golden lockfile byte-equal).
- **Sibling stories:**
  - `S5-01-recipe-registry.md` — the `RecipeEngine` Protocol this story conforms to; `RecipePlan` model.
  - `S4-01-subprocess-jail-port.md` — `SubprocessJail`, `JailedSubprocessSpec`, `NpmEnv`, `NetworkPolicy = RegistryAllowlist`.
  - `S4-02-bwrap-adapter-linux.md` / `S4-03-sandbox-exec-adapter-macos.md` — runtime substrate; this story tests against an in-memory fake `SubprocessJail` + an integration test against the real adapter.
  - `S4-04-sandboxed-path-onofollow.md` — `SandboxedPath.open(mode)` with `O_NOFOLLOW`; symlink swap raises.
  - `S4-05-allowed-binaries-capabilities.md` — `NpmInstallCapability` minted by the orchestrator; this story consumes (never mints).
  - `S1-04-transform-abc-apply-context.md` — `Transform` ABC + `TransformProvenance`.

## Goal

Ship `src/codegenie/transforms/engines/npm_lockfile.py` exposing `NpmLockfileRecipeEngine` and `NpmLockfileTransform`. `NpmLockfileRecipeEngine.apply(repo, plan, capability)` performs the six-step pipeline above and returns a typed `RecipeOutcome` discriminated-union variant for every failure mode. Golden-file test confirms `tests/golden/lockfiles/express-cve-2024-21501.before.json` → `.after.json` byte-equal under the engine.

## Acceptance criteria

> **Convention.** Every `RecipeFailed(error=…)` AC below names the `error_id` literal as a dotted-snake `ErrorId` per Phase-1 ADR-0007 (`^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`). Failures are constructed as `RecipeFailed(error=RecipeError(error_id=ErrorId("recipe.<…>"), message="…", details={…}))` per as-built `outcomes.py:222`. There is **no** `RecipeOutcome.Failed(reason=…)` shape — that was contract drift; see Validation notes #1.
> **`apply` return contract (per the Re-execution note + ADR-0014):** `async def apply(self, repo, plan, capability) -> RecipeOutcome` — a bare `RecipeOutcome`, NOT a tuple. On the happy path the engine `register`s the produced `NpmLockfileTransform` into the constructor-injected `TransformRegistry` and returns `Applied(transform_id=transform.transform_id, …)`; the orchestrator (S6-04) retrieves the Transform via `transform_registry.get(Applied.transform_id)`. This is the as-built S5-01 Protocol surface — the earlier 2-tuple wording is withdrawn.

### Surface + module shape

- [ ] **AC-Surface-1.** `from codegenie.transforms.engines.npm_lockfile import NpmLockfileRecipeEngine, NpmLockfileTransform` succeeds. Module's `__all__` is exactly `{"NpmLockfileRecipeEngine", "NpmLockfileTransform"}` (private helpers — leading underscore — never re-exported). A meta-test asserts `set(npm_lockfile.__all__) == EXPECTED`.
- [ ] **AC-Surface-2.** `NpmLockfileRecipeEngine` structurally satisfies the S5-01 `RecipeEngine` Protocol both at runtime and under mypy: (a) `isinstance(NpmLockfileRecipeEngine(jail, transform_registry), RecipeEngine) is True` (Protocol is `@runtime_checkable` per S5-01 AC-2); (b) a mypy-strict assignment `_engine: RecipeEngine = NpmLockfileRecipeEngine(jail, transform_registry)` type-checks — `apply`'s `-> RecipeOutcome` return matches the Protocol exactly (fence file `tests/unit/transforms/test_npm_lockfile_typing.py` runs `mypy --strict` on a tiny module containing the assignment and asserts exit code 0).
- [ ] **AC-Surface-3.** `NpmLockfileTransform` is a `Transform` ABC subclass (S1-04) declaring the four class-level annotations: `transform_id: TransformId`, `diff_bytes: bytes`, `files_changed: tuple[SandboxedPath, ...]` (length 2 — `package.json` + `package-lock.json`; note `tuple`, **not** `list` per as-built `transform.py:94`), `provenance: TransformProvenance`. The subclass overrides nothing else; `TypeError` on direct `Transform(...)` instantiation continues to fire (inherited).
- [ ] **AC-Surface-4.** `NpmLockfileRecipeEngine.__init__(self, jail: SubprocessJail, transform_registry: TransformRegistry)` is the only public constructor — the `jail` and the `transform_registry` are both constructor-injected (ADR-0014); no global registry write at import time; no module-level mutable state. A fence test (`tests/fence/test_engines_no_module_state.py`) AST-walks `transforms/engines/*.py` and rejects any module-level non-`Final` assignment of mutable type.

### Error-id taxonomy (closed sum)

- [x] **AC-Tax-1.** Module-top declaration: `_NpmLockfileErrorId: TypeAlias = Literal[...]` AND `_ERROR_IDS: Final[frozenset[ErrorId]]` derived from `get_args(_NpmLockfileErrorId)` at import time. A meta-test asserts `_ERROR_IDS` round-trips through the `ErrorId` newtype validator. **Adding a new failure mode is a Literal expansion + a new AC in this story; deleting one re-baselines the Phase-3 contract snapshot (S6-06).** — *Executor amendment 2026-05-20: the count is **14**, not 13. The as-built `JailedSubprocessResult` (S4-01 GREEN) carries a sixth variant `JailSetupFailed`; the `assert_never` exhaustive `match` of AC-4g cannot compile under `mypy --strict` without a sixth arm, and that arm needs an `error_id`. The 14th entry is `recipe.jail_setup_failed`. This is the story's own sanctioned extension path (a Literal expansion) and was the explicit recommendation in Attempt-1's BLOCKED analysis.*

### Step 1 — `package.json` parse + caps

- [ ] **AC-1a.** A 1 MiB + 1 byte `package.json` fixture yields `RecipeFailed(error=RecipeError(error_id=ErrorId("recipe.package_json_too_large"), message="package.json exceeds 1 MiB cap", details={"limit_bytes": 1048576, "observed_bytes": 1048577}))`. The jail spy records **zero** calls (asserted as `len(jail.calls) == 0`) — npm install MUST short-circuit before invocation.
- [ ] **AC-1b.** A depth-17 nested `package.json` (e.g., `{"a":{"a":{…×17}}}` synthesized programmatically in the test) yields `RecipeFailed(error=RecipeError(error_id=ErrorId("recipe.package_json_depth_exceeded"), message=…, details={"limit": 16, "observed": 17}))`. The jail spy still records zero calls.
- [ ] **AC-1c — Adversarial repo content** (§Edge case E20). A `package.json` whose `name` contains a NUL byte (`"name": "a\x00b"`) or a bidi-control character (U+202E) yields `RecipeFailed(error=RecipeError(error_id=ErrorId("recipe.adversarial_repo_content"), …))`. The `PackageId.parse(...)` smart-constructor rejection is the gate — the engine does not invent a parallel validator. Test parametrized over `[NUL, BIDI_RLE, "..", "/"]`.

### Step 2 — In-memory edit, key-order preserved

- [ ] **AC-2a — No-op round-trip byte-identity.** With a plan whose `to_version` equals the existing version, the post-`apply` `package.json` bytes are bit-identical to the pre-`apply` bytes. Test reads/writes `tests/fixtures/repos/express-cve-2024-21501/package.json` and asserts `before == after` (whole-file byte comparison).
- [ ] **AC-2b — Edited round-trip preserves *every other* key order + bytes.** Parametrized over each top-level dep in the express fixture (`express`, `lodash`): edit only that dep's version; assert the resulting file differs from the input in **at most the targeted version-line region** (line-diff cardinality computed via `difflib.unified_diff` ≤ 4 lines total: hunk header + minus + plus + context — exact bound asserted). Closes the mutation gap where a silent re-sort across the dict could pass AC-2a.
- [ ] **AC-2c — Dep not in `package.json`.** A plan targeting a dep absent from all four sections (`dependencies`, `devDependencies`, `optionalDependencies`, `overrides`) yields `RecipeFailed(error=RecipeError(error_id=ErrorId("recipe.package_not_in_dependencies"), details={"package": "<pkg>", "sections_searched": ["dependencies", "devDependencies", "optionalDependencies", "overrides"]}))`. The jail spy records zero calls.
- [ ] **AC-2d — Section precedence.** When a dep appears in multiple sections (e.g., both `dependencies` and `devDependencies`), the engine edits the **first** match in declaration order (`dependencies` > `devDependencies` > `optionalDependencies` > `overrides`) — asserted by a fixture seeding the same package in two sections and confirming only the first is edited; `TransformProvenance.details["edited_section"]` carries the name.

### Step 3 — Write-back via `SandboxedPath`

- [ ] **AC-3a — `SandboxedPath` API exclusively** (always-run AST fence). `tests/fence/test_engines_no_raw_os_open.py` AST-walks `src/codegenie/transforms/engines/` and rejects any `Call` whose function resolves to `os.open`, `pathlib.Path.open`, `builtins.open`, or `io.open`. The only open is `SandboxedPath.open(...)` (which will set `O_NOFOLLOW` once S4-04 substitutes the typealias).
- [ ] **AC-3b — Symlink TOCTOU integration test** (§Edge case E12, **conditional**). `tests/integration/test_npm_lockfile_engine_jail.py::test_symlink_swap_returns_filesystem_race` is decorated `@pytest.mark.skipif(SandboxedPath is pathlib.Path, reason="S4-04 substitution not yet shipped; this test re-enables when transforms/_forward.py re-exports the real SandboxedPath.")`. When enabled, the test creates a symlink-swap race against a sentinel file (NOT `/etc/passwd` — use a temp file `tmp_path / "sentinel"` whose pre-write mtime is captured, to avoid CI flakiness and rootful-runner ambiguity), asserts `RecipeFailed(error=RecipeError(error_id=ErrorId("recipe.filesystem_race"), details={"path": "package.json"}))`, AND asserts `sentinel.stat().st_mtime` is unchanged. Once S4-04 lands GREEN, the skipif gate evaluates False and the test runs.

### Step 4 — `npm install` under `SubprocessJail`

- [ ] **AC-4a — Exact `cmd` tuple.** `JailedSubprocessSpec.cmd` recorded by the spy is **exactly** `("npm", "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--prefer-offline")` — order and value bit-identical. AC fails on permutation, on missing element, on extra element.
- [ ] **AC-4b — Per-flag mutation test** (Test-Quality F3). `tests/unit/transforms/test_npm_lockfile_mutation_flags.py` parametrizes over `range(2, len(_NPM_INSTALL_CMD))` (indices 2..5 — the four flags; not `npm`, not `install`). For each index `i`, the test injects an engine constructed with a monkey-patched `_NPM_INSTALL_CMD = tuple(c for j, c in enumerate(_NPM_INSTALL_CMD) if j != i)`, runs the happy-path test, and asserts the **post-install lockfile-bytes** golden test FAILS (golden contains all four flags' effects; dropping any one produces a different lockfile under the fake jail's synthetic write). Verifies each flag carries observable weight.
- [ ] **AC-4c — Network policy.** `spec.network` is `RegistryAllowlist(hosts=("registry.npmjs.org",))` — asserted via `spec.network.kind == "registry_allowlist"` AND `spec.network.hosts == ("registry.npmjs.org",)` (the exact tuple, not subset). A second AC (`AC-4c2`) asserts that the engine NEVER constructs a `DenyAll` or `AllowAll` network policy under any code path (AST-walk fence).
- [ ] **AC-4d — Budget envelope.** `spec.time_budget_s == 60.0` AND `spec.memory_mib == 1024` AND `spec.pids_max == 1024`. All three pinned to the `_NPM_INSTALL_*` `Final` constants module-top; mutation of any constant via a parametrized test causes the AC to fail (mirrors AC-4b).
- [ ] **AC-4e — Typed env discriminator.** `spec.env.kind == "npm"` (the S4-01 `JailedEnv` sum discriminator) AND `spec.env.npm_config_ignore_scripts == "true"` (the ADR-0007 CLI-AND-env load-bearing cross-check; the CLI half lives in `_NPM_INSTALL_CMD[3]`). `mypy --strict` assignment `_env: NpmEnv = spec.env` succeeds — pinned by a small mypy-positive fence file (`tests/unit/transforms/test_npm_lockfile_typing.py`).
- [ ] **AC-4f — Non-zero exit → typed `RecipeFailed`.** When jail returns `Completed(kind="completed", exit_code=1, stdout_bytes=0, stderr_bytes=512, wall_time_s=0.01)`, engine returns `RecipeFailed(error=RecipeError(error_id=ErrorId("recipe.npm_install_exit_nonzero"), message="npm install exited 1", details={"exit_code": 1, "stderr_bytes": 512, "wall_time_s": 0.01}))`. (`stderr_tail` is **not** carried — S4-01's `Completed` exposes only counts; AC dropped from original draft.)
- [ ] **AC-4g — Exhaustive `JailedSubprocessResult` mapping** (mirrors S4-01 AC-9). Engine's mapping over `JailedSubprocessResult` is implemented via a `match` statement with `assert_never` on the discriminated union. Each non-`Completed` variant maps to a typed `RecipeFailed`:
  - `TimedOut(budget_s=60.0, elapsed_s=61.2)` → `error_id=ErrorId("recipe.install_timeout")`, `details={"budget_s": 60.0, "elapsed_s": 61.2}`
  - `OomKilled(peak_rss_mib=1100)` → `error_id=ErrorId("recipe.install_oom")`, `details={"peak_rss_mib": 1100}`
  - `NetworkDenied(host="attacker.example.com")` → `error_id=ErrorId("recipe.network_policy_violation")`, `details={"host": "attacker.example.com"}`
  - `DiskQuotaExceeded(quota_bytes=…, bytes_written=…)` → `error_id=ErrorId("recipe.disk_quota_exceeded")`, `details={"quota_bytes": …, "bytes_written": …}`
  - `JailSetupFailed(reason=…, detail=…)` → `error_id=ErrorId("recipe.jail_setup_failed")`, `details={"reason": …, "detail": …}` *(Executor amendment 2026-05-20 — the as-built `JailedSubprocessResult` sixth variant; see AC-Tax-1.)*
- [ ] **AC-4g2 — mypy-narrowing exhaustiveness** (mirrors S4-01 AC-9a). `tests/unit/transforms/test_npm_lockfile_mypy_negative.py` spawns `mypy --strict` on a temp file that omits one `match` arm for `JailedSubprocessResult` inside the engine's mapping helper and asserts the exit code is non-zero with an `assert_never` error on the missing variant. Without this, deleting a variant or widening the union silently passes the runtime exhaustiveness AC.

### Step 5 — Parse new lockfile

- [ ] **AC-5a — Lockfile size cap.** A 32 MiB + 1 byte lockfile yields `RecipeFailed(error=RecipeError(error_id=ErrorId("recipe.lockfile_too_large"), details={"limit_bytes": 33554432, "observed_bytes": 33554433}))`.
- [ ] **AC-5b — Lockfile depth cap.** A depth-25 lockfile yields `RecipeFailed(error=RecipeError(error_id=ErrorId("recipe.lockfile_depth_exceeded"), details={"limit": 24, "observed": 25}))`.
- [ ] **AC-5c — Lockfile v1 rejection** (§Edge case E1). A `lockfileVersion: 1` lockfile yields `RecipeFailed(error=RecipeError(error_id=ErrorId("recipe.lockfile_v1_unsupported"), details={"lockfile_version": 1, "supported": [3]}))` **before** parsing the body (i.e., the size+depth checks pass but the version-dispatch short-circuits). Order is asserted: a v1 *and* oversize file emits `recipe.lockfile_too_large` (size cap wins; it's the earlier check) — this ordering is pinned by a parametrized test.

### Step 6 — Build `Applied` outcome + `NpmLockfileTransform`

- [ ] **AC-Apply-1.** Happy path returns a bare `Applied(kind="applied", transform_id=TransformId(<blake3-hex>), plugin_id=…, recipe_id=…)` (a `RecipeOutcome` variant — see the Re-execution note). The engine has `register`-ed the produced `NpmLockfileTransform` into the injected `TransformRegistry`: `transform = transform_registry.get(outcome.transform_id)` succeeds and `transform.transform_id == outcome.transform_id`. `len(transform.files_changed) == 2`; both entries point under `repo`.
- [ ] **AC-Apply-2.** `transform.transform_id == TransformId(blake3.blake3(transform.diff_bytes).hexdigest())` — the BLAKE3 identity is recomputed in the test against the diff bytes; equality is structural.
- [ ] **AC-Apply-3.** `transform.provenance` is a `TransformProvenance` carrying `plugin_id`, `plugin_version` (semver-shape), `recipe_id`, `recipe_version` (semver-shape), `transform_kind` (= the `TransformKind` from the plan), `applied_at` (timezone-aware UTC), `capability_use_id` (the EventId minted by the orchestrator when it minted the `NpmInstallCapability`). The `capability` parameter is read for the `capability_use_id` field (validates the engine threads the audit anchor through — fence test for "capability parameter is observed somewhere in the function body" via AST-walk).

### Determinism + golden file

- [ ] **AC-Det-1 — Intra-run determinism (5×).** Running `apply(...)` five times against five **freshly-restored** copies of the same fixture (re-copied from a read-only source between iterations) produces five byte-identical `diff_bytes`. Asserted as `len({d for d in diffs}) == 1`. The two-file diff structure (`--- file: package.json ---` / `--- file: package-lock.json ---`) is exercised in each iteration; both files contribute to the byte set so a regression in only the second file is caught.
- [ ] **AC-Gold-1 — Golden round-trip.** `tests/golden/lockfiles/express-cve-2024-21501.before.json` (initial lockfile) + `tests/fixtures/repos/express-cve-2024-21501/package.json` → `engine.apply(plan=ApplicationPlan.for_npm_semver_bump(package=PackageId("express"), from_version="^4.17.1", to_version="^4.19.2", transform_kind=TransformKind("npm-lockfile-semver-bump")))` → the resulting lockfile bytes are byte-equal to `tests/golden/lockfiles/express-cve-2024-21501.after.json`. The test uses the **real** `BwrapAdapter` `SubprocessJail` on the Linux CI runner (gated `@pytest.mark.skipif(shutil.which("bwrap") is None, reason="…")`). The same fixture is consumed by S8-02 end-to-end.
- [ ] **AC-Gold-2 — Golden-regen guard.** `tests/golden/lockfiles/*.before.json` and `*.after.json` are write-protected by a fence test (`tests/fence/test_golden_lockfile_regen_guard.py`) that detects modifications to those files without a corresponding `tests/golden/lockfiles/<name>.regen-justification.md` sidecar (containing free-form text and at minimum a `Reason:` line). The fence test runs `git diff --name-only HEAD~1` (or the PR base in CI) and rejects any PR that touches the golden without the sidecar. Determinism contract G4 is human-reviewable at the PR boundary.

### Pure-helper / functional-core fence

- [ ] **AC-Pure-1.** AST-walk on `src/codegenie/transforms/engines/npm_lockfile.py` confirms the named pure helpers (`_read_package_json`, `_edit_dep_version`, `_max_depth`, `_build_unified_diff`, `_parse_lockfile`, `_compute_transform_id`) contain (a) **no** `await` expressions, (b) **no** call whose `attr` resolves to `os`, `subprocess`, `shutil`, `pathlib.Path.write_*`, `pathlib.Path.open` other than via a passed-in `SandboxedPath` arg, (c) **no** module-level mutable state read. Side effects live exclusively in `apply()` and `_run_npm_install()`. Fence file: `tests/fence/test_npm_lockfile_pure_helpers.py` mirrors S1-05's `_no_io_in_pure_helpers` precedent.

### `ApplicationPlan` widening (load-bearing prerequisite)

- [ ] **AC-Plan-1.** `src/codegenie/transforms/outcomes.py::ApplicationPlan` is widened additively with: `package: PackageId | None = None`, `from_version: str | None = None` (semver-shape boundary regex if non-None — same `_SEMVER_RX` precedent as `TransformProvenance.plugin_version`), `to_version: str | None = None` (same), `transform_kind: TransformKind | None = None`. The existing `summary: str | None = None` field is preserved. All four new fields are optional with `None` defaults — no existing call site `ApplicationPlan(summary=...)` breaks (asserted by a test that imports `outcomes.py` and constructs `ApplicationPlan(summary="x")` AND `ApplicationPlan()` AND `ApplicationPlan(package=PackageId("x"), from_version="1.0.0", to_version="1.0.1", transform_kind=TransformKind("npm-lockfile-semver-bump"))`).
- [ ] **AC-Plan-2.** `ApplicationPlan.for_npm_semver_bump(package: PackageId, from_version: str, to_version: str, transform_kind: TransformKind) -> ApplicationPlan` classmethod smart constructor (returns a frozen instance with all four fields set and `summary=None`). The engine reads exactly these four fields; an AC-level mypy-positive test asserts `plan.package is not None` is the precondition the engine checks (engine returns `RecipeFailed(error_id="recipe.package_not_in_dependencies", message="ApplicationPlan missing package field")` if any required field is None).
- [ ] **AC-Plan-3 — S6-06 contract snapshot.** ~~`tests/integration/test_phase5_contract_snapshot.py` is re-baselined by this story.~~ *Executor resolution 2026-05-20: **N/A — deferred to S6-06.** Neither `tests/integration/test_phase5_contract_snapshot.py` nor `tests/golden/contracts/recipe_outcome.schema.json` exists — story S6-06 (`phase5-contract-snapshot`, currently HARDENED, not shipped) is the deliverable that BUILDS that infrastructure. There is nothing to re-baseline. The additive `ApplicationPlan` widening is landed and S6-06 will snapshot it against the widened shape when it runs. Creating the snapshot now would be scope creep into S6-06 and risk conflicting with its design.*

### Determinism + Phase-3 cardinal goal G4 (cross-references)

- [ ] **AC-Det-2 — No-LLM fence.** No `import anthropic`, `import openai`, `import langchain`, `import langgraph`, `import transformers` under `src/codegenie/transforms/engines/`. Re-asserted at module level by the existing `tests/unit/test_pyproject_fence.py` + `make lint-imports` (no edits required here — the fence is already wired; this AC is a reminder, not a new test).

### Tooling + coverage

- [ ] **AC-Tool-1.** `mypy --strict src/codegenie/transforms/engines/npm_lockfile.py` exits 0 with no `Any`, no `# type: ignore`, no untyped def.
- [ ] **AC-Tool-2.** `ruff check`, `ruff format --check`, `pytest tests/unit/transforms/test_npm_lockfile_engine.py tests/integration/test_npm_lockfile_engine_jail.py tests/unit/transforms/test_npm_lockfile_mutation_flags.py tests/unit/transforms/test_npm_lockfile_mypy_negative.py tests/unit/transforms/test_npm_lockfile_typing.py tests/fence/test_engines_no_raw_os_open.py tests/fence/test_engines_no_module_state.py tests/fence/test_npm_lockfile_pure_helpers.py tests/fence/test_golden_lockfile_regen_guard.py` all green.
- [ ] **AC-Tool-3.** Branch coverage on `src/codegenie/transforms/engines/npm_lockfile.py` ≥ 95% (`pytest --cov=codegenie.transforms.engines.npm_lockfile --cov-branch --cov-fail-under=95`).
- [ ] **AC-Tool-4.** `pyproject.toml` declares `orjson` (>=3.9) in `[project].dependencies`; `[tool.importlinter]` contracts allow `orjson` import from `codegenie.transforms.engines.*`; `tests/unit/test_pyproject_fence.py::FORBIDDEN_LLM_SDKS` is **not** widened (orjson is not an LLM SDK; no fence-edit required — this AC is a fence cross-check, not a fence edit).

## Implementation outline

1. Create `src/codegenie/transforms/engines/__init__.py` (empty docstring; no re-exports beyond the engine module) and `src/codegenie/transforms/engines/npm_lockfile.py`.
2. **Widen `ApplicationPlan` additively** (AC-Plan-1, AC-Plan-2) in `src/codegenie/transforms/outcomes.py` — four optional fields (`package`, `from_version`, `to_version`, `transform_kind`) + `for_npm_semver_bump(...)` classmethod. Re-baseline `tests/golden/contracts/recipe_outcome.schema.json` (S6-06 contract snapshot) in the same commit (Validation note #3).
3. **Add `orjson` to `pyproject.toml`** (AC-Tool-4). Insert under `[project].dependencies`. No `[tool.importlinter]` edit required (orjson is not in any forbidden list).
4. Constants module-top in `npm_lockfile.py`:
   ```python
   _PACKAGE_JSON_MAX_BYTES: Final[int] = 1 * 1024 * 1024            # 1 MiB
   _PACKAGE_JSON_MAX_DEPTH: Final[int] = 16
   _LOCKFILE_MAX_BYTES:     Final[int] = 32 * 1024 * 1024           # 32 MiB
   _LOCKFILE_MAX_DEPTH:     Final[int] = 24
   _NPM_INSTALL_TIME_BUDGET_S: Final[float] = 60.0
   _NPM_INSTALL_MEMORY_MIB:    Final[int] = 1024
   _NPM_INSTALL_PIDS_MAX:      Final[int] = 1024
   _NPM_INSTALL_CMD: Final[tuple[str, ...]] = (
       "npm", "install",
       "--package-lock-only",        # index 2 — fast, no node_modules
       "--ignore-scripts",           # index 3 — ADR-0007 postinstall canary (CLI half)
       "--no-audit",                 # index 4 — deterministic, offline-respecting
       "--prefer-offline",           # index 5 — warm-cache determinism
   )
   _REGISTRY_ALLOWLIST_HOSTS: Final[tuple[str, ...]] = ("registry.npmjs.org",)
   _DEP_SECTIONS_PRECEDENCE: Final[tuple[str, ...]] = (
       "dependencies", "devDependencies", "optionalDependencies", "overrides",
   )

   _NpmLockfileErrorId: TypeAlias = Literal[
       "recipe.package_json_too_large",
       "recipe.package_json_depth_exceeded",
       "recipe.filesystem_race",
       "recipe.npm_install_exit_nonzero",
       "recipe.install_timeout",
       "recipe.install_oom",
       "recipe.network_policy_violation",
       "recipe.disk_quota_exceeded",
       "recipe.lockfile_too_large",
       "recipe.lockfile_depth_exceeded",
       "recipe.lockfile_v1_unsupported",
       "recipe.package_not_in_dependencies",
       "recipe.adversarial_repo_content",
   ]
   _ERROR_IDS: Final[frozenset[ErrorId]] = frozenset(
       ErrorId(eid) for eid in typing.get_args(_NpmLockfileErrorId)
   )
   ```
5. **Internal error sum (private, no leaking to public API).** Replace the original `Result[T, E]` invention with a discriminated union of small Pydantic models matching the codebase convention (`outcomes.py` precedent — Design-Patterns F1):
   ```python
   class _PJsonError(BaseModel):
       model_config = ConfigDict(frozen=True, extra="forbid")
       kind: Literal["pjson"] = "pjson"
       error_id: ErrorId
       details: dict[str, str | int | bool | float]

   class _IoError(BaseModel):
       model_config = ConfigDict(frozen=True, extra="forbid")
       kind: Literal["io"] = "io"
       error_id: ErrorId            # "recipe.filesystem_race" only (Phase 3 scope)
       details: dict[str, str | int | bool | float]

   class _NpmError(BaseModel):
       model_config = ConfigDict(frozen=True, extra="forbid")
       kind: Literal["npm"] = "npm"
       error_id: ErrorId
       details: dict[str, str | int | bool | float]

   class _LockfileError(BaseModel):
       model_config = ConfigDict(frozen=True, extra="forbid")
       kind: Literal["lockfile"] = "lockfile"
       error_id: ErrorId
       details: dict[str, str | int | bool | float]

   _InternalError: TypeAlias = Annotated[
       _PJsonError | _IoError | _NpmError | _LockfileError,
       Field(discriminator="kind"),
   ]
   ```
   Each pure helper returns `tuple[T | None, _InternalError | None]` (Phase-3 internal value-or-error convention). The `apply` body `match`-dispatches on `_InternalError` to construct the canonical `RecipeFailed` outcome.
6. `NpmLockfileRecipeEngine.__init__(self, jail: SubprocessJail, transform_registry: TransformRegistry)` — both the jail and the `TransformRegistry` (imported from `codegenie.transforms.transform_registry`) are constructor-injected (ADR-0014); **no other ambient state, no global registry write at import time** (AC-Surface-4).
7. `async def apply(self, repo: SandboxedPath, plan: ApplicationPlan, capability: NpmInstallCapability) -> RecipeOutcome` — pure orchestration calling private helpers; the `apply` body is a sequence of helper calls each guarded by `if err is not None: return _to_failed(err)`; on success it builds the `NpmLockfileTransform`, calls `self._transform_registry.register(transform)`, and returns `Applied(transform_id=transform.transform_id, …)`. **No `try/except`** except the precisely-scoped `OSError(ELOOP)` catch inside `_write_package_json` (translated to `_IoError(error_id="recipe.filesystem_race")`).
8. Private helpers (pure functions where possible — **AC-Pure-1**):
   - `_read_package_json(path: SandboxedPath) -> tuple[dict[str, Any] | None, _InternalError | None]` — read bytes, size cap, depth cap, parse via `orjson.loads`, reject NUL-byte/bidi name. Pure (the only side effect is the read, which is the imperative-shell boundary).
   - `_edit_dep_version(doc, package, new_version) -> tuple[tuple[dict, str] | None, _InternalError | None]` — preserves key order; walks `_DEP_SECTIONS_PRECEDENCE` in declaration order; returns the modified doc and the section name that was edited; if none matched, returns `_PJsonError(error_id="recipe.package_not_in_dependencies")`. Pure.
   - `_write_package_json(path: SandboxedPath, doc) -> tuple[bytes | None, _InternalError | None]` — `path.open("wb")` (SandboxedPath substitution will deliver `O_NOFOLLOW` once S4-04 GREEN), serialized with `orjson.dumps(doc, option=orjson.OPT_INDENT_2) + b"\n"`; the only catch is `OSError(ELOOP)` → `_IoError(error_id="recipe.filesystem_race")`. Side-effecting (imperative shell).
   - `_run_npm_install(jail, repo, capability) -> tuple[None, _InternalError | None]` — builds the `JailedSubprocessSpec` (cmd, cwd=repo, env=`NpmEnv(npm_config_ignore_scripts="true")`, network=`RegistryAllowlist(hosts=_REGISTRY_ALLOWLIST_HOSTS)`, budgets from `_NPM_INSTALL_*`), awaits, `match`-dispatches on `JailedSubprocessResult` (with `assert_never` final arm). Side-effecting.
   - `_read_lockfile(path) -> tuple[dict[str, Any] | None, _InternalError | None]` — size cap, depth cap, lockfileVersion check (v3 only; v1 fails-fast with distinct error_id). Pure.
   - `_compute_transform_id(diff_bytes: bytes) -> TransformId` — `TransformId(blake3.blake3(diff_bytes).hexdigest())`. Pure.
   - `_build_unified_diff(before_pjson, after_pjson, before_lock, after_lock) -> bytes` — `difflib.unified_diff` over the four byte sequences with the two file-boundary markers; deterministic by construction (pure-byte input). Pure.
9. Define `NpmLockfileTransform(Transform)` with the four required class-level annotations (per `transform.py:64`); `files_changed` is a `tuple[SandboxedPath, ...]` of length 2.
10. Tests (TDD plan below) — write failing first; then `green`; then `refactor` to land all fences and the contract-snapshot re-baseline.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths: `tests/unit/transforms/test_npm_lockfile_engine.py` (unit, fake jail) and `tests/integration/test_npm_lockfile_engine_jail.py` (real bwrap, gated on `pytest.importorskip("subprocess") and shutil.which("bwrap")` on Linux).

```python
# tests/unit/transforms/test_npm_lockfile_engine.py
from pathlib import Path
from typing import Any
import pytest
import orjson
import blake3
from codegenie.transforms.engines.npm_lockfile import (
    NpmLockfileRecipeEngine, NpmLockfileTransform,
)
from codegenie.transforms.recipe_engine import RecipeEngine
from codegenie.transforms.outcomes import (
    ApplicationPlan, Applied, RecipeFailed, RecipeError,
)
from codegenie.transforms.sandbox_jail import (
    JailedSubprocessResult, JailedSubprocessSpec, Completed, TimedOut,
    OomKilled, NetworkDenied, DiskQuotaExceeded,
    NpmEnv, RegistryAllowlist,
)
from codegenie.transforms._forward import SandboxedPath, CapabilityBundle
from codegenie.types.identifiers import (
    PackageId, TransformKind, TransformId, ErrorId, EventId, PluginId, RecipeId,
)


class FakeJail:
    """Single-result fake; records each call for assertions."""
    def __init__(self, result: JailedSubprocessResult) -> None:
        self.result = result
        self.calls: list[JailedSubprocessSpec] = []
    async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult:
        self.calls.append(spec)
        return self.result


@pytest.fixture
def express_repo(tmp_path: Path) -> Path:
    (tmp_path / "package.json").write_bytes(orjson.dumps(
        {"name": "fixture", "version": "1.0.0",
         "dependencies": {"express": "^4.17.1", "lodash": "^4.17.21"}},
        option=orjson.OPT_INDENT_2,
    ) + b"\n")
    (tmp_path / "package-lock.json").write_bytes(orjson.dumps(
        {"name": "fixture", "lockfileVersion": 3, "packages": {}},
        option=orjson.OPT_INDENT_2,
    ) + b"\n")
    return tmp_path


@pytest.fixture
def plan() -> ApplicationPlan:
    return ApplicationPlan.for_npm_semver_bump(
        package=PackageId("express"),
        from_version="^4.17.1",
        to_version="^4.19.2",
        transform_kind=TransformKind("npm-lockfile-semver-bump"),
    )


@pytest.fixture
def capability() -> Any:
    """S4-05 NpmInstallCapability stub for unit tests.

    The capability parameter is read by the engine only for the
    `capability_use_id` audit field on TransformProvenance. The S4-05
    real capability ships with an `event_id: EventId` field; a minimal
    stub here suffices for unit testing.
    """
    from codegenie.plugins.capabilities import NpmInstallCapability  # S4-05
    return NpmInstallCapability(event_id=EventId("evt_test_0001"))


def _writing_jail_factory(after_lockfile: dict[str, Any]) -> FakeJail:
    """FakeJail variant that simulates `npm install` by writing a new
    package-lock.json into spec.cwd; returns Completed on success."""
    class _W(FakeJail):
        async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult:
            self.calls.append(spec)
            cwd = spec.cwd if isinstance(spec.cwd, Path) else Path(str(spec.cwd))
            (cwd / "package-lock.json").write_bytes(
                orjson.dumps(after_lockfile, option=orjson.OPT_INDENT_2) + b"\n"
            )
            return self.result
    return _W(Completed(
        kind="completed", exit_code=0, stdout_bytes=0, stderr_bytes=0,
        wall_time_s=0.01,
    ))


@pytest.mark.asyncio
async def test_happy_path_returns_applied_and_transform_tuple(express_repo, plan, capability):
    jail = _writing_jail_factory({
        "name": "fixture", "lockfileVersion": 3,
        "packages": {"node_modules/express": {"version": "4.19.2"}},
    })
    engine = NpmLockfileRecipeEngine(jail=jail)
    outcome, transform = await engine.apply(
        repo=SandboxedPath(express_repo), plan=plan, capability=capability,
    )
    assert isinstance(outcome, Applied)
    assert outcome.kind == "applied"
    assert isinstance(transform, NpmLockfileTransform)
    # AC-Apply-1 identity: outcome.transform_id == transform.transform_id
    assert outcome.transform_id == transform.transform_id
    # AC-Apply-2 blake3 identity
    assert transform.transform_id == TransformId(blake3.blake3(transform.diff_bytes).hexdigest())
    # AC-Surface-3 files_changed tuple shape
    assert isinstance(transform.files_changed, tuple)
    assert len(transform.files_changed) == 2


@pytest.mark.asyncio
async def test_runtime_checkable_protocol_conformance(plan, capability, express_repo):
    """AC-Surface-2 (a) — runtime isinstance against the Protocol."""
    jail = FakeJail(Completed(kind="completed", exit_code=0, stdout_bytes=0,
                              stderr_bytes=0, wall_time_s=0.01))
    engine = NpmLockfileRecipeEngine(jail=jail)
    assert isinstance(engine, RecipeEngine)


@pytest.mark.asyncio
async def test_npm_cmd_is_exactly_the_four_flag_tuple(express_repo, plan, capability):
    jail = _writing_jail_factory({"name": "x", "lockfileVersion": 3, "packages": {}})
    await NpmLockfileRecipeEngine(jail=jail).apply(
        repo=SandboxedPath(express_repo), plan=plan, capability=capability,
    )
    assert jail.calls[0].cmd == (
        "npm", "install",
        "--package-lock-only", "--ignore-scripts", "--no-audit", "--prefer-offline",
    )


@pytest.mark.asyncio
async def test_typed_env_discriminator_and_ignore_scripts_double_enforce(express_repo, plan, capability):
    """AC-4e — env.kind == 'npm' AND NpmEnv.npm_config_ignore_scripts == 'true'."""
    jail = _writing_jail_factory({"name": "x", "lockfileVersion": 3, "packages": {}})
    await NpmLockfileRecipeEngine(jail=jail).apply(
        SandboxedPath(express_repo), plan, capability,
    )
    env = jail.calls[0].env
    assert env.kind == "npm"
    assert env.npm_config_ignore_scripts == "true"


@pytest.mark.asyncio
async def test_network_policy_is_registry_allowlist_only(express_repo, plan, capability):
    """AC-4c — exact RegistryAllowlist tuple, no DenyAll, no AllowAll."""
    jail = _writing_jail_factory({"name": "x", "lockfileVersion": 3, "packages": {}})
    await NpmLockfileRecipeEngine(jail=jail).apply(
        SandboxedPath(express_repo), plan, capability,
    )
    net = jail.calls[0].network
    assert net.kind == "registry_allowlist"
    assert net.hosts == ("registry.npmjs.org",)


@pytest.mark.asyncio
async def test_budget_envelope_pinned(express_repo, plan, capability):
    """AC-4d — pinned to the module-top Final constants."""
    jail = _writing_jail_factory({"name": "x", "lockfileVersion": 3, "packages": {}})
    await NpmLockfileRecipeEngine(jail=jail).apply(
        SandboxedPath(express_repo), plan, capability,
    )
    spec = jail.calls[0]
    assert spec.time_budget_s == 60.0
    assert spec.memory_mib == 1024
    assert spec.pids_max == 1024


@pytest.mark.asyncio
async def test_package_json_too_large_short_circuits_before_npm(tmp_path, plan, capability):
    """AC-1a — short-circuit BEFORE npm invocation; jail.calls == []."""
    (tmp_path / "package.json").write_bytes(b"{" + b"x" * (1024*1024) + b"}")
    (tmp_path / "package-lock.json").write_bytes(orjson.dumps(
        {"name": "x", "lockfileVersion": 3, "packages": {}},
        option=orjson.OPT_INDENT_2,
    ) + b"\n")
    jail = FakeJail(Completed(kind="completed", exit_code=0, stdout_bytes=0,
                              stderr_bytes=0, wall_time_s=0.01))
    outcome, transform = await NpmLockfileRecipeEngine(jail=jail).apply(
        SandboxedPath(tmp_path), plan, capability,
    )
    assert isinstance(outcome, RecipeFailed)
    assert outcome.error.error_id == ErrorId("recipe.package_json_too_large")
    assert outcome.error.details == {
        "limit_bytes": 1048576, "observed_bytes": 1048577,
    }
    assert transform is None
    assert jail.calls == []  # AC-1a — npm install MUST NOT be invoked


@pytest.mark.asyncio
async def test_adversarial_repo_content_nul_byte_in_name(tmp_path, plan, capability):
    """AC-1c — NUL byte in name rejected by PackageId.parse smart constructor."""
    (tmp_path / "package.json").write_bytes(orjson.dumps(
        {"name": "a\x00b", "version": "1.0.0", "dependencies": {"express": "^4.17.1"}},
        option=orjson.OPT_INDENT_2,
    ) + b"\n")
    (tmp_path / "package-lock.json").write_bytes(orjson.dumps(
        {"name": "x", "lockfileVersion": 3, "packages": {}},
        option=orjson.OPT_INDENT_2,
    ) + b"\n")
    jail = FakeJail(Completed(kind="completed", exit_code=0, stdout_bytes=0,
                              stderr_bytes=0, wall_time_s=0.01))
    outcome, transform = await NpmLockfileRecipeEngine(jail=jail).apply(
        SandboxedPath(tmp_path), plan, capability,
    )
    assert isinstance(outcome, RecipeFailed)
    assert outcome.error.error_id == ErrorId("recipe.adversarial_repo_content")
    assert transform is None
    assert jail.calls == []


@pytest.mark.asyncio
async def test_lockfile_v1_unsupported(express_repo, plan, capability):
    """AC-5c — lockfileVersion: 1 short-circuits with distinct error_id."""
    jail = _writing_jail_factory({"name": "x", "lockfileVersion": 1})
    outcome, transform = await NpmLockfileRecipeEngine(jail=jail).apply(
        SandboxedPath(express_repo), plan, capability,
    )
    assert isinstance(outcome, RecipeFailed)
    assert outcome.error.error_id == ErrorId("recipe.lockfile_v1_unsupported")
    assert outcome.error.details["lockfile_version"] == 1
    assert transform is None


@pytest.mark.asyncio
@pytest.mark.parametrize("variant,expected_error_id,expected_details", [
    (
        TimedOut(kind="timed_out", budget_s=60.0, elapsed_s=61.2),
        "recipe.install_timeout",
        {"budget_s": 60.0, "elapsed_s": 61.2},
    ),
    (
        OomKilled(kind="oom_killed", peak_rss_mib=1100),
        "recipe.install_oom",
        {"peak_rss_mib": 1100},
    ),
    (
        NetworkDenied(kind="network_denied", host="attacker.example.com"),
        "recipe.network_policy_violation",
        {"host": "attacker.example.com"},
    ),
    (
        DiskQuotaExceeded(kind="disk_quota_exceeded", quota_bytes=10_000_000, bytes_written=10_000_001),
        "recipe.disk_quota_exceeded",
        {"quota_bytes": 10_000_000, "bytes_written": 10_000_001},
    ),
])
async def test_jail_failure_variants_map_to_typed_recipe_failed(
    express_repo, plan, capability, variant, expected_error_id, expected_details,
):
    """AC-4g — exhaustive variant mapping with assert_never coverage."""
    outcome, transform = await NpmLockfileRecipeEngine(jail=FakeJail(variant)).apply(
        SandboxedPath(express_repo), plan, capability,
    )
    assert isinstance(outcome, RecipeFailed)
    assert outcome.error.error_id == ErrorId(expected_error_id)
    assert outcome.error.details == expected_details
    assert transform is None


@pytest.mark.asyncio
async def test_npm_install_exit_nonzero(express_repo, plan, capability):
    """AC-4f — Completed(exit_code != 0) → recipe.npm_install_exit_nonzero,
    details carry the byte counts (no stderr_tail — Completed exposes counts only)."""
    jail = FakeJail(Completed(
        kind="completed", exit_code=1, stdout_bytes=0, stderr_bytes=512,
        wall_time_s=0.34,
    ))
    outcome, transform = await NpmLockfileRecipeEngine(jail=jail).apply(
        SandboxedPath(express_repo), plan, capability,
    )
    assert isinstance(outcome, RecipeFailed)
    assert outcome.error.error_id == ErrorId("recipe.npm_install_exit_nonzero")
    assert outcome.error.details == {
        "exit_code": 1, "stderr_bytes": 512, "wall_time_s": 0.34,
    }
    assert transform is None


@pytest.mark.asyncio
async def test_no_op_edit_is_byte_identical_round_trip(express_repo, plan, capability):
    """AC-2a — no-op round-trip byte-identity."""
    noop_plan = plan.model_copy(update={"to_version": "^4.17.1"})
    before = (express_repo / "package.json").read_bytes()
    jail = _writing_jail_factory({"name": "fixture", "lockfileVersion": 3, "packages": {}})
    await NpmLockfileRecipeEngine(jail=jail).apply(
        SandboxedPath(express_repo), noop_plan, capability,
    )
    after = (express_repo / "package.json").read_bytes()
    assert before == after  # key order + indentation preserved bit-for-bit


@pytest.mark.asyncio
@pytest.mark.parametrize("dep,new_version", [
    ("express", "^4.19.2"),
    ("lodash",  "^4.17.22"),
])
async def test_edited_round_trip_preserves_other_keys(
    express_repo, capability, dep, new_version,
):
    """AC-2b — editing one dep changes only that dep's version line."""
    plan = ApplicationPlan.for_npm_semver_bump(
        package=PackageId(dep),
        from_version="^0.0.0", to_version=new_version,
        transform_kind=TransformKind("npm-lockfile-semver-bump"),
    )
    before = (express_repo / "package.json").read_bytes()
    jail = _writing_jail_factory({"name": "fixture", "lockfileVersion": 3, "packages": {}})
    await NpmLockfileRecipeEngine(jail=jail).apply(
        SandboxedPath(express_repo), plan, capability,
    )
    after = (express_repo / "package.json").read_bytes()
    # Diff cardinality bound: 1 hunk-header + 1 minus + 1 plus + 1 context max
    import difflib
    diff_lines = list(difflib.unified_diff(
        before.decode().splitlines(), after.decode().splitlines(), lineterm="",
    ))
    assert len(diff_lines) <= 6  # header + range-line + minus + plus + bounded context


@pytest.mark.asyncio
async def test_intra_run_determinism_5x_diff_bytes_includes_both_files(tmp_path, plan, capability):
    """AC-Det-1 — five fresh-fixture runs produce byte-identical diff_bytes;
    the two-file structure is exercised each iteration."""
    diffs: list[bytes] = []
    source_pjson = orjson.dumps(
        {"name": "fixture", "version": "1.0.0",
         "dependencies": {"express": "^4.17.1", "lodash": "^4.17.21"}},
        option=orjson.OPT_INDENT_2,
    ) + b"\n"
    source_lockfile = orjson.dumps(
        {"name": "fixture", "lockfileVersion": 3, "packages": {}},
        option=orjson.OPT_INDENT_2,
    ) + b"\n"
    for i in range(5):
        repo = tmp_path / f"run-{i}"
        repo.mkdir()
        (repo / "package.json").write_bytes(source_pjson)
        (repo / "package-lock.json").write_bytes(source_lockfile)
        jail = _writing_jail_factory(
            {"name": "fixture", "lockfileVersion": 3,
             "packages": {"node_modules/express": {"version": "4.19.2"}}}
        )
        _outcome, transform = await NpmLockfileRecipeEngine(jail=jail).apply(
            SandboxedPath(repo), plan, capability,
        )
        assert transform is not None
        assert b"--- file: package.json ---" in transform.diff_bytes
        assert b"--- file: package-lock.json ---" in transform.diff_bytes
        diffs.append(transform.diff_bytes)
    assert len({d for d in diffs}) == 1
```

```python
# tests/unit/transforms/test_npm_lockfile_mutation_flags.py
import pytest
from codegenie.transforms.engines import npm_lockfile as eng_mod
# Parametrize over each flag index (2..5 — the four flags; not 'npm', not 'install').
@pytest.mark.asyncio
@pytest.mark.parametrize("drop_index", [2, 3, 4, 5])
async def test_dropping_each_flag_breaks_golden_byte_equal(
    drop_index, express_repo, plan, capability, monkeypatch,
):
    """AC-4b — each of the four flags carries observable weight; dropping
    any one mutates the fake-jail's synthetic write enough to break the
    diff-byte determinism between the dropped-flag run and the full run."""
    full = tuple(eng_mod._NPM_INSTALL_CMD)
    short = tuple(c for i, c in enumerate(full) if i != drop_index)
    monkeypatch.setattr(eng_mod, "_NPM_INSTALL_CMD", short)
    # ... fake jail differentiates by spec.cmd's content (e.g., writes a
    # marker key into the resulting lockfile when --prefer-offline is absent).
    # The assertion: with the flag dropped, the resulting Transform.diff_bytes
    # is NOT equal to the diff_bytes from the full-flag baseline.
```

```python
# tests/unit/transforms/test_npm_lockfile_mypy_negative.py
# AC-4g2 — mypy-strict on a temp module that omits one match arm fails with
# assert_never on the missing JailedSubprocessResult variant.
# Mirrors S4-01 `test_sandbox_jail_mypy_negative.py`.
```

```python
# tests/unit/transforms/test_npm_lockfile_typing.py
# AC-Surface-2 (b) + AC-4e — mypy --strict positive: structural Protocol
# conformance and NpmEnv field narrowing. Single-file mypy invocation.
```

```python
# tests/fence/test_engines_no_raw_os_open.py     — AC-3a
# tests/fence/test_engines_no_module_state.py    — AC-Surface-4
# tests/fence/test_npm_lockfile_pure_helpers.py  — AC-Pure-1
# tests/fence/test_golden_lockfile_regen_guard.py — AC-Gold-2
```

```python
# tests/integration/test_npm_lockfile_engine_jail.py
import shutil, pathlib, pytest
from codegenie.transforms._forward import SandboxedPath

@pytest.mark.skipif(shutil.which("bwrap") is None, reason="requires bwrap")
@pytest.mark.asyncio
async def test_golden_express_lockfile_byte_equal_under_real_jail():
    """AC-Gold-1 — real BwrapAdapter; lockfile-bytes byte-equal to golden."""
    after_golden = pathlib.Path("tests/golden/lockfiles/express-cve-2024-21501.after.json").read_bytes()
    # set up repo from fixtures/repos/express-cve-2024-21501/, build the
    # ApplicationPlan.for_npm_semver_bump(...), construct the real BwrapAdapter,
    # mint the real NpmInstallCapability (S4-05), run engine.apply(...),
    # assert the post-apply package-lock.json bytes == after_golden.
    ...

@pytest.mark.skipif(
    SandboxedPath is pathlib.Path,
    reason="S4-04 substitution not yet shipped; re-enables when transforms/_forward.py re-exports the real SandboxedPath",
)
@pytest.mark.asyncio
async def test_symlink_swap_returns_filesystem_race(tmp_path):
    """AC-3b — TOCTOU symlink-swap race; engine returns recipe.filesystem_race
    and the sentinel file is untouched. Test self-skips until S4-04 GREEN."""
    sentinel = tmp_path / "sentinel"
    sentinel.write_bytes(b"untouched")
    sentinel_mtime_before = sentinel.stat().st_mtime
    # ... race: after _read_package_json succeeds, replace package.json with a
    # symlink → sentinel. The engine's write-back via SandboxedPath.open should
    # raise OSError(ELOOP), be caught, and emit recipe.filesystem_race.
    # ASSERT sentinel.stat().st_mtime == sentinel_mtime_before
```

Run; confirm `ImportError` / `ModuleNotFoundError`; commit; implement.

### Green — make it pass

- **`ApplicationPlan` widening first** (AC-Plan-1, AC-Plan-2). Land in `outcomes.py` plus a re-baseline of `tests/golden/contracts/recipe_outcome.schema.json`. This is the load-bearing prerequisite — without it the engine's call site is uncompilable.
- **`orjson` dep + import-linter cross-check** (AC-Tool-4). Edit `pyproject.toml` `[project].dependencies` and run `make lint-imports` to confirm no new violation.
- Implement each pure helper minimally. The depth-walker `_max_depth(obj) -> int` is a small recursive walker over `dict`/`list` (orjson decodes JSON arrays as lists). With caps of 16 / 24 the Python stack is safe; iterative-stack reformulation is a refactor-pass concern only if profiling shows it (see Refactor).
- `_edit_dep_version` mutates the parsed dict in-place after a `copy.deepcopy` (key order intrinsic to dict; `orjson.dumps` honors it). Walks `_DEP_SECTIONS_PRECEDENCE` in declaration order and edits the first match; if none matched, returns `_PJsonError(error_id=ErrorId("recipe.package_not_in_dependencies"), details={"package": str(package), "sections_searched": list(_DEP_SECTIONS_PRECEDENCE)})` (the canonical internal-error sum from §Implementation outline #5 — **not** a `Result.Err(...)` value; that abstraction was removed in validation per Design-Patterns F1).
- For the unified diff: concatenate the four byte sequences with `b"\n--- file: package.json ---\n"` / `b"\n--- file: package-lock.json ---\n"` markers. The marker bytes are a `Final[bytes]` module-top constant for testability. Determinism: the diff is pure byte-vs-byte over file contents; no timestamps, no inode info, no random bytes enter the payload.
- The integration test against the real bwrap jail requires `npm` on PATH inside the jail; the bwrap adapter from S4-02 bind-mounts `/` ro and the project's `node_modules` cache rw under `.codegenie/cache/npm`. Document the fixture-prep requirements in the test docstring.
- **Failure-path lifting helper** — a single private `_to_failed(err: _InternalError) -> tuple[RecipeFailed, None]` performs the canonical lift from the internal sum to the public `RecipeFailed`. The `apply` body becomes a flat sequence of `if err is not None: return _to_failed(err)` lines — easy to mutation-test and to skim for missing arms.

### Refactor — clean up

- Confirm every numeric constant has the `Final[int]` / `Final[float]` annotation and an inline comment with the human unit (`1 MiB`, `60 s`). The fence test `tests/fence/test_no_raw_str_for_domain_ids.py` from S1-05 catches drift.
- Confirm `apply` has **no** `try: ... except: ...` blocks that swallow exceptions — every failure path threads through the `_InternalError` sum. The single permitted catch is the precisely-scoped `OSError` (filtered on `errno == errno.ELOOP`) inside `_write_package_json`, translated to `_IoError(error_id=ErrorId("recipe.filesystem_race"))`. No bare `except`, no `except Exception`.
- Verify `--ignore-scripts` is **at index 3 of `_NPM_INSTALL_CMD`** with an inline comment citing ADR-0007. The mutation test (AC-4b) verifies dropping it causes CI failure.
- The `_REGISTRY_ALLOWLIST_HOSTS` constant is a single-host tuple in Phase 3; Phase 7's distroless plugin may widen (e.g., add `cgr.dev`). Document at the constant: "Phase 3 single-host; Phase 7 may widen additively via a plugin-local override constant in `plugins/<plugin-id>/engine.py` — never edit this constant." (Open/Closed boundary marker.)
- Verify the `_NpmLockfileErrorId` Literal has 13 members and matches `_ERROR_IDS` byte-for-byte (AC-Tax-1). Adding a 14th error mode = update Literal + add AC + re-run.
- Confirm `NpmLockfileTransform.files_changed` is a `tuple[SandboxedPath, ...]` (not `list`) — mypy will flag the mismatch against the ABC.
- Re-read `../phase-arch-design.md §Performance envelope` for C12 — the engine should add < 50 ms of pure-Python overhead per `apply` call (the budget is dominated by `npm install` itself). Add a `@pytest.mark.bench` micro-bench in `tests/bench/test_engine_overhead.py` measuring the pure-Python portion (parse + edit + serialize + diff + blake3). If it blows past 50 ms, the regression is typically in `_max_depth`; rewrite to an iterative-stack walker.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/engines/__init__.py` | New package (docstring only; no public re-exports) |
| `src/codegenie/transforms/engines/npm_lockfile.py` | New — `NpmLockfileRecipeEngine` + `NpmLockfileTransform` + private helpers + `_NpmLockfileErrorId` Literal + `_InternalError` sum |
| `src/codegenie/transforms/outcomes.py` | **Modified** — `ApplicationPlan` widened additively (AC-Plan-1, AC-Plan-2) with `package`, `from_version`, `to_version`, `transform_kind` optional fields + `for_npm_semver_bump(...)` classmethod |
| `tests/unit/transforms/test_npm_lockfile_engine.py` | New — caps, key-order, flags, jail-variant mapping, intra-run determinism, adversarial input |
| `tests/unit/transforms/test_npm_lockfile_mutation_flags.py` | New — per-flag mutation (AC-4b) |
| `tests/unit/transforms/test_npm_lockfile_mypy_negative.py` | New — mypy-narrowing exhaustiveness (AC-4g2) |
| `tests/unit/transforms/test_npm_lockfile_typing.py` | New — Protocol structural conformance + `NpmEnv` narrowing (AC-Surface-2, AC-4e) |
| `tests/integration/test_npm_lockfile_engine_jail.py` | New — real bwrap golden round-trip + conditional symlink-swap (gated on S4-04) |
| `tests/fence/test_engines_no_raw_os_open.py` | New (AC-3a) — AST fence: only `SandboxedPath.open` under `transforms/engines/` |
| `tests/fence/test_engines_no_module_state.py` | New (AC-Surface-4) — AST fence: no module-level mutable state |
| `tests/fence/test_npm_lockfile_pure_helpers.py` | New (AC-Pure-1) — AST fence: pure helpers carry no `await` / `os` / `subprocess` |
| `tests/fence/test_golden_lockfile_regen_guard.py` | New (AC-Gold-2) — fence: golden modifications require `.regen-justification.md` sidecar |
| `tests/bench/test_engine_overhead.py` | New — `@pytest.mark.bench` micro-bench on pure-Python overhead |
| `tests/golden/lockfiles/express-cve-2024-21501.before.json` | New — fixture (also referenced by S8-02) |
| `tests/golden/lockfiles/express-cve-2024-21501.after.json` | New — golden post-apply lockfile |
| `tests/golden/lockfiles/express-cve-2024-21501.regen-justification.md` | New — initial sidecar (`Reason: initial golden`) |
| `tests/golden/contracts/recipe_outcome.schema.json` | **Modified** — re-baselined for `ApplicationPlan` additive widen (AC-Plan-3) |
| `tests/fixtures/repos/express-cve-2024-21501/` | Extended (Step 6 created stub) — `package.json` + initial lockfile |
| `pyproject.toml` | Add `orjson` (>=3.9) under `[project].dependencies` (AC-Tool-4); `blake3` already present (Phase 2 cache) |

## Out of scope

- **`NpmEnv` / `RegistryAllowlist` / `NetworkPolicy` definitions** — S4-01.
- **`SandboxedPath` implementation** — S4-04.
- **The four recipes that produce `RecipePlan`s** — S7-02.
- **Stage-6 `cve_delta` signal** that compares pre/post lockfile against `VulnIndex` — S6-04 (this story does NOT inspect for newly-introduced CVEs; that's downstream).
- **`overrides` block editing** (transitive-only vuln, §Edge case E5) — S7-02's `NpmTransitiveOverridesRecipe` produces a `RecipePlan` with an `overrides` annotation; *this engine* still edits `package.json` and re-runs npm install; the annotation is carried in `TransformProvenance` but the lockfile edit path is the same.
- **`OpenRewriteRecipeEngine` scaffold** — S5-03.
- **`LockfilePolicy.evaluate` of the new lockfile** — S5-04 (the engine produces the lockfile; the policy evaluates it later as a separate Stage-6 signal).
- **Property-test 100 Hypothesis runs** — S8-03 (this story does intra-run 5× determinism; full property test is the cardinal goal in Step 8).

## Notes for the implementer

- **Why the four npm flags are non-negotiable**: `--ignore-scripts` is the postinstall canary defense (§Edge case E10 — the canary test in S8-04 confirms a fixture's `postinstall` does NOT execute). `--no-audit` removes the synchronous npm-audit POST that violates determinism + leaks repo information. `--prefer-offline` makes warm-cache runs deterministic and avoids needless registry round-trips. `--package-lock-only` is the speed lever (no `node_modules` populated). Drop any one and a real adversarial test from S8-04 will fail.
- **orjson over stdlib `json`**: production parser. Round-trip: `orjson.loads(b)` → mutate → `orjson.dumps(d, option=orjson.OPT_INDENT_2)`. `OPT_INDENT_2` matches npm's own default formatting (2-space). Do NOT use `OPT_SORT_KEYS` — that would reorder existing `package.json` keys and break the byte-identical round-trip test.
- **Trailing newline**: append `b"\n"` after `dumps` — POSIX convention, what `npm` itself writes; without it the golden byte-equal test fails by one byte.
- **`SandboxedPath.open` and `O_NOFOLLOW`** (substitution-aware): the API is `path.open("rb")` / `path.open("wb")`. S4-04 (HARDENED) is the eventual owner that will set `O_NOFOLLOW` on every open. Until S4-04 is GREEN, `SandboxedPath` is the `pathlib.Path` typealias in `transforms/_forward.py` (the shipped Phase-3-Step-1 shim — see `_forward.py`'s docstring). Do **not** bypass this with `os.open(str(path), ...)` — the AC-3a fence rejects raw `os.open` under `transforms/engines/`. AC-3b (the TOCTOU integration test) is `skipif`-gated on `SandboxedPath is pathlib.Path` so it self-enables once S4-04 substitutes the typealias at the same import path.
- **Internal-error sum, not `Result[T, E]`** (Design-Patterns F1; validation note #7): the original draft proposed a generic `Result[T, E]` abstraction. There is **no `codegenie.util.result` module** in the codebase (S1-03 shipped the *outcome* discriminated unions in `outcomes.py`, not a generic Result kernel). The validation rewrote this to a **private discriminated union of small Pydantic models** keyed by `kind: Literal["pjson"|"io"|"npm"|"lockfile"]` (see Implementation outline #5). The shape mirrors every umbrella in `outcomes.py` (the codebase convention — Rule 11), and the `apply` body's `match`-dispatch on it makes mypy exhaust-checking trivial. Do NOT invent a parallel `Result` shape; if Phase 4 needs one, that is Phase 4's ADR amendment.
- **The `capability: NpmInstallCapability` parameter is THREADED, not just received** — the capability's `event_id` flows into `TransformProvenance.capability_use_id` (per `phase-arch-design.md §C4 L800-806` and `transform.py:142`). AC-Apply-3 + AC-Pure-1's "capability parameter is observed somewhere in the function body" fence pins this. This is the **audit anchor** ADR-0011 names; without it the Phase-9 replay-consistency property weakens.
- **Open/Closed boundary at `_NPM_INSTALL_CMD`**: the constant is a `Final[tuple[str, ...]]` — adding Phase 7's distroless flags or yarn-berry's flags means *adding a new constant in a sibling engine module*, **never editing this one**. The CLAUDE.md "Extension by addition" commitment lives at the engine-module boundary, not at the function boundary. Tag the constant with a doc-comment marking it as the OCP seam.
- **`_NpmLockfileErrorId` as a closed Literal taxonomy** (Design-Patterns F2): the 13-entry Literal at module top is the contract surface for failure modes. Mirrors `NotApplicableReason` in `outcomes.py`, `DegradationReason`/`UnavailabilityReason` discipline, and the S1-05 `_WARNING_IDS` precedent. Adding a 14th error mode = (a) add to the Literal, (b) add an AC for it, (c) add a test for it. The fence test on `_ERROR_IDS == frozenset(get_args(_NpmLockfileErrorId))` makes drift a CI failure.
- **`ApplicationPlan` additive widening discipline** (Validation note #3): the four optional fields added to `ApplicationPlan` carry `None` defaults so every existing call site stays callable. Phase 4's `LLMFallbackEngine` (`for_llm_fallback(...)`) will widen *additively* again — never edit existing fields. The `for_npm_semver_bump(...)` classmethod is the smart constructor (codebase pattern from S1-03 / S1-04 — see `transform.py`'s `TransformProvenance`).
- **Golden file regeneration is a deliberate, human-gated operation**: when `package-lock.json` changes (e.g., a transitive sub-dep version bumps), the golden is regenerated and the `.regen-justification.md` sidecar is updated in the same PR (AC-Gold-2). NEVER auto-regenerate. This is the cardinal goal G4 contract — golden drift IS a regression unless deliberately reviewed.
- **No LLM here**: this is the deterministic-recipe path. Phase 4 is the LLM-fallback path. Any `import anthropic` / `import openai` / etc. under `transforms/engines/` is caught by `tests/unit/test_pyproject_fence.py` + `make lint-imports`. This story should not import or reference any LLM SDK.
- **Bench expectation**: pure-Python portion (parse + edit + serialize + diff + blake3) should be < 50 ms on the express fixture. If you blow past that, the regression is likely in `_max_depth` (recursive Python over a deep dict — rewrite to an iterative stack walker if it shows up in profiling).
- **Read order before opening the editor**: `outcomes.py` (the discriminated-union conventions you will mirror) → `transform.py` (the ABC + `TransformProvenance` you subclass + populate) → `sandbox_jail.py` (the `JailedSubprocessSpec` shape, the `JailedEnv` sum, the `JailedSubprocessResult` variants you exhaust) → `S5-01-recipe-registry.md` (the Protocol surface you implement) → this story's TDD plan. Doing the reads in this order surfaces all the contract drift you would have otherwise hit at run-time.
