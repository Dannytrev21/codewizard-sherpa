# Story S5-04 — `LockfilePolicy` YAML + Pydantic loader + `evaluate` (Gap 2 fix)

**Step:** Step 5 — Transform ABC consumers, RecipeEngine Protocol, RecipeRegistry, lockfile policy
**Status:** HARDENED
**Effort:** M
**Depends on:** S5-02
**ADRs honored:** ADR-0010, ADR-0011, ADR-0001

## Validation notes (2026-05-19, phase-story-validator)

The original draft drifted from the as-built kernel in five BLOCK-grade ways. The drifts are corrected below in place; full audit trail in `_validation/S5-04-lockfile-policy-yaml.md`.

1. **`ParseError` shape drift** — the canonical Phase-3 `ParseError` at `src/codegenie/types/errors.py` is `frozen=True, extra="forbid"` with **only** `message: str` + `value: str`. The original draft prescribed `ParseError(reason="file_missing", path=...)` — a shape that does not exist and cannot be added without an ADR-0010 amendment. **Fix:** introduce a module-local `PolicyLoadError` discriminated union (one variant per failure mode), mirroring the established `SkillsLoadError` precedent at `src/codegenie/skills/loader.py:139` (which is `Annotated[SymlinkRefused | UnsafeYaml | … | IoFailure, Field(discriminator="reason")]`). `from_yaml` returns `Result[LockfilePolicy, PolicyLoadError]`. The canonical `ParseError` stays untouched.
2. **`Result` API drift** — the as-built `Result` (`src/codegenie/result.py`) exposes `is_ok()` / `is_err()` **as methods** (not properties), and only the `Err` variant carries `.error`. The original draft tests used `result.is_ok` (a truthy bound-method ref — would silently pass), `not result.is_ok` (always `False` — every error test would fail green), and `result.error.reason` (attribute access on `Result`, undefined on `Ok`). **Fix:** every test now uses `result.is_err()` / `result.is_ok()` with parentheses, and accesses the error through `err = result.unwrap_err(); assert err.reason == "..."` or `match` on the union.
3. **`Result.Ok(...)` / `Result.Err(...)` constructor drift** — `Result` is a `TypeAlias` (`Annotated[Ok[T] | Err[E], Field(discriminator="kind")]`); it has no `.Ok` / `.Err` attributes. **Fix:** every construction site uses `Ok(value=policy)` / `Err(error=PolicyFileMissing(path=path))`, mirroring `src/codegenie/skills/loader.py:251` precedent.
4. **`dict[str, Any]` fence violation** — `tests/fence/test_no_any_in_plugin_surface.py` (S1-05 GREEN) structurally bans `Any` under `src/codegenie/transforms/`. The original draft's `evaluate(lockfile_doc: dict[str, Any])` would fail the fence; the proposed `# noqa: codegenie-no-any-in-contract` marker doesn't match the actual grammar (`# fence: any-allowed [P3-ADR-NNNN]`) and would itself be flagged. ADR-0010 §Consequences explicitly rules out `dict[str, Any]` in the contract layer. **Fix:** evaluator signature is `evaluate(lockfile_doc: Mapping[str, object]) -> list[PolicyViolation]`; walks with explicit `isinstance` narrowing (the `SchemaViolation.details: list[dict[str, object]]` precedent at `skills/loader.py:129` already validates `object` against the fence). No ADR amendment needed.
5. **Wheel-install ambiguity (Rule 7 averaging)** — original outline left wheel resolution as a "surface in the PR" branch. **Fix:** pin **one** mechanism — `LOCKFILE_POLICY_PATH = importlib.resources.files("codegenie.transforms.policy") / "lockfile-policy.yaml"` — and ship the YAML *inside the package* (`src/codegenie/transforms/policy/lockfile-policy.yaml`) with `tools/policy/lockfile-policy.yaml` as a **canonical mirror** kept in lockstep via a Make target + bytewise-equality test (the `tools/` copy is the human-review surface; the in-package copy is the runtime-loaded one). `pyproject.toml` `[tool.setuptools.package-data]` ships the YAML in the wheel.

Additional hardening: explicit port-mismatch AC (E1), property-based / metamorphic test row in TDD plan, structural fence on `evaluate`'s no-I/O purity, sharpened CODEOWNERS AC (binary pass/fail), and re-housed the codegenie-owned-path test under `tests/unit/transforms/` (it is a unit test, not an AST-walking fence test — `tests/fence/` is reserved for structural defenses per the contributing docs).

## Context

This story closes **Gap 2** from `../phase-arch-design.md` (§Gap 2). `LockfilePolicySignal` is one of the five `TrustSignal`s the Stage-6 validator emits (`build`, `install`, `tests`, `lockfile_policy`, `cve_delta` — §C6 SignalKind registry). The synthesis named the signal but never specified **where the policy lives, who owns it, or what shape it takes**. Without that pinned, two failure modes are inevitable: (a) the policy migrates into the analyzed repo's `.codegenie/`, making the analyzed repo write its own security policy (a defense-in-depth violation); or (b) the policy is hard-coded in Python and impossible to tune without a code change (operationally hostile).

The fix mirrors Phase 5's `tools/policy/sandbox-policy.yaml` ownership model: **codegenie owns the policy file**, lives at `tools/policy/lockfile-policy.yaml` in *this* repository (not the analyzed repository). The analyzed repo can never silently broaden codegenie's allowed-registry list — that's a Phase-3 PR + ADR amendment.

The policy itself is a single rule in Phase 3: `allowed_registries: list[RegistryUrl]`. The loader is `LockfilePolicy.from_yaml(path) -> Result[LockfilePolicy, ParseError]` (smart constructor — ADR-0010). The evaluator is `LockfilePolicy.evaluate(lockfile_doc) -> list[PolicyViolation]`. A `PolicyViolation` is a tagged-union; Phase 3 ships one variant: `UnauthorizedRegistry(registry, package)`. The empty-list case is `TrustSignal(kind="lockfile_policy", passed=True)`; any non-empty case is `passed=False` with the violations in `details`. Phase 7 widens the tagged union additively (e.g., `UnpinnedDigest`, `RegistryRedirect`).

The adversarial scenario this defends against — `../phase-arch-design.md §Edge case E7`: a `.npmrc` inside the analyzed repo redirects the npm registry to `attacker.example.com`. The `RegistryAllowlist` network policy (S4-01) catches outbound network attempts, but a *successfully completed* `npm install` against a permitted-by-network-but-not-by-policy registry would slip past — `LockfilePolicy.evaluate` is the in-process check on the lockfile contents after install. It reads the `resolved` URL on every package entry and matches against `allowed_registries`. The attacker-`.npmrc` fixture (`tests/fixtures/repos/malicious-npmrc/` from S8-01) is the regression case.

**Critical ownership statement**: the policy file is *codegenie-owned*. The analyzed repo cannot override it; the orchestrator (S6-04) loads it from `tools/policy/lockfile-policy.yaml` in the *codegenie* installation root, not from `<analyzed_repo>/tools/policy/`. This mirrors Phase 5's design choice for `sandbox-policy.yaml` (`docs/phases/05-sandbox-trust-gates/` — same ownership rationale).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap 2` — the exact problem and Improvement paragraph; this is the load-bearing reference.
  - `../phase-arch-design.md §C6` — `SignalKind` open registry; `lockfile_policy` is one of Phase 3's five registered signals.
  - `../phase-arch-design.md §Edge case E7` — adversarial `.npmrc` scenario; the regression target.
  - `../phase-arch-design.md §Patterns considered and deliberately rejected — Visitor on `lockfile_doc`` row — "Pattern matching on the discriminated unions handles dispatch" (the `LockfilePolicy.evaluate` walks the lockfile dict; no Visitor framework).
  - `../phase-arch-design.md §Phase boundaries — ADR-0021 (policy engine build-vs-adopt)` — Phase 3's `LockfilePolicySignal` is a one-rule policy applied in-process; the cumulative shape informs ADR-0021's adopt-vs-build decision in Phase 13.
