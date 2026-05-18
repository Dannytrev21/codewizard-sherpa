# Story S3-03 — `EgressGuard` via `sitecustomize` (no production loopback carve-out)

**Step:** Step 3 — Ship LeafLlm Port + AnthropicLeafAdapter + EgressGuard + cassette discipline
**Status:** Ready
**Effort:** M
**Depends on:** S3-02 (`AnthropicLeafAdapter` consumes `EgressGuard.pinned_to(...)`)
**ADRs honored:** ADR-0005 (Phase 4 — no SPKI pin; `EgressGuard` is layer 1 of 4 defense-in-depth), ADR-0006 (Phase 4 — loopback rejected in production; pytest-fixture-set thread-local opt-in only)

## Context

`EgressGuard` is the **process-wide socket guard** — the runtime allowlist that catches transitive deps silently dialing unexpected hosts. It is the **belt** to `LeafLlm`'s suspenders (every leaf SDK call is independently wrapped in `pinned_to(...)`), and it is the load-bearing answer to "what catches a transitive dep that opens a socket on import?"

Two non-obvious decisions from the ADRs constrain the shape:

1. **No SPKI pin.** Per ADR-0005, `api.anthropic.com:443` is the host-level allowlist; TLS uses the system trust store. SPKI pinning was rejected as self-DOS on Anthropic CA rotation.
2. **No production loopback carve-out.** Per ADR-0006, `127.0.0.1` and `::1` are **rejected by default**. A pytest-fixture-set thread-local flag `_test_only_loopback_enabled` is the only opt-in; the production code path never sets it. There is no env-var escape, no boolean parameter, no module-level constant. The flag is **thread-local** (not process-global) so concurrent Phase-9 Temporal workflows running in sibling threads cannot leak posture between each other.

The honest framing: `EgressGuard` is a process-global stateful wrapper installed via `sitecustomize.py` at interpreter start. That's a known smell (acknowledged residual in `phase-arch-design.md §Anti-patterns avoided`); the mitigation is (a) explicit `reset_for_test()` for every test that touches it, (b) thread-locality of the test-only flag, and (c) an adversarial test suite that patches `requests`/`urllib3`/`httpx`/`socket` to attempt every forbidden host shape.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 15 — EgressGuard` — public interface (`install()`, `pinned_to(host)`, `reset_for_test()`), structure (sitecustomize wrap of `socket.create_connection`), failure (`EgressViolation(host)`).
  - `../phase-arch-design.md §Edge cases #12, #15` — egress to non-Anthropic host; loopback rejection.
  - `../phase-arch-design.md §Anti-patterns avoided` — "Boolean flags on public methods" → thread-local; "Side effects in constructors / module import time" — acknowledged residual with mitigation.
  - `../phase-arch-design.md §Threat model` and §Resource & cost profile — defense-in-depth stack (EgressGuard + OS filter + nightly drift + import-linter native-ext restriction).
- **Phase ADRs:**
  - `../ADRs/0005-no-spki-pin-egress-defense-in-depth.md` §Decision — system trust; allowlist is `api.anthropic.com:443`; no SPKI pin.
  - `../ADRs/0006-egress-guard-no-production-loopback-carveout.md` §Decision — thread-local opt-in only; **no** boolean param, **no** env-var, **no** module constant.
- **Production ADRs:**
  - `../../../production/adrs/0020-leaf-agents-sdk.md` — when a second vendor lands, allowlist is *additive* (one new host); no SPKI pin set to maintain.
- **Source design:** `../final-design.md §Component 10 — EgressGuard`.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `src/codegenie/__main__.py` and `src/codegenie/cli.py` — the existing `python -m codegenie` CLI; `self-check egress` is a new subcommand.
  - `tests/conftest.py` — the root-level conftest where the `egress_test_loopback` fixture lands.
  - `pyproject.toml` `[project.scripts]` block — confirm the entry-point shape `codegenie self-check egress`.
  - There is no existing `sitecustomize.py` in the repo; this story creates it.

## Goal

Install a process-wide `socket.create_connection` wrapper that admits only `api.anthropic.com:443` (with a `pinned_to(host)` context manager for additive allowlist), rejects loopback in production unless a pytest-fixture-set thread-local is set, exposes `reset_for_test()` for explicit test cleanup, and ships a `codegenie self-check egress` CLI subcommand that reports OS-level posture without escalating any privilege.

## Acceptance criteria

### Install + wrap semantics

