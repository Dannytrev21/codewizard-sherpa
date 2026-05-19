# Validation report — S5-03 — `OpenRewriteRecipeEngine` scaffold (Protocol-conformant, Phase-7 preview)

**Validated:** 2026-05-19
**Validator:** phase-story-validator skill (autonomous run via story-validation-corrector scheduled task)
**Verdict:** **HARDENED**
**Story file:** `docs/phases/03-vuln-deterministic-recipe/stories/S5-03-openrewrite-engine-scaffold.md`

---

## Context brief

S5-03 ships the **second** day-1 `RecipeEngine` per ADR-0009 Option C — a scaffolded JVM-driven implementation that pays the "two genuine implementations from day one" rent. The scaffold:

- Implements the S5-01 `RecipeEngine` Protocol structurally (`async def apply(self, repo, plan, capability) -> tuple[RecipeOutcome, Transform | None]`).
- Builds a `JailedSubprocessSpec` invoking `java -jar <openrewrite-cli> run --recipe <yml> --in-place` under `SubprocessJail` with `DenyAll` network policy + `JvmEnv` typed env.
- Ships one Phase-7-tagged fixture (`tests/fixtures/openrewrite/dockerfile-base-image-swap/` — `node:20-alpine → cgr.dev/chainguard/node:latest`).
- Is **never invoked by any Phase-3 npm workflow**.
- Is exercised by `@pytest.mark.phase_7_preview` only — `java` is NOT in `ALLOWED_BINARIES` at Phase 3.

**Load-bearing arch context the validator pulled in:**

- `phase-arch-design.md §C12` (L714–L717) — scaffold description; the two paragraphs the story implements verbatim.
- `phase-arch-design.md §Design patterns applied row 2` — Strategy on `RecipeEngine` with two genuine implementations day-1.
- `phase-arch-design.md §Anti-patterns flagged and rejected — Premature pluggability` — 2 engines × 4 recipes earns the pluggability.
- `phase-arch-design.md §Open implementation questions` — alpine → chainguard fixture shape; this story picks it.
- `phase-arch-design.md §Phase 7 readiness P3-004` — `OpenRewriteRecipeEngine scaffolded with Phase-7 fixture`.
- ADR-0009 — RecipeEngine Protocol with two day-1 implementations; `java` NOT in Phase-3 ALLOWED_BINARIES; `tests/integration/test_recipe_engine_protocol.py` is the load-bearing conformance gate.
- ADR-0012 — `ALLOWED_BINARIES` for Phase 3: `npm, bwrap, sandbox-exec, jq` only.
- ADR-0006 — Hexagonal `SubprocessJail` Port; bwrap on Linux; sandbox-exec on macOS; `JvmEnv` is an additive widening of the `JailedEnv` discriminated sum.
- ADR-0010 — Sum-type discipline; typed env (no raw `dict`); newtype for every domain identifier.
- ADR-0001 — Phase-5 contract snapshot freeze; `RecipeEngine` is one of the six named symbols.
- Phase-1 ADR-0007 — `ErrorId` dotted-snake `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`.

**As-built state the original draft didn't address:**

The validator pulled the actual on-disk Pydantic shapes from `outcomes.py` (S1-03 GREEN) and `transform.py` (S1-04 GREEN) plus the recently-hardened S5-02 (`NpmLockfileRecipeEngine`) — which had the *same shape of drift* against the as-built outcome unions and `JailedSubprocessResult` variants. The original S5-03 draft replicated S5-02's pre-hardening drift verbatim across multiple BLOCK-grade sites.

---

## Stage 2 — Four critic reports

The four critics ran in a single combined synthesis. Findings tagged BLOCK / HARDEN / NIT.