- **Phase ADRs:**
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — ADR-0010 — `RegistryUrl` newtype; `PolicyViolation` discriminated union; smart constructor `LockfilePolicy.from_yaml` returning `Result`.
  - `../ADRs/0001-ship-phase5-contract-surface-by-name.md` — ADR-0001 — `TrustSignal` shape Phase 5 inherits; `lockfile_policy` SignalKind is one of the five Phase 3 registers.
- **Source design:**
  - `../final-design.md §Synthesis ledger row "LockfilePolicy YAML location"` (codegenie-owned).
- **High-level impl:**
  - `../High-level-impl.md §Step 5 — Features delivered` bullet 5 (`tools/policy/lockfile-policy.yaml` + `policy/lockfile_policy.py`); `Done criteria` line 4 (attacker-`.npmrc` fixture detection).
- **Related Phase 5 precedent:**
  - `docs/phases/05-sandbox-trust-gates/` — `tools/policy/sandbox-policy.yaml` ownership pattern; mirror it byte-for-byte at the codegenie ownership level.
- **Sibling stories:**
  - `S5-02-npm-lockfile-recipe-engine.md` — produces the lockfile this policy evaluates.
  - `S6-04-remediation-orchestrator.md` — Stage 6 validator that calls `policy.evaluate(lockfile_doc)` and lifts to `TrustSignal(kind="lockfile_policy", passed=..., details=...)`.
  - `S8-01-fixture-portfolio.md` — `malicious-npmrc/` fixture used by the adversarial assertion.
  - `S1-01-phase3-newtype-identifiers.md` — `RegistryUrl` newtype + smart constructor.

## Goal

Ship `src/codegenie/transforms/policy/lockfile-policy.yaml` (the runtime-loaded codegenie-owned file shipped as wheel package_data) plus its canonical mirror at repo-root `tools/policy/lockfile-policy.yaml` (the human-review surface), and `src/codegenie/transforms/policy/lockfile_policy.py` exposing:

- `LockfilePolicy` (Pydantic `frozen=True, extra="forbid"`).
- `LockfilePolicy.from_yaml(path: Path) -> Result[LockfilePolicy, PolicyLoadError]` — smart constructor returning a module-local discriminated-union error (NOT the canonical `ParseError`, which is fixed-shape per ADR-0010); mirrors the `SkillsLoadError` precedent at `src/codegenie/skills/loader.py:139`.
- `LockfilePolicy.evaluate(lockfile_doc: Mapping[str, object]) -> list[PolicyViolation]` — `Mapping[str, object]` keeps the contract layer `Any`-free per ADR-0010 §Consequences while accepting the orjson-decoded lockfile shape via `isinstance` narrowing.
- `PolicyViolation` — discriminated union; Phase 3 ships the single variant `UnauthorizedRegistry(kind="unauthorized_registry", registry: RegistryUrl, package: str)`; the union is structurally ready for Phase 7's additive variants (`UnpinnedDigest`, `RegistryRedirect`).

Adversarial test confirms `UnauthorizedRegistry` is correctly detected on the `tests/fixtures/repos/malicious-npmrc/` lockfile.

## Acceptance criteria

### File layout + ownership

- [ ] **AC-File-1** `src/codegenie/transforms/policy/lockfile-policy.yaml` exists and is the **runtime-loaded** file. Header comment: `# codegenie-owned. Per Phase 3 Gap 2 fix + ADR-0010. Analyzed repos cannot override. Changes require ADR amendment.`
- [ ] **AC-File-2** `tools/policy/lockfile-policy.yaml` exists at the repo root as the **canonical mirror** (the file humans review). Bytewise-equal to the in-package copy; a unit test (`tests/unit/transforms/test_lockfile_policy_mirror_in_sync.py`) opens both and asserts `read_bytes() == read_bytes()` and fails CI on drift.
- [ ] **AC-File-3** Both YAMLs contain exactly the Phase 3 single rule:
  ```yaml
  # codegenie-owned. Per Phase 3 Gap 2 fix + ADR-0010. Analyzed repos cannot override.
  schema_version: 1
  allowed_registries:
    - https://registry.npmjs.org/
  ```
- [ ] **AC-File-4** `pyproject.toml` ships `lockfile-policy.yaml` inside the wheel via either `[tool.setuptools.package-data] "codegenie.transforms.policy" = ["lockfile-policy.yaml"]` or the equivalent `[tool.hatch.build.targets.wheel.force-include]` entry — pick whichever the project already uses for non-Python assets. A unit test imports the policy through `importlib.resources.files("codegenie.transforms.policy") / "lockfile-policy.yaml"` and asserts `.is_file()`.

### Public surface + types

- [ ] **AC-Surface-1** `from codegenie.transforms.policy.lockfile_policy import LockfilePolicy, PolicyViolation, UnauthorizedRegistry, PolicyLoadError, LOCKFILE_POLICY_PATH` succeeds. Re-exported from `codegenie.transforms` (`src/codegenie/transforms/__init__.py`).
- [ ] **AC-Surface-2** `LockfilePolicy` is a Pydantic model with `model_config = ConfigDict(frozen=True, extra="forbid")` and fields `schema_version: Literal[1]`, `allowed_registries: tuple[RegistryUrl, ...]` (tuple — frozen, hashable, deterministic iteration).
- [ ] **AC-Surface-3** `LOCKFILE_POLICY_PATH: Final[Path]` is computed at module-import time via `importlib.resources.files("codegenie.transforms.policy") / "lockfile-policy.yaml"` (resolved to a `Path` via `as_file()` / cast). Story explicitly **does NOT** use `Path(codegenie.__file__).parent / ".." / ".."` or any cwd-relative resolution (Rule 7 — pick one; documented in module docstring).

### `PolicyLoadError` discriminated union (boundary parsing)

- [ ] **AC-Err-1** A module-local `PolicyLoadError` exists as `Annotated[PolicyFileMissing | PolicyYamlSyntax | PolicySchemaViolation | PolicyUnknownSchemaVersion | PolicyEmptyAllowlist | PolicyInvalidRegistryUrl, Field(discriminator="reason")]`, mirroring `src/codegenie/skills/loader.py:139` (`SkillsLoadError`). Each variant is a `frozen=True, extra="forbid"` Pydantic model with a `reason: Literal[...]` discriminator. **The canonical `codegenie.types.errors.ParseError` is NOT extended** — it stays the fixed-shape kernel ADR-0010 ratified.
- [ ] **AC-Err-2** Variants and field shapes:
  - `PolicyFileMissing(reason="file_missing", path: Path)`
  - `PolicyYamlSyntax(reason="yaml_syntax", path: Path, line: int, col: int, detail: str)`
  - `PolicySchemaViolation(reason="schema_violation", path: Path, errors: list[dict[str, object]])` — `errors` carries `ValidationError.errors()` shape (the same `list[dict[str, object]]` precedent established by `SchemaViolation` at `skills/loader.py:129`; `object` is fence-clean, `Any` is not).
  - `PolicyUnknownSchemaVersion(reason="unknown_schema_version", path: Path, observed: int, supported: tuple[int, ...])` — `supported` is a tuple (hashable, immutable) and at Phase 3 is exactly `(1,)`.
  - `PolicyEmptyAllowlist(reason="empty_allowlist", path: Path)`.
  - `PolicyInvalidRegistryUrl(reason="invalid_registry_url", path: Path, url: str, detail: str)`.

### `from_yaml` smart constructor (boundary)

