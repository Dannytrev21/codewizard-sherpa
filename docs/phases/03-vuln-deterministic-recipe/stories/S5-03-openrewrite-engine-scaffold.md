# Story S5-03 — `OpenRewriteRecipeEngine` scaffold (Protocol-conformant, Phase-7 preview)

**Step:** Step 5 — Transform ABC consumers, RecipeEngine Protocol, RecipeRegistry, lockfile policy
**Status:** HARDENED — un-blocked 2026-05-20 by [ADR-0014](../ADRs/0014-recipe-engine-surfaces-transform-via-transform-registry.md) + story S5-01b (`TransformRegistry`, GREEN). The prior BLOCKED `apply`-2-tuple-vs-Protocol-conformance contradiction is resolved: `apply` returns a bare `RecipeOutcome` and the produced `DockerfileBaseImageTransform` is surfaced via a constructor-injected `TransformRegistry`. The secondary blocker (`NpmLockfileRecipeEngine` absent) is sequenced away — S5-03 now `Depends on` S5-02 being GREEN. See the **Re-execution note** below — it is authoritative and supersedes every conflicting AC / outline / TDD-plan statement elsewhere in this file.
**Effort:** M
**Depends on:** S5-01 (HARDENED — `RecipeEngine` Protocol at `transforms/recipe_engine.py` + `ApplicationPlan`), S5-01b (GREEN — `TransformRegistry` at `transforms/transform_registry.py`), S5-02 (must be GREEN first — AC-Surface-2(c) imports `NpmLockfileRecipeEngine` and the `tests/fence/test_engines_no_*` engine fences S5-02 introduces), S1-03 (GREEN — `outcomes.py` discriminated unions), S1-04 (GREEN — `Transform` ABC + `TransformProvenance`), S4-01 (HARDENED — `SubprocessJail` Port + `JailedSubprocessSpec` + `JailedEnv` discriminated sum), S4-04 (HARDENED — `SandboxedPath` typealias)
**ADRs honored:** ADR-0009, ADR-0006, ADR-0012, ADR-0010, ADR-0014 (`TransformRegistry` channel), ADR-0001 (Phase-5 contract — additive `JailedEnv` widening for `JvmEnv` is logged), Phase-1 ADR-0007 (`ErrorId` dotted-snake format)

## Re-execution note (2026-05-20 — `codewizard-executer`; un-blocks this story)

This story was `BLOCKED` on 2026-05-20: it inherited S5-02's `apply`-2-tuple-vs-Protocol-conformance contradiction against the landed S5-01 `RecipeEngine.apply(...) -> RecipeOutcome`. [ADR-0014](../ADRs/0014-recipe-engine-surfaces-transform-via-transform-registry.md) resolves the design question and story **S5-01b** (`TransformRegistry`, GREEN) ships the missing component. The **corrected contract below is authoritative** — it supersedes every conflicting statement elsewhere in this file: Validation note #2, Validation note #10's `_map_jail_result` *public* framing, the Goal paragraph's 2-tuple `apply` signature, the "### `apply()` return contract" heading, AC-Surface-2(c), AC-Contract-1, AC-Surface-4, Implementation outline §3–§6, and **every `outcome, transform = await ...apply(...)` destructure in the TDD plan**.

**Corrected contract (authoritative):**

1. **`apply` returns a bare `RecipeOutcome`** — `async def apply(self, repo: SandboxedPath, plan: ApplicationPlan, capability: NpmInstallCapability) -> RecipeOutcome`. NOT a 2-tuple. This is the as-built S5-01 Protocol surface verbatim (ADR-0001 / ADR-0009 frozen); the harden-pass 2-tuple rewrite is withdrawn. AC-Surface-2(c) still holds — both engines share this *same* `-> RecipeOutcome` annotation.
2. **The constructor takes the registry** — `__init__(self, jail: SubprocessJail, transform_registry: TransformRegistry, *, cli_jar_path: str | None = None)`. `TransformRegistry` is imported from `codegenie.transforms.transform_registry`. No module-level mutable state (the `test_engines_no_module_state.py` fence is unchanged).
3. **The produced `DockerfileBaseImageTransform` is surfaced via the registry.** On the happy path the engine `register`s the transform into the injected `TransformRegistry` and returns `Applied(transform_id=transform.transform_id, …)`.
4. **The pure helper stays a tuple — only the public surface changes.** `_map_jail_result(result, plan, repo) -> tuple[RecipeOutcome, Transform | None]` remains a *pure* internal helper returning `(outcome, transform)` (functional core). The *impure* `apply` calls it, and on an `Applied` outcome does `self._transform_registry.register(transform)` before returning the bare `outcome`. The pure/impure split is preserved; only `apply`'s public return type narrows to `RecipeOutcome`.
5. **Tests obtain the Transform by lookup.** Where a TDD-plan test wrote `outcome, transform = await engine.apply(...)`, the corrected form is `outcome = await engine.apply(...)` then `transform = transform_registry.get(outcome.transform_id)`.

Nothing else changes: the Phase-7-preview fixture, the JVM-under-`SubprocessJail` integration test, and the closed error-id taxonomy all stand.

## Validation notes (2026-05-19, phase-story-validator)

The original draft carried the same shape of contract drift S5-02 had — multiple BLOCK-grade findings that would cause the executor to hard-fail on first import. Every change below was made because the corresponding shape is **already shipped** under `src/codegenie/transforms/outcomes.py` (S1-03 GREEN), `src/codegenie/transforms/transform.py` (S1-04 GREEN), or pinned by S5-01 HARDENED + S5-02 HARDENED.

**Block-grade corrections (executor would hard-fail without these):**

1. **`RecipeOutcome.Applied(...)` / `RecipeOutcome.Failed(reason=...)` / `RecipeOutcome.NotApplicable(...)` is pseudo-OO and a runtime error.** Per `outcomes.py:231`, `RecipeOutcome` is a `TypeAlias = Annotated[Applied | Skipped | RecipeNotApplicable | RecipeFailed, Field(discriminator="kind")]`. Variants are constructed directly: `Applied(kind="applied", transform_id=..., plugin_id=..., recipe_id=...)`, `RecipeFailed(kind="failed", error=RecipeError(error_id=ErrorId("recipe.<…>"), message=…, details={…}))`. Every AC + test site rewritten. (Coverage A3 / Test-Quality B2 / Consistency C1-C2.)
2. **2-tuple return contract** `apply(...) -> tuple[RecipeOutcome, Transform | None]` mirrors S5-02 HARDENED. `Applied` carries the BLAKE3-hex `transform_id`; the orchestrator (S6-04) keys the Transform instance by it. Every non-Applied branch returns `(<outcome>, None)`. Goal text + Outline §4 + every TDD test rewritten. (Consistency C6, Design-Patterns D4.)
3. **`Completed(0, b"", b"")` is the wrong shape.** Per S4-01 HARDENED, `Completed(kind, exit_code: int, stdout_bytes: int, stderr_bytes: int, wall_time_s: float)` — byte counters, not byte payloads. Every test fixture rewritten. Same for `TimedOut(budget_s, elapsed_s)` / `OomKilled(peak_rss_mib)` / `NetworkDenied(host: str)` / `DiskQuotaExceeded(quota_bytes, bytes_written)`. (Consistency C3, Test-Quality B1.)
4. **Failure reasons must be Phase-1 ADR-0007 `ErrorId` dotted-snake** (`^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`). Bare strings like `"openrewrite_nonzero_exit"` fail `ErrorId` newtype validation; they are also NOT members of the closed `NotApplicableReason` Literal. All rewritten as `ErrorId("recipe.openrewrite_nonzero_exit")` etc., enumerated module-top as a closed `_OpenRewriteErrorId: Literal[...]`. (Consistency C5, Design-Patterns D2.)
5. **`files_changed` is `tuple[SandboxedPath, ...]` (per `transform.py:94`)**, not `list`. Outline §6 corrected to `files_changed = (repo / "Dockerfile",)`. (Consistency C4.)
6. **Exhaustive `JailedSubprocessResult` mapping with `assert_never`.** Original draft maps only `Completed(0)` / `Completed(non-zero)` / `NetworkDenied`. Missing `TimedOut`, `OomKilled`, `DiskQuotaExceeded`. Added per-variant ACs + a mypy-strict negative test (mirrors S5-02 AC-4g + AC-4g2). (Coverage A1, Design-Patterns D3.)
7. **`RecipePlan` is not a thing as-built.** S5-01 HARDENED pins the Protocol parameter type to `ApplicationPlan` (`outcomes.py:174`, currently `summary: str | None = None`). Test imports rewritten to `ApplicationPlan` from `codegenie.transforms.outcomes`. The Dockerfile-specific widening (`dockerfile_path`, `target_image_ref`) is a Phase-7-additive concern — explicitly out-of-scope here. (Test-Quality B3.)

**Harden-grade corrections:**

