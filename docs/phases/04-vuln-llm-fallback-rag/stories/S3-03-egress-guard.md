# Story S3-03 — `EgressGuard` via `sitecustomize` (no production loopback carve-out)

**Step:** Step 3 — Ship LeafLlm Port + AnthropicLeafAdapter + EgressGuard + cassette discipline
**Status:** HARDENED
**Effort:** M
**Depends on:** S3-02 — the concrete `EgressGuard` must satisfy the `EgressGuardPort` Protocol that hardened S3-02 introduced (`pinned_to(host: str) -> AsyncContextManager[None]`; the adapter injects it and wraps every physical SDK attempt).
**ADRs honored:** ADR-0005 (Phase 4 — no SPKI pin; `EgressGuard` is layer 1 of 4 defense-in-depth), ADR-0006 (Phase 4 — loopback rejected in production; pytest-fixture-set thread-local opt-in only)

## Validation notes (phase-story-validator, 2026-05-21)

Verdict: **HARDENED**. The goal is sound; six executor-blocking gaps were closed and eight criteria strengthened. Full audit: `_validation/S3-03-egress-guard.md`.

- **B1 — `sitecustomize.py` auto-discovery was untested.** Every adversarial test calls `EgressGuard.install()` explicitly, so the suite would be green even if the `sitecustomize.py`-at-repo-root mechanism never fires. Added AC-26: a subprocess test that runs `python -m codegenie` in a *fresh* interpreter (no explicit `install()`) and asserts the guard is active. This is the only test that proves the load-bearing mechanism.
- **B2 — process-wide blast radius unaddressed.** Once `sitecustomize.py` is committed, every `pytest`/`python -m codegenie` run installs the guard. Added AC-25: the full existing suite (`make test`) must stay green; the executor runs it, not just the new files.
- **B3 — `pinned_to` sync/async contradiction.** S3-02's `EgressGuardPort` requires an `AsyncContextManager`; AC-11 uses `async with`; the TDD red test used a sync `with`. TDD plan corrected to `async with`.
- **B4 — the S3-02 ↔ S3-03 contract was unverified.** S3-02 introduced `EgressGuardPort` *specifically so S3-03 could satisfy it*, yet no AC checked that. Added AC-24: a typed assignability check (`EgressGuard` → `EgressGuardPort`).
- **B5 — wrong import in the TDD plan.** `from codegenie.cli import main` is wrong — `main(argv)` lives in `codegenie.__main__`; `cli.py` exports the click group `cli`. Corrected.
- **B6 — directory convention drift.** The codebase uses `tests/adv/` with per-phase subdirs (`tests/adv/phase02/`, marker `phase02_adv`); the arch/ADR prose says `tests/adversarial/`. Per Rule 11 the story now targets `tests/adv/phase04/` + a CI-gating `phase04_adv` marker. The arch/ADR `tests/adversarial/` wording is flagged for separate doc cleanup (out of scope here).

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
  - `src/codegenie/cli.py` — the CLI is **click**-based: `cli = @click.group(name="codegenie")`; subcommands are `@cli.command(...)` and subgroups are `@cli.group(...)` then `@<grp>.command(...)` (see the `audit` group at `cli.py:903` → `audit verify` at `cli.py:908`). `self-check` is a **new `@cli.group(name="self-check")`** with one `@self_check.command(name="egress")`. Mirror the `audit verify` shape.
  - `src/codegenie/__main__.py` — defines `main(argv: list[str] | None) -> int` and dispatches into `codegenie.cli.cli` with `standalone_mode=False`. **`main` lives here, not in `cli.py`.** Any in-process CLI test imports `from codegenie.__main__ import main`.
  - `src/codegenie/fallback/` does not exist yet — S3-02 creates `src/codegenie/fallback/leaf/`. This story adds `egress_guard.py` alongside S3-02's `anthropic_adapter.py`.
  - `tests/conftest.py` — **does not exist**; this story **creates** the root-level conftest to host the `egress_test_loopback` fixture (per-directory conftests already exist under `tests/unit/`, `tests/integration/`, `tests/adv/`, etc.; a new root conftest only *adds* a fixture — it is not autouse and changes no existing behavior).
  - `tests/adv/` and `tests/adv/phase02/` — the **established** adversarial-test layout. Phase-4 adversarial tests land under `tests/adv/phase04/` (the story's `tests/adversarial/...` paths in the arch/ADRs are pre-implementation prose — defer to the codebase, Rule 11).
  - `pyproject.toml` `[tool.pytest.ini_options].markers` — the `phase02_adv` marker (CI-gating) is the precedent; register a `phase04_adv` marker the same way for this story's adversarial tests.
  - There is no existing `sitecustomize.py` in the repo; this story creates it at the repo root.

## Goal

Install a process-wide `socket.create_connection` wrapper that admits only `api.anthropic.com:443` (with a `pinned_to(host)` context manager for additive allowlist), rejects loopback in production unless a pytest-fixture-set thread-local is set, exposes `reset_for_test()` for explicit test cleanup, and ships a `codegenie self-check egress` CLI subcommand that reports OS-level posture without escalating any privilege.

## Acceptance criteria

### Install + wrap semantics

- [ ] AC-1 — `src/codegenie/fallback/leaf/egress_guard.py` exports `EgressGuard` (class with classmethod `install()`, classmethod `pinned_to(host)` **async** context manager, classmethod `reset_for_test()`), `EgressViolation(Exception)`, and `_test_only_loopback_enabled: contextvars.ContextVar[bool]` (private, but test-accessible at the module level for adversarial-test set/reset). The flag is a `contextvars.ContextVar`, **not** `threading.local()` — this is now a decision, not an option: AC-15's fixture and the TDD plan both use the `ContextVar` API (`.set()` / `.get()`), and `ContextVar` propagates correctly across `await` boundaries (Phase-4 adapter calls are `async`) while still isolating `threading.Thread` workers (a freshly-started thread runs in an empty `Context`, so the parent's set value is invisible to it — exactly the AC-8 isolation guarantee, for free).
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
- [ ] AC-7 — With the `egress_test_loopback` fixture active (sets the `ContextVar` to `True`), `socket.create_connection` to loopback succeeds — the wrapper falls through to the **real** socket call. The test proves real fall-through, not a stub: it binds a throwaway `socket` listener to `("127.0.0.1", 0)` (ephemeral port), then asserts `socket.create_connection(("127.0.0.1", <bound_port>))` returns a genuinely connected socket (no `EgressViolation`). The same call with the fixture *not* active raises `EgressViolation` — this negative half is asserted in the same test so a wrapper that ignores the flag fails. (Do not "patch `create_connection` to a no-op" — a no-op cannot distinguish "fell through correctly" from "guard silently swallowed the call".)
- [ ] AC-8 — The flag is **thread-scoped**: only thread A's fixture sets the flag; thread B (spawned via `threading.Thread`) attempts loopback → thread B raises `EgressViolation`. No special implementation effort is required for this — a freshly-started `threading.Thread` runs in an *empty* `contextvars.Context`, so a value `set()` in thread A's context is simply not present in thread B (the `ContextVar`'s `default=False` applies). The test must **not** copy or propagate the context across the thread boundary; doing so would defeat the isolation. Assert thread B sees `EgressViolation` *while* thread A's fixture is still active (join thread B before the fixture's post-`yield` reset).
- [ ] AC-9 — **No env-var escape.** AST source-scan asserts `egress_guard.py` does not reference `os.environ`, `os.getenv`, or any `CODEGENIE_*` string. Adversarial test sets `CODEGENIE_TEST_ALLOW_LOOPBACK=1` and verifies loopback is still rejected without the fixture.
- [ ] AC-10 — **No boolean parameter.** `EgressGuard.install()` takes **zero arguments**. `pinned_to(host)` takes exactly the one positional host string. Signature is type-checked at `mypy --strict`.

### `pinned_to` context manager

- [ ] AC-11 — `async with EgressGuard.pinned_to("api.anthropic.com:443")` enters and exits cleanly; calling `socket.create_connection(("api.anthropic.com", 443))` succeeds inside the block and remains permitted outside (because it's in the base allowlist).
- [ ] AC-12 — `pinned_to("other.example.com:443")` raises `EgressViolation` at *enter* (not inside the body); the body never runs.
- [ ] AC-13 — Implementation note: `pinned_to` may be a no-op for Phase 4 (one allowlisted host); it exists for `LeafLlm` adapters to *explicitly* assert they're talking to the right host. Document the rationale in the docstring.

### `reset_for_test()` + fixture

- [ ] AC-14 — `EgressGuard.reset_for_test()` resets the `_test_only_loopback_enabled` `ContextVar` to `False` (in the current context) and is the only sanctioned cleanup path. It does **not** un-install the wrapper. Tests that touch the flag MUST call it explicitly in their teardown (or use the `egress_test_loopback` fixture which calls it on `yield` exit).
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

- [ ] AC-16 — `tests/adv/phase04/test_egress_guard.py` **drives real HTTP-client code paths** down to `socket.create_connection` for each parametrized forbidden host and asserts `EgressViolation` is what stops the connection. Concretely: (a) a direct `socket.create_connection((host, port))` call; (b) a `requests.get(...)`/`urllib3` request; (c) an `httpx` request. For (b)/(c) the library wraps the failure in its own connection-error type — the test asserts `EgressViolation` is the `__cause__`/`__context__` of the raised library error (or is raised directly). **Do not** monkeypatch the libraries' high-level `send`/transport to a no-op — that would bypass the socket layer and the test would assert nothing. Parametrized forbidden hosts: `evil.example.com`, `10.0.0.1`, `127.0.0.1` (no fixture), `::1` (no fixture), `localhost` (no fixture), a bare-IP literal (`1.1.1.1`), and an IDN/punycode string (`xn--api-1ub.anthropic.com`). Every case must produce an `EgressViolation`.
- [ ] AC-17 — `tests/adv/phase04/test_egress_guard_thread_isolation.py` — two threads; thread A sets fixture, thread B attempts loopback → `EgressViolation`. Phase-9 inherits this assertion.
- [ ] AC-18 — `tests/adv/phase04/test_egress_guard_no_sdk_bypass.py` — installs the wrapper; imports `anthropic` and constructs an `AsyncAnthropic` client; attempts to call `client.messages.create(...)` against a fake non-Anthropic host (monkeypatch the SDK base URL) → `EgressViolation`. Proves the SDK's `httpx` transport does **not** bypass the wrapper. Note: this test imports `anthropic`, which S3-02 added to `pyproject.toml` and which S1-05's path-scoped fence permits — a `tests/` file is outside `src/`, so the S1-06 import-linter `src/` contracts do not apply; no fence amendment is needed for the test itself.

### `codegenie self-check egress` CLI

- [ ] AC-19 — `python -m codegenie self-check egress` is a new `@cli.group(name="self-check")` + `@self_check.command(name="egress")` in `cli.py`; prints (a) the active allowlist (`api.anthropic.com:443`); (b) whether `EgressGuard` is `installed=True` (read the module-level `_installed` flag — do **not** call `install()`); (c) the OS-level posture — on Linux, whether the `iptables`/`nftables` binaries are *present on `PATH`* via `shutil.which` (presence only; reporting whether *rules are configured* would need root and is explicitly out of scope), on Darwin a one-line "macOS dev — OS filter not configured by default" message; (d) exits 0 always (a *reporting* command, not a gate). The command never opens a socket and never runs `iptables`/`nftables` as a subprocess. Tested with `pytest`'s `capsys` capture.
- [ ] AC-20 — The CLI subcommand **does not** set or unset the test-only flag (production tooling has no escape). Test: invoke the subcommand; afterward, `_test_only_loopback_enabled` is unchanged.

### Cross-cutting

- [ ] AC-21 — `mypy --strict src/codegenie/fallback/leaf/egress_guard.py` clean. `ruff check`, `ruff format --check` clean.
- [ ] AC-22 — `pre-commit run --all-files` passes (in particular, the `forbidden-patterns` hook should not complain — we are not using `subprocess.run(..., shell=True)`, `eval`, or `__import__`).
- [ ] AC-23 — TDD red test exists, was demonstrably failing before implementation, now green.

### Validation-added criteria

- [ ] AC-24 — **`EgressGuard` satisfies S3-02's `EgressGuardPort` Protocol.** Hardened S3-02 declares a local `EgressGuardPort(Protocol)` requiring `pinned_to(host: str) -> AsyncContextManager[None]` and injects it into `AnthropicLeafAdapter`. Because `EgressGuard` is an all-classmethod class (process-global state, never instantiated), the **class object itself** is the port. A test in `tests/adv/phase04/` (or `tests/fence/`) asserts assignability — a subprocess-`mypy --strict` snippet that does `guard: EgressGuardPort = EgressGuard` (importing `EgressGuardPort` from `codegenie.fallback.leaf.anthropic_adapter`) must type-check clean. This proves the S3-02 → S3-03 contract holds; without it the two stories can silently diverge on the `async`/signature shape.
- [ ] AC-25 — **The full existing test suite stays green with `sitecustomize.py` present.** Once `sitecustomize.py` is committed, every `pytest` and `python -m codegenie` invocation installs the guard process-wide. The executor MUST run the whole suite (`make test`), not just the new files. Any pre-existing test that legitimately needs loopback is updated to request the `egress_test_loopback` fixture. If any pre-existing test dials a *non-loopback, non-Anthropic* host, that is a latent issue the executor surfaces loudly (Rule 12) rather than silently widening the allowlist.
- [ ] AC-26 — **`sitecustomize.py` auto-discovery is verified, not assumed.** A subprocess test (`tests/adv/phase04/test_egress_guard_sitecustomize.py`) launches a *fresh* interpreter from the repo root — `subprocess.run([sys.executable, "-m", "codegenie", "self-check", "egress"], cwd=<repo root>, ...)` — **without** any explicit `EgressGuard.install()` — and asserts stdout reports `installed=True`. This is the **only** test that exercises the `sitecustomize.py`-at-repo-root mechanism; every other test calls `install()` explicitly and would pass even if auto-discovery silently failed. If the subprocess reports `installed=False`, the repo-root `sitecustomize.py` is not being picked up by this project's hatchling editable install — the executor must surface this as a blocker and evaluate an alternative bootstrap (an executable `.pth` line, or installing from `codegenie/__init__.py`) before the story can be GREEN. Do not paper over a failing AC-26.
- [ ] AC-27 — **The allowlist decision is a pure function.** `_is_admitted(host: str, port: int, *, loopback_enabled: bool) -> bool` is a module-level pure helper (no I/O, no `ContextVar` read inside it — `loopback_enabled` is passed in by the imperative wrapper). It is unit-tested directly with a table-driven parametrization covering: the base host, a forbidden host, each loopback form with `loopback_enabled` both `True` and `False`, and the IDN string. This is the functional core; the `socket.create_connection` wrapper is the thin imperative shell that reads the `ContextVar` and delegates.
- [ ] AC-28 — **Malformed `pinned_to` argument raises `ValueError` at enter.** `pinned_to` takes a `"host:port"` string; a string with no `:`, a non-integer port, or an empty host raises `ValueError` (not `EgressViolation`) inside `__aenter__`, before the body runs. `EgressViolation` is reserved for *well-formed but not-allowlisted* hosts (AC-12). A test parametrizes at least `"no-colon"`, `"host:notaport"`, and `":443"`.
- [ ] AC-29 — **Adversarial tests are registered and CI-gating.** The `tests/adv/phase04/` egress tests carry a `phase04_adv` marker, registered in `pyproject.toml` `[tool.pytest.ini_options].markers` exactly as `phase02_adv` is (one-line description, CI-gating). If a `phase04_adv` marker was already established by an earlier phase-4 story, reuse it rather than adding a duplicate.

## Implementation outline

1. Create `src/codegenie/fallback/leaf/egress_guard.py`:
   - Module-level `_test_only_loopback_enabled: ContextVar[bool] = ContextVar("_test_only_loopback_enabled", default=False)` (AC-1 — `ContextVar`, decided; not `threading.local()`).
   - Module-level `_installed: bool = False`.
   - Module-level `_BASE_ALLOWLIST: Final[frozenset[tuple[str, int]]] = frozenset({("api.anthropic.com", 443)})` — the extension seam: Phase 7's `cgr.dev` is one added row under an ADR amendment, not a new mechanism.
   - Module-level `_ORIGINAL_CREATE_CONNECTION` — captured once at first `install()` so the wrapper always delegates to the genuine original even if `socket.create_connection` is re-bound later; `__wrapped__` also points here (AC-2).
   - Pure helper `_is_admitted(host: str, port: int, *, loopback_enabled: bool) -> bool` — functional core (AC-27); does no I/O and does not read the `ContextVar`.
   - `class EgressViolation(Exception)` with `host: str`, `port: int` attributes and a clear message.
   - `class EgressGuard` with `install()`, `pinned_to(host: str)` (an **async** context manager — `@contextlib.asynccontextmanager` or an `__aenter__`/`__aexit__` class), `reset_for_test()` classmethods.
   - Private `_wrap_create_connection(original)` — the imperative shell: reads the `ContextVar`, calls `_is_admitted(...)`, raises `EgressViolation` or delegates.
2. Create `sitecustomize.py` at repo root with the `EgressGuard.install()` call (AC-5).
3. Create `tests/conftest.py` (new root conftest) with the `egress_test_loopback` fixture.
4. Add the `self-check` group + `egress` command to `src/codegenie/cli.py` (mirror the `audit`/`audit verify` shape at `cli.py:903`).
5. Author adversarial tests under `tests/adv/phase04/`; register the `phase04_adv` marker in `pyproject.toml` (AC-29).
6. Run the **full** suite (`make test`) to confirm the process-wide install did not break pre-existing tests (AC-25); add `egress_test_loopback` to any pre-existing loopback-using test.
7. Verify `import-linter` (S1-06) has a contract restricting native-extension-using deps; if missing, surface as a follow-up task (S1-06's responsibility; do not block S3-03 if S1-06 already landed it).

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/adv/phase04/test_egress_guard.py
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from codegenie.fallback.leaf.egress_guard import (
    EgressGuard,
    EgressViolation,
    _test_only_loopback_enabled,
)


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
    ("1.1.1.1", 443),
    ("xn--api-1ub.anthropic.com", 443),
])
def test_forbidden_hosts_raise(host, port):
    with pytest.raises(EgressViolation) as exc:
        socket.create_connection((host, port))
    assert exc.value.host == host


def test_loopback_admitted_when_fixture_set(egress_test_loopback):
    # Real fall-through: bind a throwaway listener, prove a genuine connection.
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    try:
        conn = socket.create_connection(("127.0.0.1", port))  # no EgressViolation
        conn.close()
    finally:
        listener.close()


def test_loopback_rejected_without_fixture():
    with pytest.raises(EgressViolation):
        socket.create_connection(("127.0.0.1", 8080))


def test_thread_isolation(egress_test_loopback):
    # main thread has the fixture; a fresh thread runs in an empty Context →
    # the ContextVar reverts to default=False → worker is blocked.
    results: list[str] = []

    def worker() -> None:
        try:
            socket.create_connection(("127.0.0.1", 8080))
            results.append("admitted")
        except EgressViolation:
            results.append("blocked")

    t = threading.Thread(target=worker)
    t.start()
    t.join()  # join BEFORE the fixture resets, so the assertion is meaningful
    assert results == ["blocked"]


def test_no_env_var_escape(monkeypatch):
    monkeypatch.setenv("CODEGENIE_TEST_ALLOW_LOOPBACK", "1")
    with pytest.raises(EgressViolation):
        socket.create_connection(("127.0.0.1", 8080))


async def test_pinned_to_other_host_raises():
    # pinned_to is an ASYNC context manager (S3-02's EgressGuardPort contract);
    # a well-formed but non-allowlisted host raises EgressViolation at __aenter__.
    with pytest.raises(EgressViolation):
        async with EgressGuard.pinned_to("other.example.com:443"):
            pytest.fail("body must not run")


@pytest.mark.parametrize("bad", ["no-colon", "host:notaport", ":443"])
async def test_pinned_to_malformed_raises_value_error(bad):
    with pytest.raises(ValueError):
        async with EgressGuard.pinned_to(bad):
            pytest.fail("body must not run")


def test_self_check_egress_does_not_set_flag(capsys):
    from codegenie.__main__ import main  # main(argv) lives in __main__, not cli
    rc = main(["self-check", "egress"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "api.anthropic.com:443" in out
    assert _test_only_loopback_enabled.get() is False


def test_sitecustomize_auto_installs_in_fresh_interpreter():
    # The ONLY test that proves sitecustomize.py is auto-discovered. A fresh
    # interpreter, no explicit install() — the guard must already be active.
    repo_root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [sys.executable, "-m", "codegenie", "self-check", "egress"],
        cwd=repo_root, capture_output=True, text=True, check=True,
    )
    assert "installed=True" in result.stdout
```

### Green — make it pass

Implement `egress_guard.py` as outlined; wire the CLI; install via `sitecustomize.py`.

### Refactor — clean up

- The pure helper `_is_admitted(host: str, port: int, *, loopback_enabled: bool) -> bool` is now a green-path requirement (AC-27), not an optional refactor — write it functional-core-first and unit-test it directly.
- Only add a module-level `_WARNING_IDS: Final[frozenset[str]]` catalog **if** `egress_guard.py` actually emits structured `structlog` events (e.g. `egress.installed`) — and if so, wire the import-time `raise AssertionError(...)` validation against the `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` shape, exactly as probes do (Phase 1 ADR-0007). Do not ship a `_WARNING_IDS` catalog that nothing references — `EgressViolation` is a raised exception, not a warning ID. (`egress_guard.py` is not a probe; the catalog convention is only worth honoring if the module genuinely emits those event IDs.)
- Document the IDN/punycode normalization stance: the wrapper compares `host` against the allowlist *literally* — a caller passing `xn--api-1ub.anthropic.com` is rejected. The SDK never does this (it uses the configured base URL).

## Files to touch

| Path | Create / Modify | Why |
|---|---|---|
| `src/codegenie/fallback/leaf/egress_guard.py` | Create | The wrapper module (this story's primary deliverable). |
| `sitecustomize.py` | Create | Process-wide install at interpreter start (PEP 370 / `site.py`). |
| `src/codegenie/cli.py` | Modify | Add the `self-check` group + `egress` command. |
| `tests/conftest.py` | Create | New root conftest exposing the `egress_test_loopback` fixture. |
| `pyproject.toml` | Modify | Register the `phase04_adv` pytest marker (mirror `phase02_adv`); confirm `anthropic` is present (S3-02 adds it). |
| `tests/adv/phase04/test_egress_guard.py` | Create | Forbidden hosts; loopback policy; `pinned_to`; CLI side-effect-free check; `sitecustomize` autoload. |
| `tests/adv/phase04/test_egress_guard_thread_isolation.py` | Create | Thread-scoped `ContextVar` isolation. |
| `tests/adv/phase04/test_egress_guard_no_sdk_bypass.py` | Create | Anthropic SDK does not bypass via `httpx`. |
| `tests/adv/phase04/test_egress_guard_sitecustomize.py` | Create | Subprocess autoload proof (AC-26) — may instead live in `test_egress_guard.py`; one file is fine. |
| `docs/contributing.md` | Modify | (Append) One-paragraph note on when to use `egress_test_loopback`. |

## Out of scope

- OS-level egress filter (`iptables`/`nftables`) — documented but operator-installed; CLI *reports* posture, does not *enforce*.
- Nightly real-API drift job — ADR-0005 mentions it as defense-in-depth layer 3, but its CI workflow file is Phase-7 / Phase 6.5 territory.
- C-extension `connect(2)` bypass — known residual; mitigated by `import-linter` restriction on native-extension deps in S1-06.
- Adding a second host (Phase 7 distroless plugin's `cgr.dev`) — additive ADR amendment then, not here.
- Moving the `EgressGuard` install off interpreter-import-time into an explicit `bootstrap_runtime()` — recorded as a Phase-5+ follow-up in `phase-arch-design.md §gap-analysis #2`. This story keeps the acknowledged `sitecustomize.py` residual; it does not redesign the bootstrap (unless AC-26 proves the current mechanism does not work at all — see Notes).
- Wheel-install coverage — a repo-root `sitecustomize.py` is not packaged into the hatchling wheel; it is a dev/POC mechanism. The production-service (Phase 9) bootstrap is part of the `bootstrap_runtime()` follow-up above.

## Notes for the implementer

- **Verify, do not assume, the `sitecustomize.py` mechanism.** `site.py` imports `sitecustomize` at interpreter start by scanning `sys.path` *as it stands then*. This project is a hatchling `src/`-layout editable install — the editable shim puts `src/` (not the repo root) on `sys.path`, and pytest's `pythonpath = ["."]` is applied *after* `site.py` has already run, so it does not help. Whether a repo-root `sitecustomize.py` is discovered therefore depends on the invocation (`python -m codegenie` run from the repo root adds cwd to `sys.path[0]`, which usually works; a console-script entry point may not). AC-26's subprocess test is the empirical check — treat its result as ground truth. If it fails, do not delete the AC: switch to a robust bootstrap (an executable `.pth` line installed into site-packages, or calling `EgressGuard.install()` from `codegenie/__init__.py`) and update AC-5 accordingly. The `try/except ImportError` swallow in `sitecustomize.py` only covers "codegenie not importable at all"; an `EgressViolation` or any other error during `install()` must still propagate.
- **`EgressGuard` must satisfy S3-02's `EgressGuardPort`.** S3-02 (hardened) declares a local `EgressGuardPort(Protocol)` with `pinned_to(host: str) -> AsyncContextManager[None]` and injects it into `AnthropicLeafAdapter`. `EgressGuard` is an all-classmethod class — there is no instance — so the adapter is wired with the **class object itself** as the port (`AnthropicLeafAdapter(..., egress_guard=EgressGuard)`). `mypy --strict` accepts `type[EgressGuard]` against the Protocol because the classmethods are accessible on the class. AC-24 locks this. Keep `pinned_to`'s signature byte-identical to the port: one positional `host: str`, returns an async context manager.
- `socket.create_connection` is the only function we wrap. `socket.socket(...).connect(...)` is the lower-level path that some C extensions may use; `httpx` and `requests` ultimately funnel through `create_connection`, but raw `socket.socket(...).connect()` bypasses us. Document this clearly in the module docstring — the threat-model claim is "catches typical Python `http`/`urllib3`/`httpx` paths"; the C-extension residual is ADR-0005's accepted compromise.
- The flag is a `contextvars.ContextVar` (decided — AC-1). `ContextVar` gives both properties this story needs: it propagates across `await` boundaries within one thread (Phase-4 adapter calls are `async`), *and* a freshly-started `threading.Thread` runs in an empty `Context` so the value does not leak across threads (the AC-8 isolation guarantee, with no extra code). `threading.local()` was rejected because AC-15's fixture and the TDD plan use the `.set()`/`.get()` API and because it would not propagate across `await`. Phase 9's Temporal workers inherit this `ContextVar` posture; if a Phase-9 review shows a different requirement, that is a Phase-9 ADR amendment, not a Phase-4 hedge.
- The `pinned_to(host)` method intentionally takes a `"host:port"` string rather than a `(host, port)` tuple so adapter call sites read like the URLs they protect — `pinned_to("api.anthropic.com:443")`. Parse the string in the implementation, reject malformed inputs with `ValueError` at *enter*.
- `EgressGuard.install()` must run **before** any module imports a network library at module-import time. `sitecustomize.py` is the earliest hook short of the C startup. If any test imports `requests`/`httpx` at module top-level, the install must already be done — which it will be, because `sitecustomize.py` runs before any user code.
- The `codegenie self-check egress` CLI **must not** invoke `socket.create_connection` against `api.anthropic.com` (that would spend bandwidth and surface a false "TLS error" when offline). It is a *reporting* command — just print the static allowlist and the install state.