### A. Coverage critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| A1 | BLOCK | Missing variant ACs in `JailedSubprocessResult` mapping (`TimedOut`, `OomKilled`, `DiskQuotaExceeded`). Original draft covered `Completed(0)` / `Completed(non-zero)` / `NetworkDenied` only. | Added AC-Map-2..6 + AC-Map-7 (`assert_never` exhaustiveness). Closed `_OpenRewriteErrorId` Literal enumerates each mapping target. |
| A2 | BLOCK | No determinism / byte-identical `diff_bytes` AC. `transform_id` (= BLAKE3 of `diff_bytes`) can drift across runs from `unified_diff` timestamps or wall-clock. | Added AC-Det-1 (10-run vanilla loop with frozen clock) + AC-Det-2 (AST-walk asserting `fromfiledate`/`tofiledate` are NOT passed to `difflib.unified_diff`). |
| A3 | BLOCK | No 2-tuple return-contract AC; story prescribed `apply(...) -> RecipeOutcome`. S5-02 HARDENED pins `(RecipeOutcome, Transform \| None)`. | Added AC-Contract-1/2; rewrote Goal text + Outline §4 + every TDD test. |
| A4 | HARDEN | `capability: NpmInstallCapability` mismatch for non-npm engine; story didn't flag the Phase-7 amendment trigger. | Added AC-CI-3 (`# TODO(Phase-7): widen capability union` marker + fence test). Added Out-of-scope item + Notes §3. |
| A5 | HARDEN | `JvmEnv` discriminated-sum widening unspecified. | Added AC-Env-1/2/3. Outline §1 makes the additive widening of `JailedEnv` explicit; ADR-0006 amendment block recorded. |
| A6 | HARDEN | No AST-walk fence on raw file I/O for the new module. | Added AC-Pure-2 reusing S5-02's `tests/fence/test_engines_no_raw_os_open.py`. |
| A7 | HARDEN | No pure-helper fence — Outline collapsed all logic into `apply()`. | Added AC-Pure-1 + Outline §§5-6 separating `_build_openrewrite_spec` and `_map_jail_result`. |
| A8 | HARDEN | `addopts -m` extension unpinned. `-m "not bench"` alone collects `phase_7_preview` tests under `make test`. | AC-Phase7-2 now pins `-m "not bench and not phase_7_preview"`. |
| A9 | NIT | Coverage-floor exclusion mechanism unspecified (per-file threshold vs. pragma). | AC-Tool-3 pins `# pragma: no cover  # Phase-7-only` markers (Rule 7 — pick one). |

### B. Test-Quality critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| B1 | BLOCK | `Completed(0, b"", b"")` is the wrong shape. As-built `Completed(kind, exit_code: int, stdout_bytes: int, stderr_bytes: int, wall_time_s: float)`. Test would fail at fixture construction. | Rewrote every fixture as `Completed(kind="completed", exit_code=..., stdout_bytes=..., stderr_bytes=..., wall_time_s=...)`. |
| B2 | BLOCK | `out.kind == "failed" and out.reason == "openrewrite_nonzero_exit"` — `RecipeFailed` has no `reason` field; carries `error: RecipeError(error_id, message, details)`. Reason strings also fail Phase-1 ADR-0007 `ErrorId` format (need the dot). | Rewrote all assertions to `outcome.error.error_id == ErrorId("recipe.<…>")` against the closed `_OpenRewriteErrorId` Literal. |
| B3 | BLOCK | Test imports `RecipePlan` from `codegenie.transforms.recipe_engine` — not a thing as-built. Protocol param is `plan: ApplicationPlan`. | Imports rewritten to `ApplicationPlan`. `dockerfile_plan` fixture defined explicitly. |
| B4 | HARDEN | Tautological `isinstance(engine, RecipeEngine)` — `@runtime_checkable` matches on method names only. | Strengthened AC-Surface-2 to also pin `inspect.signature(...).parameters.keys() == ("self", "repo", "plan", "capability")` + cross-engine return-annotation parity (AC-Surface-2(c)). |
| B5 | HARDEN | Missing property-based / repeated-run determinism test. | Added vanilla 10-run loop test (AC-Det-1) — Hypothesis explicitly out-of-scope for a fixed fixture. |
| B6 | HARDEN | `cmd[0] == "java"` was a thin stringly-typed check; allowlist enforcement ambiguity. | AC-Spec-1 pins the **exact tuple** (`("java", "-jar", cli_jar_path, "run", "--recipe", str(recipe_yml), "--in-place")`); FakeJail bypasses allowlist; real-bwrap test is the phase-7 path. |
| B7 | HARDEN | No test for `files_changed` being a tuple (not list). | Added explicit assertion to happy-path test + smart-constructor returns tuple. |
| B8 | NIT | Conformance test third case `assert ReExportedProtocol is RecipeEngine` was opaque. | Dropped that case in the amendment; AC-Surface-2(c) takes its place with the return-annotation parity test. |