8. **Closed `_OpenRewriteErrorId: Literal[...]` taxonomy** at module top mirroring S5-02 hardening; adding a failure mode = new entry + new AC; deleting one re-baselines Phase-5 snapshot. (Design-Patterns D2.)
9. **`JvmEnv` is added to the S4-01 `JailedEnv` discriminated sum as an additive widening.** Pinned: `kind: Literal["jvm"]`, frozen Pydantic, `java_home: str`, `max_heap_mib: int`. `JailedEnv = Annotated[NpmEnv | GitEnv | JvmEnv, Field(discriminator="kind")]`. `assert_never` exhaustiveness test added covering all three branches. (Coverage A5, Design-Patterns D1, Consistency C10-C11.)
10. **Functional core / imperative shell.** Pure helpers `_build_openrewrite_spec(repo, plan, cli_jar_path) -> JailedSubprocessSpec` and `_map_jail_result(result, plan, repo) -> tuple[RecipeOutcome, Transform | None]` carry all logic; `apply()` is a thin orchestrator. AST-walk fence rejects `await` / `os.*` / `time.*` / `subprocess` inside the pure helpers (mirrors S5-02 + S1-05 precedents). (Design-Patterns D5, Coverage A7.)
11. **Smart-constructor `DockerfileBaseImageTransform.create(diff_bytes, files_changed, provenance)`** computes `transform_id` from `blake3(diff_bytes)`, validates `diff_bytes` non-empty + `files_changed` non-empty. Direct `DockerfileBaseImageTransform()` is rejected (`Transform.__new__` already blocks ABC; the smart constructor is the only sanctioned creator). (Design-Patterns D6.)
12. **Byte-identical determinism AC.** `diff_bytes` + `transform_id` are byte-identical across ≥10 repeated runs on the fixture; `TransformProvenance.applied_at` is pinned via a frozen-clock fixture so determinism isn't contaminated by wall-clock. (Coverage A2, Test-Quality B5.)
13. **AST-walk fence on raw file I/O.** `openrewrite.py` passes the existing `tests/fence/test_engines_no_raw_os_open.py` fence introduced by S5-02 — only `SandboxedPath.open(...)` for file I/O. (Coverage A6.)
14. **Conformance test AMENDED, not recreated.** S5-01 (HARDENED) already creates `tests/integration/test_recipe_engine_protocol.py`; S5-03 adds the `test_openrewrite_engine_satisfies_protocol` case in place. Files-to-touch updated. (Consistency C9, Design-Patterns D7.)
15. **`pyproject.toml` `addopts` extended** from `-m "not bench"` to `-m "not bench and not phase_7_preview"` so `make test` excludes phase-7 tests cleanly (the `skipif(shutil.which("java") is None)` guard is a defense-in-depth fallback, not the primary mechanism). (Coverage A8, Consistency C8.)
16. **Strategy-registry decision** for `RecipeEngine` instances (`@register_recipe_engine`) explicitly **deferred** — surfaced in Notes-for-implementer §"Engine registry". Hard-coded re-exports in `transforms/__init__.py` are the Phase-3 mechanism; Phase-7's distroless plugin adding a third engine is **the trigger** for the registry seam, not S5-03. (Design-Patterns D8.)
17. **`capability: NpmInstallCapability` mismatch with OpenRewrite** acknowledged as a known Phase-7 ADR amendment, NOT corrected in S5-03. The scaffold's `apply()` accepts the parameter to satisfy the S5-01 Protocol signature and threads it through `TransformProvenance.capability_use_id` only when an `Applied` outcome is produced (which it isn't, in Phase 3, because the engine is never invoked from a Phase-3 npm workflow). A `# TODO(Phase-7): widen capability union` marker pinned at the `apply` signature site + a fence test asserts the marker is present until Phase 7 amends. (Coverage A4, Consistency C7.)

**No `RESCUE` conditions** — the story's goal, scope, and arch-trace are sound. Verdict: **HARDENED**. Full critic dossier at `_validation/S5-03-openrewrite-engine-scaffold.md`.

---

## Context

`OpenRewriteRecipeEngine` is the **second** day-1 `RecipeEngine` implementation per ADR-0009 Option C. It is **scaffolded** — Protocol-conformant, JVM-subprocess wrapped in `SubprocessJail`, ships one working Phase-7-tagged Dockerfile-base-image-swap fixture (`tests/fixtures/openrewrite/dockerfile-base-image-swap/` — alpine → cgr.dev/chainguard/node:latest is the natural shape per `../phase-arch-design.md §Open implementation questions`), and is **never invoked by any Phase-3 npm workflow**. The whole point of the scaffold is to pay the "two genuine implementations from day one" rent ADR-0009 commits to — so that Phase 7's distroless plugin adds Dockerfile-rewrite recipes as a *recipe addition*, not an engine + recipe + dispatch invention under the "zero edits to existing code" exit criterion.

The critic correctly identified the risk in `critique.md §Shared blind spots #1`: shipping `RecipeEngine` Protocol with only `NpmLockfileRecipeEngine` would be the toolkit's textbook "Strategy with a single implementation = unnecessary indirection" anti-pattern. The fix is the scaffold — small enough that it doesn't bloat Phase 3 (per ADR-0009 tradeoffs: +~250 LOC + 1 fixture), large enough that Phase 7 inherits a working engine.

**Key non-decisions Phase 3 makes explicitly:**

- The `java` binary is **NOT** in Phase 3's `ALLOWED_BINARIES`. ADR-0012 (Phase 3) amends `ALLOWED_BINARIES` with `npm`, `bwrap`, `sandbox-exec`, `jq` — no `java`. ADR-0009 §Consequences: "added only when Phase 7 enables it (`OpenRewriteRecipeEngine` is scaffolded, but the binary it would spawn is gated)." The scaffold is structurally complete — it builds the `JailedSubprocessSpec`, it knows the JVM command shape, it conforms to the Protocol — but the **integration test that actually invokes JVM** is gated behind `@pytest.mark.phase_7_preview` (a marker that's collected but skipped by default in Phase 3 CI; Phase 7 enables it).
- The **OpenRewrite recipe DSL itself is NOT shipped** in Phase 3. The fixture carries the recipe YAML; the engine knows how to invoke it; Phase 7 ships the actual Dockerfile recipe content.
- **No JVM SecurityManager.** Rejected per critic Security Issue 4 — deprecated upstream. The `SubprocessJail` boundary IS the defense for the JVM subprocess (`../phase-arch-design.md §Goals and non-goals`).

The scaffold's job per `../phase-arch-design.md §C12`: (1) construct a `JailedSubprocessSpec` whose `cmd` invokes `java -jar <openrewrite-cli>` against the Phase-7 fixture; (2) implement `apply(repo, plan, capability)` matching the `RecipeEngine` Protocol shape; (3) return `RecipeOutcome.Applied(DockerfileBaseImageTransform(...))` on success; (4) ship the one fixture + the `@pytest.mark.phase_7_preview` test that exercises the whole shape end-to-end **when** Phase 7 enables the marker.

The conformance test (`tests/integration/test_recipe_engine_protocol.py` — per ADR-0009 Consequences) runs in Phase 3 CI and asserts both engines satisfy the `RecipeEngine` Protocol structurally. That test is the rent-payment receipt.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C12` — the scaffold description (the load-bearing two paragraphs).
  - `../phase-arch-design.md §Goals and non-goals` — "No JVM SecurityManager." line.
  - `../phase-arch-design.md §Design patterns applied row 2` — Strategy on `RecipeEngine` with two implementations.
  - `../phase-arch-design.md §Anti-patterns flagged and rejected — Premature pluggability` row.
  - `../phase-arch-design.md §Departures from all three inputs #3` — "All three demoted OpenRewrite; spec ships scaffold."
  - `../phase-arch-design.md §Open implementation questions` — "OpenRewriteRecipeEngine Phase-7 fixture content (alpine → cgr.dev/chainguard/node:latest is the natural shape)" — this story picks and ships the one fixture.
  - `../phase-arch-design.md §Phase 7 readiness P3-004` — `OpenRewriteRecipeEngine scaffolded with Phase-7 fixture`.
- **Phase ADRs:**
  - `../ADRs/0009-recipe-engine-protocol-with-two-implementations-day-1.md` — ADR-0009 — the load-bearing decision; §Consequences spells out `java` is NOT in `ALLOWED_BINARIES` for Phase 3.
  - `../ADRs/0012-amend-allowed-binaries-npm-bwrap-sandbox-exec-jq.md` — ADR-0012 — confirms the `ALLOWED_BINARIES` amendment excludes `java`.
  - `../ADRs/0006-hexagonal-subprocessjail-port-bwrap-sandbox-exec.md` — ADR-0006 — `SubprocessJail` Port; the boundary that wraps the JVM subprocess.
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — ADR-0010 — `Transform` ABC subclass `DockerfileBaseImageTransform`; `RecipeOutcome` tagged union.
- **Source design:**
  - `../final-design.md §Synthesis ledger row "OpenRewriteRecipeEngine ship-or-defer"` (score 15/15).
- **High-level impl:**
  - `../High-level-impl.md §Step 5 — Features delivered` bullet 4 (`engines/openrewrite.py`); `Done criteria` line 2 (`-m phase_7_preview` test).
- **Sibling stories:**
  - `S5-01-recipe-registry.md` — the `RecipeEngine` Protocol this story conforms to.
  - `S4-01-subprocess-jail-port.md` / `S4-02-bwrap-adapter-linux.md` — `SubprocessJail` substrate; the JVM subprocess runs under bwrap on Linux.
  - `S1-04-transform-abc-apply-context.md` — `Transform` ABC; `DockerfileBaseImageTransform` is a subclass.
  - Phase 7 will spawn a follow-up story that flips `@pytest.mark.phase_7_preview` to a per-PR-required mark and adds `java` to `ALLOWED_BINARIES`.

## Goal

Ship `src/codegenie/transforms/engines/openrewrite.py` exposing `OpenRewriteRecipeEngine` and `DockerfileBaseImageTransform`. The engine structurally satisfies the `RecipeEngine` Protocol (S5-01) — `async def apply(self, repo: SandboxedPath, plan: ApplicationPlan, capability: NpmInstallCapability) -> RecipeOutcome` (a bare `RecipeOutcome`, per the Re-execution note + ADR-0014; the same shape S5-02 ships). One Phase-7-preview fixture (`tests/fixtures/openrewrite/dockerfile-base-image-swap/`) carries the recipe YAML + a Dockerfile + the expected post-rewrite Dockerfile. One `@pytest.mark.phase_7_preview` integration test asserts the engine, when invoked under a real `SubprocessJail` with `java` available, returns `Applied(transform_id=…)` and `transform_registry.get(outcome.transform_id)` yields a `DockerfileBaseImageTransform` whose `diff_bytes` matches the golden byte-for-byte. The conformance test at `tests/integration/test_recipe_engine_protocol.py` (S5-01) is **amended additively** to also assert `OpenRewriteRecipeEngine` satisfies the Protocol.

> **`apply` return contract** — mirrors S5-02 (HARDENED). The Transform instance is returned **alongside** the outcome; `Applied` carries the BLAKE3-hex `transform_id` (lookup key) only. Every non-Applied branch returns `(<outcome>, None)`.

## Acceptance criteria

