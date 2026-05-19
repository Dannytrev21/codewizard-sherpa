# Validation report — S4-01 `SubprocessJail` Port + `JailedSubprocessResult` tagged union

**Story:** `docs/phases/03-vuln-deterministic-recipe/stories/S4-01-subprocess-jail-port.md`
**Validated:** 2026-05-18
**Validator:** `/phase-story-validator` (four critics + synthesizer)
**Verdict:** **HARDENED** — real but fixable weaknesses; edits applied; ready for `phase-story-executor`.

---

## Context Brief (Stage 1)

Reads consumed:

- `docs/phases/03-vuln-deterministic-recipe/stories/S4-01-subprocess-jail-port.md` (full)
- `docs/phases/03-vuln-deterministic-recipe/phase-arch-design.md` §Goals G1, §Component design C8 (lines 608-635), §Edge cases E7/E8/E12, §Design patterns applied row 3, §Tradeoffs row "Online mode default with RegistryAllowlist"
- `docs/phases/03-vuln-deterministic-recipe/ADRs/0006-hexagonal-subprocessjail-port-bwrap-sandbox-exec.md` (full)
- `docs/phases/03-vuln-deterministic-recipe/ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` (lines 1-80)
- `src/codegenie/transforms/outcomes.py` (S1-03 precedent — discriminated-union shape this story mirrors)
- `src/codegenie/transforms/_forward.py` (S1-04 `SandboxedPath` forward-reference shim — load-bearing for AC-11)
- `src/codegenie/types/identifiers.py:60-83` (`RegistryUrl` `NewType` documentation)
- `tests/fence/test_no_any_in_plugin_surface.py` (S1-05 Phase-3 `Any`-fence — `dict[str, Any]` ban substrate)
- `tests/unit/transforms/test_exhaustiveness.py` (S1-03 precedent for the `match` + `assert_never` discipline)

**What the story promises:** a Hexagonal `SubprocessJail` Port plus typed env / network / result types. The Port is the seam Phase 5's `FirecrackerAdapter` and `DinDAdapter` substitute against.

**What the phase arch demands:** Goal G1 — Phase 3 exit criterion met without waiting for Phase 5's microVM substrate. C8 fixes the Port surface. ADR-0006 pins:
- Single-method Protocol (`async def run(spec) -> result`).
- `JailedSubprocessResult` tagged union with one variant per failure mode; no `dict[str, Any]`, no bare exceptions.
- Online-mode default with `RegistryAllowlist(["registry.npmjs.org"])` enforced at the netns / pf layer.
- `--ignore-scripts` set at both CLI and env (`npm_config_ignore_scripts=true`).

**Ambiguities surfaced before critiquing:**

- The story's `cwd` import path (`codegenie.plugins.sandbox_path` under `TYPE_CHECKING`) contradicts the already-shipped S1-04 shim (`codegenie.transforms._forward`). The shim's docstring is the canonical source: substitution happens *at the shim's import path*, not at the new module's. → Consistency critic finding (block-severity).
- ADR-0006 §Consequences defers async-vs-sync to adapter authors. The Port being `async` is correct; the Protocol's shape is the contract. → No finding.

---

## Stage 2 — Critic dossier (four lenses)

### Coverage critic

**Lens:** do the ACs guarantee the goal? Edge cases?

**Findings:**

| ID | Severity | Finding | Fix |
|---|---|---|---|
| COV-1 | harden | No AC asserts `cmd` is non-empty. `tuple[str, ...]` admits `()`. Spawning an empty command is meaningless. | New AC-3a: `min_length=1`. |
| COV-2 | harden | `time_budget_s` has no lower bound or finiteness validator. NaN, +Inf, -Inf, negative budgets all accepted. | New AC-3a: `gt=0` + `math.isfinite`. |
| COV-3 | harden | `memory_mib` / `pids_max` have no lower bound. Zero or negative caps undefined. | New AC-3a: `ge=1`. |
| COV-4 | harden | `RegistryAllowlist.hosts` accepts URLs without `https://`. `identifiers.py:71` doc says "Strict-`https://` ASCII registry URL" but `NewType` erases at runtime. | New AC-6a — strict-https smart-constructor validator. |
| COV-5 | harden | Result variants have no non-negative validators on counters (`stdout_bytes`, `wall_time_s`, etc.). A negative byte count or NaN wall-time is silently accepted. | New AC-4a — `ge=0` / `gt=0` per field, finiteness on floats. |
| COV-6 | harden | AC-15 schema snapshot only spot-checks the discriminator via `"discriminator" in str(schema)` substring. Underspecified. | Tightened to assert `propertyName == "kind"` + `len(oneOf) == 5`. |

