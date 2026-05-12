# Story S3-06 — `SandboxHealthProbe` as Phase 1 probe

**Step:** Step 3 — Implement DinD backend + SandboxSpecBuilder + SandboxHealthProbe
**Status:** Ready
**Effort:** S
**Depends on:** S3-02 (`DockerInDockerClient.health()` returns `SandboxHealth`)
**ADRs honored:** ADR-0013 (digest-pinned policy YAML — probe surfaces `policy_digest_missing`), ADR-0004 (DinD `shared_kernel` — probe records the backend it inspected), Phase 1 probe ABC contract

## Context

The Phase 1 gather pipeline runs probes against a target repo to build a `RepoContext`. `SandboxHealthProbe` is the B2 analog for Phase 5: it detects silent sandbox-backend unavailability **before any gate runs**, populates `RepoContext.health.sandbox`, and surfaces structured warnings (`strace SYS_PTRACE missing` on macOS, `policy_digest_missing` on a tampered/missing policy YAML, `daemon_unreachable` on Docker Desktop down). Per `phase-arch-design.md §Component design — SandboxHealthProbe`, it instantiates the auto-detected backend, calls `client.health()`, and emits the result. Per Edge case #19, it also verifies `tools/digests.yaml#sandbox.policy_yaml` matches the policy file's actual digest — otherwise raises `reachable=False, reasons=["policy_digest_missing"]`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — SandboxHealthProbe` — interface, `declared_inputs`, structure, failure behavior.
  - `../phase-arch-design.md §Component design — DockerInDockerClient` `health()` — the structured-reason list this probe consumes.
  - `../phase-arch-design.md §Edge case 19` — `tools/digests.yaml` missing `sandbox.policy_yaml` → `SandboxHealth(reachable=False, reasons=["policy_digest_missing"])`.
  - `../phase-arch-design.md §Goals 8 + 11` — `coverage_evidence_strength` soft signal; macOS strace warning persists in `SandboxHealth.warnings`.
- **Phase ADRs:**
  - `../ADRs/0013-digest-pinned-policy-yaml-codegenie-owned.md` — ADR-0013 — probe is the startup integrity check enforcing the pinned digest.
  - `../ADRs/0004-dind-default-macos-with-gate-isolation-class.md` — ADR-0004 — auto-detect falls back to DinD on macOS; probe records the chosen backend.
- **Production design:**
  - `../../../production/design.md` Phase 1 probe contract — the ABC every probe satisfies (`name`, `declared_inputs`, `applies_to_*`, `run`).
- **Existing code:**
  - `src/codegenie/sandbox/did/client.py` (from S3-02) — provides `health() -> SandboxHealth`.
  - `src/codegenie/sandbox/registry.py` (from S1-05) — `auto_detect()` returns the chosen `SandboxClient` (KVM-present → Firecracker once S6-01 lands; today → DinD).
  - Phase 1 `Probe` ABC location — `src/codegenie/gather/probes/base.py` (or wherever Phase 1 anchored it; grep for `class Probe(ABC)`).
  - `tools/policy/sandbox-policy.yaml` (from S3-05) — file the probe digests.
  - `tools/digests.yaml#sandbox.policy_yaml` (from S3-05) — expected digest.
- **External docs:**
  - None — this is internal plumbing.

## Goal

Land a Phase 1 `Probe` named `sandbox_health` that auto-detects the backend, calls `client.health()`, verifies `tools/policy/sandbox-policy.yaml` against `tools/digests.yaml#sandbox.policy_yaml`, and emits a `SandboxHealth` model under `RepoContext.health.sandbox`.

## Acceptance criteria

