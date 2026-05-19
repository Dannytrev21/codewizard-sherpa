# Validation report — S5-02 — `NpmLockfileRecipeEngine` (production day-1 implementation)

**Validated:** 2026-05-19
**Validator:** phase-story-validator skill (autonomous run via story-validation-corrector scheduled task)
**Verdict:** **HARDENED**
**Story file:** `docs/phases/03-vuln-deterministic-recipe/stories/S5-02-npm-lockfile-recipe-engine.md`

---

## Context brief

S5-02 implements the **production day-1 `RecipeEngine`** for Phase 3 — the deterministic-recipe path every npm vulnerability-remediation workflow routes through. It consumes:

- The `RecipeEngine` Protocol from S5-01 (HARDENED; canonical home `src/codegenie/transforms/recipe_engine.py` per S5-01 AC-2; signature `async def apply(self, repo: SandboxedPath, plan: ApplicationPlan, capability: NpmInstallCapability) -> RecipeOutcome`).
- The `Transform` ABC from S1-04 (GREEN; `src/codegenie/transforms/transform.py:64` — class-level annotations only; `files_changed: tuple[SandboxedPath, ...]`).
- The five discriminated-union sum types from S1-03 (GREEN; `src/codegenie/transforms/outcomes.py`).
- The `SubprocessJail` Port + `JailedSubprocessSpec` + `JailedSubprocessResult` variants from S4-01 (HARDENED).
- `SandboxedPath` from S4-04 (HARDENED; currently `TypeAlias = pathlib.Path` in `transforms/_forward.py`).
- `NpmInstallCapability` from S4-05 (HARDENED).

**Load-bearing arch context the validator pulled in:**

- `phase-arch-design.md §C12` (L714–L717) — the six-step pipeline this story implements verbatim.
- `phase-arch-design.md §Data model` (L793–L806) — `Transform` ABC, `NpmLockfileTransform(Transform)`, `TransformProvenance` shape (7 fields including `capability_use_id: EventId`).
- `phase-arch-design.md §Edge cases E1, E10, E11, E12, E14, E20` — lockfile v1, postinstall canary, `cve_delta`, symlink TOCTOU, lockfile depth bomb, adversarial repo content (NUL bytes / bidi).
- `phase-arch-design.md §Defaults` (L906) — `npm install --package-lock-only` time budget 60 s; memory 1024 MiB; pids_max 1024.
- ADR-0009 — RecipeEngine Protocol with two day-1 implementations; canonical `apply(repo, plan, capability)` signature.
- ADR-0007 — `npm install` MUST run inside `SubprocessJail`; `--ignore-scripts` enforcement at CLI AND env (load-bearing).
- ADR-0006 — Hexagonal `SubprocessJail` Port; bwrap on Linux + sandbox-exec on macOS Adapters.
- ADR-0010 — Domain modeling discipline; sum-type discriminated unions; newtype every domain identifier.
- ADR-0011 — Honest framing: `Capability`, `SandboxedPath` always-`O_NOFOLLOW`, `PLUGINS.lock`.
- Phase-1 ADR-0007 — `ErrorId` dotted-snake format `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`.
- ADR-0001 — Phase-5 contract snapshot; `Transform` / `RecipeOutcome` shape pinned.

**As-built state the original story didn't address:**

The validator pulled the actual on-disk Pydantic shapes from `outcomes.py`, `transform.py`, and the S4-01 / S5-01 hardened-story prescriptions. The original draft had substantial contract drift against these — multiple BLOCK-grade findings that would cause the executor to hard-fail on first import. See findings section.

---

## Stage 2 — Four critic reports

