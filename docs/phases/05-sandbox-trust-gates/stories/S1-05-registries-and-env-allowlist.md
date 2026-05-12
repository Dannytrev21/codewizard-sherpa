# Story S1-05 — Decorator registries + `env_allowlist` static filter

**Step:** Step 1 — Scaffold packages, contracts, and CI fences
**Status:** Ready
**Effort:** S
**Depends on:** S1-02, S1-03, S1-04
**ADRs honored:** ADR-0012, ADR-0003, ADR-0006

## Context

Phase 5 is "extension by addition": Phase 7 distroless adds new sandbox backends and signal kinds without editing existing files. This story ships the two decorator registries that make that possible (`@register_sandbox_backend`, `@register_signal_kind`) plus the `env_allowlist.filter()` function that ADR-0012 makes the *only* path from host env to `SandboxSpec.env`. The credential-leakage defense lives in code from this story forward; the structural fence test that exercises it lives in S1-07.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — SandboxClient (Protocol)` — registry exposes `get_backend(name)` and `auto_detect()`; `SandboxBackendInvalid` raised on Protocol violation at import.
  - `../phase-arch-design.md §Component design — Signal collectors` — `@register_signal_kind("name")` decorator on each collector function.
  - `../phase-arch-design.md §Component design — SandboxSpecBuilder` — calls `env_allowlist.filter(env)` before constructing `SandboxSpec.env`; `SandboxSpecForbidden` on a denied substring.
  - `../phase-arch-design.md §CI gates — test_env_allowlist_no_credentials.py` — asserts denied substrings (`KEY`, `TOKEN`, `SECRET`, `PASSWORD`) cannot pass even if added to the allowlist.
  - `../phase-arch-design.md §Open questions §10` — `SignalKind` registry collision policy: raise `SignalKindAlreadyRegistered` at import.
- **Phase ADRs (rules this story honors):**
  - `../ADRs/0012-static-env-allowlist-no-credentials-in-sandbox.md` — ADR-0012 — allowlist is `["PATH", "NODE_ENV", "NPM_CONFIG_*", "HTTPS_PROXY"]`; denied substrings are belt-and-suspenders.
  - `../ADRs/0003-trustscorer-extension-via-signal-kind-registry.md` — ADR-0003 — open string registry; collision raises `SignalKindAlreadyRegistered`.
  - `../ADRs/0006-protocol-vs-abc-convention.md` — ADR-0006 — backend registration validates against `SandboxClient` Protocol via `isinstance` (`runtime_checkable`).
- **Source design:**
  - `../final-design.md §Synthesis ledger — Env into sandbox row`.
- **High-level impl:**
  - `../High-level-impl.md §Step 1 — Features delivered` bullets 5 + 6.

## Goal

Ship `src/codegenie/sandbox/registry.py`, `src/codegenie/sandbox/signals/registry.py`, and `src/codegenie/sandbox/env_allowlist.py` with the decorator registries, collision policy, and the credential-filter function.

## Acceptance criteria

- [ ] `@register_sandbox_backend("dind")` decorating a class returns the class unchanged, registers it under that name, and `get_backend("dind")()` returns an instance; registering a class missing `execute`/`health` raises `SandboxBackendInvalid` at decoration time.
- [ ] Re-registering the same backend name raises `SandboxBackendInvalid` ("name already registered").
- [ ] `auto_detect()` exists with signature `() -> SandboxClient`; it returns *some* registered backend (the real KVM-vs-DiD logic is S6-04 — here it just calls `get_backend("docker_in_docker")` as a safe default and logs an INFO).
- [ ] `@register_signal_kind("build")` decorating a function returns the function unchanged and registers it under the kind; a second call with `"build"` raises `SignalKindAlreadyRegistered`; `get_signal_collector("build")` returns the function.
- [ ] `env_allowlist.filter(env)` returns a new dict containing only keys that match the allowlist patterns (literal match or `NPM_CONFIG_*` prefix). Keys whose names contain `KEY`, `TOKEN`, `SECRET`, or `PASSWORD` (case-insensitive substring) are always dropped, even if they match the allowlist.
- [ ] `env_allowlist.ALLOWLIST` and `env_allowlist.DENY_SUBSTRINGS` are exposed as module-level `Final` tuples (importable for the S1-07 fence test).
- [ ] `env_allowlist.filter` does NOT raise on a denied substring; it silently drops the key. (The `SandboxSpecForbidden` raise lives in `SandboxSpecBuilder` — S3-01.)
- [ ] TDD plan's red tests exist, are committed, and are green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/sandbox/registry.py src/codegenie/sandbox/signals/registry.py src/codegenie/sandbox/env_allowlist.py`, `pytest tests/sandbox/test_registry.py tests/sandbox/test_signal_registry.py tests/sandbox/test_env_allowlist.py` all pass.

## Implementation outline

