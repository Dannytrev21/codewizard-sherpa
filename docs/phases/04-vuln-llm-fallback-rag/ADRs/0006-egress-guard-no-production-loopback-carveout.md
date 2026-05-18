# ADR-0006: `EgressGuard` rejects loopback in production — pytest-only thread-local opt-in

**Status:** Accepted
**Date:** 2026-05-18
**Tags:** threat-model · trust-boundary · test-isolation · anti-pattern-avoidance
**Related:** ADR-0005 (this phase) · ADR-0010 (this phase)

## Context

The security design lens shipped an `EgressGuard` that allowlisted `api.anthropic.com:443` *plus* unconditionally permitted loopback (`127.0.0.1`, `::1`). The justification was that test infrastructure (e.g., `pytest-httpserver`, chromadb's embedded debug surface) needs loopback access.

The critic was direct (`critique.md §"[S] §2"`): "a loopback whitelist defeats the 'EgressGuard catches dynamic uses' argument. The control's threat-model claim ('catches transitive deps opening sockets on import') fails the moment any dep opens a loopback socket — which `chromadb` itself might do for its embedded mode debug surface, and `onnxruntime`/`torch` definitely do for telemetry-shaped behaviors." A poisoned local proxy injected by an adversarial dep from PyPI would be in-scope under loopback.

The threat model `EgressGuard` is supposed to mitigate is exactly: "transitive deps silently dial unexpected hosts." Loopback is the bypass that defeats the model. But the test infrastructure does legitimately need loopback. The choice is *how* the carve-out is gated.

## Options considered

- **Unconditional loopback carve-out** (security lens original). `EgressGuard` permits `127.0.0.1` and `::1` for any caller. **Pattern:** Hardcoded allowlist exception. Defeats the threat model.
- **Boolean flag on `EgressGuard.install(allow_loopback=...)`** — set by tests, unset in production. **Pattern:** Boolean configuration flag. The toolkit's "boolean flag on public methods" anti-pattern fires; "two behaviors for one global resource" critic flag fires; one PR sets the flag, design hopes culture enforces it.
- **Environment-variable gate** (`CODEGENIE_TEST_ALLOW_LOOPBACK=1`). **Pattern:** Environment-variable configuration. Same culture-dependency problem; one shell export in CI silently widens the threat surface.
- **Pytest-fixture-set thread-local flag** — `_test_only_loopback_enabled` thread-local set by an explicit pytest fixture; production code path never touches it; `EgressGuard.create_connection_wrapper` checks the thread-local. **Pattern:** Test-scoped capability (lexically narrow, not configurable from outside test code).

## Decision

`EgressGuard` rejects loopback by default. A pytest fixture (`@pytest.fixture def egress_test_loopback():`) sets a thread-local flag `_test_only_loopback_enabled = True`; the socket wrapper checks this flag and admits `127.0.0.1`/`::1` only when it's set. Production code paths never set the flag; there is no environment-variable escape, no boolean parameter, no module-level constant. The flag is **thread-local**, not process-global — concurrent production workflows running in sibling threads cannot leak into one another. **Pattern:** Test-scoped capability via a lexically-scoped thread-local set only by an explicit pytest fixture. `EgressGuard.reset_for_test()` is exposed for explicit test cleanup. Asserted by `tests/adversarial/test_egress_guard.py` ("loopback is rejected unless `_test_only_loopback_enabled` is set").

## Tradeoffs

| Gain | Cost |
|---|---|
| Threat model holds — transitive-dep dynamic socket-opens on loopback are caught at runtime | Test fixtures must explicitly opt in; new tests that hit loopback fail loudly until the fixture is added |
| No environment-variable surface — CI configuration cannot silently widen the egress allowlist | Engineers debugging integration tests must learn the fixture exists (documented in `tests/conftest.py` + `docs/contributing.md`) |
| Thread-local scope means concurrent workflows running in the same process (Phase 9 Temporal workers) cannot poison each other's egress posture | Async code that hops event loops must care about thread-locality — Phase 9's `asyncio` workers must not share thread-locals across workflow boundaries (test: `tests/adversarial/test_egress_guard_thread_isolation.py`) |
| The fixture is lexically explicit at the test site — `def test_x(egress_test_loopback): ...` — making the test's threat-model assumption visible in code review | Tests cannot accidentally inherit loopback access from imports; every loopback-using test must request the fixture |
| C-extension `connect(2)` bypasses Python's `socket` module — same residual as ADR-0005 — but the loopback carve-out is no longer the bypass; the bypass is now the well-known C-extension residual | We accept the C-extension residual as ADR-0005's documented residual; loopback is no longer a *second* bypass |

## Pattern fit

The toolkit's anti-pattern list explicitly flags "Boolean flags on public methods" and "Capability passed through ten frames." The thread-local fixture pattern is *neither*: it's a lexically-scoped state mutation owned by the test framework, not a configuration option on `EgressGuard`. The flag is invisible at the `EgressGuard.install()` callsite; it's visible only at the `def test_x(egress_test_loopback)` callsite — exactly where the threat-model assumption matters.

The honest framing: this is the *Test Capability* pattern (a capability that only test code can mint). Production code has no way to construct it; `EgressGuard.reset_for_test()` is the explicit teardown.

## Consequences

- `EgressGuard.create_connection` checks `_test_only_loopback_enabled` thread-local; production process never sets it.
- `tests/conftest.py` exposes the `egress_test_loopback` fixture with explicit set/reset.
- Integration tests that need `pytest-httpserver` or local chromadb HTTP introspection request the fixture; tests that don't, don't.
- The `tests/adversarial/test_egress_guard.py` test patches `requests`, `urllib3`, `httpx`, and `socket` to attempt forbidden hosts including loopback *without* the fixture; assertion is `EgressViolation` raised.
- Phase 9's Temporal worker integration must ensure no test fixture's thread-local leaks across worker boundaries — covered by `tests/adversarial/test_egress_guard_thread_isolation.py` (Phase-4-specified; Phase 9 inherits the assertion).
- A future operator-only debug command (`codegenie self-check egress`) reports OS-level posture but never sets the thread-local — production tooling has no escape.
- Phase 7's distroless plugin migration adds its own allowlist entries; the loopback policy is unchanged across phases.

## Reversibility

**Medium.** Re-introducing an unconditional loopback carve-out is a few-line code edit but loses the threat-model guarantee; would require a Phase-4 ADR amendment with explicit reasoning. Switching from thread-local to a different opt-in mechanism (e.g., a context manager) is a refactor with the same threat-model surface — low cost.

## Evidence / sources

- `../final-design.md §Component 10 — EgressGuard` ("loopback is **not** unconditionally permitted")
- `../final-design.md §Departures from all three inputs` item 5
- `../phase-arch-design.md §Component design — EgressGuard`
- `../phase-arch-design.md §Anti-patterns avoided` ("Boolean flags on public methods" → thread-local)
- `../critique.md §"[S] §2"` (loopback whitelist defeats threat model)