### C. Consistency critic — contract-drift catalog

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| C1 | BLOCK | `RecipeOutcome.Applied(...)` / `RecipeOutcome.Failed(...)` / `RecipeOutcome.NotApplicable(...)` are pseudo-OO; `RecipeOutcome` is a `TypeAlias`. | Rewrote all sites to use `Applied(kind="applied", transform_id=…, plugin_id=…, recipe_id=…)`, `RecipeFailed(kind="failed", error=RecipeError(...))`. |
| C2 | BLOCK | `RecipeFailed(reason=...)` field doesn't exist. | Rewrote to `RecipeFailed(kind="failed", error=RecipeError(error_id=ErrorId("recipe.<…>"), message=…, details={…}))`. |
| C3 | BLOCK | `Completed(0, b"", b"")` shape. | See B1. |
| C4 | BLOCK | `files_changed = [repo / "Dockerfile"]` — list, not tuple. | Outline §6 corrected to `(repo / "Dockerfile",)`; AC-Surface-3 pins `tuple`. |
| C5 | BLOCK | Reason strings (`"openrewrite_nonzero_exit"`, `"network_policy_violation"`) violate `ErrorId` format. | Rewrote with `ErrorId("recipe.openrewrite_nonzero_exit")` etc., enumerated module-top. |
| C6 | BLOCK | Return signature `-> RecipeOutcome` drifts from S5-02 2-tuple. | AC-Contract-1/2 + Outline §4 corrected. |
| C7 | BLOCK | `capability: NpmInstallCapability` mismatch with non-npm engine. | Out-of-scope item + AC-CI-3 marker + Notes §3. Phase-7 amendment trigger pinned. |
| C8 | HARDEN | `addopts -m "not bench"` vs phase-7 exclusion. | AC-Phase7-2. |
| C9 | HARDEN | Conformance test recreation vs amendment — S5-01 already creates `tests/integration/test_recipe_engine_protocol.py`. | Files-to-touch + AC-Conf-1 + TDD plan all updated to "AMEND additively". |
| C10 | HARDEN | `JvmEnv` location ambiguous ("under codegenie.transforms.sandbox_jail"). | Outline §1 pins exact import path + `JailedEnv` widening; ADR-0006 amendment block. |
| C11 | NIT | `_max_heap_mib` underscore prefix on Pydantic field is wrong. | Corrected to `max_heap_mib`. |
| C12 | NIT | `# noqa: D401` reasoning was wrong. | Dropped. |