### A. Coverage critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| C1 | BLOCK | The original AC for the symlink TOCTOU race named `/etc/passwd` as the sentinel — runner-environment-dependent, ambiguous on rootful CI, and probably benign on the typical CI runner. | Rewrote AC-3b to use a per-test `tmp_path / "sentinel"` file whose pre-write mtime is captured and asserted unchanged. Removed `/etc/passwd` reference. |
| C2 | HARDEN | Edge case E20 (NUL bytes / bidi / adversarial content) had no AC. | Added AC-1c parametrized over `[NUL, BIDI_RLE, "..", "/"]`. The `PackageId.parse` smart constructor is the rejection gate (no parallel validator invented). |
| C3 | HARDEN | The `dep_not_in_package_json` failure path was implicit only ("if none matched, return `Result.Err(...)`"). | Promoted to AC-2c with the canonical `RecipeFailed(error_id="recipe.package_not_in_dependencies")` and a `details["sections_searched"]` carry-through. |
| C4 | HARDEN | Section-precedence (same package in multiple dep sections) had no AC. | Added AC-2d pinning the precedence walk (`dependencies` > `devDependencies` > `optionalDependencies` > `overrides`) and the edit-the-first-match invariant. |
| C5 | HARDEN | `DiskQuotaExceeded` variant was named in §Implementation outline but missing from the parametrized variant-mapping AC. | Added to AC-4g parametrize tuple. Closed the exhaustiveness gap. |
| C6 | HARDEN | Determinism AC didn't validate that the **two-file** diff structure was exercised each iteration (a regression in only the second-file path could pass a one-file-only diff). | Strengthened AC-Det-1 to assert both `b"--- file: package.json ---"` and `b"--- file: package-lock.json ---"` markers appear in each iteration's `diff_bytes`. |
| C7 | HARDEN | The Phase-5 contract-snapshot re-baseline obligation (`ApplicationPlan` widening shifts the JSON schema) was unstated. | Added AC-Plan-3. |

### B. Test-Quality critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| T1 | BLOCK | Test code constructs `Completed(exit_code=0, stdout=b"", stderr=b"")` and `Completed(0, b"", b"")`. As-built `Completed` per S4-01 HARDENED: `(kind, exit_code, stdout_bytes: int, stderr_bytes: int, wall_time_s: float)`. Bare-arg `TimedOut() / OomKilled() / NetworkDenied()` similarly wrong. The TDD plan would not compile. | Rewrote every test fixture to use the S4-01 shapes with explicit kwargs. |
| T2 | BLOCK | `RecipeOutcome.Failed(reason="…", exit_code=…, stderr_tail=…)` and `out.reason` accesses don't exist in `outcomes.py`. `RecipeFailed.error: RecipeError(error_id, message, details)`. `stderr_tail` is impossible (S4-01 `Completed` exposes only `stderr_bytes: int` counter). | Rewrote every failure AC + every test assertion to use `RecipeFailed(error=RecipeError(error_id=ErrorId("recipe.<…>"), message=…, details={…}))`. Removed `stderr_tail` entirely; replaced with `details["exit_code"]`, `details["stderr_bytes"]`, `details["wall_time_s"]`. |
| T3 | BLOCK | `RecipeOutcome.Applied(transform=NpmLockfileTransform(...))` is wrong. `Applied` carries `transform_id`, not the Transform instance. | Rewrote happy-path AC + TDD test to use a 2-tuple `(RecipeOutcome, NpmLockfileTransform | None)` return contract — the orchestrator (S6-04) keys the Transform by `transform_id`. |
| T4 | BLOCK | `RecipePlan(package=…, from_version=…, to_version=…, kind=…)` does not exist. S5-01 HARDENED pins the parameter type to `ApplicationPlan`. | Added the AC-Plan-1 / AC-Plan-2 ApplicationPlan additive widening + smart constructor `ApplicationPlan.for_npm_semver_bump(...)` as a prerequisite step. |
| T5 | HARDEN | "Missing-flag mutation tests cause assertion to fail" was not operationalized. | Rewrote AC-4b as a parametrized test with `monkeypatch.setattr(eng_mod, "_NPM_INSTALL_CMD", short)` over each flag index 2..5, asserting the resulting diff bytes diverge from the full-flag baseline. |
| T6 | HARDEN | `spec.env is NpmEnv` is wrong (S4-01 ships `JailedEnv` discriminated union). | Rewrote AC-4e to `spec.env.kind == "npm"` AND `spec.env.npm_config_ignore_scripts == "true"` (the ADR-0007 CLI-AND-env load-bearing cross-check). |
| T7 | HARDEN | `--prefer-offline` warm-cache test was vague. | Removed the vague claim; the warm-cache effect is covered by AC-Gold-1 (golden round-trip under the real bwrap adapter). |
| T8 | HARDEN | mypy-narrowing exhaustiveness was missing — runtime exhaustiveness alone misses a deleted variant. | Added AC-4g2 mirroring S4-01's `test_sandbox_jail_mypy_negative.py` precedent. |
| T9 | HARDEN | The no-op round-trip AC alone doesn't catch a silent key re-sort across edits. | Added AC-2b parametrized over each dep, asserting diff line cardinality ≤ 6 lines. |
| T10 | HARDEN | Golden drift had a `make refresh-lockfile-golden` mention but no fence. | Added AC-Gold-2 with a fence test that rejects PRs modifying the golden without a `.regen-justification.md` sidecar. |

