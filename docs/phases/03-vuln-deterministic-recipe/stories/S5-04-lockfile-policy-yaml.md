# Story S5-04 — `LockfilePolicy` YAML + Pydantic loader + `evaluate` (Gap 2 fix)

**Step:** Step 5 — Transform ABC consumers, RecipeEngine Protocol, RecipeRegistry, lockfile policy
**Status:** Ready
**Effort:** M
**Depends on:** S5-02
**ADRs honored:** ADR-0010, ADR-0001

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

Ship `tools/policy/lockfile-policy.yaml` (codegenie-owned, Phase 3 single-rule) and `src/codegenie/transforms/policy/lockfile_policy.py` exposing `LockfilePolicy` (Pydantic `extra="forbid"`, `frozen=True`), `LockfilePolicy.from_yaml(path) -> Result[LockfilePolicy, ParseError]`, `LockfilePolicy.evaluate(lockfile_doc) -> list[PolicyViolation]`, and the `PolicyViolation = UnauthorizedRegistry(registry, package)` discriminated union. Adversarial test confirms `UnauthorizedRegistry` is correctly detected on the `tests/fixtures/repos/malicious-npmrc/` lockfile.

## Acceptance criteria

- [ ] `tools/policy/lockfile-policy.yaml` exists at the repo root (NOT inside any `tests/` or `plugins/` subtree) and contains exactly the Phase 3 single rule:
  ```yaml
  # codegenie-owned. Per ADR-0009 Phase 3 + Gap 2 fix. Analyzed repos cannot override.
  schema_version: 1
  allowed_registries:
    - https://registry.npmjs.org/
  ```
- [ ] `from codegenie.transforms.policy.lockfile_policy import LockfilePolicy, PolicyViolation, UnauthorizedRegistry, LOCKFILE_POLICY_PATH` succeeds.
- [ ] `LockfilePolicy` is a Pydantic model with `model_config = ConfigDict(frozen=True, extra="forbid")` and fields `schema_version: Literal[1]`, `allowed_registries: tuple[RegistryUrl, ...]` (tuple not list — frozen, hashable, deterministic iteration).
- [ ] `LockfilePolicy.from_yaml(path: Path) -> Result[LockfilePolicy, ParseError]` smart constructor:
  - Returns `Result.Ok(policy)` on a valid YAML file.
  - Returns `Result.Err(ParseError(reason="file_missing", path=...))` if path doesn't exist.
  - Returns `Result.Err(ParseError(reason="yaml_syntax", line=..., col=...))` on YAML syntax error.
  - Returns `Result.Err(ParseError(reason="schema_violation", field=..., detail=...))` on Pydantic validation failure.
  - Returns `Result.Err(ParseError(reason="unknown_schema_version", observed=..., supported=[1]))` if `schema_version != 1`.
  - Returns `Result.Err(ParseError(reason="empty_allowlist"))` if `allowed_registries == []` — empty allowlist would deny every install; that's an operational footgun, not a valid policy.
  - Returns `Result.Err(ParseError(reason="invalid_registry_url", url=..., detail=...))` if any URL fails `RegistryUrl.parse` (must be `https://`, must end with `/`, etc.).
- [ ] `LockfilePolicy.evaluate(lockfile_doc: dict) -> list[PolicyViolation]`:
  - Walks `lockfile_doc["packages"]` (npm v3 schema; `lockfile_doc["dependencies"]` is the v2 fallback but Phase 3 supports v3 only per §Edge case E1).
  - For each package entry, reads `resolved: str | None`; if `resolved` is a URL whose host does NOT match any registry in `allowed_registries`, yields `UnauthorizedRegistry(registry=<resolved_url_origin>, package=<package_path>)`.
  - **`resolved` matching is host-prefix exact**: `https://registry.npmjs.org/express/-/express-4.19.2.tgz` matches `https://registry.npmjs.org/`; `https://attacker.example.com/...` does not.
  - **Packages without `resolved`** (e.g., the root package or `link:` workspace deps) are skipped (not violations).
  - **Empty `packages` dict** → empty violations list (vacuously passing).
  - Returns a **sorted** list of violations (deterministic order — sort by `(package, registry)` tuple ascending) so downstream golden tests and `TrustSignal.details` are byte-stable.
