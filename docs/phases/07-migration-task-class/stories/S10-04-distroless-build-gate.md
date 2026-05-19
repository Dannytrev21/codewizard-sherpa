# Story S10-04 — `DistrolessBuildGate` (`docker buildx build --target=runtime` via `SandboxClient.spawn(role=Role.GATE)`)

**Step:** Step 10 — `DockerfileBaseImageSwapTransform` + `DockerfileMultiStageRefactorTransform` + three gates
**Status:** Ready
**Effort:** M
**Depends on:** S6-02 (`SandboxClient.spawn(role: SandboxRole = SandboxRole.GATE)` additive parameter), S10-01 (`DockerfileBaseImageSwapTransform` produces the rendered Dockerfile this gate builds)
**ADRs honored:** [Phase 7 ADR-0015](../ADRs/0015-allowed-binaries-amendment-dive-buildx.md) (`docker buildx` is in `ALLOWED_BINARIES`; `strace` is NOT), [Phase 7 ADR-0003](../ADRs/0003-sandbox-role-additive-enum-on-spawn.md) (`SandboxRole.GATE` vs `SandboxRole.PROBE` semantics), [Phase 5 ADR-0003](../../05-sandbox-trust-gates/ADRs/0003-trustscorer-extension-via-signal-kind-registry.md) (open `@register_signal_kind` registry)

## Context

`DistrolessBuildGate` is the second of Phase 7's three gate-catalog contributions. Its job: actually **build** the migrated image. If `DockerfileBaseImageSwapTransform`'s diff produced an unparseable or unbuildable Dockerfile (broken `COPY --from=...`, missing build-arg, network issue pulling Chainguard registry), this gate catches it deterministically. Without `DistrolessBuildGate`, the policy gate (S10-03) plus shell-delta gate (S10-05) could both pass while the image is non-buildable — strict-AND would emit a false-positive trust score.

`DistrolessBuildGate` is decorated `@register_signal_kind(name="distroless_build", isolation_class="microvm")`. It runs `docker buildx build --target=runtime` inside the microVM via `SandboxClient.spawn(role=Role.GATE)`. The `role=Role.GATE` is **intentionally different** from `Role.PROBE`: `Role.GATE` is the default Phase 5 behavior (no eBPF trace capture); `Role.PROBE` (S6-01) adds eBPF host-side trace capture for probe runs. This gate does NOT need the trace — it just needs to know "did the build succeed". Picking `Role.GATE` honors Phase 5's two-chokepoint shape (Phase 5 ADR-P5-001) without paying the trace-capture cost.

`docker buildx` (note: as a single token in `ALLOWED_BINARIES`, NOT separate `docker` + `buildx`) is the canonical Docker build CLI for multi-stage and buildx-cache scenarios. [Phase 7 ADR-0015](../ADRs/0015-allowed-binaries-amendment-dive-buildx.md) adds it to the closed `ALLOWED_BINARIES` frozenset; the gate must invoke it via `codegenie.exec.run_external_cli` (or the equivalent sandbox-side shape) — direct `subprocess.run(["docker", ...])` is repo-banned.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §12` — `DistrolessBuildGate(Gate)` decorated `@register_signal_kind(name="distroless_build", isolation_class="microvm")`; runs `docker buildx build --target=runtime` via `SandboxClient.spawn(role=Role.GATE)`; perf envelope: ≤ 14 s (warm Chainguard cache).
  - `../phase-arch-design.md §Edge cases #6` — Chainguard registry pull failure (transient network) → Phase 5 retry envelope (ADR-0014); 3 retries; 3rd failure escalates; emits `distroless_build.failed_after_retries`.
  - `../phase-arch-design.md §Control flow §step 9` — `SandboxClient.spawn(role=Role.GATE)` boots microVM for `DistrolessBuildGate` (docker buildx) + `ShellInvocationDeltaGate` (re-trace).