### C. Consistency critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| K1 | BLOCK | `Transform.files_changed: list[SandboxedPath]` contradicts as-built `transform.py:94` (`tuple[SandboxedPath, ...]`). | Corrected AC-Surface-3 and test fixtures to `tuple`. |
| K2 | BLOCK | Failure `reason` strings like `"package_json_too_large"`, `"filesystem_race"` violate Phase-1 ADR-0007 `ErrorId` format (`^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` — must have a dot). `ErrorId` newtype rejects them at construction. | Rewrote every error reason as `ErrorId("recipe.<…>")` dotted-snake. Enumerated as a `Literal` (13 entries) at module top. |
| K3 | HARDEN | `orjson` is named in arch §C12 but absent from `pyproject.toml`. | Added AC-Tool-4 + Files-to-touch row for `pyproject.toml` edit. |
| K4 | HARDEN | S4-04 (the real `SandboxedPath` with `O_NOFOLLOW`) is HARDENED but not yet GREEN. The original TOCTOU AC implicitly assumed S4-04 was shipped. | Split AC-3 into AC-3a (always-run AST fence: only `SandboxedPath.open` under `transforms/engines/`) + AC-3b (`skipif`-gated integration test that self-enables once S4-04 substitutes the typealias). |
| K5 | HARDEN | Story didn't acknowledge that `Depends on: S5-01` alone is insufficient — S4-01 / S4-04 / S4-05 are all load-bearing. | Expanded `Depends on:` to enumerate the load-bearing predecessors. |
| K6 | HARDEN | Story referenced "Phase 5 ADR-0006 `Result[T, E]` convention" but no such convention exists in the codebase (Phase-5 ADR-0006 is "protocol-vs-abc-convention", not a Result kernel). | Removed the reference; rewrote to a private discriminated union `_InternalError`. |
| K7 | HARDEN | ADR-0001 (Phase-5 contract snapshot) was implicit; `ApplicationPlan` widening shifts the snapshot. | Added ADR-0001 to "ADRs honored" + AC-Plan-3 to re-baseline. |

