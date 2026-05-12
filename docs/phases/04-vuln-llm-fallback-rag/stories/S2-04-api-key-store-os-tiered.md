# Story S2-04 — `ApiKeyStore` OS-tiered + `audit.warning(api_key.env_present)`

**Step:** Step 2 — Ship the deterministic LLM-side primitives — `OutputValidator`, `PromptLoader` + YAML prompts, `LlmInvocationGuard`, `ApiKeyStore`
**Status:** Ready
**Effort:** M
**Depends on:** S1-01
**ADRs honored:** ADR-P4-013, ADR-P4-004

## Context

The `ANTHROPIC_API_KEY` env-var default leaks the key through every shell history, `ps -E`, crash dump, and CI log. Per ADR-P4-013 the store reads platform-tiered locations (macOS Keychain; Linux secret-service / mode-600 file) and refuses env-vars with OS-tiered strictness — **warn on macOS, hard-refuse on Linux**. The asymmetry is intentional dev-ergonomics-vs-production-realism. The key never enters: prompt body, log line (only `blake3(key)[:8]` fingerprint), audit body, cassette, or cache. `read()` is callable only from `codegenie.llm.leaf_anthropic.*` — enforced by a runtime call-stack frame check in Step 3 and by fence-CI at import-graph level.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #10 "ApiKeyStore"` — public interface, the macOS Keychain command, the Linux preference order (secretstorage → mode-600 file), the hard-refuse Linux env-var rule, the `blake3(key)[:8]` fingerprint discipline.
  - `../phase-arch-design.md §"Edge cases"` row 1 — `ANTHROPIC_API_KEY` missing → `available()=False` → clean exit 4. Row 18 — bare env on Linux hard-refuses at orchestrator start.