- **Phase ADRs:**
  - [`../ADRs/0015-allowed-binaries-amendment-dive-buildx.md`](../ADRs/0015-allowed-binaries-amendment-dive-buildx.md) — `dive` and `docker buildx` rows added to `ALLOWED_BINARIES`; `strace` is NOT.
  - [`../ADRs/0003-sandbox-role-additive-enum-on-spawn.md`](../ADRs/0003-sandbox-role-additive-enum-on-spawn.md) — `SandboxRole.GATE` is default; `SandboxRole.PROBE` enables eBPF trace capture. This gate uses `Role.GATE` (no trace; just build outcome).
- **Phase 5 (existing code):**
  - `src/codegenie/sandbox/client.py` — `SandboxClient.spawn(role: SandboxRole = SandboxRole.GATE, ...)` (extended in S6-02).
  - `src/codegenie/sandbox/gates/registry.py` — `@register_signal_kind`.
- **Phase 7 (sibling code):**
  - `plugins/distroless-migration--node--npm/recipes/dockerfile_base_image_swap.py` (S10-01) — produces the rendered Dockerfile.
  - `plugins/distroless-migration--node--npm/recipes/dockerfile_policy_gate.py` (S10-03) — sibling gate; mirror its `@register_signal_kind` decoration shape (but `isolation_class="none"` differs).
- **Existing code:**
  - `src/codegenie/exec/__init__.py::ALLOWED_BINARIES` — closed frozenset; S7-04 added `dive` + `docker buildx` per ADR-0015. Verify both are present before relying on them.

## Goal

Land `plugins/distroless-migration--node--npm/recipes/distroless_build_gate.py`. `DistrolessBuildGate(Gate)` is decorated `@register_signal_kind(name="distroless_build", isolation_class="microvm")`. It spawns a microVM via `SandboxClient.spawn(role=SandboxRole.GATE, ..., command=["docker", "buildx", "build", "--target=runtime", "."])`, captures the build outcome (exit code + stderr-tail), and returns `Passed | Failed(reason: BuildFailureReason)`. Strict-AND `TrustScorer` halts on `Failed`. The gate participates in Phase 5's existing retry envelope (3 retries on transient network errors per edge case #6). p99 (warm Chainguard cache) ≤ 14 s.

## Acceptance criteria

### Gate surface + registration

- [ ] **AC-1 — Module + class location.** `plugins/distroless-migration--node--npm/recipes/distroless_build_gate.py` defines `class DistrolessBuildGate(Gate)`, decorated `@register_signal_kind(name="distroless_build", isolation_class="microvm")`. After plugin load, `signal_kind_registry["distroless_build"]` returns this class.
- [ ] **AC-2 — `isolation_class="microvm"`.** The gate spawns a microVM via `SandboxClient.spawn(...)`. The registry entry's `isolation_class` is the literal string `"microvm"`. Test: `signal_kind_registry["distroless_build"].isolation_class == "microvm"`.
- [ ] **AC-3 — `Gate` ABC compliance.** `DistrolessBuildGate` implements the `Gate` interface Phase 5 ships. `isinstance(g, Gate)` is `True`. The gate's `evaluate(...)` (or whatever Phase 5 names it) returns `DistrolessBuildGatePassed | DistrolessBuildGateFailed(reason: BuildFailureReason, stderr_tail: str)`.

### `SandboxClient.spawn(role=Role.GATE)` — NOT Role.PROBE

- [ ] **AC-4 — Role is `SandboxRole.GATE`.** The gate's `evaluate()` calls `client.spawn(role=SandboxRole.GATE, ...)`. Test (`tests/unit/gates/test_distroless_build_gate.py::test_uses_role_gate`) uses a fake `SandboxClient` and asserts the `role=` kwarg passed in is `SandboxRole.GATE` — NOT `SandboxRole.PROBE`. Rationale: the gate needs the build outcome, not an eBPF trace; trace capture is `ShellInvocationDeltaGate`'s (S10-05) territory. Document the role choice in the gate's docstring with a one-line ADR-0003 citation.
- [ ] **AC-5 — `command=["docker", "buildx", "build", "--target=runtime", "."]` (or equivalent).** The exact `command` list passed to `spawn(...)` is asserted by the fake-`SandboxClient` test. `--target=runtime` is load-bearing (multi-stage Dockerfiles produced by S10-02 have explicit `runtime` stages; building only the runtime exercises the distroless path).
- [ ] **AC-6 — `ALLOWED_BINARIES` precondition.** Module-level import-time assertion: `from codegenie.exec import ALLOWED_BINARIES; assert "docker buildx" in ALLOWED_BINARIES, "Phase 7 ADR-0015 row missing"`. Use `raise AssertionError(...)` — NOT bare `assert` (banned). Fence test (`tests/fence/test_distroless_build_gate_allowed_binaries.py`) asserts this guard is present and that `"docker buildx"` is in the frozenset at runtime.

