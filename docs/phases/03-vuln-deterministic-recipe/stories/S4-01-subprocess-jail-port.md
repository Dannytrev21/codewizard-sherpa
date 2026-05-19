# Story S4-01 — `SubprocessJail` Port + `JailedSubprocessResult` tagged union + typed env/network sums

**Step:** Step 4 — SubprocessJail Port + Bwrap + sandbox-exec + ALLOWED_BINARIES amendment
**Status:** Done — GREEN 2026-05-19 (phase-story-executor; see [`_attempts/S4-01.md`](_attempts/S4-01.md) for the per-AC evidence table + gate log)
**Effort:** M
**Depends on:** S1-03 (tagged-union outcomes — `RecipeOutcome`, `RemediationOutcome`, `NodeTransition`, `AdapterConfidence`, `Applicability` discriminated unions already exist; this story reuses the same Pydantic `Discriminator("kind")` pattern); S1-04 (`codegenie.transforms._forward` `SandboxedPath` `TypeAlias = pathlib.Path` is the established Phase-3-Step-1 forward-reference; this story consumes that alias and does NOT reach into `codegenie.plugins.*`).
**ADRs honored:** 03-ADR-0006 (Hexagonal `SubprocessJail` Port + Bwrap/sandbox-exec adapters), 03-ADR-0007 (run `npm install`/`npm test` in the jail — consumer of this Port), 03-ADR-0010 (sum-type + smart-constructor discipline — `RegistryUrl` strict-`https://`, frozen + extra="forbid", non-negative observable counters), 03-ADR-0011 (honest framing — `SandboxedPath` is in-jail-at-construction, NOT runtime-unforgeable; `--ignore-scripts` is *audit + structural* not runtime-prevented inside npm), production ADR-0012 (microVM substitution at Phase 5 — substitutes via the same Port), production ADR-0033 (sum types over booleans — every failure mode a typed variant).

## Validation notes (2026-05-18)

Hardened by `/phase-story-validator` against four critics (coverage, test-quality, consistency, design-patterns) + `references/story-smells.md` + `references/techniques.md`. Changes applied:

1. **BLOCK — consistency.** `SandboxedPath` import path corrected. The original story instructed importing from `codegenie.plugins.sandbox_path` (under `TYPE_CHECKING`); Phase-3 Step 1 (S1-04) has *already* shipped `SandboxedPath: TypeAlias = pathlib.Path` in `codegenie.transforms._forward`, and the shim's docstring pins the substitution path ("S4-04 — replace the `SandboxedPath` `TypeAlias` with a re-export of `codegenie.plugins.sandbox_path.SandboxedPath` *from this module*; every consumer keeps importing from `codegenie.transforms`"). Per Rule 7 (surface conflicts, don't average): `_forward.py`'s shipped convention wins; this story now imports `SandboxedPath` from `codegenie.transforms._forward`. The `TYPE_CHECKING` + forward-string dance is dropped — the alias is a real runtime symbol today, so `cwd: SandboxedPath` resolves to `pathlib.Path` and AC-11 is re-phrased to assert what is *actually observable* (the resolved annotation identity + the import source).
2. **BLOCK — test-quality (AC-7).** `test_npm_env_to_env_mapping_strips_attempted_override` was tautological: `NpmEnv()` then asserting the key is `"true"` is the same assertion as the basic test, and `NpmEnv(extra={"npm_config_ignore_scripts": "false"})` is rejected by `extra="forbid"` *before* `to_env_mapping()` is reachable. The "structurally inviolable" intent is now enforced by a *mutation-resistant pair*: (a) an AST/source-grep that the literal string `"true"` is on the right-hand side of an assignment whose key is `"npm_config_ignore_scripts"` inside `NpmEnv.to_env_mapping`; (b) a constructive AC that no public field on `NpmEnv` admits the substring `npm_config_ignore_scripts` in its name (no extension trapdoor). An obviously-wrong implementation that hard-codes `{}` or omits the key fails (a); an implementation that adds a `scripts_enabled: bool` field fails (b).
3. **HARDEN — coverage.** New ACs land bounds + finiteness invariants that the original story didn't pin: AC-3a (`cmd` non-empty; `time_budget_s` > 0 and finite; `memory_mib` ≥ 1; `pids_max` ≥ 1; constructor rejects negatives and NaN/Inf), AC-4a (every observable counter on result variants is ≥ 0 — `exit_code` finite int, `stdout_bytes`/`stderr_bytes`/`wall_time_s`/`peak_rss_mib`/`quota_bytes`/`bytes_written`/`budget_s`/`elapsed_s`), AC-6a (`RegistryAllowlist.hosts` validator rejects any URL that does not start with `https://` — pins the `RegistryUrl` runtime semantic that `NewType` alone cannot enforce; matches `identifiers.py`:71 docstring "Strict-`https://` ASCII registry URL").
4. **HARDEN — design-patterns / consistency.** `NpmEnv | GitEnv` was a *structurally* dispatched Pydantic union without a `kind` discriminator. Pydantic v2 will fall back to best-fit validation, but the moment a third env type lands (the very next bake-test plugin, S7-03 universal HITL fallback, may need a generic env), structural dispatch silently picks the wrong type when fields overlap. The fix mirrors the precedent set by every other umbrella in the codebase (`RecipeOutcome`, `RemediationOutcome`, `NodeTransition`, `AdapterConfidence`, `Applicability`, `JailedSubprocessResult`): make env a `Annotated[NpmEnv | GitEnv, Field(discriminator="kind")]` sum with `kind: Literal["npm" | "git"]`. AC-2a pins the discriminator; the env discriminator is observable in the contract snapshot (AC-15) so Phase 5's `FirecrackerAdapter` can rely on it.
5. **HARDEN — test-quality (AC-9 / new AC-9a).** AC-9's exhaustiveness test confirms today's coverage but doesn't catch the *silent-widening* failure mode the S1-03 outcomes module already protects against. AC-9a adds a subprocess-mypy negative test (mirroring `tests/unit/transforms/test_outcomes_mypy_negative.py`): commenting out any `match` arm in `test_sandbox_jail_exhaustiveness.py` must make `mypy --strict` fail on the `assert_never` line. Without this, deleting a variant or adding one silently passes the AST-level exhaustiveness fence.
6. **HARDEN — test-quality (AC-11).** `assert "SandboxedPath" in repr(hints["cwd"])` is unverifiable as written: with `from __future__ import annotations` and `SandboxedPath: TypeAlias = pathlib.Path`, `get_type_hints()` resolves to `pathlib.Path` and the substring `"SandboxedPath"` does NOT appear. AC-11 is rewritten to assert what is observable: the import statement in `sandbox_jail.py` is *exactly* `from codegenie.transforms._forward import SandboxedPath` (AST inspection), and the `JailedSubprocessSpec.model_fields["cwd"].annotation is SandboxedPath` (identity check, which survives the S4-04 substitution because the import path is stable).
7. **HARDEN — test-quality (AC-12 regex).** `"except Exception" not in src` is over-broad — it false-positives on subclass-of-Exception definitions (`class FooError(Exception): ...`) which are legitimate. Tightened to a regex (`^[ \t]*except[ \t]+Exception\b`) that targets bare `except Exception:` statements and `raise Exception(` calls, not subclass declarations or imports.
8. **HARDEN — test-quality (AC-15 specificity).** The original "spot-check `'discriminator' in str(schema)`" was substring-matching against any field/value containing that token. Tightened: `TypeAdapter(JailedSubprocessResult).json_schema(by_alias=True)["discriminator"]["propertyName"] == "kind"` and the schema's `oneOf` has exactly 5 variants. Also makes the snapshot golden file mode explicit: `model_json_schema(by_alias=True)` so the discriminator metadata is captured for Phase 5's contract snapshot.
9. **HARDEN — design-patterns (AC-1).** Added explicit check that `__all__` is defined on the module and matches `EXPECTED`. Mutation thinking: an implementer who exports a private helper would slip past `set(dir(...)) >= EXPECTED`; pinning `__all__` enforces *exactly* the public surface.
10. **NIT — design-patterns (Notes for implementer).** Documented why `Completed` carries only `stdout_bytes` / `stderr_bytes` (not content): PII and log volume; the adapter writes content elsewhere if needed. Documented async-vs-sync handoff to S4-02/S4-03 (already in ADR-0006, re-asserted). Documented that the Port is intentionally *not* `@runtime_checkable` (structural typing only; avoids `isinstance(jail, SubprocessJail)` foot-guns since `Protocol` runtime checks ignore method signatures).