- [ ] `PolicyViolation` is a Pydantic discriminated union; Phase 3 ships exactly one variant: `UnauthorizedRegistry(kind="unauthorized_registry", registry: RegistryUrl, package: str)`. The union is `Annotated[UnauthorizedRegistry, Discriminator("kind")]` — *one-arm union today, structurally ready for Phase 7's additional variants* (`UnpinnedDigest`, `RegistryRedirect`, etc.); the choice is documented in the module docstring.
- [ ] **Adversarial regression**: `tests/unit/transforms/test_lockfile_policy.py::test_attacker_npmrc_lockfile_yields_unauthorized_registry` reads `tests/fixtures/repos/malicious-npmrc/package-lock.json` (a lockfile whose `resolved` URLs point at `attacker.example.com`) and asserts exactly the right `UnauthorizedRegistry` violations are returned. **This is the load-bearing test** for the Gap 2 fix.
- [ ] **Codegenie-owned-not-repo-owned invariant**: `tests/fence/test_lockfile_policy_path_is_codegenie_owned.py` asserts `LOCKFILE_POLICY_PATH` is computed relative to the codegenie package root (using `importlib.resources` or `__file__` resolution), NOT relative to `os.getcwd()` or any analyzed-repo path; a test that `cd`s into a temp dir with a hostile `tools/policy/lockfile-policy.yaml` confirms the loader still reads the codegenie-owned one.
- [ ] **CODEOWNERS-style protection**: `tools/policy/lockfile-policy.yaml` is added to `CODEOWNERS` (if present in the repo) so changes require a security-team review (or equivalent). If `CODEOWNERS` doesn't exist yet, file a follow-up note in the story (do not invent CODEOWNERS); the in-file comment + the ADR amendment requirement is the documented control.
- [ ] **`schema_version`-forward compatibility**: a YAML with `schema_version: 2` returns `Result.Err(ParseError(reason="unknown_schema_version", supported=[1]))` — explicit version negotiation; future schemas must coexist or refuse cleanly.
- [ ] `mypy --strict src/codegenie/transforms/policy/lockfile_policy.py` clean.
- [ ] `ruff check`, `ruff format --check`, `pytest tests/unit/transforms/test_lockfile_policy.py tests/fence/test_lockfile_policy_path_is_codegenie_owned.py` all green.
- [ ] Branch coverage on `lockfile_policy.py` ≥ 95%.

## Implementation outline

1. Create `tools/policy/lockfile-policy.yaml` with the exact content above (single rule, schema_version=1, single-host allowlist).
2. Create `src/codegenie/transforms/policy/__init__.py` and `src/codegenie/transforms/policy/lockfile_policy.py`.
3. Define `LOCKFILE_POLICY_PATH: Final[Path]` computed via `Path(importlib.resources.files("codegenie") / ".." / ".." / "tools" / "policy" / "lockfile-policy.yaml").resolve()` (or equivalent that pins to the codegenie installation, not cwd). Document the choice with a one-line comment naming the Gap 2 fix.
4. Define `UnauthorizedRegistry(BaseModel)` with `kind: Literal["unauthorized_registry"] = "unauthorized_registry"`, `registry: RegistryUrl`, `package: str`. `model_config = ConfigDict(frozen=True, extra="forbid")`.
5. Define `PolicyViolation = Annotated[UnauthorizedRegistry, Discriminator("kind")]` (one-arm union; Phase 7 widens).
6. Define `LockfilePolicy(BaseModel)`:
   ```python
   class LockfilePolicy(BaseModel):
       model_config = ConfigDict(frozen=True, extra="forbid")
       schema_version: Literal[1]
       allowed_registries: tuple[RegistryUrl, ...]

       @classmethod
       def from_yaml(cls, path: Path) -> Result["LockfilePolicy", ParseError]: ...

       def evaluate(self, lockfile_doc: dict[str, Any]) -> list[PolicyViolation]: ...
   ```
   `dict[str, Any]` is acceptable HERE because `lockfile_doc` is the *output* of the lockfile parser (orjson) and is intentionally untyped at this boundary — the fence test from S1-05 allows `dict[str, Any]` in evaluators that consume untyped JSON parse results, *not* in contract-layer models. Document this exception with a one-line `# noqa: codegenie-no-any-in-contract — evaluator consumes orjson output`.