No `block` findings on coverage (none break the goal); all `harden`.

---

### Test-quality critic

**Lens:** mutation thinking — would the TDD plan catch an obviously wrong implementation? Intent vs behavior (Rule 9)?

**Findings:**

| ID | Severity | Finding | Fix |
|---|---|---|---|
| TQ-1 | block | AC-7's `test_npm_env_to_env_mapping_strips_attempted_override` is tautological. The "override" attempt (`NpmEnv(extra={"npm_config_ignore_scripts": "false"})`) is rejected by `extra="forbid"` *before* `to_env_mapping()` runs — so the test is identical to the basic test. An implementation that hard-codes `return {"npm_config_ignore_scripts": "true"}` and throws away every other key passes both. The "structurally inviolable" intent is unenforced. | Three-tier mutation-resistant pattern: (a) constructive test, (b) AST source-grep that the literal `"true"` is the only RHS for that key inside `to_env_mapping`, (c) no public field name contains the env-key substring (no extension trapdoor). |
| TQ-2 | block | AC-11 test `assert "SandboxedPath" in repr(hints["cwd"])` is unverifiable. With `from __future__ import annotations` and `SandboxedPath: TypeAlias = pathlib.Path` (S1-04), `get_type_hints` resolves to `pathlib.Path`; substring `"SandboxedPath"` does not appear. | Rewritten as AST-level import check + `model_fields["cwd"].annotation is SandboxedPath` identity assertion. |
| TQ-3 | harden | AC-9 exhaustiveness test only confirms runtime coverage. The real protection — silent union widening — is mypy's narrowing on `assert_never`. Without a subprocess-mypy negative test, deleting a `match` arm passes silently. | New AC-9a — subprocess-mypy negative test mirroring S1-03's `test_outcomes_mypy_negative.py`. |
| TQ-4 | harden | AC-12 grep `"except Exception" not in src` false-positives on legitimate `class FooError(Exception): ...` declarations. | Regex-tightened: `re.search(r"^[ \t]*except[ \t]+Exception\b", src, re.MULTILINE)`. |
| TQ-5 | harden | AC-3 frozen test only mutates `time_budget_s`. A future field that's accidentally mutable would slip through. | Parametrized over the full field list. |
| TQ-6 | harden | `_StubJail` in AC-10 only returns `Completed`. Mutation thinking: an adapter that always returned `Completed` regardless of failure mode would pass. The Port surface must *admit* every variant — proven structurally by a stub that dispatches on `cmd[0]` and a parametrized test exercising each variant. | Updated AC-10 + the stub's test. |
| TQ-7 | harden | AC-1 grep test "no symbol leaks `Any` in its public annotation" is asserted but not implemented in the TDD plan. | Added `inspect.get_annotations` walk; AST walk in AC-12 catches `Any` outside docstrings. |

**Property-based opportunity:** round-trip-via-`model_dump`/`validate` for all variants is the canonical hypothesis pattern. Currently 5 fixed instances. Considered, *deferred* — Rule 2 (Simplicity First): the parametrized fixed set already kills the obvious mutations; hypothesis is more value for the consumer (S5-02) which has open inputs. Recorded as Notes-for-implementer opportunity but NOT promoted to AC.

---

### Consistency critic

**Lens:** does the story contradict the arch, ADRs, or CLAUDE.md? Do ACs trace to the goal?

**Findings:**