> **Convention.** Every `RecipeFailed(error=…)` AC below names the `error_id` as a dotted-snake `ErrorId` per Phase-1 ADR-0007 (`^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`). Failures are constructed as `RecipeFailed(kind="failed", error=RecipeError(error_id=ErrorId("recipe.<…>"), message="…", details={…}))` per as-built `outcomes.py:222`. There is **no** `RecipeOutcome.Failed(reason=…)` shape — that was contract drift; see Validation note #1.

### Surface + module shape

- [ ] **AC-Surface-1.** `from codegenie.transforms.engines.openrewrite import OpenRewriteRecipeEngine, DockerfileBaseImageTransform` succeeds. Module's `__all__` is exactly `{"OpenRewriteRecipeEngine", "DockerfileBaseImageTransform"}` (private helpers — leading underscore — never re-exported); a meta-test asserts `set(openrewrite.__all__) == EXPECTED`.
- [ ] **AC-Surface-2.** `OpenRewriteRecipeEngine` structurally satisfies the S5-01 `RecipeEngine` Protocol both at runtime and under mypy: (a) `isinstance(OpenRewriteRecipeEngine(jail=fake_jail, transform_registry=registry), RecipeEngine) is True` (Protocol is `@runtime_checkable`); (b) a mypy-strict assignment `_engine: RecipeEngine = OpenRewriteRecipeEngine(jail=fake_jail, transform_registry=registry)` type-checks (fence file `tests/unit/transforms/test_openrewrite_typing.py` runs `mypy --strict` on a tiny module containing the assignment and asserts exit code 0); (c) `inspect.signature(OpenRewriteRecipeEngine.apply).return_annotation` equals `inspect.signature(NpmLockfileRecipeEngine.apply).return_annotation` — both engines share the `-> RecipeOutcome` return annotation verbatim (Design-Patterns D4).
- [ ] **AC-Surface-3.** `DockerfileBaseImageTransform(Transform)` is an ABC subclass declaring the four class-level annotations: `transform_id: TransformId`, `diff_bytes: bytes`, `files_changed: tuple[SandboxedPath, ...]` (tuple, NOT list, length 1 — just `Dockerfile` — for the scaffold; Phase 7 multi-stage may widen), `provenance: TransformProvenance`. Inherits the `TypeError` on direct `Transform(...)` instantiation. Direct `DockerfileBaseImageTransform(...)` is **also rejected** in favor of the smart constructor (AC-Smart-1).
- [ ] **AC-Surface-4.** `OpenRewriteRecipeEngine.__init__(self, jail: SubprocessJail, transform_registry: TransformRegistry, *, cli_jar_path: str | None = None)` is the only public constructor — `jail` and `transform_registry` are constructor-injected (ADR-0014); no global registry write at import time; no module-level mutable state. The existing `tests/fence/test_engines_no_module_state.py` fence (introduced by S5-02) covers `transforms/engines/*.py` — `openrewrite.py` MUST pass it without amendment.

### Error-id taxonomy (closed sum)

- [ ] **AC-Tax-1.** Module-top declaration:
  ```python
  _OpenRewriteErrorId: TypeAlias = Literal[
      "recipe.openrewrite_nonzero_exit",
      "recipe.network_policy_violation",
      "recipe.jvm_timeout",
      "recipe.jvm_oom",
      "recipe.disk_quota_exceeded",
  ]
  ```
  plus `_ERROR_IDS: Final[frozenset[ErrorId]]` derived from `get_args(_OpenRewriteErrorId)` at import time. A meta-test asserts `_ERROR_IDS` has exactly 5 entries and that every member round-trips through the `ErrorId` newtype validator. **Adding a new failure mode is a Literal expansion + a new AC; deleting one re-baselines the Phase-5 contract snapshot (S6-06).**

### Pure-helper / functional-core fence

- [ ] **AC-Pure-1 (Design-Patterns D5).** `_build_openrewrite_spec(repo, plan, cli_jar_path) -> JailedSubprocessSpec` and `_map_jail_result(result, plan, repo) -> tuple[RecipeOutcome, Transform | None]` are pure: AST-walk fence in `tests/fence/test_engines_pure_helpers.py` rejects `await`, `os.*`, `time.*`, `subprocess`, `logging`, `pathlib.Path.open`, raw `open(` calls inside their function bodies (mirrors S5-02 + S1-05 `_no_io_in_pure_helpers` precedent). `apply()` is the *only* impure surface; AST-walk asserts `apply()` body is the thin orchestration of the Re-execution note §4 — build spec, `await jail.run`, `_map_jail_result`, conditionally `transform_registry.register(transform)`, return the bare `RecipeOutcome`. `await` is allowed only inside `apply()`.
- [ ] **AC-Pure-2 — Raw I/O fence.** `openrewrite.py` passes the existing `tests/fence/test_engines_no_raw_os_open.py` AST-walk fence (introduced by S5-02): no `os.open`, no `pathlib.Path.open`, no `builtins.open`, no `io.open`. Only `SandboxedPath.open(...)` is permitted.

### `apply()` return contract — bare `RecipeOutcome`

- [ ] **AC-Contract-1 (Design-Patterns D4).** `OpenRewriteRecipeEngine.apply` return annotation is exactly `RecipeOutcome` (per the Re-execution note + ADR-0014). A test asserts `inspect.signature(...).return_annotation` resolves to `"RecipeOutcome"` after `from __future__ import annotations` resolution, and that it equals `NpmLockfileRecipeEngine.apply`'s annotation (both engines share the as-built S5-01 Protocol surface).
- [ ] **AC-Contract-2.** The pure helper `_map_jail_result` returns `(outcome, None)` on every non-`Applied` branch — tests assert the second tuple element is `None` whenever `not isinstance(outcome, Applied)`, so `apply` registers nothing and a non-`Applied` outcome leaves the injected `TransformRegistry` empty.

### Spec construction (build phase — pure helper)

- [ ] **AC-Spec-1 — Exact `cmd` tuple.** `JailedSubprocessSpec.cmd` is exactly `("java", "-jar", cli_jar_path, "run", "--recipe", str(recipe_yml_path), "--in-place")`. Asserted bit-identical by a unit test against a `FakeJail` spy; permutation, missing element, or extra element fails. `cli_jar_path` is constructor-injected (default `_OPENREWRITE_CLI_JAR`).
- [ ] **AC-Spec-2 — Time / memory budget envelope** (Phase 7 will re-tune): `spec.time_budget_s == 300.0` AND `spec.memory_mib == 2048` AND `spec.pids_max == 64`. Pinned to `_OPENREWRITE_TIME_BUDGET_S` / `_OPENREWRITE_MEMORY_MIB` / `_OPENREWRITE_PIDS_MAX` `Final` constants module-top.
- [ ] **AC-Spec-3 — Network policy is `DenyAll`.** `spec.network.kind == "deny_all"` (the `NetworkPolicy` discriminated-sum discriminator). A second AC asserts no code path under `openrewrite.py` constructs a `RegistryAllowlist` or `AllowAll` (AST-walk fence). Dockerfile recipes do not need egress; the OpenRewrite CLI jar is provisioned on-disk by Phase 7.
- [ ] **AC-Spec-4 — Typed `JvmEnv` discriminator.** `spec.env.kind == "jvm"` AND `spec.env.java_home == "/opt/java"` AND `spec.env.max_heap_mib == 1024`. A mypy-strict assignment `_env: JvmEnv = spec.env` type-checks (positive fence file).

### `JvmEnv` — additive `JailedEnv` widening (Design-Patterns D1)

- [ ] **AC-Env-1.** This story adds `JvmEnv` to `src/codegenie/transforms/sandbox_jail.py` as a `frozen=True, extra="forbid"` Pydantic model with fields `kind: Literal["jvm"] = "jvm"`, `java_home: str`, `max_heap_mib: int`. The S4-01 `JailedEnv` discriminated sum widens additively to `JailedEnv = Annotated[NpmEnv | GitEnv | JvmEnv, Field(discriminator="kind")]`. Pre-existing `NpmEnv` / `GitEnv` shapes are preserved byte-identical.
- [ ] **AC-Env-2.** A mypy-strict exhaustiveness test `tests/unit/transforms/test_jailed_env_exhaustiveness.py` covers `match env: case NpmEnv(): … case GitEnv(): … case JvmEnv(): … case _: assert_never(env)` and asserts mypy --strict accepts the file (no `assert_never` error). Deleting any branch must produce a non-zero mypy exit (negative fence in `test_jailed_env_mypy_negative.py`).
- [ ] **AC-Env-3.** ADR-0006 (Phase-3 `SubprocessJail` Port) is amended with a "2026-05-19 Amendment" block listing the additive `JvmEnv` widening + the discriminator value. ADR-0001 (Phase-5 contract snapshot) is NOT re-baked — `JailedEnv` is internal to `transforms/`; Phase 5 reads `RecipeOutcome`, not `JailedEnv`.

### Result mapping — exhaustive `JailedSubprocessResult` dispatch (Coverage A1, Design-Patterns D3)

