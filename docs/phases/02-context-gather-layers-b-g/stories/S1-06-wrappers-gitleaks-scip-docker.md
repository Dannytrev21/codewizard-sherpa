# Story S1-06 — Wrappers: `gitleaks`, `scip_typescript`, `docker`

**Step:** Step 1 — Plant sandbox extension, tool wrappers, tool-digest pin manifest, and the four Phase-0/1 in-place edits
**Status:** Ready
**Effort:** M
**Depends on:** S1-04
**ADRs honored:** ADR-0003, ADR-0005, ADR-0006

## Context

Three more Phase 2 tool wrappers. `gitleaks` is the highest-risk wrapper in Phase 2: a missing `--redact` flag leaks raw secrets to `repo-context.yaml`, the audit log, and cache blobs. Per ADR-0006's three-layer defense (wrapper invariant → sanitizer Pass 4 → schema `x-secret-finding`), this wrapper is the **first defense**: missing `--redact` raises `ToolInvariantViolation` *before the subprocess runs*. `scip_typescript` is the SCIP binary lifecycle wrapper — accepts an optional `node_modules_path` that is read-only-mounted into the sandbox if present (and **never** triggers `npm install`, per ADR-0013). `docker` is the most consequential addition (per ADR-0005 `docker` subsection): `docker build` opens a Unix socket to the host daemon (the open question — `buildx --driver=docker-container` is the documented fallback if the host-daemon coupling can't be sandboxed).

S1-06 parallelizes with S1-05 and S1-07 after S1-04 lands.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #2 (tools/ wrappers)` — full wrapper contract.
  - `../phase-arch-design.md §"Adversarial tests"` — `test_gitleaks_redaction_invariant.py` (S7-03 e2e), `test_hostile_dockerfile_curl.py` (S6-03 e2e), `test_scip_compiler_plugin_attempt.py` (S4-01 e2e); this story ships the wrapper-level pins these adversarial tests depend on.
- **Phase ADRs:**
  - `../ADRs/0003-subprocess-sandbox-profile-extension.md` — `network="none"` default; `network="scoped"` paths.
  - `../ADRs/0005-allowed-binaries-additions.md` — per-binary subsections for `gitleaks`, `scip-typescript`, `docker`; **`docker` subsection** flags Open Question #1 (`buildx --driver=docker-container` fallback).
  - `../ADRs/0006-output-sanitizer-passes-4-5.md` — ADR-0006 — gitleaks `--redact` is layer #1 of the three-layer secret defense.
  - `../ADRs/0013-scip-node-modules-conditional-mount.md` — ADR-0013 — `node_modules` is read-only-mounted *if present*; `npm install` is **never** invoked.
- **Source design:**
  - `../final-design.md §"Components" #1 tools/ wrappers` — design statement.
- **Existing code:**
  - `src/codegenie/exec.py` — `run_in_sandbox` (extended in S1-02; accepts `ro_bind`).
  - `src/codegenie/tools/__init__.py` — `ToolResult` base (S1-04).
  - `src/codegenie/errors.py` — typed exceptions (S1-01).

## Goal

Implement `src/codegenie/tools/gitleaks.py`, `src/codegenie/tools/scip_typescript.py`, and `src/codegenie/tools/docker.py` per the wrapper contract, with `gitleaks` enforcing mandatory `--redact`, `scip_typescript` accepting an optional `node_modules_path` for read-only mount, and `docker.build` defaulting `--network=none` for the build phase and supporting opt-in `scoped_egress_hosts` for the initial base-image pull.

## Acceptance criteria

