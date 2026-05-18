# Story S5-02 — `NpmLockfileRecipeEngine` (production day-1 implementation)

**Step:** Step 5 — Transform ABC consumers, RecipeEngine Protocol, RecipeRegistry, lockfile policy
**Status:** Ready
**Effort:** L
**Depends on:** S5-01
**ADRs honored:** ADR-0009, ADR-0010, ADR-0007, ADR-0006, ADR-0011

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

- [ ] `from codegenie.transforms.engines.npm_lockfile import NpmLockfileRecipeEngine, NpmLockfileTransform` succeeds.
- [ ] `NpmLockfileRecipeEngine` structurally satisfies `RecipeEngine` Protocol from S5-01 (`isinstance(NpmLockfileRecipeEngine(jail), RecipeEngine)` is True).
- [ ] `NpmLockfileTransform` is a `Transform` ABC subclass (S1-04) carrying `transform_id: TransformId` (= `blake3(diff_bytes)`), `diff_bytes: bytes` (unified diff of `package.json` + `package-lock.json`), `files_changed: list[SandboxedPath]` (length 2), `provenance: TransformProvenance`.
- [ ] **Step 1 — `package.json` size cap**: a 1 MiB + 1 byte `package.json` fixture yields `RecipeOutcome.Failed(reason="package_json_too_large", limit_bytes=1048576, observed_bytes=1048577)`; npm install is **not** invoked (assert on jail-spy call count = 0).
- [ ] **Step 1 — `package.json` depth cap**: a depth-17 nested `package.json` fixture (`{"a":{"a":{...×17}}}` under `dependencies` is implausible but the validator runs against the parsed tree) yields `RecipeOutcome.Failed(reason="package_json_depth_exceeded", limit=16, observed=17)`.
- [ ] **Step 2 — key-order preservation**: round-tripping `package.json` with no edit produces byte-identical output to the input (same keys in same order, same indentation `OPT_INDENT_2`); explicit test reads/writes the express fixture and asserts byte-equality pre/post no-op edit.
- [ ] **Step 3 — `O_NOFOLLOW` enforcement**: integration test creates a symlink-swap race (test fixture replaces `package.json` with a symlink to `/etc/passwd` between the read and the write); the engine's write-back raises `OSError(ELOOP)` which is caught and returned as `RecipeOutcome.Failed(reason="filesystem_race", path="package.json")`. The `/etc/passwd` file is unmodified (positive assertion: `stat()` mtime unchanged).
- [ ] **Step 4 — npm flags**: `JailedSubprocessSpec.cmd` recorded by the jail spy is *exactly* `("npm", "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--prefer-offline")` — order and value preserved; missing-flag mutation tests (drop each flag in turn) cause assertion to fail.
- [ ] **Step 4 — network policy**: `JailedSubprocessSpec.network` recorded is `RegistryAllowlist(hosts=("registry.npmjs.org",))`; an `--prefer-offline` warm-cache test confirms `NetworkDenied` is NOT raised when cache is warm.
- [ ] **Step 4 — time budget**: `JailedSubprocessSpec.time_budget_s == 60.0`; `JailedSubprocessSpec.memory_mib == 1024`; `JailedSubprocessSpec.pids_max == 1024`.
- [ ] **Step 4 — env wrapper typed**: `JailedSubprocessSpec.env` is `NpmEnv` (S4-01), not a raw `dict`; mypy enforces.
- [ ] **Step 4 — non-zero exit**: when the jail returns `Completed(exit_code=1)` (e.g., peer dep conflict surfaced by npm), the engine returns `RecipeOutcome.Failed(reason="npm_install_exit_nonzero", exit_code=1, stderr_tail=<last 4 KB>)`.
- [ ] **Step 4 — jail tagged-union variants**: each non-`Completed` `JailedSubprocessResult` variant maps to a typed `RecipeOutcome.Failed`: `TimedOut` → `reason="install_timeout"`; `OomKilled` → `reason="install_oom"`; `NetworkDenied(host)` → `reason="network_policy_violation", host=<host>`; `DiskQuotaExceeded` → `reason="disk_quota_exceeded"`. Each variant is tested.
- [ ] **Step 5 — lockfile size cap**: a 32 MiB + 1 byte lockfile yields `RecipeOutcome.Failed(reason="lockfile_too_large", limit_bytes=33554432)`.
- [ ] **Step 5 — lockfile depth cap**: a depth-25 lockfile yields `RecipeOutcome.Failed(reason="lockfile_depth_exceeded", limit=24)`.
- [ ] **Step 5 — lockfile v1 rejection** (§Edge case E1): a `lockfileVersion: 1` lockfile yields `RecipeOutcome.Failed(reason="lockfile_v1_unsupported")` *before* parsing the body.
- [ ] **Step 6 — happy path**: `RecipeOutcome.Applied(transform=NpmLockfileTransform(...))` where `transform.transform_id == blake3(transform.diff_bytes).hexdigest()` and `len(transform.files_changed) == 2`.
- [ ] **Golden file**: `tests/golden/lockfiles/express-cve-2024-21501.before.json` → engine.apply(plan=`semver-bump express ^4.17.1 → ^4.19.2`) → `tests/golden/lockfiles/express-cve-2024-21501.after.json` byte-equal (the same fixture S8-02 will end-to-end). This test uses the **real** `SubprocessJail` adapter for the runner the CI is on (bwrap on Linux); macOS runner is nightly.
- [ ] **Determinism within-test**: running the same `apply(...)` 5 times against the same input fixture produces byte-identical `diff_bytes` 5 times (intra-run smoke for the property test S8-03 will widen to 100 runs).
- [ ] `mypy --strict src/codegenie/transforms/engines/npm_lockfile.py` clean.
- [ ] `ruff check`, `ruff format --check`, `pytest tests/unit/transforms/test_npm_lockfile_engine.py tests/integration/test_npm_lockfile_engine_jail.py` all green.
- [ ] Branch coverage on `npm_lockfile.py` ≥ 95%.