- [ ] **AC-Map-1 — Happy path** (`Completed(exit_code=0, …)`). Engine returns `(Applied(kind="applied", transform_id=<blake3-hex>, plugin_id=…, recipe_id=…), DockerfileBaseImageTransform(...))`. `transform.transform_id == outcome.transform_id` (identity-of-value, BLAKE3-hex). `transform.diff_bytes` is non-empty; `transform.files_changed == (repo / "Dockerfile",)`.
- [ ] **AC-Map-2 — Non-zero exit.** When jail returns `Completed(exit_code=2, stdout_bytes=0, stderr_bytes=42, wall_time_s=0.1)`, engine returns `(RecipeFailed(error=RecipeError(error_id=ErrorId("recipe.openrewrite_nonzero_exit"), message="openrewrite exited 2", details={"exit_code": 2, "stderr_bytes": 42, "wall_time_s": 0.1})), None)`.
- [ ] **AC-Map-3 — `TimedOut(budget_s=300.0, elapsed_s=301.5)`** maps to `RecipeFailed(error=RecipeError(error_id=ErrorId("recipe.jvm_timeout"), details={"budget_s": 300.0, "elapsed_s": 301.5}))`. Second tuple element `None`.
- [ ] **AC-Map-4 — `OomKilled(peak_rss_mib=2100)`** maps to `RecipeFailed(error=RecipeError(error_id=ErrorId("recipe.jvm_oom"), details={"peak_rss_mib": 2100}))`.
- [ ] **AC-Map-5 — `NetworkDenied(host="maven.example.com")`** maps to `RecipeFailed(error=RecipeError(error_id=ErrorId("recipe.network_policy_violation"), details={"host": "maven.example.com"}))`.
- [ ] **AC-Map-6 — `DiskQuotaExceeded(quota_bytes=…, bytes_written=…)`** maps to `RecipeFailed(error=RecipeError(error_id=ErrorId("recipe.disk_quota_exceeded"), details={"quota_bytes": …, "bytes_written": …}))`.
- [ ] **AC-Map-7 — `match`-statement exhaustiveness with `assert_never`.** `_map_jail_result` is a `match` over `JailedSubprocessResult` with `case _: assert_never(result)` in the catch-all. mypy --strict verifies exhaustiveness. A negative-fence file `tests/unit/transforms/test_openrewrite_mypy_negative.py` omits one match arm and asserts mypy --strict exits non-zero with an `assert_never` diagnostic — without this, adding a new `JailedSubprocessResult` variant or deleting one silently passes the runtime-only check.

### `DockerfileBaseImageTransform` — smart constructor (Design-Patterns D6)

- [ ] **AC-Smart-1.** `DockerfileBaseImageTransform.create(*, diff_bytes: bytes, files_changed: tuple[SandboxedPath, ...], provenance: TransformProvenance) -> DockerfileBaseImageTransform` is the only sanctioned creation path. Computes `transform_id = TransformId(blake3.blake3(diff_bytes).hexdigest())`. Rejects `diff_bytes == b""` and `files_changed == ()` with `ValueError`. Direct `DockerfileBaseImageTransform(transform_id=..., diff_bytes=..., ...)` instantiation is permitted (Transform-ABC class-attribute pattern from S1-04) but unit-tested only via the smart constructor; AST-walk fence forbids `DockerfileBaseImageTransform(` calls outside the smart constructor's body.
- [ ] **AC-Smart-2.** `transform.provenance` is a `TransformProvenance` carrying `plugin_id=PluginId("scaffold--phase7-preview")`, `plugin_version="0.0.0"` (scaffold semver), `recipe_id=RecipeId("dockerfile-base-image-swap")`, `recipe_version="0.0.0"`, `transform_kind=TransformKind("dockerfile_base_image_swap")`, `applied_at=` tz-aware UTC, `capability_use_id=EventId("scaffold-noop")` (a sentinel — Phase 7 populates properly when the engine is actually invoked).

### Determinism (Coverage A2, Test-Quality B5)

- [ ] **AC-Det-1.** Across ≥10 repeated runs of the engine against the fixture under a `FakeJail` whose `Completed` response is identical each call, `transform.diff_bytes` and `transform.transform_id` are byte-identical. A frozen-clock fixture pins `TransformProvenance.applied_at` to a fixed UTC instant so determinism isn't contaminated by wall-clock. The 10-run loop is a vanilla `for _ in range(10):` test — Hypothesis is **out-of-scope** because the fixture is fixed.
- [ ] **AC-Det-2.** The `difflib.unified_diff` header MUST NOT include `fromfiledate` / `tofiledate` arguments (which would inject timestamps). A unit test reads `openrewrite.py` AST and asserts no call site passes `fromfiledate=` / `tofiledate=` to `difflib.unified_diff`.

### Phase 3 CI never invokes JVM

- [ ] **AC-CI-1 — Phase 3 unit tests use `FakeJail`.** No test outside `@pytest.mark.phase_7_preview` calls a real `java`. Mechanically: the test file imports `FakeJail` from `tests.helpers.fake_jail` (or constructs it inline) returning S4-01-shaped `Completed(exit_code=…, stdout_bytes=…, stderr_bytes=…, wall_time_s=…)`. A grep across `tests/unit/transforms/test_openrewrite_engine.py` for `shutil.which("java")` returns zero hits.
- [ ] **AC-CI-2 — `java` is NOT in `ALLOWED_BINARIES`.** Fence assertion lives in S1-05's existing `tests/fence/test_allowed_binaries_invariants.py` as a new case `test_java_not_in_allowed_binaries_phase3` (NOT a new file — Rule 7, pick one location). Phase 7's first PR deletes the case (and amends ADR-0012 to add `java`).
- [ ] **AC-CI-3 — `# TODO(Phase-7): widen capability union` marker** is present at the `OpenRewriteRecipeEngine.apply` signature site (the `capability: NpmInstallCapability` parameter is the Phase-3 narrow type per S5-01; OpenRewrite is not npm). A fence test (`tests/fence/test_openrewrite_phase7_markers.py`) grep-asserts the marker is present in `openrewrite.py`. Phase 7 deletes the marker + the fence test when it amends S5-01's Protocol to widen the capability union (a Phase-7 ADR amendment, NOT in S5-03 scope).

### Phase-7-preview integration test

- [ ] **AC-Phase7-1.** `tests/integration/test_openrewrite_engine_phase7_preview.py` marked `@pytest.mark.phase_7_preview` AND `@pytest.mark.skipif(shutil.which("java") is None, reason="requires java")`. Runs the engine against the fixture under a real `BwrapAdapter` (Linux) or a `pytest.skip("macOS path requires future sandbox-exec OpenRewrite policy")`. Asserts `outcome` is `Applied`, `transform.diff_bytes` is byte-equal to `tests/fixtures/openrewrite/dockerfile-base-image-swap/expected.diff`. Skipped by default in Phase 3 CI.
- [ ] **AC-Phase7-2 — Marker registration.** `pyproject.toml`'s `[tool.pytest.ini_options].markers` lists `phase_7_preview: Phase 7 preview tests; skipped in Phase 3 CI by default — collected only with -m phase_7_preview` AND `[tool.pytest.ini_options].addopts` extends `-m` to `-m "not bench and not phase_7_preview"`. `make test` (the Phase-3 default) excludes the phase-7 test cleanly; `pytest -m phase_7_preview` opt-in collects it; `pytest --collect-only -m phase_7_preview` lists exactly the one new integration test.

### Conformance test — AMENDED, not recreated (Consistency C9, Design-Patterns D7)

- [ ] **AC-Conf-1.** `tests/integration/test_recipe_engine_protocol.py` (created by S5-01 HARDENED — see S5-01 Outline §) is **AMENDED** to add `test_openrewrite_engine_satisfies_protocol(fake_jail)` and `test_openrewrite_engine_apply_return_annotation()`. Pre-existing `NpmLockfileRecipeEngine` test cases preserved verbatim. **Not** marked `phase_7_preview`; runs every PR — pure structural typing, no JVM needed.

### Fixture content

- [ ] **AC-Fix-1.** `tests/fixtures/openrewrite/dockerfile-base-image-swap/`:
  - `Dockerfile` — `FROM node:20-alpine` baseline.
  - `expected.Dockerfile` — `FROM cgr.dev/chainguard/node:latest`.
  - `expected.diff` — unified diff (byte-equal target; **no `fromfiledate` / `tofiledate` timestamps**).
  - `recipe.yml` — OpenRewrite recipe YAML targeting the Dockerfile FROM line. (Stub content — Phase 7 will rewrite when the actual rewrite recipe is authored.)
  - `README.md` — one paragraph explaining the fixture's role + that Phase 7 owns its content.

### Surface invariants + tooling

- [ ] **AC-Tool-1.** `mypy --strict src/codegenie/transforms/engines/openrewrite.py` clean. No `dict[str, Any]`; no `cast`; no `# type: ignore` without a justification comment referencing this story.
- [ ] **AC-Tool-2.** `ruff check`, `ruff format --check`, `pytest tests/unit/transforms/test_openrewrite_engine.py tests/integration/test_recipe_engine_protocol.py tests/unit/transforms/test_jailed_env_exhaustiveness.py` all green.
- [ ] **AC-Tool-3 — Coverage.** Branch coverage on `openrewrite.py` ≥ 85%. The missing 15% (JVM-stdout post-processing, exercised only by `phase_7_preview`) is excluded via `# pragma: no cover  # Phase-7-only` line markers — not a per-file threshold (Coverage A9 — pick one mechanism).
- [ ] **AC-Tool-4 — Story-level invariant.** A grep across `src/codegenie/{plugins,transforms,coordinator,probes}/` and `plugins/` for `from codegenie.transforms.engines.openrewrite` returns zero hits outside `src/codegenie/transforms/__init__.py` and the conformance test — confirming "Not invoked by any Phase-3 npm workflow." Pinned by `tests/fence/test_openrewrite_not_invoked_phase3.py`.

## Implementation outline

1. **Add `JvmEnv` to `src/codegenie/transforms/sandbox_jail.py` (S4-01) additively** (AC-Env-1..3):
   ```python
   class JvmEnv(BaseModel):
       model_config = ConfigDict(frozen=True, extra="forbid")
       kind: Literal["jvm"] = "jvm"
       java_home: str
       max_heap_mib: int

   JailedEnv = Annotated[
       NpmEnv | GitEnv | JvmEnv,
       Field(discriminator="kind"),
   ]
   ```
   Pre-existing `NpmEnv` / `GitEnv` shapes preserved byte-identical. Update ADR-0006 with a 2026-05-19 Amendment block.

2. **Create `src/codegenie/transforms/engines/openrewrite.py`.** `from __future__ import annotations`. Constants module-top (`Final`):
   ```python
   _OPENREWRITE_TIME_BUDGET_S: Final[float] = 300.0
   _OPENREWRITE_MEMORY_MIB:    Final[int]   = 2048
   _OPENREWRITE_PIDS_MAX:      Final[int]   = 64
   _OPENREWRITE_CLI_JAR:       Final[str]   = "/opt/openrewrite/rewrite-cli.jar"  # Phase 7 provisions
   _JVM_HEAP_MIB:              Final[int]   = 1024
   _JAVA_HOME:                 Final[str]   = "/opt/java"

   _OpenRewriteErrorId: TypeAlias = Literal[
       "recipe.openrewrite_nonzero_exit",
       "recipe.network_policy_violation",
       "recipe.jvm_timeout",
       "recipe.jvm_oom",
       "recipe.disk_quota_exceeded",
   ]
   _ERROR_IDS: Final[frozenset[ErrorId]] = frozenset(
       ErrorId(member) for member in get_args(_OpenRewriteErrorId)
   )
   ```