- [ ] **AC-Load-1** `LockfilePolicy.from_yaml(path: Path) -> Result[LockfilePolicy, PolicyLoadError]` returns:
  - `Ok(value=policy)` on a valid YAML file.
  - `Err(error=PolicyFileMissing(path=path))` when `path` does not exist (uses `path.is_file()`; rejects directories).
  - `Err(error=PolicyYamlSyntax(...))` on YAML parse error — `line`/`col` populated from `yaml.YAMLError.problem_mark` when available, else `(0, 0)` with `detail` carrying the exception message.
  - `Err(error=PolicySchemaViolation(...))` on Pydantic `ValidationError`; `errors` is `ve.errors()`.
  - `Err(error=PolicyUnknownSchemaVersion(observed=observed, supported=(1,)))` when YAML loads but `schema_version != 1` (fires before the Pydantic `Literal[1]` validation in the version-negotiation path; see Implementation outline §6).
  - `Err(error=PolicyEmptyAllowlist(path=path))` when `allowed_registries` is the empty list — empty allowlist would deny every install, an operational footgun, not a valid policy.
  - `Err(error=PolicyInvalidRegistryUrl(url=u, detail=msg))` when any URL fails `parse_registry_url` (S1-01); fires the **first** invalid URL only (deterministic; matches the parser-error-first convention in `skills/loader.py`).
- [ ] **AC-Load-2** Validation order is pinned and tested: `is_file → yaml.safe_load → schema_version check (early-exit) → Pydantic validate → empty-allowlist check → per-URL parse`. Each step's branch is exercised by one negative test. A negative test for "schema_version=2 AND empty allowlist AND invalid URL" returns `PolicyUnknownSchemaVersion` (the first-failing-step contract).
- [ ] **AC-Load-3** Forbidden YAML shapes are rejected:
  - `allowed_registries: null` → `PolicySchemaViolation` (Pydantic catches None-vs-tuple).
  - Extra top-level field (`sneaky_extra_field: true`) → `PolicySchemaViolation` (`extra="forbid"`).
  - `schema_version: 2` → `PolicyUnknownSchemaVersion` with `supported == (1,)`.
  - `allowed_registries: [http://insecure/]` → `PolicyInvalidRegistryUrl` (no `https://`).
  - `allowed_registries: ["https://registry.npmjs.org"]` (missing trailing slash) → `PolicyInvalidRegistryUrl` (per `parse_registry_url` rule).

### `evaluate` algorithm (pure)

