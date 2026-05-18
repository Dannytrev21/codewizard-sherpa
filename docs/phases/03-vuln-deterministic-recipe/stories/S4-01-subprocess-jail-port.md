# Story S4-01 — `SubprocessJail` Port + `JailedSubprocessResult` tagged union + typed env/network sums

**Step:** Step 4 — SubprocessJail Port + Bwrap + sandbox-exec + ALLOWED_BINARIES amendment
**Status:** Ready
**Effort:** M
**Depends on:** S1-03 (tagged-union outcomes — `RecipeOutcome`, `RemediationOutcome`, `NodeTransition`, `AdapterConfidence`, `Applicability` discriminated unions already exist; this story reuses the same Pydantic `Discriminator("kind")` pattern)
**ADRs honored:** 03-ADR-0006 (Hexagonal `SubprocessJail` Port + Bwrap/sandbox-exec adapters), 03-ADR-0007 (run `npm install`/`npm test` in the jail — consumer of this Port), production ADR-0012 (microVM substitution at Phase 5 — substitutes via the same Port)

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
1. `SubprocessJail(Protocol)` — one method `async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult`.
2. `JailedSubprocessSpec(BaseModel, frozen=True, extra="forbid")` — `cmd: tuple[str, ...]`, `cwd: SandboxedPath`, `env: NpmEnv | GitEnv`, `network: NetworkPolicy`, `time_budget_s`, `memory_mib`, `pids_max`.
3. `JailedSubprocessResult = Annotated[Completed | TimedOut | OomKilled | NetworkDenied | DiskQuotaExceeded, Field(discriminator="kind")]` — discriminated Pydantic union with one variant per failure mode; no `dict[str, Any]`; no bare exceptions returned.
4. `NpmEnv | GitEnv` typed env wrappers — Pydantic models, not raw `dict[str, str]`; only fields each tool legitimately needs.
5. `NetworkPolicy = DenyAll | RegistryAllowlist(hosts: frozenset[RegistryUrl])` sum (also `Annotated[..., Field(discriminator="kind")]`).
6. A `to_env_mapping()` helper on each `*Env` that produces the `dict[str, str]` the adapter ultimately passes to `run_external_cli`, with `--ignore-scripts`'s env half (`npm_config_ignore_scripts="true"`) hard-coded inside `NpmEnv` so a consumer cannot construct an `NpmEnv` without it (the CLI half lives at the call site — `cmd` — and is consumer responsibility per ADR-0006; the env half is structurally enforced here).