- **Phase ADRs:**
  - `../ADRs/0013-api-key-store-env-var-refused.md` — ADR-P4-013 — Mac warn vs Linux refuse; `secret-service` preferred on Linux with mode-600 fallback; fence-CI scans test output for the fingerprint pattern.
  - `../ADRs/0004-leaf-llm-agent-protocol-os-tiered.md` — ADR-P4-004 — key is loaded only into the `AnthropicClient` process; orchestrator address space never holds the bytes (Phase 5's microVM tightens this further); on macOS `InProcessLeafLlmAgent` *is* the orchestrator process — boundary is logical not enforced.
- **Production ADRs:** none directly; `production/design.md §"Secrets"` (background) — secret-handling discipline as data, not prompts.
- **Source design:** `../final-design.md §"Components" #11 "ApiKeyStore"`; `../final-design.md §"Synthesis ledger" row "API-key handling"`.
- **Existing code:**
  - `src/codegenie/errors.py` (from S1-01) — `ApiKeyMissing` / `ApiKeyEnvRefused` if registered in S1-01; verify the exact names. If not present, add under a `# Phase 4 — additive (S2-04)` block.
  - `src/codegenie/logging.py` (from S1-01) — `API_KEY_ENV_PRESENT` audit event constant; `FIELD_KEY_FINGERPRINT` structured field; verify present.

## Goal

Land `src/codegenie/llm/secrets/key_store.py` exposing `ApiKeyStore(platform: Literal["mac","linux"])` with `available() -> bool` and `read() -> str`; on macOS read from Keychain via `security find-generic-password -s codegenie-anthropic`, warn (not refuse) on bare env; on Linux read from `secretstorage` (preferred) or a mode-600 file at `~/.codegenie/secrets/anthropic-api-key` (owner/group/perm verified), and **hard refuse to start** with an explicit error when `ANTHROPIC_API_KEY` is set in the orchestrator env.

## Acceptance criteria

- [ ] `src/codegenie/llm/secrets/key_store.py` exports `ApiKeyStore(platform: Literal["mac","linux"])` with `available() -> bool` and `read() -> str`. Both methods are `mypy --strict` clean.
- [ ] `ApiKeyStore.__init__` does **not** call `read()`; lookups are lazy. Constructor stores the platform constant and probes for the storage backend (`shutil.which("security")` on Mac; `secretstorage` import attempt on Linux).
- [ ] **macOS path:** `available()` returns `True` if either (a) `ANTHROPIC_API_KEY` is in env, or (b) Keychain `security find-generic-password -s codegenie-anthropic -w` exits 0. `read()` prefers Keychain over env; if env is present, emit `audit.warning(API_KEY_ENV_PRESENT)` exactly once per process lifetime with structured fields `(platform="mac", fingerprint=blake3(key)[:8])` — the env-var works (dev ergonomics) but is logged.
- [ ] **Linux path:** `__init__` itself checks `os.environ.get("ANTHROPIC_API_KEY")` and raises `ApiKeyEnvRefused(platform="linux", remediation="codegenie auth set-anthropic-key")` immediately — orchestrator startup fails before any LLM work; CLI catches and exits with the documented non-zero code.
- [ ] **Linux key sources:** `available()` and `read()` try `secretstorage` first (lookup item by attributes `{"service": "codegenie-anthropic"}`), then fall back to `~/.codegenie/secrets/anthropic-api-key`. The file path is rejected unless: file exists, owner == process UID, group is in process group set, mode is exactly `0o600` (checked via `stat.S_IMODE(st_mode) == 0o600`). Mismatched owner/group/perm raises `ApiKeyFilePermissionInvalid(path, actual_mode_octal, actual_owner)`.
- [ ] `read()` is implemented as a **single source of truth**: subsequent calls return the cached bytes for the process lifetime (matches `phase-arch-design.md §"Component design" #10` "cached for process lifetime by LeafLlmAgent"). No re-read on each invocation.
- [ ] `read()` **must not** appear in any log line; only `_log_key_fingerprint(key)` (private helper) which logs `blake3(key)[:8]` via `logging.FIELD_KEY_FINGERPRINT`. A grep test (`tests/security/test_no_api_key_in_logs.py`) scans every captured log fixture under `tests/_log_fixtures/` and asserts the API-key fingerprint pattern (`r"sk-ant-[A-Za-z0-9_-]{40,}"`) is absent.
- [ ] Caller restriction: `read()` inspects the call stack (`inspect.stack()` first non-self frame) and raises `ApiKeyCallerForbidden(actual_caller_module)` unless the caller module name starts with `codegenie.llm.leaf_anthropic.` or is the test harness (allow `tests.*`). Document the relaxation for tests in the docstring.
- [ ] `tests/unit/llm/test_api_key_store_macos_keychain.py` covers: Keychain read (mock `subprocess.run` for `security find-generic-password`), bare env emits `API_KEY_ENV_PRESENT` exactly once, both-paths-present prefers Keychain.
- [ ] `tests/unit/llm/test_api_key_store_linux_strict.py` covers: bare env on Linux → `ApiKeyEnvRefused` at `__init__` (not at `read()`); mode-600 file with wrong owner rejected; mode-660 file rejected; `secretstorage` preferred over file fallback when both present.
- [ ] `tests/security/test_no_api_key_in_logs.py` scans every log fixture captured under `tests/_log_fixtures/api_key/` (the test plants two log lines — one with a fake but realistic `sk-ant-XXXX...` and one with `blake3(...)[:8]` — and asserts the first variant is absent from every other Step-2 fixture).
- [ ] `tests/unit/llm/test_api_key_store_caller_restriction.py` — calling `read()` from a `tests.unit.*` test module passes (test harness allowance); calling it from a stub module `tests.unit.fake_callers.unauthorized_caller` raises `ApiKeyCallerForbidden`.
- [ ] TDD red test exists, committed on a tagged commit, and the green commit brings it green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Verify which of `ApiKeyEnvRefused`, `ApiKeyFilePermissionInvalid`, `ApiKeyCallerForbidden`, `ApiKeyMissing` are already in `src/codegenie/errors.py` from S1-01. Add any missing under a `# Phase 4 — additive (S2-04)` append-only block.
2. Verify `API_KEY_ENV_PRESENT` and `FIELD_KEY_FINGERPRINT` exist in `src/codegenie/logging.py` from S1-01. Add if missing.
3. Write tests first (red) — start with `test_api_key_store_macos_keychain.py`, `test_api_key_store_linux_strict.py`, `test_no_api_key_in_logs.py`.
4. Implement `ApiKeyStore.__init__` — on Linux, the env-var check is the first statement; if present, raise `ApiKeyEnvRefused`. On Mac, store the env presence as `self._env_warning_pending: bool` to emit on first `read()`.
5. Implement `_read_keychain_mac() -> str | None` — `subprocess.run(["security", "find-generic-password", "-s", "codegenie-anthropic", "-w"], capture_output=True, text=True, check=False, timeout=5)`; returns `stdout.strip()` on exit 0, `None` otherwise.
6. Implement `_read_secretstorage_linux() -> str | None` — `import secretstorage` inside the function (lazy); `dbus = secretstorage.dbus_init()`; `collection = secretstorage.get_any_collection(dbus)`; iterate items, find one with `service == codegenie-anthropic`.
7. Implement `_read_file_linux() -> str` — open the path, `os.fstat` it, check `S_IMODE == 0o600`, owner UID matches process UID, group matches; read; strip newline.
8. Implement `read()` — first call: choose source per platform, validate, cache. Subsequent: return cached. Emit pending env-var warning on first call (Mac).
9. Implement caller restriction via `inspect.stack()[2].frame.f_globals.get("__name__", "")`.
10. Write `tests/_log_fixtures/api_key/` with `golden_with_fingerprint.log` (allowed) and `forbidden_raw_key.log` (the scan must reject if found anywhere outside this fixture). The grep test asserts the pattern is absent from every other Step-2 log fixture.
11. Run `ruff format`, `ruff check`, `mypy --strict`, `pytest`.

## TDD plan — red / green / refactor

### Red

Test file path (representative): `tests/unit/llm/test_api_key_store_linux_strict.py`

```python
# tests/unit/llm/test_api_key_store_linux_strict.py
import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from codegenie.llm.secrets.key_store import ApiKeyStore
from codegenie.errors import ApiKeyEnvRefused, ApiKeyFilePermissionInvalid


def test_bare_env_on_linux_hard_refuses_at_init(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-leaked-into-env")
    with pytest.raises(ApiKeyEnvRefused) as exc_info:
        ApiKeyStore(platform="linux")
    assert "codegenie auth set-anthropic-key" in str(exc_info.value)


def test_mode_600_file_correct_owner_reads(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    secret = tmp_path / "anthropic-api-key"
    secret.write_text("sk-ant-good-key")
    secret.chmod(0o600)
    with patch("codegenie.llm.secrets.key_store._SECRET_FILE_PATH", secret), \
         patch("codegenie.llm.secrets.key_store._read_secretstorage_linux", return_value=None):
        store = ApiKeyStore(platform="linux")
        assert store.available()
        # read() called from a tests.* module — caller restriction allows tests.
        assert store.read() == "sk-ant-good-key"


def test_mode_660_file_rejected(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    secret = tmp_path / "anthropic-api-key"
    secret.write_text("sk-ant-x")
    secret.chmod(0o660)
    with patch("codegenie.llm.secrets.key_store._SECRET_FILE_PATH", secret), \
         patch("codegenie.llm.secrets.key_store._read_secretstorage_linux", return_value=None):
        store = ApiKeyStore(platform="linux")
        with pytest.raises(ApiKeyFilePermissionInvalid):
            store.read()
```

```python
# tests/unit/llm/test_api_key_store_macos_keychain.py
def test_keychain_read_succeeds_and_no_env_warning(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "sk-ant-from-keychain\n"
        store = ApiKeyStore(platform="mac")
        assert store.read() == "sk-ant-from-keychain"
        # No env-present warning was emitted.
        # (Capture via caplog or a logging.LogCapture fixture; assert no record with API_KEY_ENV_PRESENT.)


def test_bare_env_on_mac_warns_but_does_not_refuse(monkeypatch, caplog):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-env")
    store = ApiKeyStore(platform="mac")
    assert store.read() == "sk-ant-from-env"  # works, but…
    # …emitted exactly one API_KEY_ENV_PRESENT record.
    api_key_env_events = [r for r in caplog.records if r.event == "api_key.env_present"]
    assert len(api_key_env_events) == 1
```

Run; all fail because `ApiKeyStore` does not exist. Commit as red.

### Green

Implement `ApiKeyStore` per the outline. Minimum behavior: Linux raises at `__init__` on bare env; Mac warns on first `read()`; file fallback validates mode/owner; caller restriction trips on non-allowed modules.

### Refactor

- Add docstrings naming the ADR clause each branch enforces. The Mac-vs-Linux asymmetry needs an explicit "this is intentional — ADR-P4-013 §Tradeoffs" docstring.
- Add `mypy --strict` types on every helper.
- Add a `_fingerprint(key: str) -> str` helper that returns `blake3(key.encode()).hexdigest()[:8]` — used everywhere the key needs to be referenced in a log.
- Verify the caller-restriction test does *not* relax the rule by accident — the relaxation is `tests.*` only, not `your_test_helper.*`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/llm/secrets/__init__.py` | New — package init (empty) |
| `src/codegenie/llm/secrets/key_store.py` | New — `ApiKeyStore` + private helpers |
| `src/codegenie/errors.py` | Append any of `ApiKeyEnvRefused`, `ApiKeyFilePermissionInvalid`, `ApiKeyCallerForbidden`, `ApiKeyMissing` not already shipped in S1-01 |
| `src/codegenie/logging.py` | Append `API_KEY_ENV_PRESENT` constant and `FIELD_KEY_FINGERPRINT` field constant if not in S1-01 |
| `tests/unit/llm/test_api_key_store_macos_keychain.py` | Keychain read + env warning |
| `tests/unit/llm/test_api_key_store_linux_strict.py` | Env hard-refuse + file perm checks |
| `tests/unit/llm/test_api_key_store_caller_restriction.py` | `inspect.stack` caller-module check |
| `tests/security/test_no_api_key_in_logs.py` | Pattern scan across log fixtures |
| `tests/_log_fixtures/api_key/golden_with_fingerprint.log` | Fixture proving fingerprint shape |
| `tests/_log_fixtures/api_key/forbidden_raw_key.log` | Reference fixture for the regex (only legal place) |

## Out of scope

- **`codegenie auth set-anthropic-key` / `auth status` CLI** — owned by **S2-05**. This story ships the store; the next story exposes the CLI surface.
- **`EgressProxy` daemon process that *also* reads the key** — owned by **S3-04** (Linux only). The proxy reads via the same `ApiKeyStore` at startup and never re-reads.
- **`bwrap` jail that strips env vars before exec** — owned by **S3-05**.
- **Anthropic SDK transport** — owned by **S3-01** (`AnthropicClient`); this story does not import `anthropic`.
- **Key rotation / SPKI pinning** — explicitly deferred to Phase 16 per critique §security.4.
- **`secretstorage` library dep declaration** — list in `pyproject.toml` `[project.optional-dependencies.linux]` so macOS dev installs don't pull the dbus stack. Actual `pyproject.toml` edit is a sibling change tracked here but **must not** break a Mac install.

## Notes for the implementer

- The macOS-vs-Linux asymmetry is **load-bearing on purpose** (ADR-P4-013 §Decision). Don't try to "fix" it by making Mac hard-refuse — the dev-ergonomics-vs-production-realism trade is explicit. Document the warning prominence requirement: it must end up in `remediation-report.yaml` per `phase-arch-design.md §"Edge cases"` row 18 (the report writing is Phase 6 work; this story emits the event with the right shape).
- `inspect.stack()` is the cheapest enforcement. A determined attacker inside the orchestrator process can monkey-patch the check; that is acknowledged as a threat-model concession on macOS (`ADR-P4-004 §Tradeoffs`). On Linux the `bwrap` jail (S3-05) is the structural defense — this check is the documentation-level enforcement.
- The mode-600 check is `stat.S_IMODE(st.st_mode) == 0o600` exactly — not `<= 0o600`. A file with `0o400` is rejected (group/world have no access, but neither does owner-write — likely operator error).
- Cache the key in an instance variable, not a module-level global, so unit tests can construct a fresh store and not see cross-test contamination.
- `audit.warning(api_key.env_present)` event payload (per S1-01 logging fields): `platform`, `key_fingerprint`. Do **not** include the key itself; the regex grep test will fail the build if you do.
- `subprocess.run` for `security find-generic-password` must use `timeout=5` — a hung Keychain prompt is a real Mac failure mode and a blocking call here breaks the CLI startup.
- The `_read_secretstorage_linux` helper imports `secretstorage` lazily — Mac installs do not have it; an unconditional import would break `pip install` on Mac.
- Verify that nothing in this module re-exports the key string at module level (`KEY = ...` etc). Module-level globals show up in `pickle` dumps and `dir(module)` introspection; the cache lives on the instance only.