7. `from_yaml` validation order: file existence → YAML parse → Pydantic model validate → empty-allowlist sanity check → each-URL smart-constructor check. Each failure mode is a distinct `ParseError.reason`.
8. `evaluate` algorithm:
   ```python
   def evaluate(self, lockfile_doc):
       allowed_hosts = {urlparse(r).netloc for r in self.allowed_registries}
       violations: list[PolicyViolation] = []
       for pkg_path, entry in (lockfile_doc.get("packages") or {}).items():
           resolved = entry.get("resolved")
           if not resolved or not isinstance(resolved, str):
               continue
           host = urlparse(resolved).netloc
           if host not in allowed_hosts:
               violations.append(UnauthorizedRegistry(
                   registry=RegistryUrl(f"{urlparse(resolved).scheme}://{host}/"),
                   package=pkg_path,
               ))
       return sorted(violations, key=lambda v: (v.package, v.registry))
   ```
9. Fixture for the adversarial test: `tests/fixtures/repos/malicious-npmrc/package-lock.json` (this story creates the *lockfile* portion; the full fixture including the malicious `.npmrc` is S8-01). The lockfile carries one entry with `resolved: "https://attacker.example.com/express/-/express-4.19.2.tgz"`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths: `tests/unit/transforms/test_lockfile_policy.py`, `tests/fence/test_lockfile_policy_path_is_codegenie_owned.py`.