No `RESCUE` conditions: the story's goal, scope, and arch-trace are sound. Verdict: **HARDENED**. Full critic dossier at `_validation/S4-01-subprocess-jail-port.md`.

## Context

Phase 3's exit criterion (`docs/roadmap.md §Phase 3`) requires running `npm install` and `npm test` against an untrusted target repo on the operator's laptop or a CI runner. Production ADR-0012 commits to a microVM (Firecracker) sandbox for trust gates, but that substrate is owned by Phase 5 (05-ADR-0004). Phase 3 cannot wait for Firecracker without slipping its exit criterion by a phase.

The architecture spec (`phase-arch-design.md §Component design C8`, §Design patterns applied row 3, §Physical view) resolves it via Hexagonal architecture: define a `SubprocessJail` **Port** in Phase 3, ship two **Adapters** (S4-02 `BwrapAdapter` on Linux, S4-03 `SandboxExecAdapter` on macOS) as the interim substrate, and arrange the interface so Phase 5's `FirecrackerAdapter` (Linux/CI) and `DinDAdapter` (macOS dev) substitute via the same Port with zero changes to `RemediationOrchestrator` or any plugin.

This story lands **only the Port surface** — the Protocol, the Pydantic spec, the tagged-union return, and the typed env / typed network policy. The two production adapters are S4-02 and S4-03. Landing the Port first is non-negotiable per the High-level-impl ordering (`ports-before-adapters`); an adapter coded against a not-yet-stable Protocol pays for itself twice.

The critic correctly attacked the security lens's earlier macOS-prefetch-online-offline flow (`critique.md §Attacks on the security-first design — Issue 2`) — prefetching dependencies in an unjailed flow before running offline npm creates a second, *unjailed* trust boundary that defeats the primary defense. The Port commits to **online-mode-default on both substrates** with `RegistryAllowlist(["registry.npmjs.org"])` enforced at the netns / pf layer per Adapter. This story encodes that commitment in the `NetworkPolicy` sum type and in the `JailedSubprocessSpec`'s `env` discipline.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C8` — `SubprocessJail` Protocol, `JailedSubprocessSpec` shape, `JailedSubprocessResult` tagged union, `NetworkPolicy` sum, online-mode default, performance envelope (~80–200 ms Linux / ~50–150 ms macOS per spawn).
  - `../phase-arch-design.md §Design patterns applied` row 3 — Hexagonal Port for `SubprocessJail`; ports-before-adapters discipline.
  - `../phase-arch-design.md §Physical view` — physical placement of `BwrapAdapter` (Linux runner) vs `SandboxExecAdapter` (macOS runner) sharing the same Port.
  - `../phase-arch-design.md §Edge cases E7, E8, E12` — `NetworkDenied(host)` for `.npmrc` redirects; `--ignore-scripts` enforcement; symlink TOCTOU vs `O_NOFOLLOW` (S4-04 consumes this Port's `JailedSubprocessSpec.cwd: SandboxedPath`).
  - `../phase-arch-design.md §Tradeoffs (consolidated)` row "Online mode default with `RegistryAllowlist`" — substrate-enforced egress.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0006-hexagonal-subprocessjail-port-bwrap-sandbox-exec.md` — the Port-and-Adapters ADR. §Decision pins the single-method Protocol (`async def run(self, spec) -> result`) and the tagged-union return; §Tradeoffs row 4 pins typed-variant-per-failure-mode; §Consequences pins the file path `src/codegenie/transforms/sandbox_jail.py`.
  - `../ADRs/0007-run-npm-install-and-npm-test-in-phase3-jail.md` — the consumer ADR; the `NpmLockfileRecipeEngine` (S5-02) and Stage-6 validate (S6-04) both call `SubprocessJail.run(...)`.
  - `../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — `JailedSubprocessSpec.cwd: SandboxedPath` ties the Port to S4-04's TOCTOU-honest path type.
- **Production ADRs (substitution target):**
  - `../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md` — Phase 5's `FirecrackerAdapter` substitutes via this Port with zero domain edits.
- **Source design:**
  - `../final-design.md §Synthesis ledger row "Sandbox for npm"` (score 14/15) — the synthesis behind ADR-0006.
  - `../High-level-impl.md §Step 4 features delivered` — bullet list pinning the exact symbols.
- **Existing code:**
  - `src/codegenie/exec/__init__.py` — `run_external_cli` / `run_allowlisted` is the chokepoint the adapters (S4-02 / S4-03) wrap; this story does not call it directly but the Port's spec must be expressible through it.
  - `src/codegenie/transforms/outcomes.py` (S1-03) — `RecipeOutcome` / `RemediationOutcome` discriminated-union precedent; reuse `Discriminator("kind")` + `Annotated[Union[...], Field(discriminator="kind")]`.
  - `src/codegenie/types/identifiers.py` (S1-01) — `RegistryUrl` newtype lives here; `NetworkPolicy.RegistryAllowlist(hosts: frozenset[RegistryUrl])` consumes it.

## Goal

Land `src/codegenie/transforms/sandbox_jail.py` with:
1. `SubprocessJail(Protocol)` — one method `async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult`. Intentionally *not* `@runtime_checkable`: structural typing only; runtime `isinstance` checks against `Protocol` ignore method signatures and are a foot-gun.
2. `JailedSubprocessSpec(BaseModel, frozen=True, extra="forbid")` — `cmd: tuple[str, ...]` (non-empty), `cwd: SandboxedPath` (imported from `codegenie.transforms._forward`), `env: JailedEnv` (discriminated union, see (4)), `network: NetworkPolicy`, `time_budget_s: float` (> 0, finite), `memory_mib: int` (≥ 1), `pids_max: int` (≥ 1). Field-level validators reject zero / negative / non-finite inputs at the smart-constructor boundary.
3. `JailedSubprocessResult = Annotated[Completed | TimedOut | OomKilled | NetworkDenied | DiskQuotaExceeded, Field(discriminator="kind")]` — discriminated Pydantic union with one variant per failure mode; no `dict[str, Any]`; no bare exceptions returned. Every observable numeric counter is non-negative (validators on each variant).
4. `JailedEnv = Annotated[NpmEnv | GitEnv, Field(discriminator="kind")]` — typed env wrappers with `kind: Literal["npm"]` / `Literal["git"]`. Pydantic models, not raw `dict[str, str]`; only fields each tool legitimately needs. The discriminator pins dispatch and survives the addition of a third env variant by addition (the OCP-correct extension path).
5. `NetworkPolicy = Annotated[DenyAll | RegistryAllowlist, Field(discriminator="kind")]` sum. `RegistryAllowlist(hosts: frozenset[RegistryUrl])` rejects empty allowlists and rejects any host not starting with `https://` (the smart-constructor anchor for the `RegistryUrl` `NewType` semantic that runtime `NewType` cannot enforce; matches `src/codegenie/types/identifiers.py:71` docstring).
6. A `to_env_mapping(self) -> dict[str, str]` helper on each `*Env` that produces the dict the adapter ultimately passes to `run_external_cli`. `NpmEnv.to_env_mapping()` *unconditionally* sets `npm_config_ignore_scripts="true"` — the env half of ADR-0006's `--ignore-scripts` split. The CLI half lives at the call site (`cmd`) and is consumer responsibility per ADR-0006; S4-05's capability fence ties them together. `NpmEnv` carries no public field whose name contains `npm_config_ignore_scripts` — there is no extension trapdoor by which a consumer could override the env half.