Every variant ships with a `kind: Literal[...]` discriminator. `mypy --strict` clean. Every variant must be reachable by at least one `match` statement with `assert_never` (S1-05's AST fence pins this).

`SandboxedPath` is imported as a forward-declared type — S4-04 lands the concrete implementation. This story uses a `Protocol`-typed alias (or `TYPE_CHECKING` import) so the two stories can land in either order with no circular dep. (Per High-level-impl Step 4, both depend on S4-01 and S4-04 happens to share the Step's namespace; the import discipline is documented at the symbol.)

## Acceptance criteria

- [ ] **AC-1.** `src/codegenie/transforms/sandbox_jail.py` exists and exports exactly: `SubprocessJail`, `JailedSubprocessSpec`, `JailedSubprocessResult`, `Completed`, `TimedOut`, `OomKilled`, `NetworkDenied`, `DiskQuotaExceeded`, `NpmEnv`, `GitEnv`, `NetworkPolicy`, `DenyAll`, `RegistryAllowlist`. A pytest meta-test (`test_module_exports_exact`) asserts `set(dir(sandbox_jail)) >= EXPECTED` and that no symbol leaks `Any` in its public annotation.
- [ ] **AC-2.** `SubprocessJail` is a `typing.Protocol` with one method: `async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult`. A pytest meta-test (`test_subprocess_jail_is_protocol`) asserts `inspect.isclass(SubprocessJail) and SubprocessJail._is_protocol is True` and that `SubprocessJail.__abstractmethods__ == frozenset({"run"})`.
- [ ] **AC-3.** `JailedSubprocessSpec` is a frozen Pydantic v2 model with `model_config = ConfigDict(frozen=True, extra="forbid")`. A pytest test asserts:
  - Constructing with an unknown field raises `ValidationError`.
  - Mutating any field on an instance raises `ValidationError` (frozen).
  - Every field is typed (no `Any`, no untyped `dict`).
- [ ] **AC-4.** `JailedSubprocessResult` is a discriminated union: every variant has `kind: Literal["completed" | "timed_out" | "oom_killed" | "network_denied" | "disk_quota_exceeded"]`. A pytest test round-trips each variant through `model_dump()` → `JailedSubprocessResult.model_validate(...)` and confirms the discriminator routes back to the exact same class. Wrong-kind data (`{"kind": "completed", "host": "x"}`) raises `ValidationError`.
- [ ] **AC-5.** `NetworkDenied(host: str, kind: Literal["network_denied"])` — `host` is observable per ADR-0006 §Decision. A pytest test asserts the field is required, non-empty, and present in the discriminator's serialized output.
- [ ] **AC-6.** `NetworkPolicy = Annotated[DenyAll | RegistryAllowlist, Field(discriminator="kind")]`. `RegistryAllowlist` has `hosts: frozenset[RegistryUrl]` (NOT `set`; NOT `list`; immutability via Pydantic v2's `frozen=True` plus the `frozenset` type). Constructing `RegistryAllowlist(hosts=frozenset())` raises `ValidationError` (empty allowlist is meaningless; same as `DenyAll`).
- [ ] **AC-7.** `NpmEnv` is a frozen Pydantic model. Its `to_env_mapping()` ALWAYS includes `npm_config_ignore_scripts="true"` regardless of constructor input — a parametrized test passes `NpmEnv()` and `NpmEnv(extra={"npm_config_ignore_scripts": "false"})` (or whatever field is exposed for extension) and asserts `to_env_mapping()["npm_config_ignore_scripts"] == "true"` in BOTH cases. The env-half of `--ignore-scripts` is structurally inviolable from this Port (ADR-0006 §Decision: "npm has historically respected only one or the other; we set both"). The CLI half lives at `JailedSubprocessSpec.cmd` and is the consumer's responsibility (S5-02 enforces); S4-05 adds a fence test that ties them together.
- [ ] **AC-8.** `GitEnv` is a frozen Pydantic model whose `to_env_mapping()` ALWAYS includes `GIT_TERMINAL_PROMPT="0"` and `GIT_ASKPASS="/bin/false"` (per ADR-0006 cross-reference to S6-04's `LocalGitOps`). A parametrized test asserts both keys are present regardless of constructor input.
- [ ] **AC-9.** Every `JailedSubprocessResult` variant is consumed by a `match` statement with `assert_never` in `tests/unit/transforms/test_sandbox_jail_exhaustiveness.py` — this is the AST-fence target S1-05's `tests/unit/transforms/test_exhaustiveness.py` discovers. The test must compile under `mypy --strict` and the `match` arms must cover every `kind` literal value.
- [ ] **AC-10.** A `_StubJail(SubprocessJail)` implementation in the test file demonstrates the Port can be implemented in <10 lines and round-trips a `JailedSubprocessSpec` to a `Completed` result. This is the structural proof that the Protocol is implementable; the real adapters (S4-02/S4-03) follow this shape.
- [ ] **AC-11.** `JailedSubprocessSpec.cwd` is typed as `SandboxedPath` (imported via `TYPE_CHECKING` from `codegenie.plugins.sandbox_path` per ADR-0011 §Consequences). A pytest test asserts the field's `model_fields["cwd"].annotation` is `SandboxedPath` (or its qualified name). If S4-04 has not landed yet, the test uses a `Protocol`-typed shim and the file uses `from __future__ import annotations` so the import is string-resolved.
- [ ] **AC-12.** No `dict[str, Any]` and no bare `Exception` anywhere in `sandbox_jail.py`. A grep test (`tests/unit/transforms/test_sandbox_jail_typed.py`) reads the module source and asserts neither pattern appears. Bare exceptions in the failure path are the toolkit's exact failure mode the Port is built to avoid (every failure mode is a typed variant per ADR-0006 §Tradeoffs row 4).
- [ ] **AC-13.** `mypy --strict src/codegenie/transforms/sandbox_jail.py tests/unit/transforms/` clean. `ruff check` + `ruff format --check` clean on touched files.
- [ ] **AC-14.** `make lint-imports` (Phase 3 contracts from S1-05) confirms no LLM SDK appears in `src/codegenie/transforms/sandbox_jail.py`'s import closure. (The `tests/fence/test_no_llm_in_transforms.py` test extends to cover this module specifically by virtue of being under `src/codegenie/transforms/`.)
- [ ] **AC-15.** A snapshot test (`tests/integration/test_phase5_contract_snapshot.py` extension, or a precursor `tests/unit/transforms/test_sandbox_jail_contract_snapshot.py`) records the JSON schema of `JailedSubprocessSpec` and each `JailedSubprocessResult` variant to a golden file. S6-06's contract-snapshot integration test consumes this; an additive field is permitted; a rename / removal / required-add requires explicit ADR amendment per Step 9 risk #4.

## Implementation outline

1. Create `src/codegenie/transforms/sandbox_jail.py`. Imports: `from __future__ import annotations`, `typing.Protocol`, `typing.Literal`, `typing.Annotated`, `typing.TYPE_CHECKING`, `pydantic.BaseModel`, `pydantic.ConfigDict`, `pydantic.Field`, `pydantic.field_validator`, and `codegenie.types.identifiers.RegistryUrl`.
2. Inside `if TYPE_CHECKING:`, import `SandboxedPath` from `codegenie.plugins.sandbox_path` (S4-04). Outside `TYPE_CHECKING`, declare a forward-string `"SandboxedPath"` on `JailedSubprocessSpec.cwd` so the module loads before S4-04 lands.
3. Define the `NpmEnv` / `GitEnv` Pydantic models with `model_config = ConfigDict(frozen=True, extra="forbid")` and a `to_env_mapping(self) -> dict[str, str]` that hard-codes the required defenses (`npm_config_ignore_scripts="true"` for `NpmEnv`; `GIT_TERMINAL_PROMPT="0"`, `GIT_ASKPASS="/bin/false"` for `GitEnv`).
4. Define `DenyAll(BaseModel)` with `kind: Literal["deny_all"] = "deny_all"`. Define `RegistryAllowlist(BaseModel)` with `kind: Literal["registry_allowlist"] = "registry_allowlist"`, `hosts: frozenset[RegistryUrl]`, and a `field_validator("hosts")` that rejects empty frozensets.
5. Define `NetworkPolicy = Annotated[DenyAll | RegistryAllowlist, Field(discriminator="kind")]`.
6. Define each `JailedSubprocessResult` variant — `Completed(kind: Literal["completed"], exit_code: int, stdout_bytes: int, stderr_bytes: int, wall_time_s: float)`; `TimedOut(kind: Literal["timed_out"], budget_s: float, elapsed_s: float)`; `OomKilled(kind: Literal["oom_killed"], peak_rss_mib: int)`; `NetworkDenied(kind: Literal["network_denied"], host: str)`; `DiskQuotaExceeded(kind: Literal["disk_quota_exceeded"], quota_bytes: int, bytes_written: int)`. Every model is `frozen=True, extra="forbid"`.
7. Define `JailedSubprocessResult = Annotated[Completed | TimedOut | OomKilled | NetworkDenied | DiskQuotaExceeded, Field(discriminator="kind")]`.
8. Define `JailedSubprocessSpec(BaseModel, frozen=True, extra="forbid")` with `cmd`, `cwd`, `env`, `network`, `time_budget_s`, `memory_mib`, `pids_max`.
9. Define the `SubprocessJail(Protocol)` with `async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult: ...`.
10. Write the red tests (AC-1..AC-15 minus the snapshot, which lands last so it captures the final shape).
11. Confirm `mypy --strict`, `ruff`, and `pytest tests/unit/transforms/test_sandbox_jail*.py` green.
12. Generate the contract snapshot golden file (`tests/golden/contracts/sandbox_jail.schema.json`) by serializing `JailedSubprocessSpec.model_json_schema()` and each variant's schema; commit.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file path: `tests/unit/transforms/test_sandbox_jail.py`

```python
from __future__ import annotations

import inspect
from typing import Annotated, Literal, get_args, get_origin, get_type_hints

import pytest
from pydantic import Field, ValidationError

# These imports fail RED before the module exists.
from codegenie.transforms.sandbox_jail import (
    Completed,
    DenyAll,
    DiskQuotaExceeded,
    GitEnv,
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
from codegenie.types.identifiers import RegistryUrl


# AC-2
def test_subprocess_jail_is_protocol() -> None:
    assert inspect.isclass(SubprocessJail)
    assert getattr(SubprocessJail, "_is_protocol", False) is True
    assert SubprocessJail.__abstractmethods__ == frozenset({"run"})


# AC-3
def test_jailed_subprocess_spec_is_frozen_and_forbid() -> None:
    npm = NpmEnv()
    spec = JailedSubprocessSpec(
        cmd=("npm", "install", "--ignore-scripts"),
        cwd=_FakeSandboxedPath(),  # type: ignore[arg-type]
        env=npm,
        network=DenyAll(),
        time_budget_s=60.0,
        memory_mib=512,
        pids_max=128,
    )
    with pytest.raises(ValidationError):
        JailedSubprocessSpec(
            cmd=("npm",), cwd=_FakeSandboxedPath(), env=npm, network=DenyAll(),
            time_budget_s=1.0, memory_mib=1, pids_max=1, surprise="x",  # type: ignore[call-arg]
        )
    with pytest.raises(ValidationError):
        spec.time_budget_s = 5.0  # type: ignore[misc]


# AC-4 — discriminator routing round-trips
@pytest.mark.parametrize(
    "variant",
    [
        Completed(kind="completed", exit_code=0, stdout_bytes=0, stderr_bytes=0, wall_time_s=0.1),
        TimedOut(kind="timed_out", budget_s=60.0, elapsed_s=60.0),
        OomKilled(kind="oom_killed", peak_rss_mib=512),
        NetworkDenied(kind="network_denied", host="evil.example.com"),
        DiskQuotaExceeded(kind="disk_quota_exceeded", quota_bytes=1024, bytes_written=2048),
    ],
)
def test_result_variant_roundtrip(variant: object) -> None:
    from pydantic import TypeAdapter

    adapter = TypeAdapter(JailedSubprocessResult)
    payload = adapter.dump_python(variant)
    parsed = adapter.validate_python(payload)
    assert type(parsed) is type(variant)
    assert parsed == variant


def test_result_wrong_kind_rejected() -> None:
    from pydantic import TypeAdapter

    adapter = TypeAdapter(JailedSubprocessResult)
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "completed", "host": "x"})  # missing required + extra


# AC-5
def test_network_denied_host_required_and_serialized() -> None:
    nd = NetworkDenied(kind="network_denied", host="evil.example.com")
    assert "host" in nd.model_dump()
    assert nd.model_dump()["host"] == "evil.example.com"
    with pytest.raises(ValidationError):
        NetworkDenied(kind="network_denied", host="")  # empty rejected
    with pytest.raises(ValidationError):
        NetworkDenied(kind="network_denied")  # type: ignore[call-arg]


# AC-6
def test_network_policy_discriminator_and_empty_allowlist_rejected() -> None:
    from pydantic import TypeAdapter

    adapter = TypeAdapter(NetworkPolicy)
    deny = adapter.validate_python({"kind": "deny_all"})
    assert isinstance(deny, DenyAll)

    allow = adapter.validate_python(
        {"kind": "registry_allowlist", "hosts": ["https://registry.npmjs.org"]}
    )
    assert isinstance(allow, RegistryAllowlist)
    assert RegistryUrl("https://registry.npmjs.org") in allow.hosts

    with pytest.raises(ValidationError):
        RegistryAllowlist(hosts=frozenset())


# AC-7 — npm_config_ignore_scripts is structurally enforced
def test_npm_env_ignore_scripts_is_inviolable() -> None:
    env = NpmEnv()
    assert env.to_env_mapping()["npm_config_ignore_scripts"] == "true"


def test_npm_env_to_env_mapping_strips_attempted_override() -> None:
    # Even if NpmEnv ever grows an `extra` mapping field, the structural override
    # at to_env_mapping() time MUST win. Document the discipline at the test boundary.
    env = NpmEnv()
    mapping = env.to_env_mapping()
    assert mapping.get("npm_config_ignore_scripts") == "true"


# AC-8
def test_git_env_safety_keys_inviolable() -> None:
    env = GitEnv()
    mapping = env.to_env_mapping()
    assert mapping["GIT_TERMINAL_PROMPT"] == "0"
    assert mapping["GIT_ASKPASS"] == "/bin/false"


# AC-10 — Protocol is implementable in <10 lines
class _StubJail:
    async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult:
        return Completed(
            kind="completed", exit_code=0, stdout_bytes=0, stderr_bytes=0, wall_time_s=0.0
        )


async def test_protocol_is_implementable() -> None:
    stub: SubprocessJail = _StubJail()
    spec = JailedSubprocessSpec(
        cmd=("npm", "--version"),
        cwd=_FakeSandboxedPath(),  # type: ignore[arg-type]
        env=NpmEnv(),
        network=RegistryAllowlist(hosts=frozenset({RegistryUrl("https://registry.npmjs.org")})),
        time_budget_s=5.0,
        memory_mib=128,
        pids_max=64,
    )
    result = await stub.run(spec)
    assert isinstance(result, Completed)


# AC-11 — cwd annotation is SandboxedPath
def test_cwd_annotation_is_sandboxed_path() -> None:
    hints = get_type_hints(JailedSubprocessSpec, include_extras=True)
    # SandboxedPath is forward-imported under TYPE_CHECKING; the resolved hint
    # carries the name regardless of when S4-04 lands.
    assert "SandboxedPath" in repr(hints["cwd"])


# AC-12 — typed-discipline grep
def test_module_source_has_no_dict_any_or_bare_exception() -> None:
    import codegenie.transforms.sandbox_jail as mod

    src = inspect.getsource(mod)
    assert "dict[str, Any]" not in src
    assert "Dict[str, Any]" not in src
    # bare `except Exception:` and bare `raise Exception(` both forbidden
    assert "except Exception" not in src
    assert "raise Exception(" not in src


# AC-15 — schema snapshot precursor (full snapshot test lands in S6-06)
def test_spec_schema_is_stable() -> None:
    schema = JailedSubprocessSpec.model_json_schema()
    # Spot-check the load-bearing shape; full byte-equal snapshot in S6-06.
    assert schema["properties"]["cmd"]["type"] == "array"
    assert "discriminator" in str(schema)  # network + env are discriminated


# Helper — minimal SandboxedPath shim so the spec can be constructed before S4-04.
class _FakeSandboxedPath:
    """In-test shim. S4-04 lands the real type; the Port treats `cwd` as
    structurally `SandboxedPath` and the validator runs at instance time."""
    @property
    def absolute(self) -> object: ...  # not exercised here
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

Run — every test in both files fails because the module doesn't exist. Commit the red.

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
| `src/codegenie/transforms/sandbox_jail.py` | New module: `SubprocessJail` Protocol, `JailedSubprocessSpec`, `JailedSubprocessResult` discriminated union, `NpmEnv`/`GitEnv` typed env wrappers, `NetworkPolicy = DenyAll | RegistryAllowlist` sum (AC-1..AC-12). |
| `tests/unit/transforms/test_sandbox_jail.py` | New test file. Covers AC-1..AC-8, AC-10..AC-12, AC-15 schema precursor. |
| `tests/unit/transforms/test_sandbox_jail_exhaustiveness.py` | New test file. AC-9 `match` + `assert_never` over every `JailedSubprocessResult` variant. This is the file S1-05's exhaustiveness AST fence discovers. |
| `tests/golden/contracts/sandbox_jail.schema.json` | New golden file. `JailedSubprocessSpec.model_json_schema()` + each variant's schema. S6-06 consumes. |
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
- **`SandboxedPath` import discipline.** S4-04 lands the concrete type at `src/codegenie/plugins/sandbox_path.py` (per ADR-0011 §Consequences). High-level-impl §Step 4 features-delivered bullet says `src/codegenie/transforms/sandbox_path.py` — that's a docs drift. Per Rule 7 (Surface conflicts, don't average), the ADR is the more recent, more load-bearing decision; follow `codegenie.plugins.sandbox_path`. Flag the High-level-impl bullet in the S4-04 attempt log so it can be reconciled in a follow-up doc fix story (not this one).
- **`--ignore-scripts` split discipline.** Per ADR-0006 §Decision: "npm has historically respected only one or the other; we set both." The env half (`npm_config_ignore_scripts="true"`) is **structurally enforced here** inside `NpmEnv.to_env_mapping()` — a consumer cannot bypass it without subclassing or reaching into private state. The CLI half (`--ignore-scripts` in `cmd`) lives at the consumer (S5-02's `NpmLockfileRecipeEngine`); S4-05's capability-fence test ties them together by asserting every npm-related `JailedSubprocessSpec` constructed in `src/codegenie/transforms/engines/npm_lockfile.py` has `--ignore-scripts` literally in `cmd`. Document this split at the symbol.
- **`frozenset[RegistryUrl]` for hosts.** `set` is mutable; `list` admits duplicates and ordering. `frozenset[RegistryUrl]` is the right type: immutable, set-semantics, newtype-typed per ADR-0010. Pydantic v2 supports `frozenset` natively with `frozen=True` on the parent model.
- **Discriminated-union shape matches S1-03 precedent.** `RecipeOutcome`, `RemediationOutcome`, `NodeTransition`, `AdapterConfidence`, `Applicability` all use `Annotated[Union[...], Field(discriminator="kind")]`. Mirror the pattern verbatim. The exhaustiveness AST fence (S1-05) treats every such union as a target.
- **No `dict[str, Any]`, no bare exceptions.** Per ADR-0006 §Tradeoffs row 4: "every branch typed; no `dict[str, Any]`, no bare exceptions." The AC-12 grep test enforces this at the file level; the S1-05 `test_no_any_in_plugin_surface.py` AST fence will catch any escapee at the AST level. Both fences must be green.
- **Async-vs-sync open question.** ADR-0006 §Consequences last bullet defers the choice between `asyncio.to_thread(subprocess.run, ...)` and `asyncio.create_subprocess_exec` to the adapter authors (S4-02 / S4-03). The Port is `async def run(...)`; how each adapter implements it is its concern. This story does not pick.
- **Snapshot test handoff to S6-06.** AC-15's precursor snapshot is local; S6-06 lands the integration `test_phase5_contract_snapshot.py` that consumes this story's golden plus the orchestrator / scorer / transform / apply-context / recipe-engine schemas. Per Step 9 risk #4: additive deltas (new optional field with `default_factory`) permitted; breaking deltas (rename, remove, required-add) require explicit ADR amendment + golden refresh.
