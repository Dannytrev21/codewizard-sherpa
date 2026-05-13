# Story S2-02 — `tools/buildkit.py` wrapper + builder bootstrap

**Step:** Step 2 — Tool wrappers and the pre-rendered base catalog hot view
**Status:** Ready
**Effort:** M
**Depends on:** S2-01
**ADRs honored:** ADR-P7-002 (`docker` on `ALLOWED_BINARIES`, `cgr.dev`/`docker.io` on egress allowlist), ADR-0010 (credentials via operator's `~/.docker/config.json`, no `codegenie-secretd`), ADR-0003 (egress + allowlist additive seam)

## Context

This story lands the **second** tool wrapper. Every Phase 7 component that talks to a container registry or builds a Dockerfile flows through `tools/buildkit.py`: `BaseImageProbe` uses it for `docker buildx imagetools inspect`; `ShellInvocationTraceProbe`'s candidate-build step uses it for `docker buildx build`; the Node Express E2E in Step 5 hits both paths; the buildkit cache hit-rate canary in Step 7 measures it. Determinism, auto-bootstrap of the named builder (Gap 7), and **honest `RegistryAuthFailed` parsing from stderr** (ADR-0010 — no credential storage in `codegenie`) are the three load-bearing behaviors.

The wrapper is the single chokepoint where `phase-arch-design.md §Edge cases #7` ("`~/.docker/config.json` missing or unauthenticated for `cgr.dev`") materializes — operator-friendly error, not a confusing buildkit traceback.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — 2. ShellInvocationTraceProbe` (lines ~531–559) — describes the build invocation `docker buildx build --load --cache-from=type=local,src=.codegenie/cache/buildkit --cache-to=...`.
  - `../phase-arch-design.md §Component design — 1. BaseImageProbe` (lines ~503–529) — `docker buildx imagetools inspect --raw --platform=linux/amd64` and 24h cache; `--platform` must be in the cache key (closes critic perf.assumption.2).
  - `../phase-arch-design.md §Data model ›Internal` (`BuildkitResult` Pydantic) — `exit_code`, `image_digest`, `manifest_path`, `layer_count`, `wall_clock_ms`.
  - `../phase-arch-design.md §Edge cases #4` (multi-arch manifest list silently reused — closed by `--platform=linux/amd64` cache key).
  - `../phase-arch-design.md §Edge cases #7` (auth missing → `RegistryAuthFailed`; CLI exit 11; operator-friendly message).
  - `../phase-arch-design.md §Gap analysis — Gap 7` (auto-bootstrap of named `codegenie-distroless` builder).
- **Phase ADRs:**
  - `../ADRs/0003-objective-signals-widening-and-allowlists.md` — ADR-P7-002 — `docker` newly on `ALLOWED_BINARIES`; `cgr.dev`, `docker.io` newly on the egress allowlist.
  - `../ADRs/0010-credentials-via-docker-config-no-secretd-daemon.md` — no credential storage in the wrapper; auth errors *parse* stderr, never *prompt for* credentials.
- **Source design:**
  - `../final-design.md §Conflict-resolution row 4a` — `codegenie-secretd` veto rationale.
- **High-level impl:**
  - `../High-level-impl.md §Step 2` (lines 60–82) — features + done criteria.
  - `../High-level-impl.md §Implementation-level risks #3` — toolchain pinning drift; pin every binary in `tools/digests.yaml`.

## Goal

`tools.buildkit.build(...)` and `tools.buildkit.imagetools_inspect(...)` return typed `BuildkitResult` / `ImagetoolsManifest` Pydantic objects; the `codegenie-distroless` builder is created idempotently on first use; auth failures from `cgr.dev` raise a typed `RegistryAuthFailed` exception that carries the offending registry host.

## Acceptance criteria

- [ ] `src/codegenie/tools/buildkit.py` exports `build()`, `imagetools_inspect()`, `ensure_builder()`, `RegistryAuthFailed`, `BuildkitResult`, and `ImagetoolsManifest`.
- [ ] `ensure_builder()` is idempotent: on a fresh runner with no `codegenie-distroless` builder, it runs `docker buildx create --name codegenie-distroless --driver docker-container --use` exactly once; on a runner where it already exists, it runs `docker buildx inspect codegenie-distroless` and returns without re-creating. Assertion lives in `tests/integration/test_buildkit_builder_bootstrap.py`.
- [ ] `build()` invokes `docker buildx build --builder codegenie-distroless --load --cache-from=type=local,src=<path> --cache-to=type=local,dest=<path>,mode=max --platform=linux/amd64`. Cache key includes `--platform=linux/amd64` (Edge case #4 / critic perf.assumption.2).
- [ ] `imagetools_inspect(ref, platform="linux/amd64")` invokes `docker buildx imagetools inspect --raw --platform=linux/amd64 <ref>` and returns a Pydantic `ImagetoolsManifest`.
- [ ] On `docker buildx build` exit non-zero with `cgr.dev` auth pattern in stderr (e.g., `unauthorized`, `denied`, `no basic auth credentials` for hosts in the egress allowlist), `build()` raises `RegistryAuthFailed(registry="cgr.dev", remediation="...")`. The exception message references the operator's `~/.docker/config.json`. No credentials are read, stored, minted, or daemonized inside the wrapper (ADR-0010).
- [ ] `BuildkitResult` and `ImagetoolsManifest` are Pydantic `extra="forbid", frozen=True` models; `BuildkitResult` fields match `phase-arch-design.md §Data model ›Internal` exactly.
- [ ] `tools/digests.yaml` records `sandbox.buildkit_image` pinning (S2-07 finalizes the additive set).
- [ ] The TDD plan's red tests exist, are committed, and are green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest tests/unit/tools/test_buildkit.py` and `tests/integration/test_buildkit_builder_bootstrap.py` all pass.
- [ ] Fence-CI confirms no `anthropic|chromadb|sentence-transformers` imports.

## Implementation outline

1. Write the failing tests in `tests/unit/tools/test_buildkit.py` (auth-error parsing, builder-bootstrap idempotence, `--platform` in cache-key) and `tests/integration/test_buildkit_builder_bootstrap.py` (fresh-runner integration). Commit.
2. Define Pydantic `BuildkitResult` and `ImagetoolsManifest` (`extra="forbid", frozen=True`).
3. Implement `ensure_builder()`:
   - Probe with `docker buildx inspect codegenie-distroless`; on non-zero exit, run `docker buildx create --name codegenie-distroless --driver docker-container --use`.
   - Return the builder name. Both probe and create live under a lockable path (S2-05 lock is consumed by callers).
4. Implement `build()`: call `ensure_builder()`; shell out via `subprocess.run(..., check=False, capture_output=True, text=True)`; parse stderr for auth patterns; on success, parse the resulting digest from `--metadata-file` JSON output; return `BuildkitResult`.
5. Implement `imagetools_inspect()`: subprocess `docker buildx imagetools inspect --raw --platform=linux/amd64`; parse JSON via Pydantic.
6. Wire `RegistryAuthFailed` parsing — a closed regex set (`unauthorized|denied|no basic auth credentials|UNAUTHORIZED`) scoped to allowlisted hosts (`cgr.dev`, `docker.io`) so we don't classify unrelated errors.
7. Add `tools/digests.yaml` entry for `sandbox.buildkit_image` (the `moby/buildkit:<digest>` pinned reference).
8. Refactor; verify fence-CI; mypy strict.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file path: `tests/unit/tools/test_buildkit.py`

```python
# tests/unit/tools/test_buildkit.py
import subprocess
from unittest.mock import patch, MagicMock
import pytest
from codegenie.tools.buildkit import (
    build,
    ensure_builder,
    RegistryAuthFailed,
    BuildkitResult,
)


def test_ensure_builder_creates_when_missing(tmp_path):
    """Builder absent → create exactly once."""
    calls = []
    def fake_run(cmd, **kw):
        calls.append(cmd)
        if "inspect" in cmd:
            return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="not found")
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")
    with patch("subprocess.run", side_effect=fake_run):
        ensure_builder()
    create_calls = [c for c in calls if "create" in c]
    assert len(create_calls) == 1, "should create exactly once"
    assert "codegenie-distroless" in create_calls[0]


def test_ensure_builder_idempotent_when_present():
    """Builder present → no create call (Gap 7)."""
    calls = []
    def fake_run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")
    with patch("subprocess.run", side_effect=fake_run):
        ensure_builder()
        ensure_builder()  # second call must not re-create
    assert sum(1 for c in calls if "create" in c) == 0


def test_build_parses_registry_auth_failed_from_stderr(tmp_path):
    """cgr.dev auth-failure stderr → typed RegistryAuthFailed (ADR-0010)."""
    auth_stderr = (
        "ERROR: failed to solve: cgr.dev/chainguard/node:20: "
        "failed to fetch oauth token: unexpected status: 401 Unauthorized\n"
    )
    fake_cp = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr=auth_stderr,
    )
    with patch("subprocess.run", return_value=fake_cp):
        with pytest.raises(RegistryAuthFailed) as exc:
            build(context=tmp_path, dockerfile=tmp_path / "Dockerfile", tag="x:latest")
    assert exc.value.registry == "cgr.dev"
    assert "~/.docker/config.json" in str(exc.value)


def test_build_includes_platform_in_command(tmp_path):
    """Cache key must include --platform=linux/amd64 (Edge case #4)."""
    captured = []
    def fake_run(cmd, **kw):
        captured.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")
    with patch("subprocess.run", side_effect=fake_run), \
         patch("codegenie.tools.buildkit._parse_digest_from_metadata", return_value="sha256:abc"):
        build(context=tmp_path, dockerfile=tmp_path / "Dockerfile", tag="x:latest")
    build_cmds = [c for c in captured if "build" in c]
    assert any("--platform=linux/amd64" in " ".join(c) for c in build_cmds)
```

Test file path: `tests/integration/test_buildkit_builder_bootstrap.py`

```python
def test_buildkit_builder_bootstrap_fresh_runner(tmp_path):
    """Gap 7 — on a runner where codegenie-distroless does not pre-exist,
    ensure_builder() creates it and a second call is a no-op."""
    # Use subprocess to first remove the builder if present.
    subprocess.run(["docker", "buildx", "rm", "codegenie-distroless"], check=False)
    from codegenie.tools.buildkit import ensure_builder
    ensure_builder()
    cp1 = subprocess.run(
        ["docker", "buildx", "inspect", "codegenie-distroless"],
        capture_output=True, text=True,
    )
    assert cp1.returncode == 0
    ensure_builder()  # idempotent
    cp2 = subprocess.run(
        ["docker", "buildx", "inspect", "codegenie-distroless"],
        capture_output=True, text=True,
    )
    assert cp2.returncode == 0
```

Tests must fail with `ImportError` because the module doesn't exist. Commit as the red marker.

### Green — make it pass

- Add `src/codegenie/tools/buildkit.py` with `ensure_builder()`, `build()`, `imagetools_inspect()`, and the typed exceptions/models.
- Use `subprocess.run` with `text=True, capture_output=True`. Do **not** stream raw stderr to the logger; capture, parse, and surface via the typed exception.
- The auth-pattern detector lives as a private function with a closed regex set so the test can exercise it directly later.

### Refactor — clean up

- Type hints (`Path`, `Sequence[str]`, `Literal`); docstrings on the public surface.
- Add a `structlog` `buildkit.build.ok` / `buildkit.build.failed` event with `exit_code`, `wall_clock_ms`, `registry_host` (no credential material).
- `--metadata-file` parsing isolated in a helper so it's mockable in tests.
- Honor `phase-arch-design.md §Edge cases #4` — `--platform` in both the build command **and** any cache-key derivation function exposed in the module.
- Ensure auth-pattern detection only fires for hosts on the egress allowlist (`cgr.dev`, `docker.io`); a 401 from `evil.test` does not classify as `RegistryAuthFailed`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/tools/buildkit.py` | New — wrapper, models, exceptions. |
| `tests/unit/tools/test_buildkit.py` | New — red tests; auth parsing, idempotent bootstrap, `--platform` in cache key. |
| `tests/integration/test_buildkit_builder_bootstrap.py` | New — Gap 7 fresh-runner test. |
| `tools/digests.yaml` | Add `sandbox.buildkit_image` pin (S2-07 finalizes set). |

## Out of scope

- **Multi-arch manifest handling** — Phase 7.1 follow-up (Edge case #4 names this). This wrapper pins `linux/amd64`; multi-arch is a deliberate non-goal.
- **Credential storage / minting** — vetoed by ADR-0010 + `CLAUDE.md`; auth handled entirely by the operator's `~/.docker/config.json` via the Docker daemon.
- **`tools/grype.py`, `tools/dive.py`, `tools/strace.py`** — separate stories (S2-03, S2-04, and Phase 5's pre-existing wrapper).
- **Buildkit cache hit-rate measurement** — S7-02.
- **`cache_lock`-gated cache writes** — S2-05 provides the primitive; consumers wire it in their own stories.

## Notes for the implementer

- ADR-0010 is **load-bearing**. The wrapper *never* reads `~/.docker/config.json`, *never* shells out to `docker login`, *never* writes to a credential helper. The Docker daemon does all of that; the wrapper only parses auth errors from stderr and tells the operator where to look.
- The `RegistryAuthFailed` regex set is a closed match against the egress allowlist (`cgr.dev`, `docker.io`). Resist temptation to widen it to catch all `401`s — `evil.test` getting 401 is not a credential failure we surface; it's an egress-block firing correctly (S6-09 covers that path).
- `phase-arch-design.md §Risks #7` — `cgr.dev` cold-pull rate-limits. The wrapper doesn't fix this, but `RegistryAuthFailed` messages should include the remediation pointer so operators can wire creds.
- Avoid `os.system` and `shlex.split`-from-untrusted-input. Build the argv list as a `list[str]` directly; the test's `assert "--platform=linux/amd64" in " ".join(c)` is just a readability check, not a string-splitting contract.
- `--metadata-file` (JSON) is the cleanest way to get the resulting digest deterministically; do not parse digests out of free-form stderr.
- The Gap 7 fresh-runner test is destructive (it removes the builder). Gate it behind a CI marker (`@pytest.mark.integration_docker`) and ensure the local test runner has Docker available; mark it `skipif` otherwise. Do not catch and swallow — fail loud per Rule 12.