3. **`OpenRewriteRecipeEngine.__init__(self, jail: SubprocessJail, transform_registry: TransformRegistry, *, cli_jar_path: str | None = None)`** — constructor-injected `jail` and `transform_registry` (ADR-0014); `cli_jar_path` overridable for test fixtures (default `_OPENREWRITE_CLI_JAR`). No global registry write at import time; no module-level mutable state.

4. **`async def apply` — the only impure surface:**
   ```python
   async def apply(
       self,
       repo: SandboxedPath,
       plan: ApplicationPlan,
       capability: NpmInstallCapability,  # TODO(Phase-7): widen capability union — see Notes §"Capability mismatch"
   ) -> RecipeOutcome:
       spec = _build_openrewrite_spec(repo, plan, self._cli_jar_path)
       result = await self._jail.run(spec)
       outcome, transform = _map_jail_result(result, plan, repo)
       if transform is not None:
           self._transform_registry.register(transform)
       return outcome
   ```
   AST-walk fence asserts the body is exactly these three statements (Design-Patterns D5).

5. **Pure helper `_build_openrewrite_spec(repo, plan, cli_jar_path) -> JailedSubprocessSpec`** (no I/O, no awaits):
   - `cmd = ("java", "-jar", cli_jar_path, "run", "--recipe", str(repo / "recipe.yml"), "--in-place")`.
   - `env = JvmEnv(kind="jvm", java_home=_JAVA_HOME, max_heap_mib=_JVM_HEAP_MIB)`.
   - `network = DenyAll(kind="deny_all")` — Dockerfile recipes don't need egress; ADR-0006 boundary is the defense.
   - `time_budget_s = _OPENREWRITE_TIME_BUDGET_S`, `memory_mib = _OPENREWRITE_MEMORY_MIB`, `pids_max = _OPENREWRITE_PIDS_MAX`.

6. **Pure helper `_map_jail_result(result, plan, repo) -> tuple[RecipeOutcome, Transform | None]`** — `match` over `JailedSubprocessResult`:
   ```python
   match result:
       case Completed(exit_code=0):
           transform = _build_transform(repo, plan)
           outcome = Applied(
               kind="applied",
               transform_id=transform.transform_id,
               plugin_id=plan_plugin_id(plan),     # placeholder ids for scaffold
               recipe_id=RecipeId("dockerfile-base-image-swap"),
           )
           return (outcome, transform)
       case Completed(exit_code=ec, stderr_bytes=eb, wall_time_s=w):
           return (_failed("recipe.openrewrite_nonzero_exit",
                           f"openrewrite exited {ec}",
                           {"exit_code": ec, "stderr_bytes": eb, "wall_time_s": w}), None)
       case TimedOut(budget_s=b, elapsed_s=e):
           return (_failed("recipe.jvm_timeout", "openrewrite timed out",
                           {"budget_s": b, "elapsed_s": e}), None)
       case OomKilled(peak_rss_mib=p):
           return (_failed("recipe.jvm_oom", "openrewrite OOM-killed",
                           {"peak_rss_mib": p}), None)
       case NetworkDenied(host=h):
           return (_failed("recipe.network_policy_violation",
                           f"network egress denied for {h}", {"host": h}), None)
       case DiskQuotaExceeded(quota_bytes=q, bytes_written=w):
           return (_failed("recipe.disk_quota_exceeded", "openrewrite write exceeded quota",
                           {"quota_bytes": q, "bytes_written": w}), None)
       case _:
           assert_never(result)
   ```
   `_failed(error_id, message, details)` constructs `RecipeFailed(kind="failed", error=RecipeError(error_id=ErrorId(error_id), message=message, details=details))`. mypy --strict verifies exhaustiveness — adding a `JailedSubprocessResult` variant without a `case` arm fails (AC-Map-7).

7. **`DockerfileBaseImageTransform(Transform)` subclass.** Class-level annotations only (S1-04 pattern). Add smart constructor:
   ```python
   class DockerfileBaseImageTransform(Transform):
       transform_id: TransformId
       diff_bytes: bytes
       files_changed: tuple[SandboxedPath, ...]
       provenance: TransformProvenance

       @classmethod
       def create(
           cls, *,
           diff_bytes: bytes,
           files_changed: tuple[SandboxedPath, ...],
           provenance: TransformProvenance,
       ) -> DockerfileBaseImageTransform:
           if not diff_bytes:
               raise ValueError("diff_bytes must be non-empty")
           if not files_changed:
               raise ValueError("files_changed must be non-empty")
           transform_id = TransformId(blake3.blake3(diff_bytes).hexdigest())
           instance = cls.__new__(cls)
           instance.transform_id = transform_id
           instance.diff_bytes = diff_bytes
           instance.files_changed = files_changed
           instance.provenance = provenance
           return instance
   ```

8. **`_build_transform(repo, plan)` (pure)** — reads `repo / "Dockerfile"` (pre) and `repo / "expected.Dockerfile"` (post — under the FakeJail scaffold; the real JVM-driven path replaces the file in place, but Phase 3 unit tests use the side-by-side fixture). Computes `diff_bytes = b"".join(difflib.unified_diff(pre_lines, post_lines, lineterm=""))` with **no** `fromfiledate` / `tofiledate` (determinism — AC-Det-2). Constructs `TransformProvenance` with sentinel ids per AC-Smart-2. Returns `DockerfileBaseImageTransform.create(...)`.

9. **AMEND** `tests/integration/test_recipe_engine_protocol.py` (S5-01 creates it) by adding `test_openrewrite_engine_satisfies_protocol` and `test_openrewrite_engine_apply_return_annotation` cases. Do NOT recreate the file.

10. **Phase-7-preview test** (`@pytest.mark.phase_7_preview`) at `tests/integration/test_openrewrite_engine_phase7_preview.py` — runs against the fixture under real bwrap + real `java`; skipped by default.

11. **Fence additions:**
    - Append `test_java_not_in_allowed_binaries_phase3` case to S1-05's existing `tests/fence/test_allowed_binaries_invariants.py` (NOT a new file).
    - New `tests/fence/test_openrewrite_not_invoked_phase3.py` — grep-asserts no import of `from codegenie.transforms.engines.openrewrite` outside `transforms/__init__.py` + the conformance test.
    - New `tests/fence/test_openrewrite_phase7_markers.py` — grep-asserts the `# TODO(Phase-7): widen capability union` marker is present in `openrewrite.py`.
    - Pure-helper AST-walk fence `tests/fence/test_engines_pure_helpers.py` — extend or create per AC-Pure-1.

12. **Re-export.** `src/codegenie/transforms/__init__.py` adds `"OpenRewriteRecipeEngine"` + `"DockerfileBaseImageTransform"` to `__all__`. `JvmEnv` re-exported from `transforms/sandbox_jail.py`'s existing `__all__`.

13. **`pyproject.toml`** — register `phase_7_preview` marker AND extend `addopts` `-m` to `"not bench and not phase_7_preview"` (AC-Phase7-2).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths: `tests/unit/transforms/test_openrewrite_engine.py`, `tests/unit/transforms/test_jailed_env_exhaustiveness.py`, `tests/unit/transforms/test_openrewrite_typing.py`, `tests/unit/transforms/test_openrewrite_mypy_negative.py`, `tests/integration/test_recipe_engine_protocol.py` (amend), `tests/integration/test_openrewrite_engine_phase7_preview.py`, `tests/fence/test_engines_pure_helpers.py`, `tests/fence/test_openrewrite_not_invoked_phase3.py`, `tests/fence/test_openrewrite_phase7_markers.py`.

