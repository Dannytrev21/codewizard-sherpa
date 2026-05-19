# Validation report — S5-04 — `LockfilePolicy` YAML + Pydantic loader + `evaluate` (Gap 2 fix)

**Validated:** 2026-05-19
**Validator:** phase-story-validator skill (autonomous run via `story-validation-corrector` scheduled task)
**Verdict:** **HARDENED**
**Story file:** `docs/phases/03-vuln-deterministic-recipe/stories/S5-04-lockfile-policy-yaml.md`

---

## Context brief

S5-04 closes **Gap 2** from `phase-arch-design.md` by shipping a codegenie-owned `LockfilePolicy` that the Stage-6 validator (S6-04) lifts into one of the five Phase-3 `TrustSignal`s (`lockfile_policy`). The story specifies:

- Where the policy YAML lives (codegenie-owned; **not** analyzed-repo overrideable).
- The smart-constructor + evaluator API surface.
- The `PolicyViolation` discriminated union (one Phase-3 variant; structurally Phase-7-ready).
- The adversarial regression case (`tests/fixtures/repos/malicious-npmrc/`).

**As-built kernel the validator pulled in:**

- `src/codegenie/result.py` — `Result = Annotated[Ok[T] | Err[E], Field(discriminator="kind")]`; `is_ok()` / `is_err()` are **methods**; `Ok.value` / `Err.error` are the field names.
- `src/codegenie/types/errors.py` — `ParseError` is `frozen=True, extra="forbid"` with **only** `(message, value)`. ADR-0010 ratified that shape.
- `src/codegenie/types/identifiers.py` — `RegistryUrl = NewType("RegistryUrl", str)`.
- `src/codegenie/types/parsers.py` — `parse_registry_url(s) -> Result[RegistryUrl, ParseError]` enforces `https://`, host regex, no userinfo / query / fragment.
- `src/codegenie/_phase3_fence.py` + `tests/fence/test_no_any_in_plugin_surface.py` — `Any` is **structurally banned** under `src/codegenie/transforms/`; the only escape hatch is `# fence: any-allowed [P3-ADR-NNNN]` on the offending line, referencing a real Phase-3 ADR.
- `src/codegenie/skills/loader.py` — established precedent: each loader owns a *local* discriminated-union error type (`SkillsLoadError`), NOT an extended `ParseError`. Variant fields include `list[dict[str, object]]` (fence-clean) for Pydantic `ValidationError.errors()`.
- `src/codegenie/transforms/outcomes.py` — `RecipeError.details: dict[str, str | int | bool | float] | None`, NOT `dict[str, Any]`.

---

## Stage 2 — Four critic reports (single combined synthesis)

The four critics ran in a single combined synthesis because they all converged on the same root: drift between the as-written story and the as-built kernel. Findings tagged BLOCK / HARDEN / NIT.

### A. Coverage critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| A1 | HARDEN | No port-mismatch AC (`https://registry.npmjs.org:443/` vs `https://registry.npmjs.org/`). Implementer notes mentioned it as "defensible"; without an AC, the executor's Validator pass would not catch a "normalize port 443" mutation. | Added AC-Eval-4 with explicit port-mismatch, userinfo-in-URL, and scheme-mismatch sub-bullets + dedicated tests. |
| A2 | HARDEN | No mutation-resistance test on the host-matching algorithm. A stub `evaluate` returning `[]` would pass everything except the one adversarial test. | Added property test (AC-Adv-2) covering allowlist membership in both directions + metamorphic test (AC-Adv-3) covering allowlist widening. |
| A3 | HARDEN | `unknown_schema_version` AC didn't pin the `supported` payload tuple — a stub returning the right `reason` with `supported=()` would pass. | AC-Ver-1 now asserts `supported == (1,)` AND `observed == 2`. |
| A4 | HARDEN | First-failing-step contract not pinned; story said "validation order" but no test exercised it. | Added `test_from_yaml_first_failing_step_wins` exercising "wrong version + empty list + extra field" returning `unknown_schema_version`. |
| A5 | HARDEN | `null` allowed_registries and "missing trailing slash" URL were left in implementer notes — not ACs. | Added `test_from_yaml_null_allowed_registries_rejected` and `test_from_yaml_invalid_registry_url_no_trailing_slash`. |
| A6 | HARDEN | `PolicyViolation` discriminator round-trip not tested. Phase 7 will add variants; a wrong discriminator config wouldn't be caught until Phase 7 lands. | Added AC-Union-3 + two `TypeAdapter[PolicyViolation]` tests (round-trip + reject unknown kind). |
| A7 | NIT | No purity fence on `evaluate`. Implementation outline showed pure code, but nothing structural prevents a future maintainer from sneaking `time.time()` in. | Added AC-Eval-7 + `tests/fence/test_lockfile_policy_evaluate_is_pure.py` AST-walk. |