- [ ] `src/codegenie/sandbox/health/probe.py` defines `class SandboxHealthProbe(Probe)` with `name = "sandbox_health"`, `declared_inputs = ["~/.config/codegenie/sandbox.yaml", "tools/digests.yaml", "tools/policy/sandbox-policy.yaml"]`, `applies_to_tasks = ["*"]`, `applies_to_languages = ["*"]`.
- [ ] `run(self, ctx: ProbeContext) -> ProbeResult` instantiates `auto_detect()`, calls `client.health()`, and produces a `ProbeResult` whose payload includes the resulting `SandboxHealth` model.
- [ ] Before consulting the backend, the probe verifies `blake3.blake3(open("tools/policy/sandbox-policy.yaml","rb").read()).hexdigest(length=16) == digests["sandbox"]["policy_yaml"]`; on mismatch returns `SandboxHealth(reachable=False, confidence="high", reasons=["policy_digest_missing"])` **without** calling the backend at all.
- [ ] On `daemon_unreachable` (the backend returned `reachable=False`), the probe payload carries the same reasons through unchanged.
- [ ] On macOS (`platform.system() == "Darwin"`), `warnings` includes `"strace_ptrace_missing"` if and only if the backend's `health()` already flagged it — the probe is a pass-through here.
- [ ] Registered via the Phase 1 probe registry decorator (`@register_probe` or equivalent — check Phase 1 conventions).
- [ ] `tests/sandbox/health/test_probe.py` covers: (a) happy path → `reachable=True, confidence in {"high","medium"}`; (b) policy digest mismatch → `reachable=False, reasons=["policy_digest_missing"]` and `client.health()` is **not** called; (c) `daemon_unreachable` propagation; (d) macOS warning pass-through.
- [ ] `mypy --strict src/codegenie/sandbox/health/probe.py` clean.
- [ ] No `subprocess` import; no LLM import. Fence tests green.
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `pytest` pass.

## Implementation outline

1. `src/codegenie/sandbox/health/__init__.py` (new subpackage).
2. `src/codegenie/sandbox/health/probe.py`:
   - Import `Probe`, `ProbeResult`, `ProbeContext` from the Phase 1 probe module (grep first; likely `codegenie.gather.probes.base`).
   - Import `auto_detect` from `codegenie.sandbox.registry`.
   - Import `SandboxHealth` from `codegenie.sandbox.contract`.
   - Import `blake3`, `yaml`, `pathlib`, `platform`.
   - Class `SandboxHealthProbe(Probe)`:
     - Constants per acceptance criteria.
     - `run(self, ctx)`:
       1. Load `tools/digests.yaml`; read `sandbox.policy_yaml`.
       2. Read `tools/policy/sandbox-policy.yaml` bytes; compute BLAKE3-128.
       3. Mismatch → build `SandboxHealth(reachable=False, reasons=["policy_digest_missing"], confidence="high", ...)` and return.
       4. Match → call `client = auto_detect(); health = client.health()`.
       5. Wrap `health` in a `ProbeResult` with the standard Phase 1 envelope (whatever Phase 1 uses).
3. Register the probe with the Phase 1 registry so `codegenie gather` runs it automatically.
4. structlog event `sandbox.health.probe.run` with `backend`, `reachable`, `reasons`, `warnings`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/sandbox/health/test_probe.py`

```python
# tests/sandbox/health/test_probe.py
from pathlib import Path
from unittest.mock import MagicMock, patch
import platform, pytest
from codegenie.sandbox.health.probe import SandboxHealthProbe
from codegenie.sandbox.contract import SandboxHealth

def _ctx(tmp_path: Path):
    """Phase 1 ProbeContext shim — adjust to actual signature once grep'd."""
    return MagicMock(workdir=tmp_path)

def test_policy_digest_mismatch_short_circuits_without_calling_backend(monkeypatch, tmp_path):
    """ADR-0013 enforcement: a tampered policy YAML must mark sandbox unreachable
    BEFORE any backend call. A regression here means an attacker who edited the
    policy could still get a 'reachable=True' health report."""
    # Arrange a real policy file with a known digest, plus a digests.yaml claiming the wrong digest.
    (tmp_path / "tools" / "policy").mkdir(parents=True)
    (tmp_path / "tools" / "policy" / "sandbox-policy.yaml").write_text("schema_version: 1\n")
    (tmp_path / "tools" / "digests.yaml").write_text(
        "sandbox:\n  policy_yaml: deadbeefdeadbeefdeadbeefdeadbeef\n"
    )
    monkeypatch.chdir(tmp_path)
    detect = MagicMock()
    monkeypatch.setattr("codegenie.sandbox.health.probe.auto_detect", detect)

    result = SandboxHealthProbe().run(_ctx(tmp_path))
    health: SandboxHealth = result.payload["sandbox"]
    assert health.reachable is False
    assert "policy_digest_missing" in health.reasons
    detect.assert_not_called()  # MUST NOT touch the backend on digest mismatch

def test_happy_path_returns_reachable(monkeypatch, tmp_path, write_real_digest):
    write_real_digest(tmp_path)  # fixture writes a matching policy + digests.yaml
    monkeypatch.chdir(tmp_path)
    fake = MagicMock()
    fake.health.return_value = SandboxHealth(
        backend="docker_in_docker", reachable=True, confidence="high",
        reasons=[], warnings=[], detected_at=__import__("datetime").datetime.now(),
    )
    monkeypatch.setattr("codegenie.sandbox.health.probe.auto_detect", lambda: fake)
    result = SandboxHealthProbe().run(_ctx(tmp_path))
    assert result.payload["sandbox"].reachable is True