## Implementation outline

1. Create `src/codegenie/transforms/engines/__init__.py` and `src/codegenie/transforms/engines/npm_lockfile.py`.
2. Constants module-top:
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
       "--package-lock-only",
       "--ignore-scripts",
       "--no-audit",
       "--prefer-offline",
   )
   _REGISTRY_ALLOWLIST: Final[tuple[str, ...]] = ("registry.npmjs.org",)
   ```
3. `NpmLockfileRecipeEngine.__init__(self, jail: SubprocessJail)` — constructor-injected jail (testable; no ambient state).
4. `async def apply(self, repo, plan, capability)` — pure orchestration calling private helpers; each helper returns a `Result[T, FailureReason]` (or raises a sentinel exception caught at the top); the `apply` method's body is a single `match` on those Results lifted to `RecipeOutcome`.
5. Private helpers (pure functions where possible — functional core / imperative shell):
   - `_read_package_json(path: SandboxedPath) -> Result[OrderedJson, _PJsonError]` — size cap, depth cap, parse via `orjson.loads`.
   - `_edit_dep_version(doc: OrderedJson, package: PackageId, new_version: str) -> Result[OrderedJson, _PJsonError]` — preserves key order; checks `dependencies`/`devDependencies`/`optionalDependencies`/`overrides` in declaration order; returns the modified doc and a `bool` indicating which section was touched (carried into provenance).
   - `_write_package_json(path: SandboxedPath, doc: OrderedJson) -> Result[bytes, _IoError]` — `O_NOFOLLOW`, serialized with `orjson.dumps(doc, option=orjson.OPT_INDENT_2)` then `+ b"\n"` for POSIX line-ending parity; returns the written bytes for diff.
   - `_run_npm_install(jail, repo, capability) -> Result[None, _NpmError]` — builds the `JailedSubprocessSpec`, awaits, matches on `JailedSubprocessResult`.
   - `_read_lockfile(path) -> Result[LockfileDoc, _LockfileError]` — size cap, depth cap, lockfileVersion check (v3 only; v1 fails-fast with distinct reason).
   - `_build_transform(plan, before_pjson, after_pjson, before_lock, after_lock) -> NpmLockfileTransform` — computes unified diff (`difflib.unified_diff` over the four byte sequences concatenated by file boundary marker), `transform_id = blake3(diff_bytes).hexdigest()`.
6. Define `NpmLockfileTransform(Transform)` with the four required attrs.
7. Tests (TDD plan below).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths: `tests/unit/transforms/test_npm_lockfile_engine.py` (unit, fake jail) and `tests/integration/test_npm_lockfile_engine_jail.py` (real bwrap, gated on `pytest.importorskip("subprocess") and shutil.which("bwrap")` on Linux).

```python
# tests/unit/transforms/test_npm_lockfile_engine.py
from pathlib import Path
import pytest
import orjson
from codegenie.transforms.engines.npm_lockfile import (
    NpmLockfileRecipeEngine, NpmLockfileTransform,
)
from codegenie.transforms.recipe_engine import RecipeOutcome, RecipePlan
from codegenie.transforms.sandbox_jail import (
    JailedSubprocessResult, Completed, TimedOut, OomKilled, NetworkDenied,
)
from codegenie.types.identifiers import PackageId, TransformKind