1. Create `src/codegenie/sandbox/registry.py`. Module-level `_BACKENDS: dict[str, type[SandboxClient]] = {}`. Decorator `register_sandbox_backend(name: str)` returns a decorator that: (a) checks `isinstance(_dummy_instance, SandboxClient)` via `runtime_checkable` (instantiate without args is impossible — instead check method presence: `hasattr(cls, "execute") and hasattr(cls, "health")` and verify signatures); (b) raises `SandboxBackendInvalid` if name already in `_BACKENDS`; (c) records `_BACKENDS[name] = cls`. Add `get_backend(name) -> SandboxClient` (instantiates and returns).
2. Add `auto_detect() -> SandboxClient` returning `get_backend("docker_in_docker")` with a logger INFO. Note the real platform-detection logic is S6-04.
3. Create `src/codegenie/sandbox/signals/registry.py`. Module-level `_COLLECTORS: dict[str, Callable] = {}`. Decorator `register_signal_kind(kind: str)` returns a decorator that records the function or raises `SignalKindAlreadyRegistered`. Add `get_signal_collector(kind: str) -> Callable`.
4. Create `src/codegenie/sandbox/env_allowlist.py`. Constants `ALLOWLIST: Final = ("PATH", "NODE_ENV", "HTTPS_PROXY")` and the prefix `"NPM_CONFIG_"`. `DENY_SUBSTRINGS: Final = ("KEY", "TOKEN", "SECRET", "PASSWORD")`. `def filter(env: Mapping[str, str]) -> dict[str, str]:` returns a new dict; iterate `env.items()`; include `k` iff (a) it matches a literal allowlist entry or starts with `NPM_CONFIG_`; (b) `not any(deny.lower() in k.lower() for deny in DENY_SUBSTRINGS)`.
5. Write three test files.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/sandbox/test_registry.py
import pytest
from codegenie.sandbox.registry import (
    register_sandbox_backend, get_backend, auto_detect,
)
from codegenie.sandbox.errors import SandboxBackendInvalid
from codegenie.sandbox.contract import SandboxClient, SandboxSpec, SandboxRun, SandboxHealth

@pytest.fixture(autouse=True)
def _clean_registry():
    from codegenie.sandbox import registry
    snapshot = dict(registry._BACKENDS)
    registry._BACKENDS.clear()
    yield
    registry._BACKENDS.clear()
    registry._BACKENDS.update(snapshot)

def _good_backend():
    @register_sandbox_backend("test_be")
    class _B:
        def execute(self, spec): ...
        def health(self): ...
    return _B

def test_registers_compliant_backend_and_returns_instance():
    _good_backend()
    inst = get_backend("test_be")
    assert isinstance(inst, SandboxClient)

def test_rejects_partial_backend_at_decoration():
    with pytest.raises(SandboxBackendInvalid):
        @register_sandbox_backend("partial")
        class _Bad:
            def execute(self, spec): ...
            # no health()
        return _Bad

def test_duplicate_name_raises():
    _good_backend()
    with pytest.raises(SandboxBackendInvalid):
        @register_sandbox_backend("test_be")
        class _Dup:
            def execute(self, spec): ...
            def health(self): ...

def test_auto_detect_returns_a_registered_backend():
    @register_sandbox_backend("docker_in_docker")
    class _D:
        def execute(self, spec): ...
        def health(self): ...
    inst = auto_detect()
    assert isinstance(inst, SandboxClient)
```

```python
# tests/sandbox/test_signal_registry.py
import pytest
from codegenie.sandbox.signals.registry import register_signal_kind, get_signal_collector
from codegenie.sandbox.errors import SignalKindAlreadyRegistered

@pytest.fixture(autouse=True)
def _clean():
    from codegenie.sandbox.signals import registry
    snap = dict(registry._COLLECTORS)
    registry._COLLECTORS.clear()
    yield
    registry._COLLECTORS.clear()
    registry._COLLECTORS.update(snap)

def test_register_and_retrieve_signal_collector():
    @register_signal_kind("build")
    def collect_build(run):
        return "build-signal"
    assert get_signal_collector("build")(None) == "build-signal"

def test_duplicate_kind_raises_signal_kind_already_registered():
    @register_signal_kind("install")
    def a(run): pass
    with pytest.raises(SignalKindAlreadyRegistered):
        @register_signal_kind("install")
        def b(run): pass
```

```python
# tests/sandbox/test_env_allowlist.py
import pytest
from codegenie.sandbox.env_allowlist import filter as env_filter, ALLOWLIST, DENY_SUBSTRINGS

def test_passes_allowlisted_keys():
    out = env_filter({"PATH": "/usr/bin", "NODE_ENV": "test"})
    assert out == {"PATH": "/usr/bin", "NODE_ENV": "test"}

def test_passes_npm_config_prefix():
    out = env_filter({"NPM_CONFIG_LOGLEVEL": "warn", "NPM_CONFIG_CACHE": "/tmp"})
    assert out == {"NPM_CONFIG_LOGLEVEL": "warn", "NPM_CONFIG_CACHE": "/tmp"}

def test_drops_unlisted_keys():
    out = env_filter({"FOO": "bar"})
    assert out == {}