- [ ] `src/codegenie/tools/gitleaks.py` exports `GitleaksResult(ToolResult)` (with `findings: list[GitleaksFinding]`), `TOOL_NAME = "gitleaks"`, `async def run(target: Path, raw_output_path: Path, redact: bool = True, timeout_s: float = 120.0) -> GitleaksResult`. **`redact=False` is not a supported caller path** — passing it raises `ToolInvariantViolation` *before any subprocess runs*; missing `--redact` in the constructed argv (e.g., via internal logic bug) also raises `ToolInvariantViolation`.
- [ ] `src/codegenie/tools/scip_typescript.py` exports `ScipTypescriptResult(ToolResult)`, `TOOL_NAME = "scip-typescript"`, `async def run(repo_path: Path, raw_output_path: Path, node_modules_path: Path | None = None, timeout_s: float = 600.0) -> ScipTypescriptResult`. When `node_modules_path` is provided, it is passed to `run_in_sandbox(..., ro_bind=(node_modules_path,))`; when `None`, the sandbox does **not** create or mount any `node_modules`, and the wrapper does **not** invoke `npm install` (the wrapper has no code path that can do so).
- [ ] `src/codegenie/tools/docker.py` exports `DockerBuildResult(ToolResult)` (with `image_digest: str`, `build_status: Literal["success","failed"]`), `TOOL_NAME = "docker"`, `async def build(context_path: Path, dockerfile: Path, raw_output_path: Path, scoped_egress_hosts: Sequence[str] = (), timeout_s: float = 600.0) -> DockerBuildResult`. The build phase runs with `network="none"`; the base-image pull (if needed) runs with `network="scoped"` only when `scoped_egress_hosts` is non-empty. `docker.manifest_inspect(image_ref)` is a separate async function with an LRU cache (`functools.lru_cache` or hand-rolled with `cachetools.TTLCache` 1 h).
- [ ] Every wrapper routes through `exec.run_in_sandbox`; the `scripts/check_tools_no_subprocess.py` lint passes on all three modules.
- [ ] `tests/unit/tools/test_gitleaks.py` ships ≥ 5 tests — happy path, `ToolInvariantViolation` on `redact=False`, `ToolInvariantViolation` on internal-bug missing `--redact` in argv (test the argv builder directly), `ToolNonZeroExit`, `ToolTimeout`, `ToolNotFound`, `ToolOutputMalformed`.
- [ ] `tests/unit/tools/test_scip_typescript.py` ships ≥ 5 tests — happy path with `node_modules_path`, happy path without (sandbox argv does **not** contain a `node_modules` `--ro-bind`), no `npm install` ever appears in any argv constructed by the wrapper (test the argv builder), the standard error/timeout/parse cases.
- [ ] `tests/unit/tools/test_docker.py` ships ≥ 5 tests — happy build with `network="none"`, base-image-pull with `network="scoped"` only when hosts non-empty, `manifest_inspect` is LRU-cached (second call inside TTL window does not re-spawn), `ToolNonZeroExit`, `ToolTimeout`.
- [ ] Each wrapper emits `probe.tool.invoked` per call with `tool_name`, `sandbox_network`, `wall_clock_ms`, `exit_code`.
- [ ] No `httpx` / `requests` / `urllib` / direct `subprocess` import in any of the three modules.
- [ ] The TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Write the three test files first (red); patch the `_spawn_sandboxed` indirection per S1-05's pattern.
2. Implement `src/codegenie/tools/gitleaks.py`:
   - `class GitleaksFinding(BaseModel)` (`rule_id`, `file`, `start_line`, `description`, `content_hash`, `entropy_band`, `length`) — never has `match` / `raw` / `value` fields (ADR-0006's `x-secret-finding` shape; sanitized at source).
   - `_build_argv(target, redact)` constructs `["gitleaks", "detect", "--source", str(target), "--report-format", "json", "--report-path", str(raw_output_path)]` and appends `--redact` unconditionally when `redact=True`. The function asserts `--redact in argv` before returning; failure → `ToolInvariantViolation(tool_name="gitleaks", invariant="--redact missing")`.
   - `async def run(...)` — first guard: `if redact is not True: raise ToolInvariantViolation(...)`. Then call `_build_argv`. Then `run_in_sandbox` with `network="none"`.
3. Implement `src/codegenie/tools/scip_typescript.py`:
   - `class ScipTypescriptResult(ToolResult)` — minimal; the SCIP binary is the artifact, parsed downstream by `SCIPIndexProbe` (S4-01).
   - `_build_argv(repo_path, output_path)` constructs `["scip-typescript", "index", "--output", str(output_path), str(repo_path)]`. The wrapper has no `npm install` code path — assert in a unit test that scanning the wrapper module's source via `ast.parse` finds no `Call` whose argv list contains the literal string `"npm"` followed by `"install"`.
   - `async def run(..., node_modules_path)` calls `run_in_sandbox(..., ro_bind=((node_modules_path,) if node_modules_path else ()))`.
4. Implement `src/codegenie/tools/docker.py`:
   - `class DockerBuildResult(ToolResult)` adding `image_digest: str`, `build_status: Literal["success","failed"]`.
   - `async def build(...)` — if `scoped_egress_hosts` is non-empty, the wrapper makes **two** calls: (a) a base-image pull pass with `network="scoped"`, (b) a build pass with `network="none"`. If empty, one call with `network="none"` (caller asserts the image is already on disk).
   - `async def manifest_inspect(image_ref)` — `["docker", "manifest", "inspect", image_ref]`, `network="scoped"` to the configured registry host (callers must pass the host). LRU-cache by `image_ref` with 1 h TTL; use `cachetools.TTLCache` if a dep, or a small hand-rolled cache in the module if not (preference: avoid new deps).
5. Each wrapper emits `probe.tool.invoked` after the sandbox call.
6. Run the test suite, the lint, `ruff check`, `mypy --strict`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/tools/test_gitleaks.py` (and parallel files for scip + docker).

```python
import ast
import inspect
from pathlib import Path
from unittest.mock import patch

import pytest

import codegenie.errors as e
from codegenie.tools import gitleaks


@pytest.mark.asyncio
async def test_gitleaks_redact_false_raises_invariant_before_subprocess(tmp_path: Path):
    with patch("codegenie.tools.gitleaks._spawn_sandboxed") as spawn:
        with pytest.raises(e.ToolInvariantViolation) as exc:
            await gitleaks.run(target=tmp_path, raw_output_path=tmp_path / "r.json", redact=False)
        # critically: spawn never called
        spawn.assert_not_called()
    assert "redact" in exc.value.invariant.lower()


def test_gitleaks_argv_builder_pins_redact_flag():
    argv = gitleaks._build_argv(target=Path("/r"), raw_output_path=Path("/r.json"), redact=True)
    assert "--redact" in argv


def test_gitleaks_argv_builder_missing_redact_raises():
    # Simulate an internal bug — caller passes redact=True but builder somehow omits it
    with pytest.raises(e.ToolInvariantViolation):
        gitleaks._build_argv_unsafe(target=Path("/r"), raw_output_path=Path("/r.json"))  # internal test seam
```

```python
# tests/unit/tools/test_scip_typescript.py
import ast
import inspect

from codegenie.tools import scip_typescript


def test_scip_wrapper_never_invokes_npm_install():
    # Static analysis: the wrapper module's source contains no Call with "npm" "install" in argv
    src = inspect.getsource(scip_typescript)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.List):
            literals = [n.value for n in node.elts if isinstance(n, ast.Constant) and isinstance(n.value, str)]
            assert not ("npm" in literals and "install" in literals), \
                "scip_typescript wrapper must never construct npm install argv (ADR-0013)"