def test_daemon_unreachable_propagates(monkeypatch, tmp_path, write_real_digest):
    write_real_digest(tmp_path)
    monkeypatch.chdir(tmp_path)
    fake = MagicMock()
    fake.health.return_value = SandboxHealth(
        backend="docker_in_docker", reachable=False, confidence="high",
        reasons=["daemon_unreachable"], warnings=[],
        detected_at=__import__("datetime").datetime.now(),
    )
    monkeypatch.setattr("codegenie.sandbox.health.probe.auto_detect", lambda: fake)
    result = SandboxHealthProbe().run(_ctx(tmp_path))
    assert "daemon_unreachable" in result.payload["sandbox"].reasons

@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS-only warning")
def test_macos_strace_warning_passes_through(monkeypatch, tmp_path, write_real_digest):
    """soft-signal per arch §Risk-3 — must surface as a warning, NOT flip reachable."""
    write_real_digest(tmp_path)
    monkeypatch.chdir(tmp_path)
    fake = MagicMock()
    fake.health.return_value = SandboxHealth(
        backend="docker_in_docker", reachable=True, confidence="medium",
        reasons=[], warnings=["strace_ptrace_missing"],
        detected_at=__import__("datetime").datetime.now(),
    )
    monkeypatch.setattr("codegenie.sandbox.health.probe.auto_detect", lambda: fake)
    result = SandboxHealthProbe().run(_ctx(tmp_path))
    assert result.payload["sandbox"].reachable is True
    assert "strace_ptrace_missing" in result.payload["sandbox"].warnings
```

### Green — make it pass

- Implement the probe in the order described above; short-circuit on digest mismatch before `auto_detect()`.
- Wire registration into the Phase 1 probe registry (mimic the registration pattern of `B2 IndexHealthProbe` or `B1 NodeManifest`).

### Refactor — clean up

- Type hints, docstring linking to ADR-0013.
- structlog event with stable key set.
- Verify `mypy --strict` clean.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/health/__init__.py` | New subpackage marker. |
| `src/codegenie/sandbox/health/probe.py` | New — the probe. |
| `tests/sandbox/health/__init__.py` | New test subpackage marker. |
| `tests/sandbox/health/test_probe.py` | New — four cases (digest miss / happy / daemon down / macOS warning). |
| `tests/sandbox/health/conftest.py` | New — `write_real_digest` fixture computing real BLAKE3 + writing matched files. |

## Out of scope

- The `codegenie sandbox health` CLI subcommand — S8-01 wraps this probe.
- Firecracker-specific health reasons (`kvm_missing`, `vmlinux_digest_mismatch`) — S6-01 adds them on the Firecracker side; this probe passes them through unchanged when `auto_detect()` returns Firecracker.
- Phase 1 `IndexHealthProbe` (`B2`) — separate probe, separate story.
- Performance regression on the probe (it must complete in ≤ 5 s per arch spec) — covered later in Step 7 perf gates.

## Notes for the implementer

- **The digest check must precede the backend call.** A digest mismatch should never reach `auto_detect()` — that's the contract ADR-0013 implies. If you flip the order, the test `test_policy_digest_mismatch_short_circuits_without_calling_backend` will fail, which is exactly the intent.
- The Phase 1 `Probe` ABC interface is set elsewhere — grep for `class Probe` to confirm the exact method signature (`run(self, ctx)` vs `gather(self)` etc.). Match Phase 1's convention; do not invent a new one.
- `confidence` field on `SandboxHealth` is **about the probe's confidence in its own answer**, not about a signal — it's allowed by ADR-0014's static introspection because it's on `SandboxHealth`, not on anything reachable from `ObjectiveSignals`. Verify with `tests/schema/test_objective_signals_static.py` (still green after this story).
- Don't catch broad `Exception` and silently flip `reachable=False`. Per arch: "raises only on programming errors" — let real bugs propagate; structured failure reasons are for *expected* unavailability modes only.
- The `warnings` field carries soft signals (macOS strace); it does **not** affect `reachable`. Reviewers and Phase 11 handoff read both.
- `tools/digests.yaml` schema may have multiple top-level keys — read carefully via `yaml.safe_load(...)["sandbox"]["policy_yaml"]`; raise a clear error if the path is missing rather than KeyError-ing.