### D. Design-Patterns critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| D1 | BLOCK | The `Result[T, E]` invention adds a new generic abstraction for **one** internal call site — Rule 2 (Simplicity First) + Rule 7 (don't average conflicting conventions). The codebase convention from `outcomes.py` (every umbrella is `Annotated[A \| B \| C, Field(discriminator="kind")]`) is the established shape. | Replaced with a private `_InternalError` discriminated union of four small Pydantic models (`_PJsonError | _IoError | _NpmError | _LockfileError`). Mirrors the codebase convention. |
| D2 | HARDEN | Failure-mode taxonomy was scattered across ACs without a closed-sum enumeration. Future Phase-7 or Phase-4 additions would silently scatter raw `ErrorId("…")` calls. | Added the `_NpmLockfileErrorId` Literal taxonomy + `_ERROR_IDS` `Final[frozenset]` + AC-Tax-1 fence. Mirrors S1-03 `NotApplicableReason`, S1-05 `_WARNING_IDS`, S4-01 `JailedSubprocessResult` variants. |
| D3 | HARDEN | Pure-helper separation (functional core / imperative shell) was named in §Implementation outline but not pinned by a test. | Added AC-Pure-1 AST-walk fence. Mirrors S1-05's `_no_io_in_pure_helpers` precedent. |
| D4 | HARDEN | `JailedSubprocessResult` mapping was implied but not pinned with `assert_never`-style exhaustiveness. | Added AC-4g (runtime `match` with `assert_never`) + AC-4g2 (mypy-negative test). Mirrors S4-01 AC-9 / AC-9a. |
| D5 | HARDEN | Structural Protocol conformance (Surface-2) was named at runtime only — mypy-strict structural conformance was implied but not pinned. | Strengthened AC-Surface-2 to assert both: runtime `isinstance(...)` AND a mypy-positive assignment. Mirrors S4-01's `_StubJail` Port-proof pattern. |
| D6 | NIT | `_REGISTRY_ALLOWLIST` named "Phase 7 may widen" but didn't mark it as an OCP seam. | Renamed to `_REGISTRY_ALLOWLIST_HOSTS` and added the explicit OCP boundary comment ("never edit this constant — add a sibling constant in a sibling engine module"). |
| D7 | NIT | `_DEP_SECTIONS_PRECEDENCE` was inline-magic in `_edit_dep_version`. Promoting to a module-top `Final` tuple makes the precedence explicit + testable. | Added the constant. |
| D8 | NIT | The `apply` body's failure-lifting pattern was implicit. | Named a `_to_failed(err: _InternalError) -> tuple[RecipeFailed, None]` helper in the Green section — flat sequence of `if err: return _to_failed(err)` lines, easy to skim and mutation-test. |

---

## Stage 3 — Researcher

**Not invoked.** No critic finding required external research; every fix maps to an existing codebase convention or as-built shape. The codebase precedents (S1-03 outcome sum types, S4-01 discriminated unions + assert_never, S1-05 fence pattern, S5-01 Protocol re-export) gave canonical patterns for every Stage-2 finding.

---

## Stage 4 — Edits applied

The story file was edited in place with the following sections rewritten or added:

1. **Header** — `Status: Ready → HARDENED`; expanded `Depends on:` enumerated S5-01 / S1-03 / S1-04 / S4-01 / S4-04 / S4-05; added ADR-0001 + Phase-1 ADR-0007 to `ADRs honored:`.
2. **Validation notes block** — inserted after header, before Context. 18-item ledger of every BLOCK / HARDEN correction with the as-built reference each one cites.
3. **Acceptance criteria** — rewritten end-to-end:
   - Top-of-section convention paragraph pinning the `RecipeFailed(error=RecipeError(...))` shape and the 2-tuple `(outcome, transform | None)` return contract.
   - Reorganized into 8 sub-sections (Surface, Error-id taxonomy, Step 1–6, Determinism, Pure-helper fence, ApplicationPlan widening, No-LLM fence, Tooling).
   - 31 ACs total (up from 21), each with a stable ID (AC-Surface-1, AC-Tax-1, AC-1a/b/c, AC-2a/b/c/d, AC-3a/b, AC-4a–g2, AC-5a/b/c, AC-Apply-1/2/3, AC-Det-1/2, AC-Gold-1/2, AC-Pure-1, AC-Plan-1/2/3, AC-Tool-1/2/3/4).