```python
# tests/unit/transforms/test_lockfile_policy.py
from pathlib import Path
import textwrap
import pytest
from codegenie.transforms.policy.lockfile_policy import (
    LockfilePolicy, UnauthorizedRegistry, LOCKFILE_POLICY_PATH,
)
from codegenie.types.identifiers import RegistryUrl

def _write_yaml(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "policy.yaml"
    p.write_text(textwrap.dedent(body))
    return p

def test_from_yaml_happy_path(tmp_path):
    p = _write_yaml(tmp_path, """
        schema_version: 1
        allowed_registries:
          - https://registry.npmjs.org/
    """)
    result = LockfilePolicy.from_yaml(p)
    assert result.is_ok
    policy = result.unwrap()
    assert policy.allowed_registries == (RegistryUrl("https://registry.npmjs.org/"),)

def test_from_yaml_file_missing(tmp_path):
    result = LockfilePolicy.from_yaml(tmp_path / "nope.yaml")
    assert not result.is_ok and result.error.reason == "file_missing"

def test_from_yaml_yaml_syntax_error(tmp_path):
    p = tmp_path / "p.yaml"; p.write_text("this: is: broken: yaml")
    result = LockfilePolicy.from_yaml(p)
    assert not result.is_ok and result.error.reason == "yaml_syntax"

def test_from_yaml_unknown_schema_version_2(tmp_path):
    p = _write_yaml(tmp_path, "schema_version: 2\nallowed_registries: [https://x/]")
    result = LockfilePolicy.from_yaml(p)
    assert not result.is_ok and result.error.reason == "unknown_schema_version"

def test_from_yaml_empty_allowlist_rejected(tmp_path):
    p = _write_yaml(tmp_path, "schema_version: 1\nallowed_registries: []")
    result = LockfilePolicy.from_yaml(p)
    assert not result.is_ok and result.error.reason == "empty_allowlist"

def test_from_yaml_invalid_registry_url(tmp_path):
    p = _write_yaml(tmp_path, "schema_version: 1\nallowed_registries: [http://insecure/]")
    result = LockfilePolicy.from_yaml(p)
    assert not result.is_ok and result.error.reason == "invalid_registry_url"

def test_from_yaml_extra_field_rejected(tmp_path):
    p = _write_yaml(tmp_path, """
        schema_version: 1
        allowed_registries: [https://registry.npmjs.org/]
        sneaky_extra_field: true
    """)
    result = LockfilePolicy.from_yaml(p)
    assert not result.is_ok and result.error.reason == "schema_violation"

@pytest.fixture
def npm_policy():
    return LockfilePolicy(
        schema_version=1,
        allowed_registries=(RegistryUrl("https://registry.npmjs.org/"),),
    )

def test_evaluate_empty_packages_returns_no_violations(npm_policy):
    assert npm_policy.evaluate({"packages": {}}) == []

def test_evaluate_root_pkg_without_resolved_is_skipped(npm_policy):
    doc = {"packages": {"": {"name": "root", "version": "1.0.0"}}}
    assert npm_policy.evaluate(doc) == []

def test_evaluate_legit_registry_passes(npm_policy):
    doc = {"packages": {"node_modules/express": {
        "version": "4.19.2",
        "resolved": "https://registry.npmjs.org/express/-/express-4.19.2.tgz",
    }}}
    assert npm_policy.evaluate(doc) == []

def test_evaluate_attacker_npmrc_yields_unauthorized_registry(npm_policy):
    # The Gap 2 regression: the load-bearing test for this story
    doc = {"packages": {"node_modules/express": {
        "version": "4.19.2",
        "resolved": "https://attacker.example.com/express/-/express-4.19.2.tgz",
    }}}
    violations = npm_policy.evaluate(doc)
    assert len(violations) == 1
    v = violations[0]
    assert isinstance(v, UnauthorizedRegistry)
    assert v.registry == RegistryUrl("https://attacker.example.com/")
    assert v.package == "node_modules/express"

def test_evaluate_violations_sorted_deterministically(npm_policy):
    doc = {"packages": {
        "node_modules/z-bad":     {"resolved": "https://evil2.example/z/-/z-1.tgz"},
        "node_modules/a-bad":     {"resolved": "https://evil1.example/a/-/a-1.tgz"},
        "node_modules/m-bad":     {"resolved": "https://evil1.example/m/-/m-1.tgz"},
    }}
    violations = npm_policy.evaluate(doc)
    assert [v.package for v in violations] == ["node_modules/a-bad", "node_modules/m-bad", "node_modules/z-bad"]

def test_lockfile_policy_path_loads_real_codegenie_owned_yaml():
    # Live test — the shipped tools/policy/lockfile-policy.yaml parses cleanly
    result = LockfilePolicy.from_yaml(LOCKFILE_POLICY_PATH)
    assert result.is_ok
    assert RegistryUrl("https://registry.npmjs.org/") in result.unwrap().allowed_registries
```