```python
# tests/unit/transforms/test_openrewrite_engine.py
from __future__ import annotations
import inspect
from datetime import UTC, datetime
from typing import get_args

import pytest

from codegenie.transforms.engines.openrewrite import (
    OpenRewriteRecipeEngine,
    DockerfileBaseImageTransform,
    _OpenRewriteErrorId,
    _ERROR_IDS,
)
from codegenie.transforms.recipe_engine import RecipeEngine
from codegenie.transforms.outcomes import (
    Applied,
    RecipeError,
    RecipeFailed,
    ApplicationPlan,
)
from codegenie.transforms.transform import Transform
from codegenie.transforms.sandbox_jail import (
    Completed,
    DenyAll,
    DiskQuotaExceeded,
    JvmEnv,
    NetworkDenied,
    OomKilled,
    TimedOut,
)
from codegenie.types.identifiers import ErrorId


class FakeJail:
    """S4-01-shape spy. `result` is a JailedSubprocessResult variant or callable."""

    def __init__(self, result):
        self.result = result
        self.calls: list = []

    async def run(self, spec):
        self.calls.append(spec)
        return self.result(spec) if callable(self.result) else self.result


@pytest.fixture
def fake_jail() -> FakeJail:
    return FakeJail(Completed(kind="completed", exit_code=0, stdout_bytes=0,
                              stderr_bytes=0, wall_time_s=0.0))


@pytest.fixture
def dockerfile_plan() -> ApplicationPlan:
    # Phase-3 `ApplicationPlan` is `summary: str | None` only; Phase-7 widens.
    return ApplicationPlan(summary="dockerfile-base-image-swap")


@pytest.fixture
def frozen_clock(monkeypatch):
    fixed = datetime(2026, 5, 19, 0, 0, 0, tzinfo=UTC)
    import codegenie.transforms.engines.openrewrite as mod
    monkeypatch.setattr(mod, "_now_utc", lambda: fixed)
    return fixed


# --- Surface -----------------------------------------------------------------

def test_module_all_exact():
    """AC-Surface-1 — `__all__` is exactly the two public names."""
    import codegenie.transforms.engines.openrewrite as mod
    assert set(mod.__all__) == {"OpenRewriteRecipeEngine", "DockerfileBaseImageTransform"}


def test_engine_satisfies_recipe_engine_protocol_runtime(fake_jail):
    """AC-Surface-2(a) — @runtime_checkable Protocol structural match."""
    assert isinstance(OpenRewriteRecipeEngine(jail=fake_jail), RecipeEngine)


def test_engine_apply_signature_matches_npm(fake_jail):
    """AC-Surface-2(c) — both engines share the 2-tuple return contract."""
    from codegenie.transforms.engines.npm_lockfile import NpmLockfileRecipeEngine
    or_sig = inspect.signature(OpenRewriteRecipeEngine.apply)
    npm_sig = inspect.signature(NpmLockfileRecipeEngine.apply)
    assert str(or_sig.return_annotation) == str(npm_sig.return_annotation)
    assert list(or_sig.parameters.keys()) == ["self", "repo", "plan", "capability"]


# --- Error-id taxonomy -------------------------------------------------------

def test_error_ids_closed_set():
    """AC-Tax-1 — frozen 5-entry Literal; every member round-trips ErrorId."""
    assert len(_ERROR_IDS) == 5
    for e in get_args(_OpenRewriteErrorId):
        assert ErrorId(e) in _ERROR_IDS  # newtype-validates on construction


# --- Spec construction -------------------------------------------------------

@pytest.mark.asyncio
async def test_spec_cmd_exact_tuple(tmp_path, dockerfile_plan):
    """AC-Spec-1 — bit-identical cmd tuple including the recipe path."""
    jail = FakeJail(Completed(kind="completed", exit_code=0, stdout_bytes=0,
                              stderr_bytes=0, wall_time_s=0.0))
    await OpenRewriteRecipeEngine(jail=jail, cli_jar_path="/test/rewrite.jar").apply(
        tmp_path, dockerfile_plan, capability=...)
    expected = ("java", "-jar", "/test/rewrite.jar", "run", "--recipe",
                str(tmp_path / "recipe.yml"), "--in-place")
    assert jail.calls[0].cmd == expected


@pytest.mark.asyncio
async def test_spec_budget_envelope_exact(tmp_path, dockerfile_plan, fake_jail):
    """AC-Spec-2 — pinned budgets; mutation of any constant fails the AC."""
    await OpenRewriteRecipeEngine(jail=fake_jail).apply(tmp_path, dockerfile_plan, ...)
    spec = fake_jail.calls[0]
    assert spec.time_budget_s == 300.0
    assert spec.memory_mib == 2048
    assert spec.pids_max == 64


@pytest.mark.asyncio
async def test_spec_network_policy_is_deny_all(tmp_path, dockerfile_plan, fake_jail):
    """AC-Spec-3 — DenyAll discriminator; no allowlist constructed."""
    await OpenRewriteRecipeEngine(jail=fake_jail).apply(tmp_path, dockerfile_plan, ...)
    assert fake_jail.calls[0].network.kind == "deny_all"


@pytest.mark.asyncio
async def test_spec_env_is_jvm_typed(tmp_path, dockerfile_plan, fake_jail):
    """AC-Spec-4 — JvmEnv discriminator + per-field assertions."""
    await OpenRewriteRecipeEngine(jail=fake_jail).apply(tmp_path, dockerfile_plan, ...)
    env = fake_jail.calls[0].env
    assert env.kind == "jvm"
    assert env.java_home == "/opt/java"
    assert env.max_heap_mib == 1024
    assert isinstance(env, JvmEnv)


# --- Result mapping — exhaustive variant dispatch ----------------------------

@pytest.mark.asyncio
async def test_happy_path_returns_applied_tuple(tmp_path, dockerfile_plan, frozen_clock):
    """AC-Map-1 + AC-Contract-1 + AC-Smart-2."""
    jail = FakeJail(Completed(kind="completed", exit_code=0, stdout_bytes=0,
                              stderr_bytes=0, wall_time_s=0.0))
    # Seed fixture files so _build_transform can compute a real diff
    _seed_dockerfile_fixture(tmp_path)
    outcome, transform = await OpenRewriteRecipeEngine(jail=jail).apply(
        tmp_path, dockerfile_plan, ...)
    assert isinstance(outcome, Applied)
    assert isinstance(transform, DockerfileBaseImageTransform)
    assert outcome.transform_id == transform.transform_id  # identity-of-value
    assert transform.files_changed == (tmp_path / "Dockerfile",)
    assert isinstance(transform.files_changed, tuple)
    assert transform.diff_bytes  # non-empty


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result", "expected_id", "expected_details_keys"),
    [
        (Completed(kind="completed", exit_code=2, stdout_bytes=0,
                   stderr_bytes=42, wall_time_s=0.1),
         "recipe.openrewrite_nonzero_exit",
         {"exit_code", "stderr_bytes", "wall_time_s"}),
        (TimedOut(kind="timed_out", budget_s=300.0, elapsed_s=301.5),
         "recipe.jvm_timeout",
         {"budget_s", "elapsed_s"}),
        (OomKilled(kind="oom_killed", peak_rss_mib=2100),
         "recipe.jvm_oom",
         {"peak_rss_mib"}),
        (NetworkDenied(kind="network_denied", host="maven.example.com"),
         "recipe.network_policy_violation",
         {"host"}),
        (DiskQuotaExceeded(kind="disk_quota_exceeded",
                           quota_bytes=1024**3, bytes_written=1024**3 + 1),
         "recipe.disk_quota_exceeded",
         {"quota_bytes", "bytes_written"}),
    ],
)
async def test_failure_variant_mapping(
    tmp_path, dockerfile_plan, result, expected_id, expected_details_keys,
):
    """AC-Map-2..6 — every JailedSubprocessResult non-Completed-0 variant
    maps to a specific RecipeFailed.error_id with the expected details keys."""
    jail = FakeJail(result)
    outcome, transform = await OpenRewriteRecipeEngine(jail=jail).apply(
        tmp_path, dockerfile_plan, ...)
    assert isinstance(outcome, RecipeFailed)
    assert isinstance(outcome.error, RecipeError)
    assert outcome.error.error_id == ErrorId(expected_id)
    assert outcome.error.details is not None
    assert set(outcome.error.details.keys()) == expected_details_keys
    assert transform is None  # AC-Contract-2 — non-Applied → None


# --- Determinism -------------------------------------------------------------

@pytest.mark.asyncio
async def test_diff_bytes_byte_identical_across_runs(
    tmp_path, dockerfile_plan, frozen_clock,
):
    """AC-Det-1 — 10 runs against same fixture produce byte-identical diff/id."""
    _seed_dockerfile_fixture(tmp_path)
    seen_diffs: set[bytes] = set()
    seen_ids: set[str] = set()
    for _ in range(10):
        jail = FakeJail(Completed(kind="completed", exit_code=0, stdout_bytes=0,
                                  stderr_bytes=0, wall_time_s=0.0))
        _, t = await OpenRewriteRecipeEngine(jail=jail).apply(
            tmp_path, dockerfile_plan, ...)
        seen_diffs.add(t.diff_bytes)
        seen_ids.add(t.transform_id)
    assert len(seen_diffs) == 1
    assert len(seen_ids) == 1


def test_unified_diff_no_timestamp_arguments():
    """AC-Det-2 — AST-walk confirms `difflib.unified_diff` calls do NOT
    pass `fromfiledate=` or `tofiledate=` (which would inject timestamps)."""
    import ast
    src = (open("src/codegenie/transforms/engines/openrewrite.py").read())
    for node in ast.walk(ast.parse(src)):
        if (isinstance(node, ast.Call)
                and getattr(node.func, "attr", None) == "unified_diff"):
            kwarg_names = {kw.arg for kw in node.keywords}
            assert "fromfiledate" not in kwarg_names
            assert "tofiledate" not in kwarg_names


# --- Smart-constructor invariants --------------------------------------------

def test_smart_constructor_rejects_empty_diff_bytes():
    """AC-Smart-1 — empty diff is invalid."""
    with pytest.raises(ValueError, match="diff_bytes must be non-empty"):
        DockerfileBaseImageTransform.create(
            diff_bytes=b"",
            files_changed=(_path_stub(),),
            provenance=_provenance_stub(),
        )


def test_smart_constructor_rejects_empty_files_changed():
    """AC-Smart-1 — empty files_changed is invalid."""
    with pytest.raises(ValueError, match="files_changed must be non-empty"):
        DockerfileBaseImageTransform.create(
            diff_bytes=b"+1\n",
            files_changed=(),
            provenance=_provenance_stub(),
        )


def test_smart_constructor_transform_id_is_blake3_of_diff():
    """AC-Smart-1 — transform_id == BLAKE3(diff_bytes)."""
    import blake3
    db = b"+FROM cgr.dev/chainguard/node:latest\n-FROM node:20-alpine\n"
    t = DockerfileBaseImageTransform.create(
        diff_bytes=db, files_changed=(_path_stub(),), provenance=_provenance_stub(),
    )
    assert t.transform_id == blake3.blake3(db).hexdigest()


# Helpers used by the tests above (defined in test module or conftest)
def _seed_dockerfile_fixture(tmp_path): ...
def _path_stub(): ...
def _provenance_stub(): ...
```

```python
# tests/unit/transforms/test_jailed_env_exhaustiveness.py
# AC-Env-2 — mypy --strict accepts an exhaustive match over JailedEnv.
# (The file body is a tiny module with an assert_never match arm.)
from typing import assert_never
from codegenie.transforms.sandbox_jail import NpmEnv, GitEnv, JvmEnv, JailedEnv

def render(env: JailedEnv) -> str:
    match env:
        case NpmEnv():
            return "npm"
        case GitEnv():
            return "git"
        case JvmEnv():
            return "jvm"
        case _:
            assert_never(env)
```

