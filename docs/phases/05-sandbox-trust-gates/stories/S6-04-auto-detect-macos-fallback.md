# Story S6-04 — `sandbox.registry.auto_detect` + macOS fallback INFO log

**Step:** Step 6 — FirecrackerClient backend + KVM-gated CI smoke test
**Status:** Ready
**Effort:** S
**Depends on:** S6-01
**ADRs honored:** ADR-0004, ADR-0001

## Context

Both `SandboxClient` backends now exist (DinD from S3-02, Firecracker from S6-01), but no caller knows which to pick at runtime. `phase-arch-design.md §Component design` and `ADR-0004` commit us to `sandbox.registry.auto_detect()`: if `/dev/kvm` is readable+writable, return Firecracker; otherwise return DinD with a structured INFO log of the fallback reason. The orchestrator passes `auto_detect()` (default) into `GateRunner` unless `--sandbox-backend {did,firecracker,auto}` overrides it. This story is small but it is the **only** seam where a Linux/CI run silently picks the wrong backend if we get it wrong — so the test must exercise both branches plus the on-macOS log line that operators rely on to diagnose surprises.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — SandboxClient` — `sandbox.registry` exposes `get_backend(name)` and `auto_detect() -> SandboxClient`.
  - `../phase-arch-design.md §Edge cases §15` — `/dev/kvm` absent → auto-detect falls back to DinD with INFO log.
  - `../phase-arch-design.md §CLI surface` — `--sandbox-backend {did,firecracker,auto}` defaults to `auto`.
- **Phase ADRs:**
  - `../ADRs/0004-dind-default-macos-with-gate-isolation-class.md` — "`codegenie sandbox auto-detect` returns Firecracker if `/dev/kvm` is readable, else DinD; structured fallback INFO log on macOS." This is the verbatim consequence we are landing.
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — `SandboxClient` is the seam; `auto_detect` returns one, never both.
- **Production ADRs:**
  - `../../../production/adrs/0019-sandbox-stack.md` — auto-detect picks the production-shaped backend; evidence feeds eventual resolution.
- **Source design:**
  - `../final-design.md §Synthesis ledger row "Sandbox stack default macOS"` — fallback semantics in plain language.
- **Existing code:**
  - `src/codegenie/sandbox/registry.py` (from S1-05) — already exposes `get_backend(name)` and the `@register_sandbox_backend` decorator; add `auto_detect()` here.
  - `src/codegenie/sandbox/did/client.py` (from S3-02) — DinD client construction.
  - `src/codegenie/sandbox/firecracker/client.py` (from S6-01) — `FirecrackerClient.from_digests_yaml()` (from S6-03) or the bare constructor.
  - `src/codegenie/sandbox/errors.py` — `FirecrackerKvmMissing` message includes the literal `docker_in_docker` per S6-01's contract — the INFO log can match on that for human-readable reasons.
- **External docs:** None — pure host-detection logic.

## Goal

Implement `sandbox.registry.auto_detect()` so KVM-capable Linux hosts get `FirecrackerClient`, everything else gets `DockerInDockerClient`, and the fallback emits a single structured INFO log line every operator can grep.

## Acceptance criteria

- [ ] `sandbox.registry.auto_detect() -> SandboxClient` is implemented in `src/codegenie/sandbox/registry.py`.
- [ ] KVM-present detection is `Path("/dev/kvm").exists() and os.access("/dev/kvm", os.R_OK | os.W_OK)` — both conditions, not either; a read-only `/dev/kvm` still falls back to DinD (verified by a test that mocks `os.access` to return False).
- [ ] On KVM-present, returns `FirecrackerClient` (via `from_digests_yaml()` if S6-03 has landed, else the constructor with digests loaded inline); on KVM-absent, returns `DockerInDockerClient`.
- [ ] Fallback (KVM-absent or KVM-present-but-not-accessible) emits exactly one structlog event at INFO level: `sandbox.registry.fallback_to_did` with structured fields `reason` (one of `"kvm_missing"`, `"kvm_not_accessible"`, `"platform_not_linux"`), `platform` (e.g., `"darwin"`, `"linux"`), `selected_backend="docker_in_docker"`.
- [ ] On the happy path (Firecracker selected), emits one structlog event at INFO level: `sandbox.registry.selected` with `selected_backend="firecracker"`, `reason="kvm_available"`.
- [ ] On macOS (`sys.platform == "darwin"`), `auto_detect` short-circuits the KVM probe (no `/dev/kvm` check attempted — would fail anyway) and emits the fallback log with `reason="platform_not_linux"`.
- [ ] If `FirecrackerClient` construction itself raises (e.g., digest mismatch surfaced by S6-03 at construction), `auto_detect` **does not** silently fall back — it re-raises so operators do not run gates on the unintended backend. (The fallback policy is for `/dev/kvm` only.)
- [ ] `tests/sandbox/test_auto_detect.py` covers four cases: (1) macOS → DinD + fallback log, (2) Linux + `/dev/kvm` readable → Firecracker + selected log, (3) Linux + `/dev/kvm` absent → DinD + fallback log, (4) Linux + `/dev/kvm` present but not r+w → DinD + fallback log.
- [ ] The INFO log is emitted **before** the chosen client is returned (so even a panicked caller upstream sees the selection in logs).
- [ ] `auto_detect` itself does not raise on KVM probing — `OSError` / `PermissionError` from `os.access` is treated as "not accessible" → fallback.
- [ ] No new dependencies; no new `subprocess` calls (this story changes nothing under the chokepoint discipline).
- [ ] Branch coverage on the new code in `src/codegenie/sandbox/registry.py` ≥ 95%.
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/sandbox`, `pytest tests/sandbox/test_auto_detect.py` all pass.