### B. Test-Quality critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| B1 | **BLOCK** | `result.is_ok` (no parens) is a truthy bound-method reference. `assert result.is_ok` always passes; `assert not result.is_ok` always **fails**. Every error test (`test_from_yaml_file_missing` etc.) would error out at the `assert not result.is_ok` line — but for the wrong reason, and `result.error` access would AttributeError before reaching the `.reason` check. | Rewrote every test to use `result.is_ok()` / `result.is_err()` with parentheses + `err = result.unwrap_err()` for typed access. |
| B2 | **BLOCK** | `Result.Ok(policy)` / `Result.Err(ParseError(...))` constructor pattern is invalid. `Result` is a `TypeAlias`, not a class with `.Ok` / `.Err` attributes. Implementer would either hit `AttributeError` or hand-roll a hostile shim. | Rewrote ACs and tests to use `Ok(value=policy)` / `Err(error=PolicyFileMissing(path=path))`, matching the established `skills/loader.py:251` precedent. |
| B3 | **BLOCK** | Tests construct `ParseError(reason="file_missing", path=...)` — but the canonical `ParseError` is `(message, value)` with `extra="forbid"`. Pydantic would raise on the `reason` and `path` kwargs. | Introduced module-local `PolicyLoadError` discriminated union with six variants (`PolicyFileMissing` etc.). The canonical `ParseError` stays untouched. |
| B4 | HARDEN | Property-based tests absent. A stub `evaluate` returning `[]` passes 11 of 12 happy/sort tests; only the load-bearing adversarial test fails. Mutation-resistance is weak. | Added AC-Adv-2 (Hypothesis property: iff `host not in allowed`) + AC-Adv-3 (metamorphic widening). |
| B5 | HARDEN | The shipped-yaml smoke test was loosely worded (`assert result.is_ok` again). | Tightened to `result.is_ok()` + `policy.allowed_registries` contains the expected URL. |
| B6 | NIT | Tests typed as `def test_...(tmp_path):` instead of `def test_...(tmp_path: Path) -> None:`. The project uses `mypy --strict`; tests as-written would either need a `# type: ignore` per file or fail typecheck. | All test signatures now carry `Path` annotation and `-> None`. |