- [ ] **AC-Eval-1** Signature: `LockfilePolicy.evaluate(lockfile_doc: Mapping[str, object]) -> list[PolicyViolation]`. **`Mapping[str, object]` — not `dict[str, Any]`**; the fence at `tests/fence/test_no_any_in_plugin_surface.py` would block the latter without an ADR amendment (no such amendment exists; ADR-0010 §Consequences explicitly bans `dict[str, Any]` in the contract layer).
- [ ] **AC-Eval-2** Walks `lockfile_doc.get("packages")` (npm v3 schema; `dependencies` is v2 fallback, NOT supported in Phase 3 per §Edge case E1). When `packages` is missing OR not a mapping → returns `[]` (vacuously passing — empty input yields empty output).
- [ ] **AC-Eval-3** Per package entry: narrows `entry` via `isinstance(entry, Mapping)`; reads `entry.get("resolved")`; narrows via `isinstance(resolved, str)`. Non-string / missing `resolved` is **skipped** (root pkg, `link:`/`file:` workspace deps, partially-populated entries). Skip is silent — no warning, no violation.
- [ ] **AC-Eval-4** Host matching is **scheme + netloc exact** (strict `urlparse(url).netloc` equality, no normalization):
  - `https://registry.npmjs.org/express/-/express-4.19.2.tgz` MATCHES `https://registry.npmjs.org/` (allowed).
  - `https://attacker.example.com/...` does NOT match (violation).
  - **Port mismatch IS a host mismatch**: `https://registry.npmjs.org:443/...` does NOT match `https://registry.npmjs.org/` even though `443` is the default https port. Documented policy decision: strict equality beats normalization (defense-in-depth — an attacker who can inject `:443` is fishing for a comparison-normalization bug; we don't normalize). Test pins this.
  - **Credentials in URL** (`https://user:pass@registry.npmjs.org/`): `urlparse(...).hostname` is `registry.npmjs.org`, but `netloc` is `user:pass@registry.npmjs.org` — strict netloc equality treats this as a host mismatch (violation). Pinned by test.
  - **Non-https scheme** (`http://registry.npmjs.org/`): violation (allowed list is https-only by `parse_registry_url` validation; `evaluate` compares the scheme+netloc tuple, so `http://` ≠ `https://`).
- [ ] **AC-Eval-5** For each violation, the `registry` field is set to `RegistryUrl(f"{scheme}://{netloc}/")` (reconstructed origin with trailing slash); the `package` field is the lockfile key (e.g., `node_modules/express`).
- [ ] **AC-Eval-6** Returns a **sorted** list of violations: sort key is `(v.package, v.registry)` ascending. Determinism is load-bearing — `TrustSignal.details` flows into `remediation-report.yaml` golden tests downstream.
- [ ] **AC-Eval-7** **Functional-core purity:** `evaluate` and every helper it calls are pure (no `Path`, `open`, `os.`, `socket.`, `urllib.request`, `time.`, `random.`, `datetime.`). Enforced by `tests/fence/test_lockfile_policy_evaluate_is_pure.py` — an AST-walking test loads `lockfile_policy.py`, identifies the `evaluate` method + its transitive helper calls, and asserts none of those nodes contain `ast.Call` resolving to the banned names (mirrors the AST-walk pattern used by `_phase3_fence.py`).

### `PolicyViolation` discriminated union

- [ ] **AC-Union-1** `PolicyViolation = Annotated[UnauthorizedRegistry, Field(discriminator="kind")]` — one-arm union today, structurally ready for Phase 7's additive variants (`UnpinnedDigest`, `RegistryRedirect`). Documented in module docstring with the rule "**Phase 7 widens the union in a new module; this file is not edited**."
- [ ] **AC-Union-2** `UnauthorizedRegistry(BaseModel)` carries `model_config = ConfigDict(frozen=True, extra="forbid")`, `kind: Literal["unauthorized_registry"] = "unauthorized_registry"`, `registry: RegistryUrl`, `package: str`.
- [ ] **AC-Union-3** Round-trip discriminator behavior is tested via a Pydantic `TypeAdapter[PolicyViolation]`: `model_validate({"kind": "unauthorized_registry", "registry": "https://x/", "package": "p"})` round-trips; `model_validate({"kind": "unknown_kind", ...})` raises `ValidationError`. Locks the discriminator dispatch surface so Phase 7's new variant lands cleanly.

### Adversarial regression (load-bearing)

- [ ] **AC-Adv-1** `tests/unit/transforms/test_lockfile_policy.py::test_attacker_npmrc_lockfile_yields_unauthorized_registry` reads `tests/fixtures/repos/malicious-npmrc/package-lock.json` (a lockfile whose `resolved` URLs point at `attacker.example.com`) and asserts:
  - `len(violations) == 1`
  - `violations[0]` is an `UnauthorizedRegistry`
  - `violations[0].registry == RegistryUrl("https://attacker.example.com/")` (reconstructed origin, with trailing slash)
  - `violations[0].package == "node_modules/express"`
  - The check passes when run from a temp cwd (no analyzed-repo-cwd dependency).
- [ ] **AC-Adv-2** Property test (`hypothesis`): for any generated `(allowed_set, resolved_url_host)` pair where `host not in allowed_set`, `evaluate` yields exactly one violation per package entry with that resolved url; when `host in allowed_set`, zero violations. Generators use `st.from_regex(r"[a-z][a-z0-9.-]{2,40}")` for hostnames and a fixed-size `st.lists(... max_size=5)` allow-set.
- [ ] **AC-Adv-3** Metamorphic test: for any lockfile fixture `L` and policy `P`, **adding** an entry to `P.allowed_registries` can only **reduce or preserve** the count of violations on `L` — never increase. Asserted on the malicious-npmrc fixture across three policy variants (`P_strict ⊂ P_loose1 ⊂ P_loose2`).

### Codegenie-owned-not-repo-owned invariant

- [ ] **AC-Own-1** `tests/unit/transforms/test_lockfile_policy_path_is_codegenie_owned.py` (NOT under `tests/fence/` — `tests/fence/` is reserved for AST-walking structural defenses per `docs/contributing.md`):
  - Asserts `LOCKFILE_POLICY_PATH` is a real file (`.is_file() is True`).
  - Asserts `LOCKFILE_POLICY_PATH` resolves under the codegenie package root (`"codegenie/transforms/policy/lockfile-policy.yaml"` substring of `str(LOCKFILE_POLICY_PATH.resolve())`).
  - Creates a hostile `tools/policy/lockfile-policy.yaml` under a temp cwd via `monkeypatch.chdir(tmp_path)`; calls `LockfilePolicy.from_yaml(LOCKFILE_POLICY_PATH)`; asserts the loaded `allowed_registries` does NOT contain any `attacker.example.com` URL — the codegenie-owned-not-cwd-relative invariant.

### CODEOWNERS (binary-pass control)

- [ ] **AC-Codeowners-1** A unit test (`tests/unit/transforms/test_lockfile_policy_codeowners.py`) checks the state of `CODEOWNERS` and `.github/CODEOWNERS` in the repo:
  - If neither file exists: the test asserts that `src/codegenie/transforms/policy/lockfile-policy.yaml` and `tools/policy/lockfile-policy.yaml` both have the required header comment (`codegenie-owned. … Changes require ADR amendment.`) — that comment IS the documented control of last resort.
  - If either file exists: the test asserts BOTH paths are listed in it (one line each), so changes require a security-team review. Binary pass/fail — no story-author judgment call. No invention of CODEOWNERS if it's absent.

### Version negotiation

- [ ] **AC-Ver-1** A YAML with `schema_version: 2` returns `Err(error=PolicyUnknownSchemaVersion(observed=2, supported=(1,)))`. The test asserts both the discriminator (`reason == "unknown_schema_version"`) AND the `supported` tuple equals `(1,)` (catches a stub that returns the right `reason` with a wrong `supported`).

### Mechanical gates

- [ ] **AC-Mech-1** `mypy --strict src/codegenie/transforms/policy/lockfile_policy.py` clean.
- [ ] **AC-Mech-2** `tests/fence/test_no_any_in_plugin_surface.py` stays green — no `Any` annotation is introduced under `src/codegenie/transforms/policy/`. No `# fence: any-allowed` marker is added (none is needed; `Mapping[str, object]` satisfies the contract).
- [ ] **AC-Mech-3** `ruff check`, `ruff format --check`, `pytest tests/unit/transforms/test_lockfile_policy*.py tests/fence/test_lockfile_policy_evaluate_is_pure.py` all green.
- [ ] **AC-Mech-4** Branch coverage on `src/codegenie/transforms/policy/lockfile_policy.py` ≥ 95%.

## Implementation outline

1. Create `src/codegenie/transforms/policy/__init__.py` (empty re-export surface) and `src/codegenie/transforms/policy/lockfile_policy.py`.
2. Create `src/codegenie/transforms/policy/lockfile-policy.yaml` (the runtime-loaded file). Create the canonical mirror at repo-root `tools/policy/lockfile-policy.yaml`.
3. Add wheel inclusion in `pyproject.toml` (use whichever build backend the repo already uses for non-Python assets — check existing `package_data` / `force-include` entries first).
4. Define `LOCKFILE_POLICY_PATH: Final[Path]` exactly:
   ```python
   from importlib.resources import as_file, files
   _RESOURCE = files("codegenie.transforms.policy") / "lockfile-policy.yaml"
   with as_file(_RESOURCE) as _p:  # works under both editable and wheel installs
       LOCKFILE_POLICY_PATH: Final[Path] = Path(_p).resolve()
   ```
   Document the choice with a one-line comment: `# Codegenie-owned, wheel-shipped (Phase 3 Gap 2 fix; ADR-0010). Never cwd-relative.`
5. Define `UnauthorizedRegistry(BaseModel)` with `kind: Literal["unauthorized_registry"] = "unauthorized_registry"`, `registry: RegistryUrl`, `package: str`, `model_config = ConfigDict(frozen=True, extra="forbid")`. Define `PolicyViolation = Annotated[UnauthorizedRegistry, Field(discriminator="kind")]` (one-arm union; Phase 7 widens in a new module).
6. Define the six `PolicyLoadError` variants (`PolicyFileMissing`, `PolicyYamlSyntax`, `PolicySchemaViolation`, `PolicyUnknownSchemaVersion`, `PolicyEmptyAllowlist`, `PolicyInvalidRegistryUrl`) as separate `frozen=True, extra="forbid"` models with `reason: Literal["..."]` discriminators. Union: `PolicyLoadError = Annotated[<all six>, Field(discriminator="reason")]`. The shape is the established `SkillsLoadError` precedent at `src/codegenie/skills/loader.py:139`.
7. Define `LockfilePolicy(BaseModel)`:
   ```python
   class LockfilePolicy(BaseModel):
       model_config = ConfigDict(frozen=True, extra="forbid")
       schema_version: Literal[1]
       allowed_registries: tuple[RegistryUrl, ...]

       @classmethod
       def from_yaml(cls, path: Path) -> Result["LockfilePolicy", PolicyLoadError]: ...

       def evaluate(self, lockfile_doc: Mapping[str, object]) -> list[PolicyViolation]: ...
   ```
   Use `Mapping[str, object]` from `collections.abc` — fence-clean (no `Any`); the `isinstance` narrowing in `evaluate` recovers the precise shape at runtime.
8. `from_yaml` validation order (pinned by AC-Load-2):
   1. `path.is_file()` → else `PolicyFileMissing`.
   2. `yaml.safe_load` → on `YAMLError`, extract `problem_mark.line / problem_mark.column` if present, else `(0, 0)`. Use `safe_load` not `load`; do NOT introduce a YAML loader other than the stdlib `pyyaml` already in `requirements`.
   3. Extract `observed = data.get("schema_version")`; if it's an `int` ≠ 1, return `PolicyUnknownSchemaVersion(observed=observed, supported=(1,))` immediately. (This pre-empts the Pydantic `Literal[1]` validation, giving a discriminator-stable error before schema validation; otherwise Pydantic would emit a `PolicySchemaViolation` for a wrong-version YAML, which a Phase-7 v2-aware caller can't tell apart from a syntactically-wrong v1 YAML.)
   4. `LockfilePolicy.model_validate(data)` → on `ValidationError`, return `PolicySchemaViolation(errors=ve.errors())`.
   5. `if not validated.allowed_registries:` return `PolicyEmptyAllowlist(path=path)`.
   6. For each URL, call `parse_registry_url(url)` (from `codegenie.types.parsers`, S1-01); on the first `Err`, return `PolicyInvalidRegistryUrl(url=url, detail=<err.message>)`. (Pydantic's `RegistryUrl` `NewType` is `lambda x: x` — it does NOT validate; the smart constructor is the validation seam, so this step is necessary.)
9. `evaluate` algorithm (functional core — pure, fence-checked):
   ```python
   from collections.abc import Mapping
   from urllib.parse import urlparse

   def evaluate(self, lockfile_doc: Mapping[str, object]) -> list[PolicyViolation]:
       allowed_keys = {
           f"{urlparse(r).scheme}://{urlparse(r).netloc}/"
           for r in self.allowed_registries
       }
       violations: list[PolicyViolation] = []
       packages = lockfile_doc.get("packages")
       if not isinstance(packages, Mapping):
           return violations
       for pkg_path, entry in packages.items():
           if not isinstance(entry, Mapping):
               continue
           resolved = entry.get("resolved")
           if not isinstance(resolved, str):
               continue
           parsed = urlparse(resolved)
           origin = f"{parsed.scheme}://{parsed.netloc}/"
           if origin not in allowed_keys:
               violations.append(
                   UnauthorizedRegistry(
                       registry=RegistryUrl(origin),
                       package=pkg_path,
                   )
               )
       return sorted(violations, key=lambda v: (v.package, v.registry))
   ```
   Notes:
   - Strict `scheme://netloc/` equality (not `hostname`-only) — this is what makes the port-mismatch and credentials-in-URL ACs structural (AC-Eval-4).
   - `RegistryUrl(origin)` is the `NewType` lift; safe because `origin` was reconstructed from a parsed URL and is shaped `https?://<host>/`. (The strict `parse_registry_url` validation already ran on the *allow-list* entries at load time.)
   - No `Any`, no `dict[str, Any]`. The `isinstance(packages, Mapping)` and `isinstance(entry, Mapping)` narrowings keep mypy --strict green without a `cast` or `# type: ignore`.
10. Fixture for the adversarial test: `tests/fixtures/repos/malicious-npmrc/package-lock.json` (this story creates the *lockfile* portion; the full fixture including the malicious `.npmrc` is S8-01). The lockfile carries one entry with `resolved: "https://attacker.example.com/express/-/express-4.19.2.tgz"` plus a root entry (no `resolved`) to exercise the skip path.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths (note: `tests/fence/` only carries the AST-walking purity check; the path-is-codegenie-owned and CODEOWNERS tests are unit tests, NOT fence tests, per `docs/contributing.md` "Structural defense tests" — fence directory is reserved for repo-wide AST walkers):

- `tests/unit/transforms/test_lockfile_policy.py`
- `tests/unit/transforms/test_lockfile_policy_path_is_codegenie_owned.py`
- `tests/unit/transforms/test_lockfile_policy_mirror_in_sync.py`
- `tests/unit/transforms/test_lockfile_policy_codeowners.py`
- `tests/fence/test_lockfile_policy_evaluate_is_pure.py`

**Critical API reminders (the original draft drifted on these — all corrected below):**

- `Result` is a `TypeAlias`, NOT a class. Construct with `Ok(value=...)` / `Err(error=...)` — `Result.Ok(...)` does NOT exist.
- `is_ok()` and `is_err()` are **methods**, not properties: `result.is_ok()` not `result.is_ok`. Writing `result.is_ok` returns a truthy bound-method ref so every error test would silently pass green.
- Only the `Err` variant carries `.error`; `Ok` carries `.value`. Use `result.unwrap_err()` (or `match`) to read the error after `is_err()` narrows.

```python
# tests/unit/transforms/test_lockfile_policy.py
from collections.abc import Mapping
from pathlib import Path
import textwrap

import pytest
from pydantic import TypeAdapter

from codegenie.result import Err, Ok
from codegenie.transforms.policy.lockfile_policy import (
    LOCKFILE_POLICY_PATH,
    LockfilePolicy,
    PolicyLoadError,
    PolicyViolation,
    UnauthorizedRegistry,
)
from codegenie.types.identifiers import RegistryUrl


def _write_yaml(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "policy.yaml"
    p.write_text(textwrap.dedent(body).lstrip())
    return p


# ---- from_yaml --------------------------------------------------------------

def test_from_yaml_happy_path(tmp_path: Path) -> None:
    p = _write_yaml(tmp_path, """\
        schema_version: 1
        allowed_registries:
          - https://registry.npmjs.org/
    """)
    result = LockfilePolicy.from_yaml(p)
    assert result.is_ok()
    policy = result.unwrap()
    assert policy.allowed_registries == (RegistryUrl("https://registry.npmjs.org/"),)


def test_from_yaml_file_missing(tmp_path: Path) -> None:
    result = LockfilePolicy.from_yaml(tmp_path / "nope.yaml")
    assert result.is_err()
    err = result.unwrap_err()
    assert err.reason == "file_missing"
    assert err.path == tmp_path / "nope.yaml"


def test_from_yaml_yaml_syntax_error(tmp_path: Path) -> None:
    p = tmp_path / "p.yaml"
    p.write_text("foo: [unterminated")
    result = LockfilePolicy.from_yaml(p)
    assert result.is_err()
    err = result.unwrap_err()
    assert err.reason == "yaml_syntax"
    assert err.line >= 0 and err.col >= 0


def test_from_yaml_unknown_schema_version_2_pins_supported_tuple(tmp_path: Path) -> None:
    p = _write_yaml(tmp_path, "schema_version: 2\nallowed_registries: [https://x/]\n")
    result = LockfilePolicy.from_yaml(p)
    assert result.is_err()
    err = result.unwrap_err()
    assert err.reason == "unknown_schema_version"
    # AC-Ver-1: stub that only sets `reason` would fail here
    assert err.observed == 2
    assert err.supported == (1,)


def test_from_yaml_empty_allowlist_rejected(tmp_path: Path) -> None:
    p = _write_yaml(tmp_path, "schema_version: 1\nallowed_registries: []\n")
    result = LockfilePolicy.from_yaml(p)
    assert result.is_err()
    assert result.unwrap_err().reason == "empty_allowlist"


def test_from_yaml_invalid_registry_url_http_rejected(tmp_path: Path) -> None:
    p = _write_yaml(tmp_path, "schema_version: 1\nallowed_registries: [http://insecure/]\n")
    result = LockfilePolicy.from_yaml(p)
    assert result.is_err()
    err = result.unwrap_err()
    assert err.reason == "invalid_registry_url"
    assert err.url == "http://insecure/"


def test_from_yaml_invalid_registry_url_no_trailing_slash(tmp_path: Path) -> None:
    p = _write_yaml(tmp_path, "schema_version: 1\nallowed_registries: [https://registry.npmjs.org]\n")
    result = LockfilePolicy.from_yaml(p)
    assert result.is_err()
    assert result.unwrap_err().reason == "invalid_registry_url"


def test_from_yaml_extra_field_rejected(tmp_path: Path) -> None:
    p = _write_yaml(tmp_path, """\
        schema_version: 1
        allowed_registries: [https://registry.npmjs.org/]
        sneaky_extra_field: true
    """)
    result = LockfilePolicy.from_yaml(p)
    assert result.is_err()
    assert result.unwrap_err().reason == "schema_violation"


def test_from_yaml_null_allowed_registries_rejected(tmp_path: Path) -> None:
    p = _write_yaml(tmp_path, "schema_version: 1\nallowed_registries: null\n")
    result = LockfilePolicy.from_yaml(p)
    assert result.is_err()
    assert result.unwrap_err().reason == "schema_violation"


def test_from_yaml_first_failing_step_wins(tmp_path: Path) -> None:
    # AC-Load-2: schema_version is checked BEFORE schema_validation / empty_allowlist / per-URL
    p = _write_yaml(tmp_path, "schema_version: 2\nallowed_registries: []\nsneaky: true\n")
    result = LockfilePolicy.from_yaml(p)
    assert result.is_err()
    assert result.unwrap_err().reason == "unknown_schema_version"


# ---- evaluate ---------------------------------------------------------------

@pytest.fixture
def npm_policy() -> LockfilePolicy:
    return LockfilePolicy(
        schema_version=1,
        allowed_registries=(RegistryUrl("https://registry.npmjs.org/"),),
    )


def test_evaluate_empty_packages_returns_no_violations(npm_policy: LockfilePolicy) -> None:
    assert npm_policy.evaluate({"packages": {}}) == []


def test_evaluate_missing_packages_key_returns_no_violations(npm_policy: LockfilePolicy) -> None:
    assert npm_policy.evaluate({"lockfileVersion": 3}) == []


def test_evaluate_packages_not_a_mapping_returns_no_violations(npm_policy: LockfilePolicy) -> None:
    # Defensive: corrupted lockfile shape should not crash, just yield no violations
    assert npm_policy.evaluate({"packages": [1, 2, 3]}) == []


def test_evaluate_root_pkg_without_resolved_is_skipped(npm_policy: LockfilePolicy) -> None:
    doc: Mapping[str, object] = {"packages": {"": {"name": "root", "version": "1.0.0"}}}
    assert npm_policy.evaluate(doc) == []


def test_evaluate_link_workspace_dep_skipped(npm_policy: LockfilePolicy) -> None:
    doc: Mapping[str, object] = {
        "packages": {"node_modules/local-pkg": {"link": True, "resolved": None}}
    }
    assert npm_policy.evaluate(doc) == []


def test_evaluate_legit_registry_passes(npm_policy: LockfilePolicy) -> None:
    doc: Mapping[str, object] = {
        "packages": {
            "node_modules/express": {
                "version": "4.19.2",
                "resolved": "https://registry.npmjs.org/express/-/express-4.19.2.tgz",
            }
        }
    }
    assert npm_policy.evaluate(doc) == []


def test_evaluate_attacker_host_yields_violation(npm_policy: LockfilePolicy) -> None:
    # The Gap 2 regression — the load-bearing test for this story (AC-Adv-1)
    doc: Mapping[str, object] = {
        "packages": {
            "node_modules/express": {
                "version": "4.19.2",
                "resolved": "https://attacker.example.com/express/-/express-4.19.2.tgz",
            }
        }
    }
    violations = npm_policy.evaluate(doc)
    assert len(violations) == 1
    v = violations[0]
    assert isinstance(v, UnauthorizedRegistry)
    assert v.registry == RegistryUrl("https://attacker.example.com/")
    assert v.package == "node_modules/express"


def test_evaluate_port_mismatch_is_violation(npm_policy: LockfilePolicy) -> None:
    # AC-Eval-4 strict netloc equality — :443 != no port (even though 443 is default https)
    doc: Mapping[str, object] = {
        "packages": {
            "node_modules/express": {
                "resolved": "https://registry.npmjs.org:443/express/-/express-4.19.2.tgz",
            }
        }
    }
    violations = npm_policy.evaluate(doc)
    assert len(violations) == 1
    assert violations[0].registry == RegistryUrl("https://registry.npmjs.org:443/")


def test_evaluate_userinfo_in_url_is_violation(npm_policy: LockfilePolicy) -> None:
    # AC-Eval-4 credentials in URL make the netloc differ — treated as host mismatch
    doc: Mapping[str, object] = {
        "packages": {
            "node_modules/express": {
                "resolved": "https://user:pass@registry.npmjs.org/express/-/express-4.19.2.tgz",
            }
        }
    }
    violations = npm_policy.evaluate(doc)
    assert len(violations) == 1


def test_evaluate_http_scheme_is_violation(npm_policy: LockfilePolicy) -> None:
    # AC-Eval-4 strict scheme — http://registry.npmjs.org/ != https://registry.npmjs.org/
    doc: Mapping[str, object] = {
        "packages": {
            "node_modules/express": {
                "resolved": "http://registry.npmjs.org/express/-/express-4.19.2.tgz",
            }
        }
    }
    violations = npm_policy.evaluate(doc)
    assert len(violations) == 1


def test_evaluate_violations_sorted_deterministically(npm_policy: LockfilePolicy) -> None:
    # AC-Eval-6 stable sort by (package, registry)
    doc: Mapping[str, object] = {
        "packages": {
            "node_modules/z-bad": {"resolved": "https://evil2.example/z/-/z-1.tgz"},
            "node_modules/a-bad": {"resolved": "https://evil1.example/a/-/a-1.tgz"},
            "node_modules/m-bad": {"resolved": "https://evil1.example/m/-/m-1.tgz"},
        }
    }
    violations = npm_policy.evaluate(doc)
    assert [v.package for v in violations] == [
        "node_modules/a-bad",
        "node_modules/m-bad",
        "node_modules/z-bad",
    ]


# ---- property-based / metamorphic (AC-Adv-2, AC-Adv-3) ----------------------

from hypothesis import given, settings, strategies as st

_HOST = st.from_regex(r"^[a-z][a-z0-9.-]{2,40}$", fullmatch=True)


@settings(max_examples=200, deadline=None)
@given(
    allowed_hosts=st.lists(_HOST, min_size=1, max_size=4, unique=True),
    pkg_host=_HOST,
)
def test_property_evaluate_iff_host_not_in_allowlist(allowed_hosts: list[str], pkg_host: str) -> None:
    allowed = tuple(RegistryUrl(f"https://{h}/") for h in allowed_hosts)
    policy = LockfilePolicy(schema_version=1, allowed_registries=allowed)
    doc: Mapping[str, object] = {
        "packages": {"node_modules/p": {"resolved": f"https://{pkg_host}/p/-/p-1.tgz"}}
    }
    violations = policy.evaluate(doc)
    in_allowlist = any(pkg_host == h for h in allowed_hosts)
    assert (len(violations) == 0) == in_allowlist


@settings(max_examples=100, deadline=None)
@given(
    base_hosts=st.lists(_HOST, min_size=1, max_size=3, unique=True),
    extra_hosts=st.lists(_HOST, min_size=0, max_size=3, unique=True),
    pkg_hosts=st.lists(_HOST, min_size=1, max_size=5),
)
def test_metamorphic_widening_allowlist_only_reduces_violations(
    base_hosts: list[str], extra_hosts: list[str], pkg_hosts: list[str]
) -> None:
    # AC-Adv-3: adding to allowed_registries can only reduce or preserve violations
    p_strict = LockfilePolicy(
        schema_version=1,
        allowed_registries=tuple(RegistryUrl(f"https://{h}/") for h in base_hosts),
    )
    p_loose = LockfilePolicy(
        schema_version=1,
        allowed_registries=tuple(
            RegistryUrl(f"https://{h}/") for h in {*base_hosts, *extra_hosts}
        ),
    )
    doc: Mapping[str, object] = {
        "packages": {
            f"node_modules/p{i}": {"resolved": f"https://{h}/p{i}/-/p{i}-1.tgz"}
            for i, h in enumerate(pkg_hosts)
        }
    }
    assert len(p_loose.evaluate(doc)) <= len(p_strict.evaluate(doc))


# ---- PolicyViolation discriminator (AC-Union-3) -----------------------------

def test_policy_violation_typeadapter_round_trip() -> None:
    adapter = TypeAdapter(PolicyViolation)
    obj = adapter.validate_python(
        {"kind": "unauthorized_registry", "registry": "https://x/", "package": "p"}
    )
    assert isinstance(obj, UnauthorizedRegistry)
    assert adapter.dump_python(obj)["kind"] == "unauthorized_registry"


def test_policy_violation_typeadapter_rejects_unknown_kind() -> None:
    from pydantic import ValidationError
    adapter = TypeAdapter(PolicyViolation)
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {"kind": "not_a_real_kind", "registry": "https://x/", "package": "p"}
        )


# ---- shipped policy parses --------------------------------------------------

def test_shipped_lockfile_policy_yaml_loads_clean() -> None:
    result = LockfilePolicy.from_yaml(LOCKFILE_POLICY_PATH)
    assert result.is_ok()
    policy = result.unwrap()
    assert RegistryUrl("https://registry.npmjs.org/") in policy.allowed_registries
```

```python
# tests/unit/transforms/test_lockfile_policy_path_is_codegenie_owned.py
from pathlib import Path

import pytest

from codegenie.transforms.policy.lockfile_policy import (
    LOCKFILE_POLICY_PATH,
    LockfilePolicy,
)
from codegenie.types.identifiers import RegistryUrl


def test_path_is_a_real_file() -> None:
    assert LOCKFILE_POLICY_PATH.is_file()


def test_path_resolves_under_codegenie_package_root() -> None:
    s = str(LOCKFILE_POLICY_PATH.resolve())
    assert "codegenie/transforms/policy/lockfile-policy.yaml" in s


def test_path_immune_to_hostile_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    hostile = tmp_path / "tools" / "policy"
    hostile.mkdir(parents=True)
    (hostile / "lockfile-policy.yaml").write_text(
        "schema_version: 1\nallowed_registries: [https://attacker.example.com/]\n"
    )
    monkeypatch.chdir(tmp_path)
    result = LockfilePolicy.from_yaml(LOCKFILE_POLICY_PATH)
    assert result.is_ok()
    hosts = {str(r) for r in result.unwrap().allowed_registries}
    assert not any("attacker.example.com" in h for h in hosts)
```

```python
# tests/unit/transforms/test_lockfile_policy_mirror_in_sync.py
from pathlib import Path

from codegenie.transforms.policy.lockfile_policy import LOCKFILE_POLICY_PATH


def test_repo_root_mirror_byte_for_byte_equal_to_shipped() -> None:
    mirror = Path("tools/policy/lockfile-policy.yaml").resolve()
    assert mirror.is_file(), "canonical mirror missing — see Files-to-touch"
    assert mirror.read_bytes() == LOCKFILE_POLICY_PATH.read_bytes(), (
        "tools/policy/lockfile-policy.yaml drifted from src/codegenie/transforms/policy/lockfile-policy.yaml; "
        "the mirror is the human-review surface but the in-package copy is loaded at runtime — keep them equal."
    )
```

```python
# tests/unit/transforms/test_lockfile_policy_codeowners.py
from pathlib import Path

from codegenie.transforms.policy.lockfile_policy import LOCKFILE_POLICY_PATH

_HEADER = "codegenie-owned"


def _codeowners_paths() -> list[Path]:
    return [p for p in (Path("CODEOWNERS"), Path(".github/CODEOWNERS")) if p.is_file()]


def test_policy_files_carry_codegenie_owned_header() -> None:
    # Documented control of last resort (per AC-Codeowners-1 first branch)
    for p in (LOCKFILE_POLICY_PATH, Path("tools/policy/lockfile-policy.yaml")):
        assert _HEADER in p.read_text(), f"missing codegenie-owned header in {p}"


def test_codeowners_lists_both_policy_paths_when_present() -> None:
    files = _codeowners_paths()
    if not files:
        return  # other branch of AC-Codeowners-1 (header-only control)
    expected = {
        "tools/policy/lockfile-policy.yaml",
        "src/codegenie/transforms/policy/lockfile-policy.yaml",
    }
    listed: set[str] = set()
    for cf in files:
        for line in cf.read_text().splitlines():
            for path in expected:
                if path in line:
                    listed.add(path)
    assert listed == expected, f"CODEOWNERS missing {expected - listed}"
```

```python
# tests/fence/test_lockfile_policy_evaluate_is_pure.py
"""AC-Eval-7: structural fence on ``LockfilePolicy.evaluate`` — no I/O, no clock, no network.

AST-walk pattern mirrors ``codegenie._phase3_fence``: load the source, find
the ``evaluate`` method's body, recurse through every callee in the same
module, and assert no banned-name call (``Path``, ``open``, ``os.``,
``socket.``, ``urllib.request``, ``time.``, ``random.``, ``datetime.``)
appears anywhere in the closure.
"""
import ast
import inspect

from codegenie.transforms.policy import lockfile_policy as mod

_BANNED_NAMES = frozenset({"open", "Path"})
_BANNED_PREFIXES = ("os.", "socket.", "urllib.request", "time.", "random.", "datetime.")


def _collect_calls(tree: ast.AST) -> list[str]:
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                out.append(func.id)
            elif isinstance(func, ast.Attribute):
                # join nested attrs into a dotted string for prefix matching
                parts: list[str] = [func.attr]
                cur: ast.AST = func.value
                while isinstance(cur, ast.Attribute):
                    parts.append(cur.attr)
                    cur = cur.value
                if isinstance(cur, ast.Name):
                    parts.append(cur.id)
                out.append(".".join(reversed(parts)))
    return out


def test_evaluate_is_pure_no_io_no_clock() -> None:
    src = inspect.getsource(mod)
    tree = ast.parse(src)
    evaluate_node: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "evaluate":
            evaluate_node = node
            break
    assert evaluate_node is not None, "evaluate() method not found in lockfile_policy.py"
    calls = _collect_calls(evaluate_node)
    bad = [
        c
        for c in calls
        if c in _BANNED_NAMES or any(c.startswith(p) for p in _BANNED_PREFIXES)
    ]
    assert bad == [], f"evaluate() must be pure; found banned calls: {bad}"
```

Run; confirm `ImportError`; commit; implement.

### Green — make it pass

- Implement `from_yaml` as a sequence of `Result`-returning steps; chain via early `return`s on `Err`. Keep each branch one screen tall.
- `evaluate` is a small function — the `urlparse + set membership` pattern is the simplest correct shape; don't introduce a URL-matching library.
- `LOCKFILE_POLICY_PATH` computed at module-load time:
  ```python
  import codegenie
  _PKG_ROOT = Path(codegenie.__file__).resolve().parent
  # codegenie lives at src/codegenie/; tools/policy/ is at repo root
  LOCKFILE_POLICY_PATH: Final[Path] = (_PKG_ROOT / ".." / ".." / "tools" / "policy" / "lockfile-policy.yaml").resolve()
  ```
  Confirm this resolves correctly under both editable-install (`pip install -e .`) and wheel-install (the wheel doesn't include `tools/` so production deployment must ship `tools/policy/lockfile-policy.yaml` separately or via `package_data`). **Surface this in the PR** — if the wheel install path is broken, change to `importlib.resources.files("codegenie.transforms.policy") / "lockfile-policy.yaml"` and bundle the YAML inside the package (Rule 7 — pick one and document; do not average).
- The fence test reads the resolved path and asserts it lives under the codegenie repo root, NOT under a temp dir.

### Refactor — clean up

- Confirm the `PolicyViolation` discriminated union is correctly structured for Phase 7 addition. Phase 7 adds `UnpinnedDigest(kind="unpinned_digest", package, digest_expected, digest_observed)` — the `Annotated[..., Discriminator("kind")]` shape accommodates this with no edit to *this* file (Phase 7 widens the union in a new variant module + updates the type alias). Document the additive-extension contract in the union's docstring.
- Re-check that `tools/policy/lockfile-policy.yaml` has a **header comment** explaining ownership: "Codegenie-owned. Per Phase 3 Gap 2 fix. Analyzed repos cannot override. Changes require ADR amendment." This is the documentation control.
- Verify `RegistryUrl.parse` (from S1-01) enforces `https://` prefix and trailing slash; if it doesn't, surface that as a S1-01 follow-up rather than weakening the policy check (Rule 8 — read before you write).
- Cross-check with `../phase-arch-design.md §Phase boundaries — ADR-0021 — Phase 13 may adopt a real policy engine` — leave a one-line module docstring note: "In-process evaluator; Phase 13 may swap for a real policy engine (OPA/Rego, etc.). Contract surface is `evaluate(lockfile_doc) -> list[PolicyViolation]` — keep stable."

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/policy/__init__.py` | New package — empty re-export surface |
| `src/codegenie/transforms/policy/lockfile_policy.py` | New — `LockfilePolicy`, `PolicyViolation`, `UnauthorizedRegistry`, six `PolicyLoadError` variants + union, `LOCKFILE_POLICY_PATH`, `from_yaml`, `evaluate` |
| `src/codegenie/transforms/policy/lockfile-policy.yaml` | New — **runtime-loaded** codegenie-owned single-rule policy (the Gap 2 fix file); shipped inside the wheel |
| `tools/policy/lockfile-policy.yaml` | New — **canonical mirror** at repo root (human-review surface); bytewise-equal to the in-package copy |
| `pyproject.toml` | Update — include `lockfile-policy.yaml` as wheel package_data (`[tool.setuptools.package-data]` / `[tool.hatch.build.targets.wheel.force-include]` — match the existing convention) |
| `src/codegenie/transforms/__init__.py` | Re-export `LockfilePolicy`, `PolicyViolation`, `UnauthorizedRegistry`, `PolicyLoadError` |
| `tests/unit/transforms/test_lockfile_policy.py` | New — happy path + every `PolicyLoadError.reason` variant + adversarial registry detection + sort determinism + port/userinfo/scheme ACs + property + metamorphic + discriminator round-trip + shipped-yaml smoke |
| `tests/unit/transforms/test_lockfile_policy_path_is_codegenie_owned.py` | New — codegenie-owned-not-cwd-relative invariant (unit test, NOT a fence test) |
| `tests/unit/transforms/test_lockfile_policy_mirror_in_sync.py` | New — bytewise-equality between the in-package YAML and `tools/policy/lockfile-policy.yaml` |
| `tests/unit/transforms/test_lockfile_policy_codeowners.py` | New — codegenie-owned-header invariant + CODEOWNERS listing when the file exists |
| `tests/fence/test_lockfile_policy_evaluate_is_pure.py` | New — AST-walk asserting `evaluate()` contains no I/O / clock / network calls |
| `tests/fixtures/repos/malicious-npmrc/package-lock.json` | New — lockfile portion of the Gap 2 fixture (full fixture in S8-01) |
| `CODEOWNERS` / `.github/CODEOWNERS` (if either exists) | Add ownership lines for BOTH `tools/policy/lockfile-policy.yaml` and `src/codegenie/transforms/policy/lockfile-policy.yaml` |

## Out of scope

- **The `lockfile_policy` `TrustSignal` emission** in the Stage-6 validator — S6-04 (this story produces `list[PolicyViolation]`; S6-04 lifts to `TrustSignal(kind="lockfile_policy", passed=..., details={"violations": [...]})`).
- **Phase 7's additional `PolicyViolation` variants** (`UnpinnedDigest`, `RegistryRedirect`) — Phase 7 (this story ships the discriminated-union shape ready for additive extension).
- **The full `malicious-npmrc/` fixture** including the malicious `.npmrc` and adversarial network test — S8-01 + S8-04 (this story only ships the lockfile portion needed for the unit test).
- **A general policy framework** (OPA/Rego, OPA WASM, etc.) — Phase 13's ADR-0021 decision.
- **CVE-delta policy** — that's the `cve_delta` `TrustSignal` (a different signal; S6-04 / a separate evaluator that compares pre/post lockfile against `VulnIndex`).
- **Per-analyzed-repo policy override** — explicitly rejected per Gap 2 ownership rationale.
- **`schema_version: 2` migration** — Phase 7 or later; this story only refuses unknown versions cleanly.

## Notes for the implementer

- **Why a tuple, not a list, for `allowed_registries`**: Pydantic `frozen=True` requires hashable members; lists are unhashable; tuples are. Also: tuples force "this is a deliberate ordered sequence we don't mutate," which matches the policy's read-only nature.
- **`schema_version` literal `1` is not `Literal[1] | Literal[2]`**: Phase 3 supports v1 only. Forward versions raise `unknown_schema_version`. Phase 7 widens the literal when v2 is needed and documents the migration. Do NOT pre-emptively allow v2 — that's premature pluggability.
- **No `dict[str, Any]` anywhere** (validator-hardened): the original draft proposed `lockfile_doc: dict[str, Any]` with a `# noqa` comment — that path was structurally blocked by `tests/fence/test_no_any_in_plugin_surface.py` AND its proposed marker grammar (`# noqa: codegenie-no-any-in-contract`) didn't match the fence's actual grammar (`# fence: any-allowed [P3-ADR-NNNN]`). The replacement (`Mapping[str, object]` with `isinstance` narrowing) is mechanical, fence-clean, and aligns with the `SchemaViolation.details: list[dict[str, object]]` precedent in `skills/loader.py`.
- **Why a module-local `PolicyLoadError` and not the canonical `ParseError`**: `codegenie.types.errors.ParseError` is the kernel-tier parse error type — `frozen=True, extra="forbid"`, just `(message, value)`. ADR-0010 ratified that shape; extending it would fork the canonical home consumed by every Phase-3 smart constructor (Rule 7 — surface conflict, don't average). The `SkillsLoadError` precedent at `skills/loader.py:139` shows the right move: each loader owns a *local* discriminated-union error type with the per-failure-mode fields it needs.
- **Host extraction**: `urlparse(url).netloc` is the standard library answer. Avoid regex on URLs — it's the canonical case where stdlib beats clever code. The ACs deliberately pin strict equality (port/userinfo/scheme mismatch ≡ host mismatch) — that's a policy decision, not an oversight; an attacker who can inject `:443` is fishing for a comparison-normalization bug.
- **Why sorted violations**: `TrustSignal.details` flows into `remediation-report.yaml`; non-deterministic ordering breaks golden-file tests. The sort key is `(package, registry)` — pkg first because that's the human-reading order; registry second for tie-breaking when one package has multiple `resolved` entries (shouldn't happen, but defensive).
- **Wheel vs editable install** (validator-hardened): The implementation uses `importlib.resources.files("codegenie.transforms.policy") / "lockfile-policy.yaml"` which works under both editable (`pip install -e .`) and wheel installs IF the YAML is wheel package_data. `pyproject.toml` must ship the YAML in the wheel; do NOT use `Path(codegenie.__file__).parent / ".." / ".."` (works under editable, breaks under wheel). The repo-root `tools/policy/lockfile-policy.yaml` is the **human-review surface**; the in-package copy is the **runtime-loaded** one; the bytewise-equality unit test catches drift.
- **Why ship a mirror at all?** Two-copy systems are usually a smell. Here the costs are mitigated: the bytewise-equality test catches drift on every CI run, and the human-review purpose (CODEOWNERS, security scanners, casual `find tools/`) is real. If a future maintainer wants to collapse to one copy, the natural move is to delete `tools/policy/lockfile-policy.yaml` (and its CODEOWNERS line) and document that `src/codegenie/transforms/policy/lockfile-policy.yaml` is the only source. Mirror exists for human ergonomics, not for runtime correctness.
- **CODEOWNERS check** (validator-hardened to binary pass/fail): the unit test inspects the repo's CODEOWNERS state and either asserts both policy paths are listed (when CODEOWNERS exists) or asserts the codegenie-owned header is present in both YAMLs (when CODEOWNERS doesn't exist). No story-author judgment call; no "follow-up note" handwaving.
- **Mirror Phase 5's `sandbox-policy.yaml` shape**: open `docs/phases/05-sandbox-trust-gates/` and find Phase 5's `tools/policy/sandbox-policy.yaml` precedent before authoring this YAML. Match the header-comment style, the `schema_version` placement, the codegenie-ownership statement. If Phase 5 hasn't shipped its YAML yet (Phase 5 is post-Phase-3 in the roadmap), follow the Phase 5 *design doc's* shape — they will harmonize at integration time.
- **Why not in-process Python check for `.npmrc` directly?** The `.npmrc` lives in the analyzed repo and is *interpreted by npm* during install. Reading it ourselves and rejecting based on its contents is brittle (npm has complex precedence rules: project `.npmrc`, user `.npmrc`, env `npm_config_*`, CLI flags). The lockfile is the *output* — if a hostile `.npmrc` redirects successfully, the `resolved` URLs in `package-lock.json` will reflect it. Checking the lockfile is the structural defense; the `RegistryAllowlist` network policy (S4-01) is the network-layer defense. Defense in depth.
- **Open/Closed seam — Phase 7 widening of `PolicyViolation`**: the discriminated-union shape (`Annotated[..., Field(discriminator="kind")]`) is the right Open/Closed seam — Phase 7 adds new variants (`UnpinnedDigest`, `RegistryRedirect`) in a **new module** and widens the type alias in *this* module's `__init__.py` (or its sibling file), without editing `lockfile_policy.py`. The kernel-rule-of-three for a policy-rule plugin registry has **not** been reached (Phase 3 ships one rule; Rule 2 — three similar lines is better than premature abstraction). Do NOT introduce a `PolicyRule` Protocol / `@register_policy_rule` registry in this story.
- **Functional core / imperative shell**: the AST-walk fence (`test_lockfile_policy_evaluate_is_pure.py`) pins `evaluate` to pure-function territory. The only side-effecting code in the module is `from_yaml` (file read + YAML parse). Keep new helpers on the pure side of the line; if you reach for `time.time()` / `os.environ` while implementing `evaluate`, surface it — there's probably a model-level field you should be carrying instead.