## Implementation outline

1. Open `src/codegenie/sandbox/registry.py` and add `auto_detect() -> SandboxClient` alongside the existing `get_backend(name)`:
   ```python
   def auto_detect() -> SandboxClient:
       reason, platform_name = _probe_kvm()
       if reason is None:
           logger.info("sandbox.registry.selected",
                       selected_backend="firecracker",
                       reason="kvm_available",
                       platform=platform_name)
           return get_backend("firecracker")
       logger.info("sandbox.registry.fallback_to_did",
                   selected_backend="docker_in_docker",
                   reason=reason,
                   platform=platform_name)
       return get_backend("docker_in_docker")
   ```
2. Add the helper `_probe_kvm() -> tuple[str | None, str]`:
   - Return `("platform_not_linux", sys.platform)` if `sys.platform != "linux"`.
   - Return `("kvm_missing", "linux")` if `not Path("/dev/kvm").exists()`.
   - Return `("kvm_not_accessible", "linux")` if `os.access("/dev/kvm", os.R_OK | os.W_OK) is False` (or raises).
   - Return `(None, "linux")` on full success.
3. Re-export `auto_detect` from `src/codegenie/sandbox/__init__.py`.
4. Add a structlog event constant in the events module (from S1-01) for `sandbox.registry.selected` and `sandbox.registry.fallback_to_did`.
5. Wire `RemediationOrchestrator` to default to `auto_detect()` when `--sandbox-backend auto` (S8-02) is passed; for this story, only the registry function needs to exist and have tests — orchestrator wiring lands in S8-02.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/sandbox/test_auto_detect.py`

```python
# tests/sandbox/test_auto_detect.py
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest
import structlog

from codegenie.sandbox import registry
from codegenie.sandbox.did.client import DockerInDockerClient
from codegenie.sandbox.firecracker.client import FirecrackerClient


@pytest.fixture
def log_capture():
    """Capture structlog events for assertion."""
    cap = structlog.testing.LogCapture()
    structlog.configure(processors=[cap])
    yield cap


def test_macos_falls_back_to_did_with_platform_reason(log_capture) -> None:
    with patch.object(sys, "platform", "darwin"):
        client = registry.auto_detect()
    assert isinstance(client, DockerInDockerClient)
    events = [e for e in log_capture.entries if "sandbox.registry" in e["event"]]
    assert len(events) == 1
    e = events[0]
    assert e["event"] == "sandbox.registry.fallback_to_did"
    assert e["reason"] == "platform_not_linux"
    assert e["platform"] == "darwin"
    assert e["selected_backend"] == "docker_in_docker"


def test_linux_with_readable_writable_kvm_picks_firecracker(log_capture) -> None:
    with patch.object(sys, "platform", "linux"), \
         patch("codegenie.sandbox.registry.Path.exists", return_value=True), \
         patch("codegenie.sandbox.registry.os.access", return_value=True), \
         patch("codegenie.sandbox.registry.get_backend") as gb:
        gb.return_value = FirecrackerClient.__new__(FirecrackerClient)
        client = registry.auto_detect()
    assert client is gb.return_value
    events = [e for e in log_capture.entries if "sandbox.registry" in e["event"]]
    assert events[0]["event"] == "sandbox.registry.selected"
    assert events[0]["selected_backend"] == "firecracker"
    assert events[0]["reason"] == "kvm_available"


def test_linux_missing_kvm_falls_back_to_did(log_capture) -> None:
    with patch.object(sys, "platform", "linux"), \
         patch("codegenie.sandbox.registry.Path.exists", return_value=False):
        client = registry.auto_detect()
    assert isinstance(client, DockerInDockerClient)
    events = [e for e in log_capture.entries if "sandbox.registry" in e["event"]]
    assert events[0]["reason"] == "kvm_missing"