class FakeJail:
    def __init__(self, result: JailedSubprocessResult) -> None:
        self.result = result
        self.calls: list = []
    async def run(self, spec):
        self.calls.append(spec)
        return self.result

@pytest.fixture
def express_repo(tmp_path: Path):
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
def plan():
    return RecipePlan(
        package=PackageId("express"), from_version="^4.17.1", to_version="^4.19.2",
        kind=TransformKind("npm-lockfile-semver-bump"),
    )

@pytest.mark.asyncio
async def test_happy_path_returns_applied_with_transform(express_repo, plan):
    # Fake jail "regenerates" lockfile by writing a new file (test-only convenience)
    class WritingJail:
        calls: list = []
        async def run(self, spec):
            WritingJail.calls.append(spec)
            (Path(spec.cwd) / "package-lock.json").write_bytes(orjson.dumps(
                {"name":"fixture","lockfileVersion":3,
                 "packages":{"node_modules/express":{"version":"4.19.2"}}},
                option=orjson.OPT_INDENT_2) + b"\n")
            return Completed(exit_code=0, stdout=b"", stderr=b"")
    engine = NpmLockfileRecipeEngine(jail=WritingJail())
    out = await engine.apply(repo=SandboxedPath(express_repo), plan=plan, capability=...)
    assert isinstance(out, RecipeOutcome) and out.kind == "applied"
    assert isinstance(out.transform, NpmLockfileTransform)
    assert out.transform.transform_id == _blake3_hex(out.transform.diff_bytes)
    assert len(out.transform.files_changed) == 2

@pytest.mark.asyncio
async def test_npm_cmd_is_exactly_four_flags(express_repo, plan):
    jail = FakeJail(Completed(exit_code=0, stdout=b"", stderr=b""))
    await NpmLockfileRecipeEngine(jail=jail).apply(SandboxedPath(express_repo), plan, ...)
    assert jail.calls[0].cmd == (
        "npm", "install",
        "--package-lock-only", "--ignore-scripts", "--no-audit", "--prefer-offline",
    )

@pytest.mark.asyncio
async def test_package_json_too_large_short_circuits_before_npm(tmp_path, plan):
    (tmp_path / "package.json").write_bytes(b"{" + b"x" * (1024*1024) + b"}")
    jail = FakeJail(Completed(exit_code=0, stdout=b"", stderr=b""))
    out = await NpmLockfileRecipeEngine(jail=jail).apply(SandboxedPath(tmp_path), plan, ...)
    assert out.kind == "failed" and out.reason == "package_json_too_large"
    assert jail.calls == []  # npm install MUST NOT be invoked