```python
# tests/unit/transforms/test_openrewrite_mypy_negative.py
# AC-Map-7 — spawns mypy --strict on a temp file omitting one match arm
# of JailedSubprocessResult and asserts non-zero exit with `assert_never`.
import subprocess, sys, tempfile, textwrap

_OMIT_TIMEOUT_BODY = textwrap.dedent('''
    from typing import assert_never
    from codegenie.transforms.sandbox_jail import (
        Completed, OomKilled, NetworkDenied, DiskQuotaExceeded, JailedSubprocessResult,
    )
    def m(r: JailedSubprocessResult) -> str:
        match r:
            case Completed(): return "c"
            case OomKilled(): return "o"      # missing TimedOut on purpose
            case NetworkDenied(): return "n"
            case DiskQuotaExceeded(): return "d"
            case _: assert_never(r)
''')

def test_mypy_strict_rejects_missing_timed_out_arm(tmp_path):
    f = tmp_path / "_neg.py"; f.write_text(_OMIT_TIMEOUT_BODY)
    p = subprocess.run([sys.executable, "-m", "mypy", "--strict", str(f)],
                       capture_output=True, text=True)
    assert p.returncode != 0
    assert "assert_never" in (p.stdout + p.stderr)
```

```python
# tests/integration/test_recipe_engine_protocol.py  (AMEND — S5-01 created it)
# Existing S5-01 cases preserved. New cases below.
def test_openrewrite_engine_satisfies_protocol(fake_jail):
    from codegenie.transforms.engines.openrewrite import OpenRewriteRecipeEngine
    from codegenie.transforms.recipe_engine import RecipeEngine
    assert isinstance(OpenRewriteRecipeEngine(jail=fake_jail), RecipeEngine)


def test_openrewrite_engine_apply_return_annotation():
    """AC-Conf-1 + AC-Contract-1 — return annotation is the 2-tuple shape."""
    import inspect
    from codegenie.transforms.engines.openrewrite import OpenRewriteRecipeEngine
    sig = inspect.signature(OpenRewriteRecipeEngine.apply)
    assert "tuple[RecipeOutcome, Transform" in str(sig.return_annotation)
```

```python
# tests/integration/test_openrewrite_engine_phase7_preview.py  (AC-Phase7-1)
import shutil, pytest
from pathlib import Path

@pytest.mark.phase_7_preview
@pytest.mark.skipif(shutil.which("java") is None, reason="requires java")
@pytest.mark.asyncio
async def test_dockerfile_base_image_swap_under_real_jvm(tmp_path):
    """Under real bwrap + real JVM: outcome is Applied; diff_bytes byte-equals golden."""
    fixture = Path("tests/fixtures/openrewrite/dockerfile-base-image-swap")
    # Copy fixture into tmp_path; instantiate BwrapAdapter; construct engine;
    # call apply; assert (Applied, DockerfileBaseImageTransform) tuple;
    # assert transform.diff_bytes == (fixture / "expected.diff").read_bytes().
    ...
```

```python
# tests/fence/test_openrewrite_not_invoked_phase3.py  (AC-Tool-4)
import subprocess
def test_openrewrite_engine_not_imported_from_npm_workflows():
    result = subprocess.run(
        ["git", "grep", "-l", "from codegenie.transforms.engines.openrewrite",
         "src/codegenie/", "plugins/"],
        capture_output=True, text=True,
    )
    files = [f for f in result.stdout.splitlines()
             if not f.endswith("transforms/__init__.py")]
    assert files == [], f"Phase-3 invocation leak: {files}"
```

```python
# tests/fence/test_openrewrite_phase7_markers.py  (AC-CI-3)
def test_capability_widening_todo_present():
    src = open("src/codegenie/transforms/engines/openrewrite.py").read()
    assert "TODO(Phase-7): widen capability union" in src, (
        "Phase-3 marker must be present until Phase 7 widens RecipeEngine.apply "
        "to accept a capability sum. Deleting this marker without the Phase-7 "
        "ADR amendment is a contract break.")
```