### C. Consistency critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| C1 | **BLOCK** | `evaluate(self, lockfile_doc: dict[str, Any])` violates `tests/fence/test_no_any_in_plugin_surface.py` (S1-05 GREEN). The proposed `# noqa: codegenie-no-any-in-contract` marker also does not match the fence's actual grammar (`# fence: any-allowed [P3-ADR-NNNN]`) — it would itself be flagged as a bare marker. ADR-0010 §Consequences explicitly bans `dict[str, Any]` in the contract layer. | Replaced with `evaluate(lockfile_doc: Mapping[str, object])` + `isinstance` narrowing. Aligns with `SchemaViolation.details: list[dict[str, object]]` precedent at `skills/loader.py:129`. |
| C2 | **BLOCK** | Story prescribes extending `ParseError` with `reason: Literal["file_missing" \| ...]`, `path`, `line`, `col` etc. — but `codegenie.types.errors.ParseError` is `frozen=True, extra="forbid"` with `(message, value)`. ADR-0010 ratified the shape; extending it would fork the canonical home consumed by every Phase-3 smart constructor (Rule 7 violation). | Introduced module-local `PolicyLoadError` discriminated union (`Annotated[<six variants>, Field(discriminator="reason")]`). Canonical `ParseError` untouched. |
| C3 | **BLOCK** | `LOCKFILE_POLICY_PATH` outline said "Path(codegenie.__file__).resolve().parent / .. / .. / tools / policy / ..." — works under editable, breaks under wheel install (the wheel doesn't carry repo-root `tools/`). Story acknowledged "surface this in the PR if wheel install path is broken; pick one and document; do not average" but then specified both. | Pinned **one** mechanism: `importlib.resources.files("codegenie.transforms.policy") / "lockfile-policy.yaml"`; ship the YAML inside the package via `pyproject.toml` package_data; keep `tools/policy/lockfile-policy.yaml` as a canonical mirror with a bytewise-equality unit test. |
| C4 | HARDEN | `tests/fence/test_lockfile_policy_path_is_codegenie_owned.py` is a unit test (`monkeypatch.chdir` + assert), not an AST-walk structural fence. `tests/fence/` is reserved for AST-walking defenses per `docs/contributing.md` "Structural defense tests". | Renamed to `tests/unit/transforms/test_lockfile_policy_path_is_codegenie_owned.py`. `tests/fence/test_lockfile_policy_evaluate_is_pure.py` (new) is the actual fence — AST-walking. |
| C5 | HARDEN | CODEOWNERS AC was non-binary ("if present, add it; if not, file a follow-up note"). Executor can't pass/fail. | Replaced with a unit test that branches on `Path("CODEOWNERS").is_file() or Path(".github/CODEOWNERS").is_file()`: when present, asserts both policy paths are listed; when absent, asserts the codegenie-owned header is in both YAMLs. Binary pass/fail. |
| C6 | HARDEN | `RegistryUrl(...)` is `NewType` — `lambda x: x`. Test fixtures using `RegistryUrl("https://registry.npmjs.org/")` are syntactically fine but bypass validation. Story should clarify the validation seam is `parse_registry_url`, not the constructor. | Implementation outline §6 now explicitly states "`RegistryUrl(...)` is the lift; the validation seam is `parse_registry_url(url)` from `codegenie.types.parsers` (S1-01)". |

### D. Design-Patterns critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| D1 | HARDEN | The `PolicyViolation` discriminated union is correctly placed for Open/Closed extension by addition — Phase 7 adds new variants in a new module. **But:** the story didn't pin that contract. A Phase-7 implementer could easily edit `lockfile_policy.py` to add the variant, losing the Open/Closed property. | Locked the rule in module docstring + AC-Union-1 + Notes-for-implementer: "**Phase 7 widens the union in a new module; this file is not edited.**" |
| D2 | NIT | Story did not flag the rule-of-three threshold for a policy-rule registry. Phase 3 ships one rule; introducing a `PolicyRule` Protocol now would be premature pluggability. | Added Notes-for-implementer line: "kernel-rule-of-three has NOT been reached; do NOT introduce a `PolicyRule` Protocol or `@register_policy_rule` registry in this story (Rule 2 — three similar lines beats premature abstraction)." |
| D3 | HARDEN | Functional-core / imperative-shell line is implicit but unenforced. `evaluate` is pure; `from_yaml` is the only side-effecting path. A future maintainer adding `time.time()` to `evaluate` would not be caught by any test. | Added AC-Eval-7 + AST-walking fence test (`tests/fence/test_lockfile_policy_evaluate_is_pure.py`). |
| D4 | NIT | Smart-constructor pattern is correctly applied (`from_yaml` returns `Result`; raw `__init__` is permitted but not the boundary). Implementation outline §6 stated `parse_registry_url` is the validation; consistency with `skills/loader.py` precedent confirmed. | No edit; recorded for completeness. |
| D5 | NIT | Two-copy YAML system (mirror at `tools/policy/` + in-package copy) is *usually* a smell. The bytewise-equality test mitigates drift; documented the costs and the natural collapse path (delete the mirror) in Notes. | Added Notes-for-implementer paragraph on the mirror's purpose. |

---

## Stage 3 — Researcher

**Not invoked.** All findings resolved by direct edit + reference to in-repo precedents (`skills/loader.py`, `_phase3_fence.py`). No `NEEDS RESEARCH` tags.

---

## Stage 4 — Synthesizer + Editor

### Conflict resolutions

- **Conflict: keep `ParseError` extended vs. introduce a local `PolicyLoadError`.** Consistency wins (ADR-0010 ratified `ParseError` as `(message, value)`; the precedent for module-local discriminated-union errors is `SkillsLoadError`). The local error type matches every other Phase-3 boundary loader.
- **Conflict: `dict[str, Any]` with marker vs. `Mapping[str, object]` with isinstance narrowing.** Consistency wins again (ADR-0010 + the fence ban). The marker grammar in the original draft would have failed the fence regardless, and ADR-0010 explicitly bans `dict[str, Any]` in the contract layer.
- **Conflict: `Path(__file__)`-based path resolution vs. `importlib.resources`.** Rule 7 — pick one. Picked `importlib.resources` because (a) wheel-compatible without per-build-backend logic, (b) does not depend on cwd, (c) `as_file()` handles both editable + wheel installs uniformly. Cost: must ship YAML as package_data in `pyproject.toml`. Mitigation: the mirror at `tools/policy/` is the human-review surface.

### Edits applied (story file diff)

- **Status:** `Ready` → `HARDENED`.
- **Added** "Validation notes (2026-05-19, phase-story-validator)" block immediately after the header — summarizes the five BLOCK-grade drifts + the rationale.
- **Rewrote Goal** to name `PolicyLoadError`, `Mapping[str, object]`, the in-package YAML path + canonical mirror.
- **Rewrote Acceptance Criteria** as labeled buckets (`AC-File-*`, `AC-Surface-*`, `AC-Err-*`, `AC-Load-*`, `AC-Eval-*`, `AC-Union-*`, `AC-Adv-*`, `AC-Own-*`, `AC-Codeowners-*`, `AC-Ver-*`, `AC-Mech-*`) — each individually verifiable, each tracing to a TDD test.
- **Rewrote Implementation outline** §1–§10 with the canonical `importlib.resources` resolution, the `PolicyLoadError` discriminated union, the `Mapping[str, object]` evaluator, and the pinned validation order.
- **Rewrote TDD plan tests** end-to-end with the correct `Result` API (`is_ok()`/`is_err()` methods, `Ok(value=...)`/`Err(error=...)` constructors, `result.unwrap_err()` for error access). Added property test (`hypothesis`), metamorphic test, port/userinfo/scheme tests, discriminator round-trip tests, first-failing-step test, and the AST-walking purity fence.
- **Rewrote Files-to-touch** table: in-package YAML + mirror + `pyproject.toml` update + four new unit tests + one new fence test + CODEOWNERS entries.
- **Rewrote Notes-for-implementer** to record the validation hardenings (no `Any`, local error type, wheel-install pinning, mirror rationale, Open/Closed via discriminated union, functional-core).

### Before / after snippets (key drifts)

| Site | Before | After |
|---|---|---|
| AC `from_yaml` happy path | `Result.Ok(policy)` | `Ok(value=policy)` (with `PolicyLoadError` typed `Err`) |
| Test `is_ok` check | `assert result.is_ok` | `assert result.is_ok()` |
| Test error access | `assert not result.is_ok and result.error.reason == "file_missing"` | `assert result.is_err(); err = result.unwrap_err(); assert err.reason == "file_missing"` |
| `evaluate` signature | `def evaluate(self, lockfile_doc: dict[str, Any])` | `def evaluate(self, lockfile_doc: Mapping[str, object])` |
| Error type | `ParseError(reason="file_missing", path=...)` | `PolicyFileMissing(reason="file_missing", path=...)` (in `PolicyLoadError` union) |
| Path resolution | `Path(codegenie.__file__).parent / ".." / ".." / "tools" / ...` (with "surface in PR" branch) | `files("codegenie.transforms.policy") / "lockfile-policy.yaml"` (one mechanism, package_data-shipped) |
| Fence test housing | `tests/fence/test_lockfile_policy_path_is_codegenie_owned.py` (a unit test mis-housed) | `tests/unit/transforms/test_lockfile_policy_path_is_codegenie_owned.py` + new genuine fence `tests/fence/test_lockfile_policy_evaluate_is_pure.py` (AST-walk) |
| CODEOWNERS AC | "If CODEOWNERS doesn't exist yet, file a follow-up note" (non-binary) | Unit test branches binary on presence; tests header invariant in absence, listing invariant in presence |

---

## Verdict

**HARDENED.** The story now traces every AC to either a runtime-verifiable test or a structural defense. The original draft had five BLOCK-grade drifts from the as-built kernel (canonical `ParseError`, canonical `Result` API, `Result.Ok/Err` non-existence, `dict[str, Any]` fence, wheel/editable averaging) — all five corrected with reference to in-repo precedents. The TDD plan now contains property + metamorphic tests that would catch a stub `evaluate` returning `[]`. The codegenie-owned invariant is now anchored by an `importlib.resources` resolution + a bytewise-equality test + a binary-pass CODEOWNERS check. The Open/Closed seam (discriminated union widened by addition) is documented in module docstring and Notes-for-implementer. Ready for `phase-story-executor`.