@pytest.mark.asyncio
async def test_lockfile_v1_unsupported(express_repo, plan):
    class V1Jail:
        calls: list = []
        async def run(self, spec):
            V1Jail.calls.append(spec)
            (Path(spec.cwd) / "package-lock.json").write_bytes(orjson.dumps(
                {"name":"x","lockfileVersion":1}) + b"\n")
            return Completed(0, b"", b"")
    out = await NpmLockfileRecipeEngine(jail=V1Jail()).apply(SandboxedPath(express_repo), plan, ...)
    assert out.kind == "failed" and out.reason == "lockfile_v1_unsupported"

@pytest.mark.asyncio
@pytest.mark.parametrize("variant,expected_reason", [
    (TimedOut(), "install_timeout"),
    (OomKilled(), "install_oom"),
    (NetworkDenied(host="attacker.example.com"), "network_policy_violation"),
])
async def test_jail_failure_variants_map_to_typed_recipe_outcome(express_repo, plan, variant, expected_reason):
    out = await NpmLockfileRecipeEngine(jail=FakeJail(variant)).apply(SandboxedPath(express_repo), plan, ...)
    assert out.kind == "failed" and out.reason == expected_reason

@pytest.mark.asyncio
async def test_no_op_edit_is_byte_identical_round_trip(express_repo, plan):
    # Use a plan whose target_version equals the existing version → no edit performed
    noop_plan = plan.model_copy(update={"to_version": "^4.17.1"})
    before = (express_repo / "package.json").read_bytes()
    await NpmLockfileRecipeEngine(jail=FakeJail(Completed(0,b"",b""))).apply(SandboxedPath(express_repo), noop_plan, ...)
    after = (express_repo / "package.json").read_bytes()
    assert before == after  # key order + indentation preserved

@pytest.mark.asyncio
async def test_intra_run_determinism_5x(express_repo, plan):
    diffs = []
    for _ in range(5):
        # fresh fixture each iteration (reset side effects)
        ...
        out = await NpmLockfileRecipeEngine(jail=...).apply(...)
        diffs.append(out.transform.diff_bytes)
    assert len(set(diffs)) == 1
```

```python
# tests/integration/test_npm_lockfile_engine_jail.py
@pytest.mark.skipif(shutil.which("bwrap") is None, reason="requires bwrap")
@pytest.mark.asyncio
async def test_golden_express_lockfile_byte_equal_under_real_jail():
    before = Path("tests/golden/lockfiles/express-cve-2024-21501.before.json").read_bytes()
    after_golden = Path("tests/golden/lockfiles/express-cve-2024-21501.after.json").read_bytes()
    # set up repo, plan, real BwrapAdapter, run apply, assert lockfile written equals after_golden byte-for-byte
    ...