4. **Implementation outline** — added the load-bearing `ApplicationPlan` widening step (#2), the `orjson` dep step (#3), the `_NpmLockfileErrorId` Literal + `_ERROR_IDS` `Final[frozenset]` at module top (#4), and the `_InternalError` discriminated-union design (#5) replacing the `Result[T, E]` invention.
5. **TDD plan** — every test fixture rewritten to use S4-01 / S1-03 as-built shapes. Added `_writing_jail_factory` helper for jail-mocked happy-path. Added mutation-flags test, mypy-negative test, mypy-positive test, four fence-test stubs. Added `test_adversarial_repo_content_nul_byte_in_name`, `test_edited_round_trip_preserves_other_keys` (parametrized), and re-formulated `test_intra_run_determinism_5x_diff_bytes_includes_both_files`. Symlink TOCTOU test made `skipif`-gated on `SandboxedPath is pathlib.Path`.
6. **Files to touch** — added 11 new rows: 4 new test files, 4 new fence files, the bench file, the `.regen-justification.md` sidecar, the contracts-snapshot re-baseline. Marked `outcomes.py` and `pyproject.toml` as **Modified** (not just create).
7. **Notes for the implementer** — rewrote the `Result[T, E]` paragraph to "Internal-error sum, not `Result[T, E]`" with the design rationale. Added explicit Open/Closed boundary comments on `_NPM_INSTALL_CMD` and `_REGISTRY_ALLOWLIST_HOSTS`. Added a "Read order before opening the editor" paragraph listing the modules to read in dependency order.

---

## Final verdict

**HARDENED.** The original story had block-grade contract drift against multiple shipped modules — particularly the failure-outcome shape, the Completed/TimedOut variant shapes, the Transform `files_changed` tuple-vs-list mismatch, the `RecipePlan` / `ApplicationPlan` confusion, and the `Result[T, E]` invention. Without these fixes the executor would have failed on first import (or worse, written code that "passes" thin tests but doesn't match the Phase-5 contract surface).

The story now constrains a correct implementation:

- Every failure outcome has a closed-Literal `error_id` enumerated module-top.
- Every `JailedSubprocessResult` variant has an explicit AC with the correct as-built constructor.
- Every Pydantic shape (RecipeFailed, Applied, ApplicationPlan, NpmLockfileTransform, TransformProvenance) matches the as-built code in `outcomes.py` + `transform.py`.
- Every pure helper has a fence-tested no-side-effect contract.
- Every constant has an Open/Closed boundary marker.
- The mutation, mypy-negative, mypy-positive, and exhaustiveness tests mirror the S4-01 precedent.
- The integration TOCTOU test self-enables once S4-04 substitutes `SandboxedPath`.

**Ready for `phase-story-executor`.**

---

## Appendix — As-built code references the validator pulled in

- `src/codegenie/transforms/outcomes.py` — `RecipeFailed`, `RecipeError`, `Applied`, `ApplicationPlan`, `NotApplicableReason`.
- `src/codegenie/transforms/transform.py` — `Transform(ABC)`, `TransformProvenance` (7 fields incl. `capability_use_id`).
- `src/codegenie/transforms/_forward.py` — `SandboxedPath: TypeAlias = pathlib.Path` (Phase-3-Step-1 shim; S4-04 substitutes).
- `src/codegenie/plugins/protocols.py` — temporary `RecipeEngine` Protocol stub (S2-01 deferred to Step 5; S5-01 HARDENED moves canonical home to `transforms/recipe_engine.py`).
- `docs/phases/03-vuln-deterministic-recipe/stories/S4-01-subprocess-jail-port.md` — HARDENED `JailedSubprocessSpec` + `JailedSubprocessResult` variant constructor shapes.
- `docs/phases/03-vuln-deterministic-recipe/stories/S5-01-recipe-registry.md` — HARDENED `RecipeEngine` Protocol home + canonical `apply(self, repo, plan, capability) -> RecipeOutcome` signature.
- `docs/phases/03-vuln-deterministic-recipe/phase-arch-design.md` §C12 (L714–L717), §Data model (L793–L806), §Defaults (L906), §Edge cases E1/E10/E11/E12/E20.