Run; confirm `ImportError` (the engine module doesn't exist yet); commit; implement.

### Green — make it pass

- Land Outline §1 (`JvmEnv` additive widening of `JailedEnv` in `sandbox_jail.py`) **first** — every subsequent test that references `JvmEnv` will `ImportError` until it lands. Add the ADR-0006 amendment block in the same PR.
- Implement `openrewrite.py` per Outline §§2-8. `apply` body is exactly the three statements pinned by AC-Pure-1.
- Amend `tests/integration/test_recipe_engine_protocol.py` additively per AC-Conf-1.
- Register the `phase_7_preview` marker AND extend `addopts -m` to `"not bench and not phase_7_preview"` in `pyproject.toml`. Verify `make test` excludes the phase-7 test by collection (`pytest --collect-only` should show 0 phase-7 tests under default `addopts`).
- Append `test_java_not_in_allowed_binaries_phase3` to S1-05's existing `tests/fence/test_allowed_binaries_invariants.py`.
- Create the three fence files (pure-helpers, not-invoked-phase3, phase7-markers) per Outline §11.

### Refactor — clean up

- Confirm the scaffold is **structurally complete but functionally inert** — `apply` builds the spec, awaits the jail, and maps the result. It does NOT parse OpenRewrite's stdout into structured results (that's Phase 7's job). Document this in the engine docstring with a `Phase 7 will extend by:` block.
- Cross-check `../phase-arch-design.md §C12` — every commitment ("Protocol-conformant", "JVM-subprocess wrapped in SubprocessJail", "one fixture", "Phase-7-tagged test", "not invoked by Phase 3 npm workflows", "2-tuple return contract matching `NpmLockfileRecipeEngine`") has a matching AC. If a criterion is missing, add it before merging.
- Verify the conformance test (`test_recipe_engine_protocol.py`) remains **unmarked** `phase_7_preview` — it runs every PR. The Protocol-satisfaction check is pure structural typing; no JVM needed.
- Confirm `_build_openrewrite_spec` and `_map_jail_result` carry **all** logic (the AST-walk fence catches `await` / `os.*` / `time.*` leaks). `apply()` is the only impure surface.
- Confirm no raw `str` in public signatures (`PluginId`, `RecipeId`, `TransformKind`, `ErrorId`, `TransformId` are the typed currencies).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/engines/openrewrite.py` | **New** — `OpenRewriteRecipeEngine`, `DockerfileBaseImageTransform` (+ smart constructor), `_build_openrewrite_spec` / `_map_jail_result` pure helpers, `_OpenRewriteErrorId` closed Literal |
| `src/codegenie/transforms/sandbox_jail.py` | **Amend additively** — add `JvmEnv` (Pydantic frozen, `kind="jvm"`); widen `JailedEnv = NpmEnv \| GitEnv \| JvmEnv`. Pre-existing surface preserved byte-identical |
| `src/codegenie/transforms/__init__.py` | Add `"OpenRewriteRecipeEngine"`, `"DockerfileBaseImageTransform"` to `__all__` |
| `tests/unit/transforms/test_openrewrite_engine.py` | **New** — surface, error-id taxonomy, spec construction, exhaustive variant mapping, smart-constructor invariants, determinism |
| `tests/unit/transforms/test_jailed_env_exhaustiveness.py` | **New** — `assert_never` over `NpmEnv \| GitEnv \| JvmEnv` (mypy-strict positive fence) |
| `tests/unit/transforms/test_openrewrite_typing.py` | **New** — mypy-strict positive fence: `_engine: RecipeEngine = OpenRewriteRecipeEngine(jail=...)` type-checks |
| `tests/unit/transforms/test_openrewrite_mypy_negative.py` | **New** — mypy-strict NEGATIVE fence: omitting a `JailedSubprocessResult` arm fails with `assert_never` diagnostic |
| `tests/integration/test_recipe_engine_protocol.py` | **Amend** — S5-01 created it; this story adds `test_openrewrite_engine_satisfies_protocol` + `test_openrewrite_engine_apply_return_annotation` cases. Pre-existing S5-01 cases preserved |
| `tests/integration/test_openrewrite_engine_phase7_preview.py` | **New** — `@pytest.mark.phase_7_preview` real-JVM end-to-end test (skipped in Phase 3 CI) |
| `tests/fence/test_allowed_binaries_invariants.py` | **Amend** — append `test_java_not_in_allowed_binaries_phase3` case (S1-05's existing suite — Rule 7: one location). Phase 7 deletes the case |
| `tests/fence/test_engines_pure_helpers.py` | **New** — AST-walk fence rejecting `await` / `os.*` / `time.*` / `subprocess` / `logging` / raw `open(` inside `_build_openrewrite_spec` and `_map_jail_result`; asserts `apply` body is exactly the three statements |
| `tests/fence/test_openrewrite_not_invoked_phase3.py` | **New** — grep-asserts no Phase-3 import of `from codegenie.transforms.engines.openrewrite` outside `transforms/__init__.py` and conformance test |
| `tests/fence/test_openrewrite_phase7_markers.py` | **New** — grep-asserts the `# TODO(Phase-7): widen capability union` marker is present |
| `tests/fixtures/openrewrite/dockerfile-base-image-swap/Dockerfile` | **New** — `FROM node:20-alpine` baseline |
| `tests/fixtures/openrewrite/dockerfile-base-image-swap/expected.Dockerfile` | **New** — `FROM cgr.dev/chainguard/node:latest` target |
| `tests/fixtures/openrewrite/dockerfile-base-image-swap/expected.diff` | **New** — golden diff (no timestamps) |
| `tests/fixtures/openrewrite/dockerfile-base-image-swap/recipe.yml` | **New** — placeholder recipe (Phase 7 owns content) |
| `tests/fixtures/openrewrite/dockerfile-base-image-swap/README.md` | **New** — one-paragraph fixture purpose + Phase-7 owner note |
| `pyproject.toml` | Register `phase_7_preview` marker AND extend `addopts -m` to `"not bench and not phase_7_preview"` |
| `docs/phases/03-vuln-deterministic-recipe/ADRs/0006-hexagonal-subprocessjail-port-bwrap-sandbox-exec.md` | **Amend** — 2026-05-19 Amendment block: `JvmEnv` added to `JailedEnv` discriminated sum (additive widening) |

## Out of scope

- **Actual OpenRewrite Dockerfile-rewrite recipe content** — Phase 7. The fixture's `recipe.yml` is a placeholder that the JVM CLI will accept syntactically; meaningful rewrites are Phase 7's job.
- **Adding `java` to `ALLOWED_BINARIES`** — Phase 7 (this story explicitly forbids it via a fence case in S1-05's `tests/fence/test_allowed_binaries_invariants.py`).
- **Widening `RecipeEngine.apply` `capability` parameter** from `NpmInstallCapability` to a union (`NpmInstallCapability | DockerRewriteCapability | …`) — Phase-7 ADR amendment. S5-03's scaffold receives the Phase-3-narrow `NpmInstallCapability` parameter and threads it semantically *unchanged*; the `# TODO(Phase-7)` marker (AC-CI-3) pins the deferred work. Editing S5-01's Protocol now is an edit-not-addition.
- **Phase 7's distroless plugin** registration / subgraph / TCCM — Phase 7.
- **OpenRewrite stdout-parsing** of structured recipe-application results — Phase 7.
- **Multi-Dockerfile or multi-stage Dockerfile** support — Phase 7 (the fixture is a single, single-stage Dockerfile).
- **Maven / Gradle / other JVM-ecosystem recipes** — Phase 8+.
- **JVM SecurityManager / JEP-411 compatibility** — explicitly rejected (critic Security Issue 4); `SubprocessJail` is the only boundary.
- **`RecipeEngine` registry seam** (`@register_recipe_engine`) — explicitly deferred per Notes §"Engine registry". Phase-7 distroless plugin adding a third engine is **the trigger**; until then, two hard-coded re-exports under `transforms/__init__.py` are the mechanism.
- **`ApplicationPlan` widening for Dockerfile-base-image fields** (`dockerfile_path`, `target_image_ref`) — Phase 7. S5-03 reads only `plan.summary`.
- **`NetworkPolicy.DenyAll` introduction** — assumed pre-existing in S4-01 as a variant of the `NetworkPolicy` discriminated sum. If not yet shipped, surface via an S4-01 amendment, not in S5-03.
- **Hypothesis property-based testing on `diff_bytes`** — the fixture is fixed, so a 10-run vanilla loop is sufficient and avoids the Hypothesis dependency in the scaffold path.

## Notes for the implementer

### §1 — The scaffold's value is structural, not functional

It proves the `RecipeEngine` Protocol accommodates a wildly-different implementation (JVM subprocess vs. pure-Python npm parser) without contract distortion. If you find yourself adding a Protocol method to make OpenRewrite "fit," stop — the Protocol shape is the contract Phase 7 inherits; distortion now is distortion forever (S6-06 snapshot pins it).

### §2 — Mirror S5-02's hardened shape literally

S5-02 (HARDENED) is the *production* day-1 engine and S5-03 is the *scaffolded* day-1 engine. They must be **structurally indistinguishable** under the Protocol surface: identical `apply` return annotation (`tuple[RecipeOutcome, Transform | None]`); identical `_build_*_spec` / `_map_jail_result` separation; identical closed-Literal error-id taxonomy at module top; identical AST-walk fence on pure helpers; identical mypy-strict negative fence on missing match arms. Read `S5-02-npm-lockfile-recipe-engine.md` and its `_validation/S5-02-…md` companion before writing.

### §3 — Capability mismatch (Phase-7 amendment trigger)

S5-01's `RecipeEngine.apply` signature is `capability: NpmInstallCapability` (Phase-3 narrow). OpenRewrite is not npm. The scaffold accepts the parameter, threads it semantically unchanged into the (unused-in-Phase-3) `TransformProvenance.capability_use_id`, and pins a `# TODO(Phase-7): widen capability union` marker at the signature site. Phase 7's first PR widens S5-01's Protocol to `capability: NpmInstallCapability | DockerRewriteCapability` (or a `RecipeEngineCapability` Protocol) — that's a Phase-7 ADR amendment, NOT S5-03 scope. Do not "fix" it now; you'd be editing a Phase-3 contract.

### §4 — Why `JvmEnv` widens `JailedEnv` rather than living in `openrewrite.py`

ADR-0010 + ADR-0006: typed env, never raw `dict`; the env discriminator lives in the S4-01 sum. Phase 7 inherits the typed surface. If you skip the typed env now and Phase 7 retrofits one, that's an edit-not-addition (violates the "zero edits" exit criterion). The widening is **additive** — pre-existing `NpmEnv` / `GitEnv` shapes are byte-identical preserved.

### §5 — Engine registry (deferred decision)

Phase 3 ships two `RecipeEngine` instances re-exported from `transforms/__init__.py`. A registry seam (`@register_recipe_engine(EngineId)` analogous to S2-01's `@register_plugin` / S5-01's `@register_recipe`) would let Phase 7's distroless plugin add a third engine by addition. The decision is **explicitly deferred**:

- **Today (Phase 3):** Two engines; hard-coded re-exports. Adding a third requires editing `transforms/__init__.py` — a single-line edit that's audit-traceable.
- **Trigger to extract:** Phase 7 adds the third engine. At that point: extract `@register_recipe_engine` decorator + `RecipeEngineRegistry` mirroring S5-01's `RecipeRegistry`. Until then, Rule 2 (simplicity first) wins.
- **Cross-reference:** S5-01's `RecipeRegistry` is per-plugin (matchers); a future `RecipeEngineRegistry` would be per-engine (workers). They're complementary, not duplicative.

Surface this paragraph in the PR description.

### §6 — `@pytest.mark.phase_7_preview` lifecycle

Registered here; collected by `pytest -m phase_7_preview` so reviewers can see what's deferred; excluded by `make test`'s default via `addopts -m "not bench and not phase_7_preview"`. Phase 7's first PR:
- Adds `java` to `ALLOWED_BINARIES` (its own ADR amendment to ADR-0012).
- Deletes the `test_java_not_in_allowed_binaries_phase3` case from `tests/fence/test_allowed_binaries_invariants.py`.
- Deletes the `# TODO(Phase-7): widen capability union` marker + `tests/fence/test_openrewrite_phase7_markers.py`.
- Widens `RecipeEngine.apply` `capability` parameter.
- Decides whether to extract the engine registry (§5).
- Either deletes `not phase_7_preview` from `addopts -m` (graduate the suite) or extends to `not phase_7_preview and not phase_8_preview` if a new generation lands.

Document this lifecycle in the marker's description string.

### §7 — Network policy `DenyAll` is not a guess

OpenRewrite recipes for Dockerfile rewrites operate on local files; the recipe YAML is checked in; the JVM doesn't need to fetch from Maven Central at runtime (the CLI jar is provisioned on-disk by Phase 7's distroless plugin TCCM). If Phase 7 needs Maven access for a recipe that pulls AST grammars, that's a per-plugin override at the spec construction site, not a default loosening here.

### §8 — CLI-jar provisioning

The default `_OPENREWRITE_CLI_JAR = "/opt/openrewrite/rewrite-cli.jar"` is intentionally a Phase-7-provisioned location. Phase 3 unit tests inject a stub path via `cli_jar_path=` kwarg (no actual jar fetched). The phase-7-preview test downloads/caches the jar under `tests/fixtures/openrewrite/_cli.jar` once when the marker is enabled and `shutil.which("java")` is non-None. Document as "overridable; production path TBD by Phase 7 distroless plugin TCCM" in the engine docstring.

### §9 — `DockerfileBaseImageTransform` is the second concrete `Transform` subclass

The first is `NpmLockfileTransform` (S5-02). The `Transform` ABC (S1-04) has a sealed hierarchy by convention — every subclass lives under `src/codegenie/transforms/` or `plugins/*/recipes/`. Document this subclass at its definition with a one-liner: *"Phase-7-preview. Provenance carries OpenRewrite recipe id."* Use the smart constructor (`DockerfileBaseImageTransform.create(...)`) — direct `__init__` is permitted by the Transform-ABC class-attribute pattern but discouraged here so invariants (BLAKE3 = `transform_id`, non-empty `diff_bytes`, non-empty `files_changed`) are centralised.

### §10 — Coverage carve-out, NOT a per-file threshold

Per Coverage A9 (validator) and AC-Tool-3: use `# pragma: no cover  # Phase-7-only` markers on the JVM-stdout post-processing path. Do NOT introduce a per-file coverage threshold (`[tool.coverage.report]` doesn't support per-file thresholds natively, and adding a custom one is over-engineering). The pragma is auditable + the `phase_7_preview` test exercises the marked path under opt-in collection.

### §11 — Don't ship JVM code yet

No Java sources, no `pom.xml`, no Maven config in the codebase. The scaffold is Python-only — the JVM is an *external dependency invoked via `SubprocessJail`*. If you find yourself adding `.java` files, you've gone past the scaffold's scope. The fixture's `recipe.yml` is the only YAML; the JVM consumes it via `--recipe`.

### §12 — Determinism is non-negotiable

`difflib.unified_diff` MUST be called without `fromfiledate` / `tofiledate` arguments (which would inject timestamps). `TransformProvenance.applied_at` is wall-clock; tests pin it via a frozen-clock fixture (`_now_utc` is the module-local seam). Without these, `transform_id` (BLAKE3 of `diff_bytes`) drifts across runs and the determinism contract from G4 breaks silently.

### §13 — ADR amendments triggered

- **ADR-0006** (Phase 3) — 2026-05-19 Amendment block listing the additive `JvmEnv` widening of `JailedEnv` + the `kind="jvm"` discriminator value.
- **ADR-0012** (Phase 3) — NOT amended (still excludes `java`); a Phase-7 PR amends it.
- **ADR-0001** (Phase 5 contract snapshot) — NOT re-baked; `JailedEnv` is internal to `transforms/`; Phase 5 reads `RecipeOutcome`, which is unchanged.

### §14 — Deliberately not adopted (YAGNI applications)

- **`OpenRewriteRecipeEngine` registry seam** — see §5.
- **Hypothesis property-based determinism** — fixture is fixed; vanilla 10-run loop is sufficient.
- **Per-file coverage threshold** — pragma is cleaner; see §10.
- **`SemverVersion` newtype for `_OPENREWRITE_CLI_JAR`** — Phase 7's CliJarPath newtype is a Phase-7 task.