def test_linux_kvm_not_accessible_falls_back_to_did(log_capture) -> None:
    with patch.object(sys, "platform", "linux"), \
         patch("codegenie.sandbox.registry.Path.exists", return_value=True), \
         patch("codegenie.sandbox.registry.os.access", return_value=False):
        client = registry.auto_detect()
    assert isinstance(client, DockerInDockerClient)
    events = [e for e in log_capture.entries if "sandbox.registry" in e["event"]]
    assert events[0]["reason"] == "kvm_not_accessible"


def test_os_access_raising_treats_kvm_as_inaccessible(log_capture) -> None:
    with patch.object(sys, "platform", "linux"), \
         patch("codegenie.sandbox.registry.Path.exists", return_value=True), \
         patch("codegenie.sandbox.registry.os.access", side_effect=PermissionError):
        client = registry.auto_detect()
    assert isinstance(client, DockerInDockerClient)
    assert log_capture.entries[-1]["reason"] == "kvm_not_accessible"


def test_firecracker_construction_failure_propagates(log_capture) -> None:
    """If Firecracker construction itself raises, auto_detect re-raises — not silent fallback."""
    with patch.object(sys, "platform", "linux"), \
         patch("codegenie.sandbox.registry.Path.exists", return_value=True), \
         patch("codegenie.sandbox.registry.os.access", return_value=True), \
         patch("codegenie.sandbox.registry.get_backend",
               side_effect=RuntimeError("digest mismatch")):
        with pytest.raises(RuntimeError, match="digest mismatch"):
            registry.auto_detect()
```

Use `pytest.mark.skip_if_no_kvm` is **not** used in this story — the unit tests must run on every contributor laptop, KVM or not.

### Green — make it pass

Minimal: implement `_probe_kvm` and `auto_detect` per the outline; emit two distinct structlog events; return the right client. No new dependencies.

### Refactor — clean up

- Pull the four return-tuples in `_probe_kvm` into named-constant strings exported alongside the events module so consumers can match on the canonical strings.
- Hoist the `logger = structlog.get_logger(__name__)` to module scope.
- Add a docstring on `auto_detect` citing ADR-0004 and the on-macOS fallback contract.
- Consider exposing `auto_detect_dry_run() -> tuple[str, str]` returning `(selected_backend, reason)` without instantiating clients — useful for `codegenie sandbox health` (S8-01). If exposed, add it; otherwise leave a TODO with the ticket reference.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/registry.py` | Add `auto_detect()` and `_probe_kvm()`. |
| `src/codegenie/sandbox/__init__.py` | Re-export `auto_detect`. |
| `src/codegenie/sandbox/_events.py` (or wherever S1-01 placed event constants) | Add the two new event-name constants. |
| `tests/sandbox/test_auto_detect.py` | The six tests above. |

## Out of scope

- Orchestrator wiring of `--sandbox-backend auto` → `auto_detect()` — S8-02.
- `codegenie sandbox health` surfacing `auto_detect_dry_run` — S8-01.
- KVM-gated integration smoke test — S6-05.
- Firecracker construction errors during health checks — surfaced by S6-01 / S6-03; this story propagates them, does not handle them.
- Allowing operators to *force* Firecracker on a non-KVM host via env-var fallback — explicit non-goal; the CLI `--sandbox-backend firecracker` is the override (S8-02).

## Notes for the implementer

- `os.access` is *advisory* under POSIX — it answers the access question for the real (not effective) user, and on some systems can return `True` while the open still fails. We accept the imprecision: `auto_detect` is a hint, `FirecrackerClient._assert_kvm()` (S6-01) is the authoritative gate. Do not bolt on a second check here.
- The INFO log must be emitted **before** the return so a crash in `get_backend("docker_in_docker")` still leaves the operator with the diagnostic. Wire the log call as the line before `return`.
- Do not catch `Exception` around `_probe_kvm`. The only acceptable raised exception is the one from `Path.exists`/`os.access`, both already handled. A wider catch hides real bugs.
- The four `reason` strings are part of the structured-logging contract — they will be grepped by operators and ingested by Phase 13's cost dashboard. Do not rename or add new ones without an ADR amendment.
- The test fixture uses `structlog.testing.LogCapture`; this is the project-standard structlog test helper (used in S1-01's scaffolding). Do not introduce a custom capture mechanism.
- Resist building a "tier" system (try Firecracker → on `FirecrackerKvmMissing` swap to DinD mid-run). The decision is made once at `auto_detect` time and is final. Mid-run swaps would invalidate the audit chain (S2-01) and `gate_isolation_class` annotation (ADR-0004).
- `sys.platform` is `"linux"` on every Linux distro (including WSL2 — which does have KVM); the test mocks `sys.platform` directly. Do not switch to `platform.system()` — `sys.platform` is the project-standard discriminator.