| ID | Severity | Finding | Fix |
|---|---|---|---|
| CS-1 | block | Story says `SandboxedPath` is imported from `codegenie.plugins.sandbox_path` (Goal #2 paragraph, AC-11, implementation outline step 2). `src/codegenie/transforms/_forward.py` lines 10-14 (already shipped via S1-04) pin the substitution path: "S4-04 — Replace the `SandboxedPath` `TypeAlias` with a re-export of `codegenie.plugins.sandbox_path.SandboxedPath` *from this module*. Every consumer keeps importing from `codegenie.transforms`; the import path stays stable." Following the story's instruction would import the symbol from the wrong location, defeating the shim's substitution discipline. | Per Rule 7 (surface conflicts, don't average; pick the more recent / load-bearing): `_forward.py` shipped first; this story now imports `SandboxedPath` from `codegenie.transforms._forward`. The original Notes-for-implementer paragraph that flagged the doc drift is rewritten to match. |
| CS-2 | harden | ADR-0006 §Tradeoffs row 4 says "every branch typed; no `dict[str, Any]`, no bare exceptions." Story honors. ✓ |
| CS-3 | harden | ADR-0010 (sum-type + smart-constructor discipline) implies smart-constructor invariants on `RegistryUrl`. Original story didn't validate `https://` prefix on `RegistryAllowlist.hosts`. | New AC-6a (matches identifiers.py:71 docstring). |
| CS-4 | nit | ADR list in story header missed ADR-0010 (sum-type discipline) and ADR-0033 production (sum-types-over-booleans) — both load-bearing for this story's shape. | Expanded ADRs-honored line. |
| CS-5 | nit | `JailedEnv | None` was never specified in the original story — `env: NpmEnv | GitEnv` is correct, but the *typed alias* (`JailedEnv = ...`) should exist as a named export so future code refers to the union, not the variants. | Added `JailedEnv` to `__all__` (AC-1). |

`CS-1` is the most consequential block-severity finding of the validation.

---

### Design-patterns critic

**Lens:** maintainability, extension-by-addition, design patterns.

**Findings:**

| ID | Severity | Finding | Fix |
|---|---|---|---|
| DP-1 | harden | `env: NpmEnv | GitEnv` is a structurally-dispatched Pydantic union with no `kind` discriminator. Pydantic v2 falls back to best-fit validation. The codebase precedent (`RecipeOutcome`, `RemediationOutcome`, `NodeTransition`, `AdapterConfidence`, `Applicability`, `NetworkPolicy`, `JailedSubprocessResult`) uses `Annotated[Union[...], Field(discriminator="kind")]` everywhere else. Inconsistent with codebase conventions (CLAUDE.md "Match the codebase's conventions"). The moment a third env type lands (S7-03's universal HITL fallback may need one), structural dispatch silently picks the wrong type. | New AC-2a: `JailedEnv = Annotated[NpmEnv | GitEnv, Field(discriminator="kind")]` with `kind: Literal["npm"]` / `Literal["git"]`. OCP-correct extension path. |
| DP-2 | harden | AC-1 asserts `set(dir(...)) >= EXPECTED` (superset). A leaked private helper passes. `__all__` is the established public-surface convention; the equality form is the correct contract. | AC-1 rewritten as `set(__all__) == EXPECTED`. |
| DP-3 | harden | AC-15 snapshot via `model_json_schema()` *without* `by_alias=True` omits the `discriminator` keyword from emitted JSON Schema (Pydantic v2 quirk). Phase 5's contract consumer relies on the discriminator metadata. | Implementation outline + AC-15 now specify `by_alias=True`. |
| DP-4 | nit | The Port is implicitly `@runtime_checkable`-friendly but the story doesn't pin. Runtime-checkable Protocols admit `isinstance` checks that ignore method signatures — a foot-gun. | New AC-2 assertion: `_is_runtime_protocol is False`. Documented in Notes for implementer. |
| DP-5 | rule-of-three deferred | A `VariantRegistry` for `JailedSubprocessResult` would maximize OCP — each adapter registers its failure-mode variant. Currently only 2 consumers (the two interim adapters); Phase 5's `FirecrackerAdapter` is the third. Per Rule 2 / Rule 8 ("three similar lines is better than premature abstraction"), defer. | Recorded in Notes-for-implementer; NOT promoted to AC. The current closed union is correct *for now*. |
| DP-6 | nit | `Completed` carries `stdout_bytes` / `stderr_bytes` (counts) but not content. Threat-model rationale (npm logs can leak `~/.npmrc` tokens) is implicit in the design but not documented. | Added Notes-for-implementer paragraph explaining the redirection-to-log discipline. |

No `block` design-pattern findings; the Hexagonal Port shape is correct.

---

## Stage 3 — Research

**Skipped.** No critic finding tagged `NEEDS RESEARCH`. All findings are codebase-specific (S1-04 shim, S1-03 outcomes precedent, identifiers.py docs) or canonical Pydantic v2 patterns. Stage-3 research without a question is token-burn (skill README).

---

## Stage 4 — Synthesis + edits applied

**Conflict resolution applied:**

- **DP-1 (env discriminator) vs Rule 2 (Simplicity First).** Two env types is the *threshold* — Pydantic v2 dispatches structurally on field shape, but the literal-discriminator pattern is established repo-wide and the cost of adding `kind: Literal["npm"|"git"]` is one line per model. Inconsistency with codebase convention is the dominant cost. Resolved in favor of the discriminator (CLAUDE.md "Match the codebase's conventions, even if you disagree").

- **CS-1 (SandboxedPath import) vs original story's prescription.** Resolved by Rule 7 + Rule 8: the `_forward.py` shim is shipped and documents its own substitution discipline; the original draft contradicts a shipped convention. The shim wins.

- **TQ-1 (AC-7 mutation resistance) vs simplicity.** The original AC-7 was *less than one assertion* (tautology). The fix is one extra AST-walk test plus a one-line no-trapdoor check — net code is small, and the inviolability claim is now actually enforced.

**Edits applied to story file** (full diff visible in `git log`):

1. Status: `Ready` → `HARDENED`.
2. ADRs-honored expanded (CS-4): +ADR-0010, +ADR-0011 framing, +production ADR-0033.
3. Validation-notes block appended (10 entries summarizing every change).
4. Goal section: discriminator on `JailedEnv` (DP-1), import path correction (CS-1), smart-constructor bounds (COV-1..3), strict-`https://` validator (COV-4, CS-3), non-negative result counters (COV-5), `__all__` discipline (DP-2), `@runtime_checkable` negative (DP-4).
5. ACs: AC-1 tightened (equality + `Any` walk); AC-2 split to add `@runtime_checkable` negative; new AC-2a (env discriminator); AC-3 parametrized; new AC-3a (smart-constructor bounds); new AC-4a (non-negative variants); new AC-6a (strict-`https://`); AC-7 rewritten with three-tier inviolability; AC-8 mirrors AC-7's pattern; new AC-9a (mypy-negative); AC-10 widened to admit every variant; AC-11 rewritten (AST + identity); AC-12 regex-tightened; AC-15 specificity tightened with `by_alias=True` + structural assertions.
6. Implementation outline: import path corrected; `__all__` first; smart-constructor validators wired into each model.
7. TDD plan: red tests rewritten end-to-end to match the new ACs (mutation-resistant pattern at AC-7 / AC-8 / AC-9a / AC-10 / AC-11 / AC-12 / AC-15).
8. Files-to-touch: added the new mypy-negative + contract-snapshot test files.
9. Notes for implementer: import-discipline rewrite, `--ignore-scripts` discipline rewrite, smart-constructor anchor for `RegistryUrl`, JailedEnv OCP path, `Completed` byte-count rationale, `@runtime_checkable` foot-gun, `__all__` contract, deferred `VariantRegistry` opportunity.

---

## Verdict

**HARDENED.** The story now:

- Traces every AC to the goal (G1 → exit criterion → Port surface → variant taxonomy → bounds → schema snapshot).
- Has every AC individually verifiable (no "handles errors gracefully" smells).
- Includes mutation-resistant tests at every load-bearing claim (AC-7 inviolability, AC-9 exhaustiveness, AC-11 import path, AC-12 typed discipline).
- Honors the Phase-3-Step-1 shipped conventions (`_forward.py` shim, discriminated-union precedent, `Any`-fence, sum-type discipline).
- Leaves a documented OCP extension path for the next adapter generation (Phase 5 `FirecrackerAdapter`) without pre-building it (Rule 2 + Rule 8).

Ready for `phase-story-executor`.