```python
# tests/fence/test_lockfile_policy_path_is_codegenie_owned.py
import os
from pathlib import Path
from codegenie.transforms.policy.lockfile_policy import LOCKFILE_POLICY_PATH, LockfilePolicy

def test_path_resolves_relative_to_codegenie_not_cwd(tmp_path, monkeypatch):
    # Create a hostile policy in a temp dir
    hostile = tmp_path / "tools" / "policy"
    hostile.mkdir(parents=True)
    (hostile / "lockfile-policy.yaml").write_text(
        "schema_version: 1\nallowed_registries: [https://attacker.example.com/]\n"
    )
    monkeypatch.chdir(tmp_path)
    # Loader must STILL find the codegenie-owned policy
    result = LockfilePolicy.from_yaml(LOCKFILE_POLICY_PATH)
    assert result.is_ok
    # And the loaded allowlist must NOT contain the attacker host
    assert "attacker.example.com" not in {r for r in result.unwrap().allowed_registries}

def test_lockfile_policy_path_lives_under_codegenie_repo_root():
    # Sanity: the resolved path must be under the codegenie repo (not under /tmp, not under analyzed_repo)
    p = Path(LOCKFILE_POLICY_PATH).resolve()
    assert "tools/policy/lockfile-policy.yaml" in str(p)
    assert p.exists()
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
| `tools/policy/lockfile-policy.yaml` | New — codegenie-owned single-rule policy (the Gap 2 fix file) |
| `src/codegenie/transforms/policy/__init__.py` | New package |
| `src/codegenie/transforms/policy/lockfile_policy.py` | New — `LockfilePolicy`, `PolicyViolation`, `UnauthorizedRegistry`, `LOCKFILE_POLICY_PATH`, `from_yaml`, `evaluate` |
| `tests/unit/transforms/test_lockfile_policy.py` | New — happy path + every `ParseError.reason` + adversarial registry detection + sort determinism |
| `tests/fence/test_lockfile_policy_path_is_codegenie_owned.py` | New — codegenie-owned-not-repo-owned invariant |
| `tests/fixtures/repos/malicious-npmrc/package-lock.json` | New — lockfile portion of the Gap 2 fixture (full fixture in S8-01) |
| `src/codegenie/transforms/__init__.py` | Re-export `LockfilePolicy`, `PolicyViolation`, `UnauthorizedRegistry` |
| `CODEOWNERS` (if present) | Add `tools/policy/lockfile-policy.yaml` ownership line |

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
- **The `dict[str, Any]` exception in `evaluate`**: this is the one place in `transforms/` where `dict[str, Any]` is acceptable, because the input is the *output of `orjson.loads`* on the lockfile and is intentionally untyped at this boundary. S1-05's fence test (`test_no_any_in_contract_layer.py`) should have an `# noqa: codegenie-no-any-in-contract` allowlist for this signature OR an explicit `# type: ignore` with a comment referencing this story. Surface the choice in PR review.
- **Host extraction**: `urlparse(url).netloc` is the standard library answer. Avoid regex on URLs — it's the canonical case where stdlib beats clever code. Confirm the test cases cover URLs with ports (`https://registry.npmjs.org:443/`) and credentials (`https://user:pass@registry.npmjs.org/`); the test fixture should make a deliberate choice and document it (the conservative read: strict-equality on netloc means port-bearing URLs are treated as a different host — that's defensible as a policy decision).
- **Why sorted violations**: `TrustSignal.details` flows into `remediation-report.yaml`; non-deterministic ordering breaks golden-file tests. The sort key is `(package, registry)` — pkg first because that's the human-reading order; registry second for tie-breaking when one package has multiple `resolved` entries (shouldn't happen, but defensive).
- **CODEOWNERS check**: if the repo doesn't have CODEOWNERS yet, file a one-line note in the PR description; don't invent CODEOWNERS in this story. The in-file header comment + the load-bearing ADR amendment requirement is the documented control. (The architecture spec's §Open implementation questions item "CODEOWNERS entry for `plugins/PLUGINS.lock`" is the S2-03 analog; cross-reference if useful.)
- **Mirror Phase 5's `sandbox-policy.yaml` shape**: open `docs/phases/05-sandbox-trust-gates/` and find Phase 5's `tools/policy/sandbox-policy.yaml` precedent before authoring this YAML. Match the header-comment style, the `schema_version` placement, the codegenie-ownership statement. If Phase 5 hasn't shipped its YAML yet (Phase 5 is post-Phase-3 in the roadmap), follow the Phase 5 *design doc's* shape — they will harmonize at integration time.
- **Why not in-process Python check for `.npmrc` directly?** The `.npmrc` lives in the analyzed repo and is *interpreted by npm* during install. Reading it ourselves and rejecting based on its contents is brittle (npm has complex precedence rules: project `.npmrc`, user `.npmrc`, env `npm_config_*`, CLI flags). The lockfile is the *output* — if a hostile `.npmrc` redirects successfully, the `resolved` URLs in `package-lock.json` will reflect it. Checking the lockfile is the structural defense; the `RegistryAllowlist` network policy (S4-01) is the network-layer defense. Defense in depth.