```

Run; confirm `ImportError`; commit; implement.

### Green — make it pass

- Implement each helper minimally. The depth-walker is a small recursive `_max_depth(obj) -> int` over `dict`/`list`/`tuple` (orjson decodes JSON arrays as lists).
- `_edit_dep_version` mutates the parsed dict in-place after copying via `copy.deepcopy` (preserving order is intrinsic to dict, and `orjson.dumps` honors it); search the four sections in spec order and edit the first match; if none matched, return `Result.Err(_PJsonError(reason="package_not_in_dependencies", package=package))`.
- For the unified diff, concatenate the four byte sequences with `b"\n--- file: package.json ---\n"` / `b"\n--- file: package-lock.json ---\n"` markers; this is the `diff_bytes` payload. Determinism: any non-deterministic input (e.g., timestamps) is excluded by construction (the diff is pure byte-vs-byte over file contents).
- The integration test against the real bwrap jail requires `npm` on PATH inside the jail; the bwrap adapter from S4-02 bind-mounts `/` ro and the project's `node_modules` cache rw under `.codegenie/cache/npm`. Document the fixture-prep requirements in the test docstring.

### Refactor — clean up

- Confirm every numeric constant has the `Final[int]` annotation and an inline comment with the human unit (`1 MiB`). The fence test `tests/fence/test_no_raw_str_for_domain_ids.py` from S1-05 will catch any `: int` parameter named `_max_bytes` that isn't `Final[int]`.
- Confirm `apply` has *no* `try: ... except: ...` blocks that swallow exceptions — every failure path returns a typed `RecipeOutcome.Failed(reason=...)`. The one place exceptions are caught is the `OSError(ELOOP)` from `SandboxedPath.open(O_NOFOLLOW)` — caught precisely (not bare `except`), turned into `Failed(filesystem_race)`.
- Verify `--ignore-scripts` is **at index 3 of `_NPM_INSTALL_CMD`** with an inline comment citing ADR-0007 — mutation-test of dropping it must cause CI failure.
- The `_REGISTRY_ALLOWLIST` constant is a single-host tuple in Phase 3; Phase 7's distroless plugin may widen (e.g., add `cgr.dev`). Document at the constant: "Phase 3 single-host; Phase 7 may widen additively via plugin-local override."
- Re-read `../phase-arch-design.md §Performance envelope` for C12 — the engine should add < 50 ms of pure-Python overhead per `apply` call (the budget is dominated by `npm install` itself). Add a `@pytest.mark.bench` micro-bench in `tests/bench/test_engine_overhead.py` measuring the pure-Python portion.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/engines/__init__.py` | New package |
| `src/codegenie/transforms/engines/npm_lockfile.py` | New — `NpmLockfileRecipeEngine` + `NpmLockfileTransform` + private helpers |
| `tests/unit/transforms/test_npm_lockfile_engine.py` | New — caps, key-order, flags, jail-variant mapping, intra-run determinism |
| `tests/integration/test_npm_lockfile_engine_jail.py` | New — real bwrap; golden lockfile byte-equal |
| `tests/golden/lockfiles/express-cve-2024-21501.before.json` | New — fixture (also referenced by S8-02) |
| `tests/golden/lockfiles/express-cve-2024-21501.after.json` | New — golden post-apply lockfile |
| `tests/fixtures/repos/express-cve-2024-21501/` | Extended (Step 6 created stub) — `package.json` + initial lockfile |
| `pyproject.toml` | Add `orjson = "^3.9"` if not present; `blake3` likely already present from Phase 2 cache |

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
- **`SandboxedPath.open` and `O_NOFOLLOW`**: the API is `path.open("rb")` / `path.open("wb")` — both modes always set `O_NOFOLLOW` (per ADR-0011). Do not bypass this with `os.open(str(path), ...)` — the fence test (S4-04) AST-walks for raw `os.open` under `transforms/` and fails CI.
- **`Result[T, E]` convention**: Phase 3 follows the convention from Phase 5 ADR-0006 (`docs/phases/05-sandbox-trust-gates/ADRs/0006-protocol-vs-abc-convention.md`). If a `codegenie.util.result` module already exists from S1-03, import from there; otherwise define a minimal local `_Result` and surface it for Phase 4 reuse. **Surface this conflict in your PR** (Global Rule 7) — do not invent a parallel `Result` shape if one already lives in the codebase.
- **The `capability: NpmInstallCapability` parameter is unused at this story's call boundary** — the capability is *enforced* by the orchestrator (S6-04) at mint-time + the jail substrate; the engine accepts the parameter for typed-API hygiene (mypy enforces the capability flows through) but does not introspect it. This is the standard pattern from Phase 5; documented at the parameter with a one-line comment.
- **Golden file regeneration is a deliberate operation**: when `package-lock.json` changes (e.g., a transitive sub-dep version bumps), the golden is regenerated by a make target `make refresh-lockfile-golden` (NOT auto-regenerated) and the diff is reviewed in the PR. This is the cardinal goal G4 contract — golden drift IS a regression unless deliberate.
- **Why no LLM here**: this is the deterministic-recipe path. Phase 4 is the LLM-fallback path. Any `import anthropic` or `import openai` under this module is caught by S1-05's fence test and CI-blocked. This story should not import or reference any LLM SDK.
- **Bench expectation**: pure-Python portion (parse + edit + serialize + diff + blake3) should be < 50 ms on the express fixture. If you blow past that, the regression is likely in `_max_depth` (recursive Python over a deep dict — use an iterative stack walker if it shows up in profiling).