- [ ] AC-1 — `src/codegenie/fallback/leaf/egress_guard.py` exports `EgressGuard` (class with classmethod `install()`, classmethod `pinned_to(host)` context manager, classmethod `reset_for_test()`), `EgressViolation(Exception)`, and `_test_only_loopback_enabled: contextvars.ContextVar[bool] | threading.local` (private, but test-accessible at the module level for adversarial-test set/reset).
- [ ] AC-2 — `EgressGuard.install()` is **idempotent**: calling it twice in the same process does not double-wrap `socket.create_connection`. Implementation should check a module-level `_installed: bool` flag. Test: call `install()` twice; assert `socket.create_connection.__wrapped__` exists and is the original; the wrapped function's identity is stable across calls.
- [ ] AC-3 — The wrapped `socket.create_connection((host, port), *args, **kwargs)` raises `EgressViolation(host=host, port=port)` if `(host, port)` is not in the active allowlist; otherwise calls the original `socket.create_connection`.
- [ ] AC-4 — The base allowlist is the single tuple `("api.anthropic.com", 443)`. `EgressGuard.pinned_to("api.anthropic.com:443")` is a re-affirmation context manager (Phase-4 ships a single host; it is the **only** active allowlist for a Phase-4 process). Calling `pinned_to(other_host)` raises `EgressViolation` (no Phase-4 dynamic host registration; Phase 7's distroless plugin is the ADR amendment vehicle for adding hosts).
- [ ] AC-5 — `sitecustomize.py` lives at repo root and contains exactly:
  ```python
  # repo-root sitecustomize.py — installed at interpreter start per PEP 370 / site.py
  try:
      from codegenie.fallback.leaf.egress_guard import EgressGuard
      EgressGuard.install()
  except ImportError:
      pass  # codegenie not in path (e.g., contributor's tox env without -e .)
  ```
  The `try/except ImportError` is the **only** acceptable swallow; any other exception propagates. Test: import error swallowed; `EgressViolation`-raising init bug would NOT be swallowed.

### Loopback policy (ADR-0006)

- [ ] AC-6 — With no test fixture active, `socket.create_connection(("127.0.0.1", 8080))` raises `EgressViolation`. Same for `("::1", 8080)`, `("localhost", 8080)`. Adversarial test parametrizes over these three.
- [ ] AC-7 — With the `egress_test_loopback` pytest fixture active (sets the thread-local flag to `True`), `socket.create_connection(("127.0.0.1", any_port))` succeeds (the wrapper falls through to the real socket call). Test asserts the fixture's set/reset (uses `pytest.fixture` with `yield`; the post-yield resets the flag to `False`).
- [ ] AC-8 — The flag is **thread-local**: a test spawns two threads, only thread A's fixture sets the flag, thread B attempts loopback → thread B raises `EgressViolation`. Implementation: `threading.local()` or `contextvars.ContextVar` with explicit copy on thread boundary.
- [ ] AC-9 — **No env-var escape.** AST source-scan asserts `egress_guard.py` does not reference `os.environ`, `os.getenv`, or any `CODEGENIE_*` string. Adversarial test sets `CODEGENIE_TEST_ALLOW_LOOPBACK=1` and verifies loopback is still rejected without the fixture.
- [ ] AC-10 — **No boolean parameter.** `EgressGuard.install()` takes **zero arguments**. `pinned_to(host)` takes exactly the one positional host string. Signature is type-checked at `mypy --strict`.

### `pinned_to` context manager

- [ ] AC-11 — `async with EgressGuard.pinned_to("api.anthropic.com:443")` enters and exits cleanly; calling `socket.create_connection(("api.anthropic.com", 443))` succeeds inside the block and remains permitted outside (because it's in the base allowlist).
- [ ] AC-12 — `pinned_to("other.example.com:443")` raises `EgressViolation` at *enter* (not inside the body); the body never runs.
- [ ] AC-13 — Implementation note: `pinned_to` may be a no-op for Phase 4 (one allowlisted host); it exists for `LeafLlm` adapters to *explicitly* assert they're talking to the right host. Document the rationale in the docstring.

### `reset_for_test()` + fixture

- [ ] AC-14 — `EgressGuard.reset_for_test()` resets the thread-local flag to `False` and is the only sanctioned cleanup path. Tests that touch the flag MUST call it explicitly in their teardown (or use the `egress_test_loopback` fixture which calls it on `yield` exit).
- [ ] AC-15 — `tests/conftest.py` exposes `egress_test_loopback` fixture:
  ```python
  @pytest.fixture
  def egress_test_loopback():
      from codegenie.fallback.leaf.egress_guard import EgressGuard, _test_only_loopback_enabled
      _test_only_loopback_enabled.set(True)
      try:
          yield
      finally:
          EgressGuard.reset_for_test()
  ```
  Plus the documentation block in `docs/contributing.md` (or `tests/conftest.py` docstring) explaining when to request the fixture.

### Adversarial suite

- [ ] AC-16 — `tests/adversarial/test_egress_guard.py` patches `requests.adapters.HTTPAdapter.send`, `urllib3.connection.HTTPConnection._new_conn`, `httpx._transports.default.HTTPTransport`, and the raw `socket.create_connection` to attempt connections to the parametrized forbidden hosts: `evil.example.com`, `10.0.0.1`, `127.0.0.1` (without fixture), `::1` (without fixture), `localhost`, an IPv4-in-hostname trick (`1.1.1.1` literal), an IDN homoglyph (`xn--api-1ub.anthropic.com`). Each must raise `EgressViolation`.
- [ ] AC-17 — `tests/adversarial/test_egress_guard_thread_isolation.py` — two threads; thread A sets fixture, thread B attempts loopback → `EgressViolation`. Phase-9 inherits this assertion.
- [ ] AC-18 — `tests/adversarial/test_egress_guard_no_sdk_bypass.py` — installs the wrapper; imports `anthropic` and constructs an `AsyncAnthropic` client; attempts to call `client.messages.create(...)` against a fake non-Anthropic host (monkeypatch the SDK base URL) → `EgressViolation`. Proves the SDK's `httpx` transport does **not** bypass the wrapper.

### `codegenie self-check egress` CLI

- [ ] AC-19 — `python -m codegenie self-check egress` is a new subcommand under the existing `cli.py` dispatcher; prints (a) the active allowlist (`api.anthropic.com:443`); (b) whether `EgressGuard` is `installed=True`; (c) the OS-level posture (a one-line check of `iptables`/`nftables` presence on Linux, a one-line "macOS dev — OS filter not configured by default" message on Darwin); (d) exits 0 always (it's a *reporting* command, not a gate). Tested with `pytest`'s `capsys` capture.
- [ ] AC-20 — The CLI subcommand **does not** set or unset the test-only flag (production tooling has no escape). Test: invoke the subcommand; afterward, `_test_only_loopback_enabled` is unchanged.

### Cross-cutting

- [ ] AC-21 — `mypy --strict src/codegenie/fallback/leaf/egress_guard.py` clean. `ruff check`, `ruff format --check` clean.
- [ ] AC-22 — `pre-commit run --all-files` passes (in particular, the `forbidden-patterns` hook should not complain — we are not using `subprocess.run(..., shell=True)`, `eval`, or `__import__`).
- [ ] AC-23 — TDD red test exists, was demonstrably failing before implementation, now green.

## Implementation outline

1. Create `src/codegenie/fallback/leaf/egress_guard.py`:
   - Module-level `_test_only_loopback_enabled: ContextVar[bool] = ContextVar("_test_only_loopback_enabled", default=False)` (or `threading.local()` — pick one; document why).
   - Module-level `_installed: bool = False`.
   - Module-level `_BASE_ALLOWLIST: Final[frozenset[tuple[str, int]]] = frozenset({("api.anthropic.com", 443)})`.
   - `class EgressViolation(Exception)` with `host: str`, `port: int` attributes.
   - `class EgressGuard` with `install()`, `pinned_to(host: str)`, `reset_for_test()` classmethods.
   - Private `_wrap_create_connection(original)` function returning the wrapped callable.
2. Create `sitecustomize.py` at repo root with the `EgressGuard.install()` call (AC-5).
3. Wire the `egress_test_loopback` fixture into `tests/conftest.py`.
4. Add the `self-check egress` subcommand to `src/codegenie/cli.py` (mirror the existing `audit verify` subcommand shape).
5. Author adversarial tests under `tests/adversarial/`.
6. Verify `import-linter` (S1-06) has a contract restricting native-extension-using deps; if missing, surface as a follow-up task (S1-06's responsibility; do not block S3-03 if S1-06 already landed it).

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/adversarial/test_egress_guard.py
import socket
import threading
import pytest
from codegenie.fallback.leaf.egress_guard import EgressGuard, EgressViolation


@pytest.fixture(autouse=True)
def _install():
    EgressGuard.install()  # idempotent
    yield
    EgressGuard.reset_for_test()


@pytest.mark.parametrize("host,port", [
    ("evil.example.com", 443),
    ("10.0.0.1", 443),
    ("127.0.0.1", 8080),
    ("::1", 8080),
    ("localhost", 8080),
    ("xn--api-1ub.anthropic.com", 443),
])
def test_forbidden_hosts_raise(host, port):
    with pytest.raises(EgressViolation) as exc:
        socket.create_connection((host, port))
    assert exc.value.host == host


def test_loopback_admitted_when_fixture_set(egress_test_loopback):
    # ... patch the real create_connection to a no-op; assert no EgressViolation.
    ...


def test_thread_local_isolation(egress_test_loopback):
    # main thread has fixture; spawn worker thread; worker attempts loopback → EgressViolation
    results = []
    def worker():
        try:
            socket.create_connection(("127.0.0.1", 8080))
            results.append("admitted")
        except EgressViolation:
            results.append("blocked")
    t = threading.Thread(target=worker); t.start(); t.join()
    assert results == ["blocked"]


def test_no_env_var_escape(monkeypatch):
    monkeypatch.setenv("CODEGENIE_TEST_ALLOW_LOOPBACK", "1")
    with pytest.raises(EgressViolation):
        socket.create_connection(("127.0.0.1", 8080))


def test_pinned_to_other_host_raises():
    with pytest.raises(EgressViolation):
        with EgressGuard.pinned_to("other.example.com:443"):
            pass


def test_self_check_egress_does_not_set_flag(capsys):
    from codegenie.cli import main
    main(["self-check", "egress"])
    out = capsys.readouterr().out
    assert "api.anthropic.com:443" in out
    # _test_only_loopback_enabled remains False
    from codegenie.fallback.leaf.egress_guard import _test_only_loopback_enabled
    assert _test_only_loopback_enabled.get() is False
```

### Green — make it pass

Implement `egress_guard.py` as outlined; wire the CLI; install via `sitecustomize.py`.

### Refactor — clean up

- Extract the `(host, port)` allowlist check into a pure helper `_is_admitted(host: str, port: int, *, loopback_enabled: bool) -> bool` so the wrapping logic is functional-core-only.
- Add module-level `_WARNING_IDS: Final[frozenset[str]] = frozenset({"egress.violation", "egress.installed"})`.
- Document the IDN/punycode normalization stance: the wrapper compares `host` against the allowlist *literally* — a caller passing `xn--api-1ub.anthropic.com` is rejected. The SDK never does this (it uses the configured base URL).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/fallback/leaf/egress_guard.py` | The wrapper module (this story's primary deliverable). |
| `sitecustomize.py` | Process-wide install at interpreter start (PEP 370). |
| `src/codegenie/cli.py` | Add `self-check egress` subcommand. |
| `tests/conftest.py` | Expose `egress_test_loopback` fixture. |
| `tests/adversarial/test_egress_guard.py` | Forbidden hosts; loopback policy; CLI side-effect-free check. |
| `tests/adversarial/test_egress_guard_thread_isolation.py` | Thread-local isolation. |
| `tests/adversarial/test_egress_guard_no_sdk_bypass.py` | Anthropic SDK does not bypass via `httpx`. |
| `docs/contributing.md` | (Append) One-paragraph note on when to use `egress_test_loopback`. |

## Out of scope

- OS-level egress filter (`iptables`/`nftables`) — documented but operator-installed; CLI *reports* posture, does not *enforce*.
- Nightly real-API drift job — ADR-0005 mentions it as defense-in-depth layer 3, but its CI workflow file is Phase-7 / Phase 6.5 territory.
- C-extension `connect(2)` bypass — known residual; mitigated by `import-linter` restriction on native-extension deps in S1-06.
- Adding a second host (Phase 7 distroless plugin's `cgr.dev`) — additive ADR amendment then, not here.

## Notes for the implementer

- `sitecustomize.py` at the repo root works only when the repo root is on `sys.path` (which `pip install -e .` arranges via the `.pth` shim). For contributors using a non-`-e` install, the `try/except ImportError` swallow is acceptable; the `EgressGuard` does not install but the AC-16 adversarial tests would surface this as a `pytest` failure.
- `socket.create_connection` is the only function we wrap. `socket.socket(...).connect(...)` is the lower-level path that some C extensions may use; `httpx` and `requests` ultimately funnel through `create_connection`, but raw `socket.socket(...).connect()` bypasses us. Document this clearly in the module docstring — the threat-model claim is "catches typical Python `http`/`urllib3`/`httpx` paths"; the C-extension residual is ADR-0005's accepted compromise.
- Choose `contextvars.ContextVar` over `threading.local()` if you want propagation across `await` boundaries; choose `threading.local()` if you specifically want *no* propagation (Phase 9's Temporal workers want thread-local — verify the contract by reading the Phase 9 architectural notes when they land). For Phase 4, `ContextVar` with `default=False` is the simpler choice; document the Phase-9 follow-up if a shift is needed.
- The `pinned_to(host)` method intentionally takes a `"host:port"` string rather than a `(host, port)` tuple so adapter call sites read like the URLs they protect — `pinned_to("api.anthropic.com:443")`. Parse the string in the implementation, reject malformed inputs with `ValueError` at *enter*.
- `EgressGuard.install()` must run **before** any module imports a network library at module-import time. `sitecustomize.py` is the earliest hook short of the C startup. If any test imports `requests`/`httpx` at module top-level, the install must already be done — which it will be, because `sitecustomize.py` runs before any user code.
- The `codegenie self-check egress` CLI **must not** invoke `socket.create_connection` against `api.anthropic.com` (that would spend bandwidth and surface a false "TLS error" when offline). It is a *reporting* command — just print the static allowlist and the install state.