### D. Design-Patterns critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| D1 | BLOCK | `JvmEnv` additive widening of `JailedEnv` sum unspecified. | AC-Env-1/2/3 + Outline §1 pin `kind="jvm"` discriminator + exhaustiveness test. |
| D2 | BLOCK | Error-id taxonomy is not a closed Literal. | Added `_OpenRewriteErrorId: TypeAlias = Literal[...]` (5 entries) at module top + `_ERROR_IDS: Final[frozenset[ErrorId]]` + AC-Tax-1. |
| D3 | BLOCK | No `assert_never` exhaustiveness on `JailedSubprocessResult`. | AC-Map-7 + mypy-strict negative-fence file `test_openrewrite_mypy_negative.py`. |
| D4 | BLOCK | 2-tuple return-contract consistency with S5-02 missing. | AC-Surface-2(c): `inspect.signature(OpenRewriteRecipeEngine.apply).return_annotation == NpmLockfileRecipeEngine.apply.return_annotation`. |
| D5 | HARDEN | Functional core / imperative shell separation missing. | Split into `_build_openrewrite_spec` + `_map_jail_result` pure helpers; `apply()` is exactly 3 statements; AST-walk fence in AC-Pure-1. |
| D6 | HARDEN | `DockerfileBaseImageTransform` smart constructor missing. | AC-Smart-1/2: `DockerfileBaseImageTransform.create(...)` validates non-empty `diff_bytes` + `files_changed`, computes `transform_id`. |
| D7 | HARDEN | Conformance test AMENDED, not recreated. | See C9. |
| D8 | HARDEN | `RecipeEngine` registry seam missed. | Surfaced as Notes §5 — explicit deferred decision; trigger is Phase 7's third engine. Out-of-scope item added. |
| D9 | HARDEN | Anaemic `ApplicationPlan` + Phase 7 widening trail. | Notes §" Capability mismatch" + Out-of-scope; story reads only `plan.summary`. |
| D10 | HARDEN | `NetworkPolicy` as discriminated sum, not predicate. | AC-Spec-3 asserts `spec.network.kind == "deny_all"`; AST-walk fence rejects `RegistryAllowlist`/`AllowAll` in this module. |
| D11 | NIT | `_OPENREWRITE_CLI_JAR` magic string. | Acceptable scaffold-grade; Notes §8 + §14 surface the Phase-7 newtype path. |
| D12 | NIT | Fence test file vs S1-05 suite. | Resolved: append a case to S1-05's existing `test_allowed_binaries_invariants.py` (Rule 7 — one location). |
| D13 | NIT | `isinstance` against Protocol confusion. | Resolved by AC-Surface-2 strengthening (B4). |

---

## Stage 3 — Research

**Skipped.** No critic finding was tagged `NEEDS RESEARCH`. Every issue was resolvable from the as-built shapes (`outcomes.py`, `transform.py`, S5-02 hardening) and the codebase conventions (closed Literal error-ids, `assert_never` mypy-negative fences, AST-walk pure-helper fences) already established by S1-05 / S5-02. No external pattern library was needed.

---

## Stage 4 — Synthesizer + Editor

Conflict-resolution priority `Consistency > Coverage > Test-Quality > Design-Patterns` was applied:

- Consistency C7 (capability mismatch) **beats** Design-Patterns "widen the Protocol now" → keep S5-01's Protocol intact; defer to Phase 7 via marker.
- Design-Patterns D8 (engine registry) **subordinated** to Rule 2 (simplicity first) → defer until Phase 7's third engine is the trigger; record decision in Notes §5.
- Coverage A8 + Consistency C8 (addopts extension) **merged** into a single AC-Phase7-2.
- All BLOCK-grade contract drift edits land in the story body (Goal, ACs, Outline, TDD plan, Files to touch).

**Edits applied in place** to `docs/phases/03-vuln-deterministic-recipe/stories/S5-03-openrewrite-engine-scaffold.md`:

1. **Status:** `Ready` → `HARDENED`.
2. **Depends on / ADRs honored** expanded to load-bearing predecessors (S1-03, S1-04, S4-01, S4-04) and Phase-1 ADR-0007.
3. **Validation notes (2026-05-19, phase-story-validator)** block appended under the header summarising 17 block-grade corrections + 11 harden-grade corrections.
4. **Goal** rewritten to include the 2-tuple return contract and the conformance-test amendment.
5. **Acceptance criteria** restructured into Surface / Error-id taxonomy / Pure-helper fence / `apply` return contract / Spec construction / `JvmEnv` widening / Result mapping / Smart constructor / Determinism / Phase-3 CI / Phase-7-preview / Conformance / Fixture / Tooling — total of 31 ACs (was 14).
6. **Implementation outline** rewritten into 13 steps: `JvmEnv` widening → constants → `__init__` → `apply` body (3 statements) → pure helpers → `_map_jail_result` `match` exhaustiveness → smart constructor → fixture-diff helper → conformance amendment → phase-7-preview test → fence files → re-exports → `pyproject.toml` marker + addopts.
7. **TDD plan** rewritten with as-built constructors (`Completed(kind=..., exit_code=..., stdout_bytes=..., stderr_bytes=..., wall_time_s=...)`, `Applied(kind="applied", transform_id=..., ...)`, `RecipeFailed(...).error.error_id == ErrorId("recipe.<…>")`); parametrized variant-mapping test; 10-run determinism test; smart-constructor invariant tests; mypy-negative fence; conformance-test amendment.
8. **Files to touch** expanded from 12 → 20 entries; row for conformance test changed from "New" to "Amend"; new `sandbox_jail.py` row for `JvmEnv` widening; ADR-0006 amendment row.
9. **Out of scope** expanded with: capability widening (Phase-7 amendment); engine registry seam (deferred decision); `ApplicationPlan` Dockerfile widening (Phase 7); Hypothesis (YAGNI for fixed fixture); `NetworkPolicy.DenyAll` introduction (S4-01).
10. **Notes for the implementer** rewritten into 14 sections including: structural value vs functional; mirror S5-02; capability mismatch (Phase-7 amendment trigger); `JvmEnv` rationale; engine registry deferred decision (with extract trigger); marker lifecycle; network policy; CLI jar provisioning; `DockerfileBaseImageTransform` precedent; coverage carve-out via pragma; no JVM code; determinism non-negotiable; ADR amendments triggered; YAGNI applications.

---

## Final verdict

**HARDENED.** Story carries 17 BLOCK-grade and 11 HARDEN-grade corrections from the original draft. All edits land in place; no `RESCUE` conditions found — the story's goal, scope, and arch-trace are sound. Ready for `phase-story-executor`.

The executor should pay particular attention to:

- **Outline §1 first** — `JvmEnv` additive widening of `JailedEnv` must land before the engine; tests that reference `JvmEnv` will `ImportError` until it ships.
- **2-tuple return contract** — every `apply` callsite returns `(RecipeOutcome, Transform | None)`; the orchestrator (S6-04) keys the Transform by `Applied.transform_id`.
- **Phase-3 CI never invokes JVM** — every unit test uses `FakeJail`; only `@pytest.mark.phase_7_preview` calls real `java`.
- **Story-level invariant** — `tests/fence/test_openrewrite_not_invoked_phase3.py` grep-asserts no Phase-3 npm workflow imports from `codegenie.transforms.engines.openrewrite`.
- **ADR-0006 amendment** lands in the same PR as the code; ADR-0001 / ADR-0012 do NOT amend (Phase 7 amends those).

---

## Audit anchors

- Story file: [`stories/S5-03-openrewrite-engine-scaffold.md`](../S5-03-openrewrite-engine-scaffold.md)
- Sibling validation: [`stories/_validation/S5-02-npm-lockfile-recipe-engine.md`](S5-02-npm-lockfile-recipe-engine.md) — same shape of drift; S5-03's hardening mirrors S5-02's literally.
- ADR-0009: [`ADRs/0009-recipe-engine-protocol-with-two-implementations-day-1.md`](../../ADRs/0009-recipe-engine-protocol-with-two-implementations-day-1.md)
- As-built `outcomes.py`: [`src/codegenie/transforms/outcomes.py`](../../../../../src/codegenie/transforms/outcomes.py)
- As-built `transform.py`: [`src/codegenie/transforms/transform.py`](../../../../../src/codegenie/transforms/transform.py)