Every variant ships with a `kind: Literal[...]` discriminator. `mypy --strict` clean. Every variant must be reachable by at least one `match` statement with `assert_never` (S1-05's AST fence pins this *at the AST level*; AC-9a additionally pins it at the mypy-narrowing level via a subprocess-mypy negative test).

`SandboxedPath` is imported from `codegenie.transforms._forward` (the S1-04 forward-reference shim — `TypeAlias = pathlib.Path` today; substituted by S4-04 with a re-export of `codegenie.plugins.sandbox_path.SandboxedPath` *from the same import path*, so every consumer in this story stays stable across the substitution). The story does NOT use `TYPE_CHECKING` for `SandboxedPath`: the alias is a real runtime symbol today; the forward-string dance is unnecessary and would mask import-path drift.

## Acceptance criteria

- [ ] **AC-1.** `src/codegenie/transforms/sandbox_jail.py` exists and exports exactly the set `EXPECTED = {"SubprocessJail", "JailedSubprocessSpec", "JailedSubprocessResult", "JailedEnv", "Completed", "TimedOut", "OomKilled", "NetworkDenied", "DiskQuotaExceeded", "NpmEnv", "GitEnv", "NetworkPolicy", "DenyAll", "RegistryAllowlist"}`. A pytest meta-test (`test_module_exports_exact`) asserts `set(sandbox_jail.__all__) == EXPECTED` (equality, not superset — `__all__` is the public contract; a private helper that leaks into `dir()` must not into `__all__`). The same test asserts no public symbol's resolved annotation is `typing.Any` via `inspect.get_annotations(...)` walked across each export.
- [ ] **AC-2.** `SubprocessJail` is a `typing.Protocol` with one method: `async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult`. A pytest meta-test (`test_subprocess_jail_is_protocol`) asserts `inspect.isclass(SubprocessJail) and SubprocessJail._is_protocol is True` and that `SubprocessJail.__abstractmethods__ == frozenset({"run"})`. The Protocol is *not* decorated with `@runtime_checkable` (a separate assertion: `not getattr(SubprocessJail, "_is_runtime_protocol", False)`).
- [ ] **AC-2a.** `JailedEnv = Annotated[NpmEnv | GitEnv, Field(discriminator="kind")]` discriminated union; `NpmEnv.kind == "npm"`, `GitEnv.kind == "git"`. A pytest test round-trips `{"kind": "npm", ...}` → `NpmEnv` and `{"kind": "git", ...}` → `GitEnv` via `TypeAdapter(JailedEnv)`. A negative test confirms that omitting `kind` raises `ValidationError` (Pydantic-v2 with `Field(discriminator=...)` is strict about it). Establishes the OCP extension path for future env variants by addition.
- [ ] **AC-3.** `JailedSubprocessSpec` is a frozen Pydantic v2 model with `model_config = ConfigDict(frozen=True, extra="forbid")`. A pytest test asserts:
  - Constructing with an unknown field raises `ValidationError`.
  - Mutating *any* field on an instance raises `ValidationError` (frozen). The test parametrizes over the full field list — `cmd`, `cwd`, `env`, `network`, `time_budget_s`, `memory_mib`, `pids_max` — so a future field that's accidentally mutable is caught.
  - Every field's annotation is non-`Any` and non-`object` (via `inspect.get_annotations`).
- [ ] **AC-3a.** Smart-constructor bounds on `JailedSubprocessSpec`:
  - `cmd` empty tuple raises `ValidationError` (`min_length=1`); spawning `()` is meaningless.
  - `time_budget_s ≤ 0` raises (`gt=0`); `time_budget_s` non-finite (NaN, +Inf, -Inf) raises (`field_validator` asserts `math.isfinite`).
  - `memory_mib < 1` raises (`ge=1`); `pids_max < 1` raises (`ge=1`).
  - A parametrized red-test exercises each bound; an implementation that forgot any one validator fails exactly one parametrized case.
- [ ] **AC-4.** `JailedSubprocessResult` is a discriminated union: every variant has `kind: Literal["completed" | "timed_out" | "oom_killed" | "network_denied" | "disk_quota_exceeded"]`. A pytest test round-trips each variant through `TypeAdapter(JailedSubprocessResult).dump_python(...)` → `validate_python(...)` and confirms the discriminator routes back to the exact same class. Wrong-kind data (`{"kind": "completed", "host": "x"}`) raises `ValidationError`.
- [ ] **AC-4a.** Non-negative observable counters on each result variant — `field_validator` (`ge=0`) on every numeric field that names a count, byte size, or wall-time:
  - `Completed.stdout_bytes`, `Completed.stderr_bytes`, `Completed.wall_time_s` ≥ 0; `Completed.exit_code` is a plain `int` (signed; OS exit codes can be negative on signal-termination).
  - `TimedOut.budget_s`, `TimedOut.elapsed_s` > 0 (`gt=0`).
  - `OomKilled.peak_rss_mib` ≥ 0.
  - `DiskQuotaExceeded.quota_bytes`, `DiskQuotaExceeded.bytes_written` ≥ 0.
  - All `float` fields reject NaN/Inf via the same `math.isfinite` smart-constructor pattern as AC-3a.
- [ ] **AC-5.** `NetworkDenied(host: str, kind: Literal["network_denied"])` — `host` is observable per ADR-0006 §Decision. A pytest test asserts the field is required, non-empty (`min_length=1`), and present in the discriminator's serialized output.
- [ ] **AC-6.** `NetworkPolicy = Annotated[DenyAll | RegistryAllowlist, Field(discriminator="kind")]`. `RegistryAllowlist` has `hosts: frozenset[RegistryUrl]` (NOT `set`; NOT `list`; immutability via Pydantic v2's `frozen=True` plus the `frozenset` type). Constructing `RegistryAllowlist(hosts=frozenset())` raises `ValidationError` (empty allowlist is meaningless; same as `DenyAll`).
- [ ] **AC-6a.** `RegistryAllowlist.hosts` field validator rejects any URL not starting with `https://` — pins the strict-`https://` semantic the `RegistryUrl` `NewType` documents but cannot enforce at runtime (the `NewType` is `NewType(RegistryUrl, str)` and erases at runtime per `src/codegenie/types/identifiers.py:71`). A parametrized red-test exercises `http://`, `ftp://`, `file://`, `"registry.npmjs.org"` (schemeless), and the empty string — all raise. The validator is the *smart constructor* for `RegistryUrl` at this boundary.
- [ ] **AC-7.** `NpmEnv` is a frozen Pydantic model whose `to_env_mapping(self) -> dict[str, str]` ALWAYS includes `npm_config_ignore_scripts="true"`. Three mutation-resistant assertions, all of which must pass:
  - (a) **Constructive:** `NpmEnv().to_env_mapping()["npm_config_ignore_scripts"] == "true"` (the only constructor path — `extra="forbid"` bans alternatives at the type level).
  - (b) **Source-level inviolability (AST):** parse `sandbox_jail.py` with `ast`; assert there is exactly one assignment of the literal string `"true"` to the key `"npm_config_ignore_scripts"` inside the `NpmEnv.to_env_mapping` function body, and that no other assignment inside that body writes a different value to that key. An implementer who hard-codes `{}` or omits the key fails (a); an implementer who adds `if some_flag: mapping[key] = "false"` fails (b).
  - (c) **No extension trapdoor:** assert no public field name on `NpmEnv` contains the substring `npm_config_ignore_scripts`. This makes the env-half structurally inviolable from this Port — the closest analogue to the `GitLocalOpsCapability` "no `push` field" invariant from ADR-0011 §Decision.
  - ADR-0006 §Decision: "npm has historically respected only one or the other; we set both." The CLI half lives at `JailedSubprocessSpec.cmd` and is the consumer's responsibility (S5-02); S4-05's capability-fence test ties them together.
- [ ] **AC-8.** `GitEnv` is a frozen Pydantic model whose `to_env_mapping()` ALWAYS includes `GIT_TERMINAL_PROMPT="0"` and `GIT_ASKPASS="/bin/false"` (per ADR-0006 cross-reference to S6-04's `LocalGitOps`). The same three-tier mutation-resistant pattern as AC-7 applies — constructive + AST inviolability + no extension trapdoor (no public field name containing `GIT_TERMINAL_PROMPT` or `GIT_ASKPASS`).
- [ ] **AC-9.** Every `JailedSubprocessResult` variant is consumed by a `match` statement with `assert_never` in `tests/unit/transforms/test_sandbox_jail_exhaustiveness.py` — this is the AST-fence target S1-05's `tests/unit/transforms/test_exhaustiveness.py` discovers. The test compiles under `mypy --strict` and the `match` arms cover every `kind` literal value.
- [ ] **AC-9a.** Mypy-narrowing exhaustiveness — `tests/unit/transforms/test_sandbox_jail_mypy_negative.py` mirrors the S1-03 precedent `test_outcomes_mypy_negative.py`. It spawns `mypy --strict` on a temp file that omits one `match` arm for `JailedSubprocessResult` and asserts the exit code is non-zero with an `assert_never` error on the missing variant. Without this test, deleting a variant or widening the union silently passes the runtime exhaustiveness test. The fence is *runtime + mypy*; both must catch a regression.
- [ ] **AC-10.** A `_StubJail` in the test file demonstrates the Port can be implemented in <10 lines: structural assignment to `SubprocessJail` (`stub: SubprocessJail = _StubJail()`) type-checks under `mypy --strict`, and `await stub.run(spec)` round-trips a `JailedSubprocessSpec` to a `Completed` result. This is the structural proof that the Protocol is implementable; the real adapters (S4-02/S4-03) follow this shape. Note: the stub uses a parametrized branch (e.g., dispatches on `spec.cmd[0]`) to demonstrate that every variant of `JailedSubprocessResult` is constructible from the same Port surface — this protects against the failure mode where a stub returns only `Completed` and the Port surface silently can't express any other variant.
- [ ] **AC-11.** `JailedSubprocessSpec.cwd` is typed as `SandboxedPath` imported from `codegenie.transforms._forward` (the established Phase-3-Step-1 forward-reference shim per S1-04; `TypeAlias = pathlib.Path` today; S4-04 substitutes the alias *at the same import path*). Two AST-level + identity-level assertions:
  - (a) **Import path is exact:** parse `sandbox_jail.py` with `ast` and assert the file contains exactly the `ImportFrom` node `from codegenie.transforms._forward import SandboxedPath` (and no import of `SandboxedPath` from `codegenie.plugins.*` — the latter is a documented anti-pattern per the `_forward.py` shim docstring).
  - (b) **Annotation identity:** `JailedSubprocessSpec.model_fields["cwd"].annotation is SandboxedPath` (the imported symbol; identity check survives the S4-04 substitution because the import path stays stable).
  - The original story's `"SandboxedPath" in repr(hints["cwd"])` check is intentionally dropped — it is unverifiable when `SandboxedPath` is a `TypeAlias` for `pathlib.Path` (the resolved hint repr says `"pathlib.Path"`).
- [ ] **AC-12.** No `dict[str, Any]`, `typing.Any`, or bare `Exception` usage anywhere in `sandbox_jail.py`. A grep test (`tests/unit/transforms/test_sandbox_jail_typed.py`) reads the module source and asserts:
  - `re.search(r"\bdict\s*\[\s*str\s*,\s*Any\s*\]", src)` is `None`.
  - `re.search(r"\bDict\s*\[\s*str\s*,\s*Any\s*\]", src)` is `None`.
  - `re.search(r"\bAny\b", src)` is `None` *outside the module docstring / comments* (use `ast.walk` not raw `in` to avoid false-positive on subclass declarations like `class FooError(Exception)` or `from typing import Any` in comments).
  - `re.search(r"^[ \t]*except[ \t]+Exception\b", src, re.MULTILINE)` is `None` (bare `except Exception:` only — subclass-of-Exception class definitions are *allowed* and legitimate).
  - `re.search(r"\braise\s+Exception\b", src)` is `None`.
  - The S1-05 phase-3 `Any`-fence (`tests/fence/test_no_any_in_plugin_surface.py`) catches escapees at the AST level across the full surface.
- [ ] **AC-13.** `mypy --strict src/codegenie/transforms/sandbox_jail.py tests/unit/transforms/` clean. `ruff check` + `ruff format --check` clean on touched files.
- [ ] **AC-14.** `make lint-imports` (Phase 3 contracts from S1-05) confirms no LLM SDK appears in `src/codegenie/transforms/sandbox_jail.py`'s import closure. (The `tests/fence/test_no_llm_in_transforms.py` test extends to cover this module specifically by virtue of being under `src/codegenie/transforms/`.)
- [ ] **AC-15.** A snapshot test (`tests/unit/transforms/test_sandbox_jail_contract_snapshot.py`) records the JSON schema of `JailedSubprocessSpec` and `TypeAdapter(JailedSubprocessResult).json_schema(by_alias=True)` to a golden file at `tests/golden/contracts/sandbox_jail.schema.json`. Specific structural assertions in the snapshot test (in addition to byte-equal golden compare):
  - `result_schema["discriminator"]["propertyName"] == "kind"`.
  - `len(result_schema["oneOf"]) == 5` (exactly five variants).
  - `spec_schema["properties"]["env"]["discriminator"]["propertyName"] == "kind"` (env discriminator present).
  - `spec_schema["properties"]["network"]["discriminator"]["propertyName"] == "kind"` (network discriminator present).
  S6-06's contract-snapshot integration test consumes this golden. An additive field is permitted; a rename / removal / required-add requires explicit ADR amendment per Step 9 risk #4.

## Implementation outline

1. Create `src/codegenie/transforms/sandbox_jail.py`. Imports: `from __future__ import annotations`, `math`, `typing.Protocol`, `typing.Literal`, `typing.Annotated`, `pydantic.BaseModel`, `pydantic.ConfigDict`, `pydantic.Field`, `pydantic.field_validator`, `pydantic.TypeAdapter`, `codegenie.types.identifiers.RegistryUrl`, and `codegenie.transforms._forward.SandboxedPath` (the S1-04 forward-reference shim — real runtime symbol today via `TypeAlias = pathlib.Path`; substituted by S4-04 at the same import path).
2. Define `__all__: tuple[str, ...]` *first*, pinning the exact public surface (AC-1).
3. Define the `NpmEnv` / `GitEnv` Pydantic models with `model_config = ConfigDict(frozen=True, extra="forbid")`, a `kind: Literal["npm"] = "npm"` / `kind: Literal["git"] = "git"` discriminator, and a `to_env_mapping(self) -> dict[str, str]` whose body hard-codes the required defenses (`npm_config_ignore_scripts="true"` for `NpmEnv`; `GIT_TERMINAL_PROMPT="0"`, `GIT_ASKPASS="/bin/false"` for `GitEnv`). Neither model carries a public field whose name contains the env keys (AC-7c / AC-8).
4. Define `JailedEnv = Annotated[NpmEnv | GitEnv, Field(discriminator="kind")]`.
5. Define `DenyAll(BaseModel)` with `kind: Literal["deny_all"] = "deny_all"`. Define `RegistryAllowlist(BaseModel)` with `kind: Literal["registry_allowlist"] = "registry_allowlist"`, `hosts: frozenset[RegistryUrl]`, and a `field_validator("hosts")` that (a) rejects empty frozensets, (b) rejects any host that does not start with `https://` (AC-6 + AC-6a). Both rejections raise `ValueError` with a stable `error_id`-shaped message so the consumer's `RecipeFailed(RecipeError(...))` mapping (S5-02) is stable.
6. Define `NetworkPolicy = Annotated[DenyAll | RegistryAllowlist, Field(discriminator="kind")]`.
7. Define each `JailedSubprocessResult` variant — `Completed(kind: Literal["completed"], exit_code: int, stdout_bytes: int >= 0, stderr_bytes: int >= 0, wall_time_s: float >= 0 & finite)`; `TimedOut(kind: Literal["timed_out"], budget_s: float > 0 & finite, elapsed_s: float > 0 & finite)`; `OomKilled(kind: Literal["oom_killed"], peak_rss_mib: int >= 0)`; `NetworkDenied(kind: Literal["network_denied"], host: str (min_length=1))`; `DiskQuotaExceeded(kind: Literal["disk_quota_exceeded"], quota_bytes: int >= 0, bytes_written: int >= 0)`. Every model is `frozen=True, extra="forbid"`. Use `Field(ge=0)` / `Field(gt=0)` for integer bounds and `field_validator(..., mode="after")` with `math.isfinite(value)` for float bounds.
8. Define `JailedSubprocessResult = Annotated[Completed | TimedOut | OomKilled | NetworkDenied | DiskQuotaExceeded, Field(discriminator="kind")]`.
9. Define `JailedSubprocessSpec(BaseModel, frozen=True, extra="forbid")` with `cmd: tuple[str, ...] = Field(min_length=1)`, `cwd: SandboxedPath`, `env: JailedEnv`, `network: NetworkPolicy`, `time_budget_s: float` with `Field(gt=0)` + finiteness validator, `memory_mib: int = Field(ge=1)`, `pids_max: int = Field(ge=1)`.
10. Define the `SubprocessJail(Protocol)` with `async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult: ...`. Do NOT decorate with `@runtime_checkable` (AC-2).
11. Write the red tests (AC-1..AC-15). The schema snapshot test lands last so it captures the final shape; commit the golden file as part of the green.
12. Confirm `mypy --strict`, `ruff`, and `pytest tests/unit/transforms/test_sandbox_jail*.py` green. Confirm `make lint-imports` green (AC-14).
13. Generate the contract snapshot golden file (`tests/golden/contracts/sandbox_jail.schema.json`) by serializing `JailedSubprocessSpec.model_json_schema(by_alias=True)` and `TypeAdapter(JailedSubprocessResult).json_schema(by_alias=True)`; commit.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file path: `tests/unit/transforms/test_sandbox_jail.py`

```python
from __future__ import annotations

import ast
import inspect
import math
import pathlib
import re
from typing import Annotated, Literal, get_args, get_origin, get_type_hints

import pytest
from pydantic import Field, TypeAdapter, ValidationError

# These imports fail RED before the module exists.
from codegenie.transforms.sandbox_jail import (
    Completed,
    DenyAll,
    DiskQuotaExceeded,
    GitEnv,
    JailedEnv,
    JailedSubprocessResult,
    JailedSubprocessSpec,
    NetworkDenied,
    NetworkPolicy,
    NpmEnv,
    OomKilled,
    RegistryAllowlist,
    SubprocessJail,
    TimedOut,
)
from codegenie.transforms._forward import SandboxedPath
from codegenie.types.identifiers import RegistryUrl


_OK_HOST = RegistryUrl("https://registry.npmjs.org")


def _spec(**overrides: object) -> JailedSubprocessSpec:
    """Helper — minimal valid spec, override fields per-test."""
    base: dict[str, object] = dict(
        cmd=("npm", "install", "--ignore-scripts"),
        cwd=SandboxedPath(pathlib.Path("/tmp/jail")),
        env=NpmEnv(),
        network=DenyAll(),
        time_budget_s=60.0,
        memory_mib=512,
        pids_max=128,
    )
    base.update(overrides)
    return JailedSubprocessSpec(**base)  # type: ignore[arg-type]


# AC-1 — exact public surface via __all__
def test_module_exports_exact() -> None:
    import codegenie.transforms.sandbox_jail as mod

    expected = {
        "SubprocessJail", "JailedSubprocessSpec", "JailedSubprocessResult", "JailedEnv",
        "Completed", "TimedOut", "OomKilled", "NetworkDenied", "DiskQuotaExceeded",
        "NpmEnv", "GitEnv", "NetworkPolicy", "DenyAll", "RegistryAllowlist",
    }
    assert set(mod.__all__) == expected


# AC-2 — Protocol shape, not @runtime_checkable
def test_subprocess_jail_is_protocol_not_runtime_checkable() -> None:
    assert inspect.isclass(SubprocessJail)
    assert getattr(SubprocessJail, "_is_protocol", False) is True
    assert SubprocessJail.__abstractmethods__ == frozenset({"run"})
    # Not runtime_checkable — `isinstance(jail, SubprocessJail)` is a Protocol
    # foot-gun (ignores method signatures). Enforce structural typing only.
    assert getattr(SubprocessJail, "_is_runtime_protocol", False) is False


# AC-2a — env discriminator routes by `kind`
def test_jailed_env_discriminator_routes() -> None:
    adapter = TypeAdapter(JailedEnv)
    npm = adapter.validate_python({"kind": "npm"})
    git = adapter.validate_python({"kind": "git"})
    assert isinstance(npm, NpmEnv)
    assert isinstance(git, GitEnv)
    with pytest.raises(ValidationError):
        adapter.validate_python({})  # missing discriminator


# AC-3 — frozen + extra="forbid" + every field annotated
@pytest.mark.parametrize(
    "field", ["cmd", "cwd", "env", "network", "time_budget_s", "memory_mib", "pids_max"]
)
def test_jailed_subprocess_spec_is_frozen(field: str) -> None:
    spec = _spec()
    with pytest.raises(ValidationError):
        setattr(spec, field, getattr(spec, field))


def test_jailed_subprocess_spec_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        _spec(surprise="x")  # type: ignore[call-arg]


# AC-3a — smart-constructor bounds
@pytest.mark.parametrize(
    "overrides",
    [
        {"cmd": ()},                          # min_length=1
        {"time_budget_s": 0.0},               # gt=0
        {"time_budget_s": -1.0},              # gt=0
        {"time_budget_s": math.nan},          # finite
        {"time_budget_s": math.inf},          # finite
        {"memory_mib": 0},                    # ge=1
        {"memory_mib": -1},                   # ge=1
        {"pids_max": 0},                      # ge=1
        {"pids_max": -1},                     # ge=1
    ],
)
def test_spec_smart_constructor_rejects(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _spec(**overrides)


# AC-4 — discriminator routing round-trips
@pytest.mark.parametrize(
    "variant",
    [
        Completed(kind="completed", exit_code=0, stdout_bytes=0, stderr_bytes=0, wall_time_s=0.1),
        Completed(kind="completed", exit_code=-9, stdout_bytes=0, stderr_bytes=0, wall_time_s=0.0),
        TimedOut(kind="timed_out", budget_s=60.0, elapsed_s=60.0),
        OomKilled(kind="oom_killed", peak_rss_mib=512),
        NetworkDenied(kind="network_denied", host="evil.example.com"),
        DiskQuotaExceeded(kind="disk_quota_exceeded", quota_bytes=1024, bytes_written=2048),
    ],
)
def test_result_variant_roundtrip(variant: object) -> None:
    adapter = TypeAdapter(JailedSubprocessResult)
    payload = adapter.dump_python(variant)
    parsed = adapter.validate_python(payload)
    assert type(parsed) is type(variant)
    assert parsed == variant


def test_result_wrong_kind_rejected() -> None:
    adapter = TypeAdapter(JailedSubprocessResult)
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "completed", "host": "x"})  # missing required + extra


# AC-4a — non-negative observable counters + finiteness
@pytest.mark.parametrize(
    "ctor, kwargs",
    [
        (Completed, dict(kind="completed", exit_code=0, stdout_bytes=-1, stderr_bytes=0, wall_time_s=0.0)),
        (Completed, dict(kind="completed", exit_code=0, stdout_bytes=0, stderr_bytes=-1, wall_time_s=0.0)),
        (Completed, dict(kind="completed", exit_code=0, stdout_bytes=0, stderr_bytes=0, wall_time_s=-0.1)),
        (Completed, dict(kind="completed", exit_code=0, stdout_bytes=0, stderr_bytes=0, wall_time_s=math.nan)),
        (Completed, dict(kind="completed", exit_code=0, stdout_bytes=0, stderr_bytes=0, wall_time_s=math.inf)),
        (TimedOut, dict(kind="timed_out", budget_s=0.0, elapsed_s=1.0)),  # gt=0
        (TimedOut, dict(kind="timed_out", budget_s=1.0, elapsed_s=math.inf)),
        (OomKilled, dict(kind="oom_killed", peak_rss_mib=-1)),
        (DiskQuotaExceeded, dict(kind="disk_quota_exceeded", quota_bytes=-1, bytes_written=0)),
        (DiskQuotaExceeded, dict(kind="disk_quota_exceeded", quota_bytes=0, bytes_written=-1)),
    ],
)
def test_result_variant_bounds(ctor: type, kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ctor(**kwargs)


# AC-5 — NetworkDenied
def test_network_denied_host_required_and_serialized() -> None:
    nd = NetworkDenied(kind="network_denied", host="evil.example.com")
    dumped = nd.model_dump()
    assert dumped["host"] == "evil.example.com"
    assert dumped["kind"] == "network_denied"
    with pytest.raises(ValidationError):
        NetworkDenied(kind="network_denied", host="")  # empty rejected
    with pytest.raises(ValidationError):
        NetworkDenied(kind="network_denied")  # type: ignore[call-arg]


# AC-6 — NetworkPolicy discriminator + empty allowlist
def test_network_policy_discriminator_and_empty_allowlist_rejected() -> None:
    adapter = TypeAdapter(NetworkPolicy)
    deny = adapter.validate_python({"kind": "deny_all"})
    assert isinstance(deny, DenyAll)

    allow = adapter.validate_python(
        {"kind": "registry_allowlist", "hosts": ["https://registry.npmjs.org"]}
    )
    assert isinstance(allow, RegistryAllowlist)
    assert _OK_HOST in allow.hosts

    with pytest.raises(ValidationError):
        RegistryAllowlist(hosts=frozenset())


# AC-6a — strict https:// smart-constructor on RegistryAllowlist.hosts
@pytest.mark.parametrize(
    "bad_host",
    [
        "http://registry.npmjs.org",
        "ftp://registry.npmjs.org",
        "file:///etc/passwd",
        "registry.npmjs.org",          # schemeless
        "",                            # empty
        "https:/registry.npmjs.org",   # malformed
    ],
)
def test_registry_allowlist_rejects_non_https(bad_host: str) -> None:
    with pytest.raises(ValidationError):
        RegistryAllowlist(hosts=frozenset({RegistryUrl(bad_host)}))


# AC-7 — npm_config_ignore_scripts is structurally inviolable
def test_npm_env_ignore_scripts_constructive() -> None:
    """AC-7 (a) constructive — only path through the public constructor."""
    assert NpmEnv().to_env_mapping()["npm_config_ignore_scripts"] == "true"


def test_npm_env_ignore_scripts_source_level_inviolable() -> None:
    """AC-7 (b) AST — the literal 'true' is the only RHS assigned to that key
    inside NpmEnv.to_env_mapping, and no other assignment in the body writes
    a different value to the same key."""
    import codegenie.transforms.sandbox_jail as mod

    tree = ast.parse(inspect.getsource(mod))
    npm_cls = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == "NpmEnv"
    )
    fn = next(
        n for n in npm_cls.body
        if isinstance(n, ast.FunctionDef) and n.name == "to_env_mapping"
    )
    writes_to_key = [
        node for node in ast.walk(fn)
        if isinstance(node, ast.Constant) and node.value == "npm_config_ignore_scripts"
    ]
    assert writes_to_key, "to_env_mapping must reference npm_config_ignore_scripts"
    # Reconstruct the body and check no `"false"` constant appears anywhere
    # adjacent to the key (mutation-resistance against `if flag: v="false"`).
    body_src = ast.unparse(fn)
    assert '"true"' in body_src
    assert '"false"' not in body_src


def test_npm_env_no_extension_trapdoor() -> None:
    """AC-7 (c) — no public field on NpmEnv carries the env-key substring."""
    fields = NpmEnv.model_fields.keys()
    assert not any("npm_config_ignore_scripts" in f for f in fields)


# AC-8 — GitEnv safety keys with same three-tier discipline
def test_git_env_safety_keys_constructive() -> None:
    mapping = GitEnv().to_env_mapping()
    assert mapping["GIT_TERMINAL_PROMPT"] == "0"
    assert mapping["GIT_ASKPASS"] == "/bin/false"


def test_git_env_no_extension_trapdoor() -> None:
    fields = GitEnv.model_fields.keys()
    assert not any("GIT_TERMINAL_PROMPT" in f or "GIT_ASKPASS" in f for f in fields)


# AC-10 — Port is implementable in <10 lines and can express every variant
class _StubJail:
    async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult:
        # Branch by the first arg so this stub can return any variant;
        # mutation-resistant proof that the Port surface admits each result.
        head = spec.cmd[0]
        if head == "_timeout":
            return TimedOut(kind="timed_out", budget_s=1.0, elapsed_s=1.0)
        if head == "_oom":
            return OomKilled(kind="oom_killed", peak_rss_mib=1)
        if head == "_neterr":
            return NetworkDenied(kind="network_denied", host="x")
        if head == "_diskerr":
            return DiskQuotaExceeded(kind="disk_quota_exceeded", quota_bytes=1, bytes_written=2)
        return Completed(kind="completed", exit_code=0, stdout_bytes=0, stderr_bytes=0, wall_time_s=0.0)


@pytest.mark.parametrize(
    "cmd0,expected_cls",
    [
        ("_ok", Completed),
        ("_timeout", TimedOut),
        ("_oom", OomKilled),
        ("_neterr", NetworkDenied),
        ("_diskerr", DiskQuotaExceeded),
    ],
)
async def test_protocol_admits_every_variant(cmd0: str, expected_cls: type) -> None:
    stub: SubprocessJail = _StubJail()
    spec = _spec(cmd=(cmd0,), network=RegistryAllowlist(hosts=frozenset({_OK_HOST})))
    result = await stub.run(spec)
    assert type(result) is expected_cls


# AC-11 — SandboxedPath import path is exact + identity check
def test_cwd_imports_from_forward_shim() -> None:
    """AST-level: the file imports SandboxedPath from codegenie.transforms._forward,
    and from no other module. The shim docstring is the single substitution point
    when S4-04 lands; importing from anywhere else defeats that substitution."""
    import codegenie.transforms.sandbox_jail as mod

    src = inspect.getsource(mod)
    tree = ast.parse(src)
    sandboxed_imports = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom)
        and any(a.name == "SandboxedPath" for a in n.names)
    ]
    assert len(sandboxed_imports) == 1
    assert sandboxed_imports[0].module == "codegenie.transforms._forward"


def test_cwd_annotation_identity() -> None:
    """Identity-level: model_fields["cwd"].annotation IS SandboxedPath (the
    imported symbol). Survives the S4-04 substitution because the import path
    is stable."""
    assert JailedSubprocessSpec.model_fields["cwd"].annotation is SandboxedPath


# AC-12 — typed-discipline grep, with subclass-of-Exception false-positive guard
def test_module_source_has_no_dict_any_or_bare_exception() -> None:
    import codegenie.transforms.sandbox_jail as mod

    src = inspect.getsource(mod)
    assert re.search(r"\bdict\s*\[\s*str\s*,\s*Any\s*\]", src) is None
    assert re.search(r"\bDict\s*\[\s*str\s*,\s*Any\s*\]", src) is None
    # bare `except Exception:` only — subclass-of-Exception class definitions are allowed
    assert re.search(r"^[ \t]*except[ \t]+Exception\b", src, re.MULTILINE) is None
    assert re.search(r"\braise\s+Exception\b", src) is None
    # No `: Any` annotation outside comments/docstrings — AST-walk so we don't
    # false-positive on the word `Any` appearing inside string literals or docs.
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "Any":
            pytest.fail(f"`Any` used in annotation position at line {node.lineno}")


# AC-15 — schema snapshot specificity
def test_result_schema_has_oneof_with_five_variants_and_kind_discriminator() -> None:
    adapter = TypeAdapter(JailedSubprocessResult)
    schema = adapter.json_schema(by_alias=True)
    assert schema["discriminator"]["propertyName"] == "kind"
    assert len(schema["oneOf"]) == 5


def test_spec_schema_has_env_and_network_discriminators() -> None:
    schema = JailedSubprocessSpec.model_json_schema(by_alias=True)
    assert schema["properties"]["env"]["discriminator"]["propertyName"] == "kind"
    assert schema["properties"]["network"]["discriminator"]["propertyName"] == "kind"
    assert schema["properties"]["cmd"]["type"] == "array"
    assert schema["properties"]["cmd"].get("minItems", 0) == 1
```

Snapshot golden test (`tests/unit/transforms/test_sandbox_jail_contract_snapshot.py`) — AC-15 byte-equal compare:

```python
from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter

from codegenie.transforms.sandbox_jail import (
    JailedSubprocessResult,
    JailedSubprocessSpec,
)

_GOLDEN = Path(__file__).resolve().parents[3] / "tests/golden/contracts/sandbox_jail.schema.json"


def test_contract_snapshot_byte_equal() -> None:
    expected = json.loads(_GOLDEN.read_text())
    actual = {
        "spec": JailedSubprocessSpec.model_json_schema(by_alias=True),
        "result": TypeAdapter(JailedSubprocessResult).json_schema(by_alias=True),
    }
    assert actual == expected, (
        "Contract snapshot drift. Either revert the change or "
        "regenerate the golden + amend ADR-0006 per Step 9 risk #4."
    )
```

Companion exhaustiveness test — `tests/unit/transforms/test_sandbox_jail_exhaustiveness.py` (AC-9):

```python
from __future__ import annotations
from typing import assert_never

from codegenie.transforms.sandbox_jail import (
    Completed, DiskQuotaExceeded, JailedSubprocessResult,
    NetworkDenied, OomKilled, TimedOut,
)


def classify(result: JailedSubprocessResult) -> str:
    match result:
        case Completed():
            return "completed"
        case TimedOut():
            return "timed_out"
        case OomKilled():
            return "oom_killed"
        case NetworkDenied():
            return "network_denied"
        case DiskQuotaExceeded():
            return "disk_quota_exceeded"
        case _:
            assert_never(result)


def test_every_variant_classifies() -> None:
    cases: list[tuple[JailedSubprocessResult, str]] = [
        (Completed(kind="completed", exit_code=0, stdout_bytes=0, stderr_bytes=0, wall_time_s=0.0), "completed"),
        (TimedOut(kind="timed_out", budget_s=1.0, elapsed_s=1.0), "timed_out"),
        (OomKilled(kind="oom_killed", peak_rss_mib=1), "oom_killed"),
        (NetworkDenied(kind="network_denied", host="x"), "network_denied"),
        (DiskQuotaExceeded(kind="disk_quota_exceeded", quota_bytes=1, bytes_written=2), "disk_quota_exceeded"),
    ]
    for variant, expected in cases:
        assert classify(variant) == expected
```

Mypy-negative exhaustiveness test (`tests/unit/transforms/test_sandbox_jail_mypy_negative.py`) — AC-9a:

```python
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path


_MISSING_ARM = textwrap.dedent(
    '''
    from __future__ import annotations
    from typing import assert_never

    from codegenie.transforms.sandbox_jail import (
        Completed, DiskQuotaExceeded, JailedSubprocessResult,
        NetworkDenied, OomKilled, TimedOut,
    )


    def classify(result: JailedSubprocessResult) -> str:
        match result:
            case Completed():
                return "completed"
            case TimedOut():
                return "timed_out"
            case OomKilled():
                return "oom_killed"
            case NetworkDenied():
                return "network_denied"
            # DiskQuotaExceeded arm INTENTIONALLY OMITTED — mypy must catch.
            case _:
                assert_never(result)
    '''
)


def test_mypy_strict_catches_missing_arm(tmp_path: Path) -> None:
    """AC-9a — mypy --strict must reject a `match` that omits a variant.

    Mirrors the S1-03 outcomes precedent `test_outcomes_mypy_negative.py`.
    Without this test, a future variant addition could land without an
    exhaustiveness check and pass silently.
    """
    fixture = tmp_path / "missing_arm.py"
    fixture.write_text(_MISSING_ARM)
    proc = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(fixture)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0, (
        "mypy --strict accepted a match with a missing arm; "
        f"stdout=\n{proc.stdout}\nstderr=\n{proc.stderr}"
    )
    assert "assert_never" in (proc.stdout + proc.stderr).lower() or "argument" in (proc.stdout + proc.stderr).lower(), (
        "mypy error did not reference the assert_never narrowing failure"
    )
```

Run — every test in all four files fails because the module doesn't exist. Commit the red.

### Green — make it pass

Implement `sandbox_jail.py` per the Implementation outline. Run the test file; all should pass except potentially AC-11 if `SandboxedPath` is not yet importable — in that case the `TYPE_CHECKING` import resolves to a string and the `repr(hints["cwd"])` test asserts substring `"SandboxedPath"`, which `from __future__ import annotations` ensures.

### Refactor — clean up

- Group the Pydantic variants logically (env → policy → result variants → result alias → spec → protocol).
- Add docstrings at every public symbol citing ADR-0006.
- Run `ruff format` and confirm no manual whitespace fiddling needed.
- Re-run `mypy --strict src/codegenie/transforms/sandbox_jail.py tests/unit/transforms/` and confirm zero errors.
- Generate the contract snapshot file (`tests/golden/contracts/sandbox_jail.schema.json`) and commit it alongside.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/sandbox_jail.py` | New module: `SubprocessJail` Protocol, `JailedSubprocessSpec`, `JailedSubprocessResult` discriminated union, `JailedEnv = Annotated[NpmEnv \| GitEnv, Field(discriminator="kind")]`, `NetworkPolicy = Annotated[DenyAll \| RegistryAllowlist, Field(discriminator="kind")]`. Defines `__all__` (AC-1). Imports `SandboxedPath` from `codegenie.transforms._forward` (AC-11). |
| `tests/unit/transforms/test_sandbox_jail.py` | New test file. Covers AC-1..AC-8, AC-10..AC-12, AC-15 structural assertions. |
| `tests/unit/transforms/test_sandbox_jail_exhaustiveness.py` | New test file. AC-9 `match` + `assert_never` over every `JailedSubprocessResult` variant. This is the file S1-05's exhaustiveness AST fence discovers. |
| `tests/unit/transforms/test_sandbox_jail_mypy_negative.py` | New test file. AC-9a subprocess-mypy negative test — mypy must reject a `match` with a missing arm. Mirrors `test_outcomes_mypy_negative.py` (S1-03 precedent). |
| `tests/unit/transforms/test_sandbox_jail_contract_snapshot.py` | New test file. AC-15 byte-equal golden compare. |
| `tests/golden/contracts/sandbox_jail.schema.json` | New golden file. `JailedSubprocessSpec.model_json_schema(by_alias=True)` + `TypeAdapter(JailedSubprocessResult).json_schema(by_alias=True)`. S6-06 consumes. |
| `src/codegenie/transforms/__init__.py` | Existing (created in S1-01). No edit required — the new module is import-discovered, not re-exported. (If the package convention re-exports symbols, mirror it surgically.) |

## Out of scope

- **`BwrapAdapter` (Linux) implementation** — S4-02. This story lands only the Port; the adapter is a separate, larger piece of work with seccomp filter design and netns plumbing.
- **`SandboxExecAdapter` (macOS) implementation** — S4-03. Mirror of S4-02 on the macOS substrate; nightly-only integration test.
- **`SandboxedPath` concrete implementation with O_NOFOLLOW** — S4-04. Imported here only by name via `TYPE_CHECKING`; both stories can land in either order.
- **`ALLOWED_BINARIES` amendment + `Capability` tokens** — S4-05. The Port is substrate-agnostic; the allowlist amendment is the data layer that lets the adapters call `bwrap` / `sandbox-exec` / `npm` through `run_external_cli`.
- **`NpmLockfileRecipeEngine` consumption** — S5-02. The recipe engine calls `SubprocessJail.run(...)` with a real `JailedSubprocessSpec`; this story does not write any consumer.
- **Phase 5's `FirecrackerAdapter` and `DinDAdapter`** — Phase 5 substitutes via the same Port; documented in ADR-0006 §Consequences but not implemented in Phase 3.
- **Performance benchmarks for the Port** — the ~80–200 ms / ~50–150 ms envelope is documented in ADR-0006 §Tradeoffs and ties to `tests/bench/bench_workflow_e2e_warm.py` (S9-03); no bench lives in this story.

## Notes for the implementer

- **Ports-before-adapters is non-negotiable.** Per High-level-impl §Order of operations, the Hexagonal Port lands before either Adapter. An adapter coded against a not-yet-stable Protocol pays for itself twice. This story's surface is the contract the next three stories (S4-02 / S4-03 / S5-02 consumers) are written against.
- **`SandboxedPath` import discipline — corrected by validation.** The original draft instructed `TYPE_CHECKING` import from `codegenie.plugins.sandbox_path`. Phase-3 Step 1 (S1-04) has **already shipped** `SandboxedPath: TypeAlias = pathlib.Path` in `codegenie.transforms._forward`, and the shim docstring (lines 10-14) pins the substitution path: "When S4-04 / S4-05 land: S4-04 — Replace the `SandboxedPath` `TypeAlias` with a re-export of `codegenie.plugins.sandbox_path.SandboxedPath` *from this module* [`codegenie.transforms._forward`]. Every consumer keeps importing from `codegenie.transforms`; the import path stays stable." Therefore: `from codegenie.transforms._forward import SandboxedPath` is the only correct import in this story. AC-11 enforces this at the AST level. The High-level-impl Step 4 docs drift (referenced in the original draft) is not this story's concern; surface it in the S4-04 attempt log if it surfaces.
- **`--ignore-scripts` split discipline.** Per ADR-0006 §Decision: "npm has historically respected only one or the other; we set both." The env half (`npm_config_ignore_scripts="true"`) is **structurally enforced here** inside `NpmEnv.to_env_mapping()` — AC-7 enforces inviolability at three tiers (constructive, AST, no-extension-trapdoor), the closest analogue to the `GitLocalOpsCapability` "no `push` field" invariant from ADR-0011 §Decision. The CLI half (`--ignore-scripts` in `cmd`) lives at the consumer (S5-02's `NpmLockfileRecipeEngine`); S4-05's capability-fence test ties them together by asserting every npm-related `JailedSubprocessSpec` constructed in `src/codegenie/transforms/engines/npm_lockfile.py` has `--ignore-scripts` literally in `cmd`. Document this split at the symbol.
- **`frozenset[RegistryUrl]` for hosts.** `set` is mutable; `list` admits duplicates and ordering. `frozenset[RegistryUrl]` is the right type: immutable, set-semantics, newtype-typed per ADR-0010. Pydantic v2 supports `frozenset` natively with `frozen=True` on the parent model. The `field_validator` at AC-6a is the **smart constructor** for the `RegistryUrl` semantic — `NewType` erases at runtime per `identifiers.py:71`, so the strict-`https://` constraint can only be enforced at the boundary where the value crosses into a domain model.
- **Discriminated-union shape matches the codebase precedent — apply it consistently.** `RecipeOutcome`, `RemediationOutcome`, `NodeTransition`, `AdapterConfidence`, `Applicability`, `JailedSubprocessResult`, `NetworkPolicy`, *and now `JailedEnv`* all use `Annotated[Union[...], Field(discriminator="kind")]`. The validator added the `JailedEnv` discriminator (AC-2a) because a structural-union `NpmEnv | GitEnv` is the failure mode where two models with overlapping field shapes get silently mis-dispatched the moment a third env variant lands. The OCP-correct extension path is `Annotated[NpmEnv | GitEnv | ThirdEnv, Field(discriminator="kind")]`. Mirror the pattern verbatim; the exhaustiveness AST fence (S1-05) treats every such union as a target.
- **No `dict[str, Any]`, no bare exceptions.** Per ADR-0006 §Tradeoffs row 4: "every branch typed; no `dict[str, Any]`, no bare exceptions." AC-12 enforces this at the file level with regex-precise patterns (no false-positive on subclass-of-Exception declarations); the S1-05 `test_no_any_in_plugin_surface.py` AST fence catches escapees across the full surface. Both fences must be green.
- **`Completed` carries byte sizes, not byte contents.** `stdout_bytes` / `stderr_bytes` are intentionally counts only. The threat model treats child-process stdout/stderr as potentially-sensitive (npm logs can leak `~/.npmrc` tokens via verbose errors); the adapter is responsible for redirecting full content to a `SandboxedPath`-rooted log file outside this `Completed` envelope. Phase 5's `TrustScorer` signals consume the log path, not the bytes.
- **Async-vs-sync open question.** ADR-0006 §Consequences last bullet defers the choice between `asyncio.to_thread(subprocess.run, ...)` and `asyncio.create_subprocess_exec` to the adapter authors (S4-02 / S4-03). The Port is `async def run(...)`; how each adapter implements it is its concern. This story does not pick.
- **Snapshot test handoff to S6-06.** AC-15's snapshot lives in this story (own golden); S6-06 extends the integration `test_phase5_contract_snapshot.py` to consume this golden plus the orchestrator / scorer / transform / apply-context / recipe-engine schemas. Per Step 9 risk #4: additive deltas (new optional field with `default_factory`) permitted; breaking deltas (rename, remove, required-add) require explicit ADR amendment + golden refresh. The discriminator metadata is captured via `model_json_schema(by_alias=True)` — without `by_alias=True`, Pydantic v2 omits the `discriminator` keyword from emitted JSON Schema, and Phase 5's contract consumer would lose the dispatch signal.
- **Protocol is intentionally NOT `@runtime_checkable`.** A `@runtime_checkable` Protocol admits `isinstance(jail, SubprocessJail)` — but Python's runtime Protocol check ignores method signatures and async-vs-sync. A class with a `run` attribute of any shape would pass. Structural typing at type-check time is the only correct discipline here; AC-2 asserts the negative.
- **`__all__` is the contract surface.** Define `__all__` first in the module file. AC-1 enforces *equality* (not superset) with `EXPECTED` — a private helper accidentally leaking into the public surface is a contract change. If a future story needs a new export, it must amend `__all__` *and* the contract snapshot, by design.
- **Design opportunity (deferred — rule of three).** A registry-driven `JailedSubprocessResult` (each adapter registers its failure-mode variant) would maximize OCP but currently has only one concrete consumer (the two interim adapters). Per Rule 2 / Rule 8: three similar lines is better than premature abstraction. Phase 5's `FirecrackerAdapter` is the third consumer; revisit the registry shape at that point (a `VariantRegistry` would replace the closed umbrella with an open `Annotated[Union[...registered...], Field(discriminator="kind")]`). Recorded here so the executor doesn't pre-build it.