@pytest.mark.parametrize("k", [
    "ANTHROPIC_API_KEY", "GITHUB_TOKEN", "DB_SECRET", "REGISTRY_PASSWORD",
    "MY_PATH_KEY",  # contains KEY substring even though PATH allowlisted
])
def test_drops_denied_substrings_even_if_otherwise_allowlisted(k):
    # Worst-case: an operator accidentally adds a key with a denied substring
    out = env_filter({k: "secret-value", "PATH": "/usr/bin"})
    assert k not in out
    assert out == {"PATH": "/usr/bin"}

def test_filter_is_case_insensitive_on_deny_substrings():
    out = env_filter({"MyApiKey": "x", "PATH": "/usr/bin"})
    assert "MyApiKey" not in out

def test_filter_returns_new_dict_not_mutating_input():
    env = {"PATH": "/usr/bin", "GITHUB_TOKEN": "abc"}
    snapshot = dict(env)
    env_filter(env)
    assert env == snapshot

def test_allowlist_and_deny_constants_are_tuples():
    assert isinstance(ALLOWLIST, tuple) and isinstance(DENY_SUBSTRINGS, tuple)
```

Run; confirm `ImportError`/`AttributeError`, commit, then implement.

### Green — make it pass

Implement each module minimally. For `register_sandbox_backend`, the Protocol check is structural: validate `hasattr(cls, "execute")` and `hasattr(cls, "health")` and use `inspect.signature` to confirm `execute` takes a `spec` argument; on failure raise `SandboxBackendInvalid`. Do NOT instantiate the class during registration — backends may require real Docker daemons in `__init__`. (The runtime `isinstance(b, SandboxClient)` check happens later, on the instance produced by `get_backend`.)

For `env_allowlist.filter`, write the predicate as two functions: `_is_allowed(k)` and `_is_denied(k)`. Apply `not _is_denied(k) and _is_allowed(k)` — the `not denied` check goes first as a fail-loud short circuit (matches ADR-0012's belt-and-suspenders rationale).

### Refactor — clean up

- Add docstrings on each public function (one sentence).
- `auto_detect` should `logging.getLogger(__name__).info("sandbox.auto_detect.fallback", extra={"backend": "docker_in_docker"})` — use the structured event constant from S1-01. The real KVM-vs-DiD branch lives in S6-04.
- Edge case (ADR-0012): the test `MY_PATH_KEY` would be passed by `_is_allowed` (matches `PATH`? — only if you use literal match, not substring; double-check the allowlist semantics is *exact match* or `startswith("NPM_CONFIG_")`. Spec is exact + prefix; document this in the module docstring.)
- Edge case: the registry collision test must execute in module-import order — write `tests/sandbox/test_registry.py` with the autouse fixture so cross-test pollution does not corrupt the `_BACKENDS` dict.
- Logging: every registration emits a structured log line.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/registry.py` | New file — sandbox backend registry per ADR-0003 pattern |
| `src/codegenie/sandbox/signals/registry.py` | New file — signal kind registry per ADR-0003 |
| `src/codegenie/sandbox/env_allowlist.py` | New file — host-env filter per ADR-0012 |
| `tests/sandbox/test_registry.py` | New test — backend register + collision + auto_detect |
| `tests/sandbox/test_signal_registry.py` | New test — signal kind register + collision |
| `tests/sandbox/test_env_allowlist.py` | New test — allowlist + deny substrings + case-insensitivity + non-mutation |

## Out of scope

- **Real `auto_detect` (KVM check)** — S6-04.
- **`SandboxSpecBuilder.for_gate`** — S3-01 (consumes `env_allowlist.filter`).
- **Six concrete signal collectors** — Step 4 (register via the decorator landed here).
- **Phase 3 `@register_trust_signal_kind` widening** — S4-04 (separate registry, separate decorator).
- **The structural CI fence `tests/schema/test_env_allowlist_no_credentials.py`** — S1-07 (depends on the function landed here).

## Notes for the implementer

- The registry's `isinstance(b, SandboxClient)` check happens at `get_backend` (post-instantiation) not at `@register_sandbox_backend` (which only validates structurally on the class). Some backends (`FirecrackerClient`) require digests to instantiate; you cannot construct them at decoration time. Document this in the module docstring.
- `_BACKENDS` and `_COLLECTORS` are module-level globals. Tests rely on snapshot/restore fixtures (see the autouse fixture in the red tests). Do NOT make them per-process singletons via a class — Phase 7 needs to add backends at import time and `pytest` collection re-imports modules.
- Substring matching for denied env-var names is **case-insensitive**. `MyApiKey` must be filtered. Use `k.upper()` (or `.lower()`) on both sides before `in`.
- The `_is_allowed` predicate should treat `NPM_CONFIG_` as a prefix — `k.startswith("NPM_CONFIG_")`. Document the allowlist semantics with a single sentence in the module docstring.
- Never instantiate the class during `register_sandbox_backend`. ADR-0012's allowlist runs at `for_gate` time (story S3-01), not at backend registration.
- The 90/80 coverage floor applies here. Write parametrized tests for every allowlist edge: pure allowlist hit, prefix match, prefix+denied substring, mixed-case denied, denied-but-allowed-name (`MY_PATH_KEY` shape).