```

```python
# tests/unit/tools/test_docker.py
from pathlib import Path
from unittest.mock import patch

import pytest

from codegenie.tools import docker


@pytest.mark.asyncio
async def test_docker_build_network_none_when_no_scoped_hosts(tmp_path: Path):
    with patch("codegenie.tools.docker._spawn_sandboxed") as spawn:
        spawn.return_value = ("", "", 0, 100)
        await docker.build(context_path=tmp_path, dockerfile=tmp_path / "Dockerfile",
                           raw_output_path=tmp_path / "out.json", scoped_egress_hosts=())
    # Verify the call passed network="none"
    _, kw = spawn.call_args
    assert kw.get("network") == "none"


@pytest.mark.asyncio
async def test_docker_manifest_inspect_lru_cached(tmp_path: Path):
    with patch("codegenie.tools.docker._spawn_sandboxed") as spawn:
        spawn.return_value = ('{"digest":"sha256:abc"}', "", 0, 30)
        await docker.manifest_inspect("alpine:3.18", registry_host="registry-1.docker.io")
        await docker.manifest_inspect("alpine:3.18", registry_host="registry-1.docker.io")
    assert spawn.call_count == 1  # second call hit cache
```

Run; confirm `ImportError` on the three modules. Commit as red marker.

### Green — make it pass

Land the three wrappers per the implementation outline.

### Refactor — clean up

- The gitleaks `_build_argv` + `_build_argv_unsafe` pair is intentionally asymmetric: the safe version always inserts `--redact`; the unsafe version exists solely for the negative test that asserts the invariant fires when the flag is missing. Document `_build_argv_unsafe` as a test seam in its docstring; do not export it from the module's `__all__`.
- `docker.manifest_inspect` caching: prefer a tiny `dict` + `time.monotonic()` TTL check over a new dep. The TTL is 1 h; cache hit is the common case; eviction is on next-call check. Confirm `mypy --strict` clean.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/tools/gitleaks.py` | New — wrapper with `--redact` invariant |
| `src/codegenie/tools/scip_typescript.py` | New — wrapper with optional `node_modules` ro-bind |
| `src/codegenie/tools/docker.py` | New — `build` + `manifest_inspect` with TTL cache |
| `tests/unit/tools/test_gitleaks.py` | New — invariant + standard error coverage |
| `tests/unit/tools/test_scip_typescript.py` | New — incl. `no npm install` static check |
| `tests/unit/tools/test_docker.py` | New — incl. LRU cache + network-mode coverage |
| `tests/fixtures/tool_outputs/{gitleaks,scip,docker}/...` | New — recorded fixtures |