### Pass / fail / retry outcomes

- [ ] **AC-7 — `BuildFailureReason` sum type.** Module-level `class BuildFailureReason(StrEnum)` with at minimum these values (extended additively by future ADR if needed):
  - `BUILD_NON_ZERO_EXIT` — `docker buildx build` returned non-zero (catch-all; stderr-tail carries the diagnostic).
  - `CHAINGUARD_REGISTRY_PULL_FAILED` — network/registry error (regex match against stderr-tail; eligible for retry per edge case #6).
  - `DOCKERFILE_SYNTAX_REJECTED_BY_BUILDX` — buildx parsed the Dockerfile and refused it (recipe bug; not retryable).
  - `SANDBOX_TIMEOUT` — microVM timed out before build completed.
- [ ] **AC-8 — `DistrolessBuildGatePassed` Pydantic model.** Frozen, `extra="forbid"`. Fields: `rendered_dockerfile_digest: str`, `build_duration_ms: int`, `image_digest: ImageDigest` (Phase 7 S1-01 newtype; pinned to the digest `docker buildx` reports for the built image).
- [ ] **AC-9 — `DistrolessBuildGateFailed` Pydantic model.** Frozen, `extra="forbid"`. Fields: `rendered_dockerfile_digest: str`, `reason: BuildFailureReason`, `stderr_tail: str` (truncated to 8 KB UTF-8 bytes per Phase 3 S1-04 precedent; NUL/control/bidi rejected).
- [ ] **AC-10 — Retry envelope integration.** When `evaluate()` returns `DistrolessBuildGateFailed(reason=CHAINGUARD_REGISTRY_PULL_FAILED)`, Phase 5's existing retry envelope retries up to 3 times (ADR-P5-002 / edge case #6). After 3 failures, emit `distroless_build.failed_after_retries` warning ID and escalate. `BUILD_NON_ZERO_EXIT` / `DOCKERFILE_SYNTAX_REJECTED_BY_BUILDX` are NOT retryable — they signal recipe/Dockerfile bugs. Test: `tests/unit/gates/test_distroless_build_gate.py::test_retry_classification` parametrized over each reason.

### Strict-AND scoring

- [ ] **AC-11 — Participates in strict-AND `TrustScorer`.** `tests/integration/test_gates_register_phase7.py` (the same suite S10-05 covers all three gates in) asserts: after plugin load, `signal_kind_registry` has `dockerfile_policy`, `distroless_build`, `shell_invocation_delta`; the `TrustScorer` is queried with `required_signals=("dockerfile_policy", "distroless_build", "shell_invocation_delta")` and returns the conjunction (any `Failed` → overall fail).
- [ ] **AC-12 — `--allow-policy-violations` flag also absent for this gate.** Same fence as S10-03 AC-10 (`tests/fence/test_no_policy_override_flag.py` is the shared fence — it already covers `--help` and source-tree grep). Verify the fence is green; no per-gate override exists.

### Audit + diagnostic

- [ ] **AC-13 — `_WARNING_IDS`** `Final[frozenset[str]]` validated at import via `raise AssertionError(...)`. IDs include `distroless_build.build_non_zero_exit`, `distroless_build.chainguard_registry_pull_failed`, `distroless_build.dockerfile_syntax_rejected_by_buildx`, `distroless_build.sandbox_timeout`, `distroless_build.failed_after_retries`.
- [ ] **AC-14 — Failing build emits typed event to spanning log.** `tests/integration/test_distroless_build_gate_audit_trail.py` runs the gate against a deliberately-broken Dockerfile fixture (e.g., missing `COPY` source), asserts the spanning log carries `DistrolessBuildGateFailed(rendered_dockerfile_digest=..., reason=BUILD_NON_ZERO_EXIT, stderr_tail=...)`.
- [ ] **AC-15 — Stderr-tail truncation.** Test: a `docker buildx build` failure that produces 100 KB of stderr → the gate's `stderr_tail` field is exactly `8192` UTF-8 bytes (tail-end, not head; the relevant error is at the end of buildx output). Bytes, not chars (E20 closure; mirrors Phase 3 S1-04).

### Perf + gates

- [ ] **AC-16 — Warm-cache p99 ≤ 14 s.** `tests/perf/test_distroless_build_gate.py::test_build_p99_under_14s_warm_cache` runs the gate against `tests/fixtures/portfolio/node-vulnerable-base-only/Dockerfile` 100 times (not 1000 — each build is expensive; smaller sample is acceptable). Marked `@pytest.mark.bench` AND `@pytest.mark.phase07_e2e` (requires `--privileged` Linux runner per arch §Testing strategy §End-to-end tests). Cold-cache runs are not budgeted; the arch's ≤ 14 s envelope is warm-cache only.
- [ ] **AC-17** — `mypy --strict plugins/distroless-migration--node--npm/recipes/` clean.
- [ ] **AC-18** — `ruff check ... && ruff format --check` clean.
- [ ] **AC-19** — `make lint-imports` green.
- [ ] **AC-20** — Phase 3–6.5 regression suite + `bench/vuln-remediation/` cassette replay byte-equal.

## Implementation outline

1. **`plugins/distroless-migration--node--npm/recipes/distroless_build_gate.py`** — define `class BuildFailureReason(StrEnum)`, `class DistrolessBuildGatePassed(BaseModel)`, `class DistrolessBuildGateFailed(BaseModel)`, `class DistrolessBuildGate(Gate)` decorated `@register_signal_kind(...)`.
2. **`evaluate()` implementation** —
   - Module-level import-time assertion confirms `"docker buildx" in ALLOWED_BINARIES`.
   - Construct the `SandboxSpec` / `SpawnSpec` (whatever Phase 5 names) with `role=SandboxRole.GATE`, `command=["docker", "buildx", "build", "--target=runtime", "."]`, `workdir=ctx.repo_root` (or whatever Phase 5 calls the mount path), reasonable timeout (e.g., 60 s — covers cold-cache pulls too).
   - Call `client.spawn(...)`.
   - On exit code 0: parse `image_digest` from buildx output, return `DistrolessBuildGatePassed(...)`.
   - On non-zero: classify the failure via `_classify_failure_reason(stderr_tail: str) -> BuildFailureReason` (regex over stderr-tail; module-level `Final` tuple of `(BuildFailureReason, Pattern[str])` rows iterated, not branched).
3. **Module-level `_FAILURE_PATTERNS: Final[tuple[tuple[BuildFailureReason, Pattern[str]], ...]]`** — data-driven classification. Documented patterns: Chainguard registry network errors, buildx Dockerfile-parse errors, sandbox timeout.
4. **`tests/unit/gates/test_distroless_build_gate.py`** — fake-`SandboxClient` tests: AC-4 (role assertion), AC-5 (command assertion), AC-7 / AC-10 (reason classification + retry per reason).
5. **`tests/fence/test_distroless_build_gate_allowed_binaries.py`** — confirms `"docker buildx" in ALLOWED_BINARIES` at runtime AND the import-time assertion is present in the gate module.
6. **`tests/integration/test_distroless_build_gate_audit_trail.py`** — runs against a real microVM (Phase 7 e2e marker) with a broken Dockerfile; asserts the typed event in the spanning log.
7. **`tests/perf/test_distroless_build_gate.py`** — warm-cache p99 bench.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/unit/gates/test_distroless_build_gate.py`

```python
from dataclasses import dataclass, field
from typing import Any
import pytest

from codegenie.sandbox import SandboxRole  # from S6-01

# Will fail with ImportError until the module exists.
from plugins.distroless_migration__node__npm.recipes.distroless_build_gate import (
    BuildFailureReason,
    DistrolessBuildGate,
    DistrolessBuildGateFailed,
    DistrolessBuildGatePassed,
)


@dataclass
class _FakeSandboxRun:
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    image_digest: str = "sha256:" + "a" * 64


@dataclass
class _FakeSandboxClient:
    scripted_runs: list[_FakeSandboxRun]
    received_kwargs: list[dict[str, Any]] = field(default_factory=list)

    def spawn(self, **kwargs: Any) -> _FakeSandboxRun:
        self.received_kwargs.append(kwargs)
        return self.scripted_runs.pop(0)


def test_uses_role_gate_not_role_probe() -> None:
    """ADR-0003: this gate uses Role.GATE (no eBPF trace); Role.PROBE is for shell-trace probe."""
    client = _FakeSandboxClient(scripted_runs=[_FakeSandboxRun(exit_code=0)])
    gate = DistrolessBuildGate(client=client)
    gate.evaluate(rendered_dockerfile_digest="sha256:" + "0" * 64, repo_root="/tmp/x")
    assert client.received_kwargs[0]["role"] == SandboxRole.GATE


def test_uses_docker_buildx_target_runtime_command() -> None:
    """ADR-0015: docker buildx in ALLOWED_BINARIES; --target=runtime is load-bearing."""
    client = _FakeSandboxClient(scripted_runs=[_FakeSandboxRun(exit_code=0)])
    gate = DistrolessBuildGate(client=client)
    gate.evaluate(rendered_dockerfile_digest="sha256:" + "0" * 64, repo_root="/tmp/x")
    cmd = client.received_kwargs[0]["command"]
    assert cmd[0:2] == ["docker", "buildx"]
    assert "build" in cmd
    assert "--target=runtime" in cmd


def test_zero_exit_returns_passed_with_image_digest() -> None:
    client = _FakeSandboxClient(scripted_runs=[_FakeSandboxRun(exit_code=0)])
    gate = DistrolessBuildGate(client=client)
    result = gate.evaluate(rendered_dockerfile_digest="sha256:" + "0" * 64, repo_root="/tmp/x")
    assert isinstance(result, DistrolessBuildGatePassed)


def test_non_zero_with_chainguard_pull_error_is_retryable() -> None:
    stderr = "ERROR: failed to solve: failed to pull cgr.dev/chainguard/node: net/http: TLS handshake timeout"
    client = _FakeSandboxClient(scripted_runs=[_FakeSandboxRun(exit_code=1, stderr=stderr)])
    gate = DistrolessBuildGate(client=client)
    result = gate.evaluate(rendered_dockerfile_digest="sha256:" + "0" * 64, repo_root="/tmp/x")
    assert isinstance(result, DistrolessBuildGateFailed)
    assert result.reason == BuildFailureReason.CHAINGUARD_REGISTRY_PULL_FAILED


def test_non_zero_with_dockerfile_syntax_error_is_not_retryable() -> None:
    stderr = "ERROR: failed to solve: dockerfile parse error line 5: unknown instruction: FORM"
    client = _FakeSandboxClient(scripted_runs=[_FakeSandboxRun(exit_code=1, stderr=stderr)])
    gate = DistrolessBuildGate(client=client)
    result = gate.evaluate(rendered_dockerfile_digest="sha256:" + "0" * 64, repo_root="/tmp/x")
    assert isinstance(result, DistrolessBuildGateFailed)
    assert result.reason == BuildFailureReason.DOCKERFILE_SYNTAX_REJECTED_BY_BUILDX


def test_stderr_tail_truncated_to_8192_utf8_bytes() -> None:
    long_stderr = "x" * 100_000
    client = _FakeSandboxClient(scripted_runs=[_FakeSandboxRun(exit_code=1, stderr=long_stderr)])
    gate = DistrolessBuildGate(client=client)
    result = gate.evaluate(rendered_dockerfile_digest="sha256:" + "0" * 64, repo_root="/tmp/x")
    assert isinstance(result, DistrolessBuildGateFailed)
    assert len(result.stderr_tail.encode("utf-8")) <= 8192


def test_failing_invariants_emits_correct_signal_kind() -> None:
    from codegenie.sandbox.gates.registry import signal_kind_registry
    assert "distroless_build" in signal_kind_registry
    assert signal_kind_registry["distroless_build"].isolation_class == "microvm"
```

State why it fails: `ModuleNotFoundError` — the gate module does not exist yet.

### Green — minimal pass

- Land `distroless_build_gate.py` with the gate class, the two Pydantic outcome models, `BuildFailureReason` enum, `_FAILURE_PATTERNS` tuple, and a minimal `evaluate()` that calls `client.spawn(role=SandboxRole.GATE, command=[...])` and classifies the result.
- Module-level import-time `"docker buildx" in ALLOWED_BINARIES` assertion using `raise AssertionError(...)`.

### Refactor

- Hoist `_classify_failure_reason(stderr_tail: str) -> BuildFailureReason` into a pure function; test in isolation over each failure pattern.
- Pin `_FAILURE_PATTERNS` as a module-level `Final` tuple iterated, not branched.
- Add the `_WARNING_IDS` import-time validation.
- Add the fence test (`tests/fence/test_distroless_build_gate_allowed_binaries.py`) confirming the import-time assertion is present in the module body via AST-walk.
- Confirm `mypy --strict` clean; the `SandboxClient` Protocol from Phase 5 should accept the fake in tests via structural typing.

## Files to touch

| Path | Why |
|---|---|
| `plugins/distroless-migration--node--npm/recipes/distroless_build_gate.py` | NEW — `DistrolessBuildGate(Gate)` + `BuildFailureReason` + `Passed`/`Failed` Pydantic models; `@register_signal_kind(name="distroless_build", isolation_class="microvm")`; uses `SandboxClient.spawn(role=Role.GATE)` and `docker buildx build --target=runtime`. |
| `plugins/distroless-migration--node--npm/recipes/__init__.py` | Extend — additive import line for side-effect registration. |
| `tests/unit/gates/test_distroless_build_gate.py` | NEW — AC-4..AC-10, AC-15 via fake-`SandboxClient`. |
| `tests/fence/test_distroless_build_gate_allowed_binaries.py` | NEW — confirms `"docker buildx" in ALLOWED_BINARIES` at runtime AND the import-time assertion is present (AST-walk). |
| `tests/integration/test_distroless_build_gate_audit_trail.py` | NEW — runs against real microVM (`@pytest.mark.phase07_e2e`); typed event in spanning log (AC-14). |
| `tests/perf/test_distroless_build_gate.py` | NEW — warm-cache p99 ≤ 14 s (AC-16); `@pytest.mark.bench` + `@pytest.mark.phase07_e2e`. |

## Out of scope

- **`SandboxClient.spawn` itself** — S6-02. This story depends on the `role: SandboxRole = SandboxRole.GATE` parameter being live; if S6-02 is incomplete, this story BLOCKED.
- **`ShellInvocationDeltaGate`** — S10-05. Different gate; uses `role=Role.GATE` too (NOT `Role.PROBE` — see S10-05 for rationale).
- **`DockerfilePolicyGate`** — S10-03. Different `isolation_class` (`"none"` vs `"microvm"`).
- **Phase 5 retry-envelope wiring itself** — Phase 5 owns it; this story only emits the correct `BuildFailureReason` for the retry envelope to classify.
- **`docker buildx` warm-cache provisioning** — runner-image baseline owned by CI infra; out of plugin scope.
- **`dive` invocation** — `dive` is in `ALLOWED_BINARIES` per ADR-0015 but no S10 story uses it directly; reserved for future portfolio-validation stories.

## Notes for the implementer

- **`role=SandboxRole.GATE` — NOT `Role.PROBE`.** This is the intentional choice. `Role.GATE` is default Phase 5 behavior (Phase 5's existing `SandboxClient.spawn` shape pre-S6-01); `Role.PROBE` (S6-01) adds eBPF host-side trace capture for `ShellInvocationTraceProbe`. This gate needs the build outcome — not a trace. Picking `Role.PROBE` would pay the trace-capture cost for no benefit. Document the choice in the gate's docstring with an ADR-0003 citation. AC-4 is the mechanical enforcement.
- **`"docker buildx"` is ONE token, not two.** `ALLOWED_BINARIES` has it as a single string `"docker buildx"` (per ADR-0015 §Decision). The `command=[...]` list passed to `spawn` is `["docker", "buildx", "build", ...]` — that's argv-style; `run_external_cli` (Phase 2 wrapper) handles the binary-allowlist matching via prefix. Don't try to register `docker` and `buildx` separately. The `__init__` import-time assertion looks for the exact `"docker buildx"` string.
- **`docker build` is NOT in `ALLOWED_BINARIES`** — only `docker buildx`. If you reach for legacy `docker build ...`, it's not allowlisted; the subprocess wrapper rejects. Use `docker buildx build`.
- **`--target=runtime` is load-bearing.** S10-02's `DockerfileMultiStageRefactorTransform` produces Dockerfiles with explicit `builder` + `runtime` stages. Building only the runtime stage (a) exercises the distroless path; (b) avoids paying the builder-stage's heavy build cost twice (the builder was already built by `ShellInvocationTraceProbe` for shell-trace capture in S7-02). For single-stage Dockerfiles (S10-01's swap output), `--target=runtime` is harmless — buildx treats a single-stage Dockerfile as having an implicit runtime stage.
- **Retry classification matters.** Phase 5's retry envelope reads `BuildFailureReason` to decide retry vs escalate. `CHAINGUARD_REGISTRY_PULL_FAILED` → 3 retries (transient network). `BUILD_NON_ZERO_EXIT` (catch-all) → not retryable (more failures don't help if the cause is a recipe bug). `DOCKERFILE_SYNTAX_REJECTED_BY_BUILDX` → not retryable. `SANDBOX_TIMEOUT` → not retryable (raising the budget is a config change, not a retry). Document each reason's retryability in the enum's docstring.
- **Stderr-tail, not stderr-head.** When `docker buildx build` fails, the relevant error message is at the END of stderr (build progress dominates the head). Truncate to 8 KB UTF-8 bytes from the TAIL, not the head. Same byte-cap discipline as Phase 3 S1-04's `prior_failure_summary`. NUL/control/bidi rejection applies.
- **`image_digest` on `Passed`** — buildx outputs the image digest in its stdout. Parse it via regex (`re.search(r"writing image (sha256:[a-f0-9]{64})", stdout)`) and wrap in `ImageDigest(...)` (Phase 7 S1-01 newtype with `sha256:` prefix assertion). If parsing fails, the build technically succeeded but we can't capture the digest — emit a `warning` event with ID `distroless_build.digest_parse_failed` and use a sentinel `ImageDigest("sha256:" + "0" * 64)`. Don't fail the gate over digest-parse — the build outcome is what matters.
- **Performance — ≤ 14 s warm cache.** "Warm cache" means the Chainguard image layers are already in the local Docker layer cache. Cold-cache pulls can take 30+ s (network-bound). The perf bench (AC-16) is warm-cache only; cold-cache is unbenched. The 14 s envelope is generous because buildx has overhead even on cached layers (manifest verification, signature checks, etc.).
- **Match S10-03's gate shape.** Sibling gate; same `@register_signal_kind` decoration style, same Pydantic outcome model pattern, same `_WARNING_IDS` validation, same `tuple[BuildFailureReason, ...]`-style failing list (here just one reason at a time — no combinatorial). Convention > taste.
- **`isolation_class="microvm"`** — the gate spawns a microVM. The `signal_kind_registry` entry carries the string `"microvm"`; Phase 5's `TrustScorer` reads this for orchestration (sequencing, parallelism). Don't deviate.
- **The fence is not just `make check`.** The integration test (AC-14) requires a `--privileged` Linux runner (the microVM needs kernel features). Phase 7's CI matrix uses `@pytest.mark.phase07_e2e` to gate these (S12-05); ensure your marker is right. On non-privileged runners (your laptop), the test is skipped; that's expected.