## Out of scope

- **`semgrep`, `syft`, `grype` wrappers** — handled by S1-05.
- **`treesitter` in-process wrapper** — handled by S1-07.
- **Tool digest pin manifest** — handled by S1-08.
- **Signed `grype-db-listing.signed.json`** — handled by S6-02.
- **End-to-end `test_hostile_dockerfile_curl.py` adversarial** — handled by S6-03.
- **End-to-end `test_gitleaks_redaction_invariant.py` adversarial** — handled by S7-03 (planted `AKIAFAKE...` byte test).
- **The `buildx --driver=docker-container` fallback** — Open Question #1 from ADR-0005 resolves in S6-01 if host-daemon coupling fails at integration. This story uses default `docker build`.
- **`SCIPIndexProbe` itself** (`.codegenie/index/scip-index.scip` lifecycle) — handled by S4-01.

## Notes for the implementer

- **The gitleaks `--redact` invariant is the most security-critical line of code in Phase 2.** Per ADR-0006, sanitizer Pass 4 and the schema `x-secret-finding` tag are belt-and-suspenders defenses; the wrapper is the **first defense**. A wrapper bug here means raw secrets reach disk before any other defense can fire. The two-test pattern (one for the public `run(..., redact=False)` path, one for the internal argv builder) pins both surfaces.
- The "no `npm install`" static check on `scip_typescript.py` is the wrapper-level pin for ADR-0013. If a future contributor adds an `npm install` call (intentionally or accidentally), the static AST scan fails CI. Per Rule 12 (Fail loud), this is louder than relying on integration tests to catch the regression.
- `docker.build` makes two sandbox calls when `scoped_egress_hosts` is non-empty: pull (scoped) → build (none). The pull pass writes the image layers to the local daemon's image store (which is on the host); the build pass references the same image. If the implementation can't get this two-pass behavior to work without leaking the host daemon socket, the fallback is `confidence: low` with structured warning (Open Question #1 from ADR-0005); document the fallback in `docker.py` even though it's not invoked here.
- `docker.manifest_inspect` is called by `SyftSBOMProbe` (S6-01) to populate the cache-key field `base_image_digest_at_registry`. The 1 h TTL is per ADR-0004's cache discipline — long enough to amortize over a gather run, short enough that a base-image rotation lands within a workday.
- `node_modules_path` is `Path | None`, not `Path` with a default. The `None` case is the common case (most repos analyzed in Phase 2 don't have `node_modules` checked in); ADR-0013 says when it's absent the probe emits `confidence: medium` rather than degrading. The wrapper's contract: if `None`, no `ro_bind`; the probe is responsible for whatever degradation logic ADR-0013 specifies.
- The `_spawn_sandboxed` indirection is the same seam used in S1-05. Keep the function name verbatim across all six wrappers so test patches stay uniform.
- Do **not** add a `dry_run` or `print_argv_only` mode to any wrapper. Per Rule 2 (Simplicity First), the test seam (`_spawn_sandboxed` patch) is sufficient.
- The `docker` wrapper has the largest threat surface (per ADR-0005's `docker` subsection). Triple-check the argv construction against the `bwrap` capability list — particularly that `--network=none` is in the bwrap argv and not just declared in a structlog field.
