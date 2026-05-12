# Story S2-05 — `codegenie auth set-anthropic-key` + `auth status` CLI

**Step:** Step 2 — Ship the deterministic LLM-side primitives — `OutputValidator`, `PromptLoader` + YAML prompts, `LlmInvocationGuard`, `ApiKeyStore`
**Status:** Ready
**Effort:** S
**Depends on:** S2-04, S1-06
**ADRs honored:** ADR-P4-013

## Context

S2-04 ships `ApiKeyStore` but no documented setup path; operators currently have no way to land a key without violating the env-var rule (Linux hard-refuse). S1-06 already stubbed the `auth` subcommand group (`--help` prints + exit 2). This story wires the two operator-facing verbs — `set-anthropic-key` writes to the platform store without ever echoing the key; `status` prints whether a key is present plus `blake3(key)[:8]` only. Both verbs are the only documented path; without them, the ADR-P4-013 discipline is a barrier rather than a workflow.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #10 "ApiKeyStore"` — `codegenie auth set-anthropic-key` is the documented setup path; `codegenie auth fingerprint` (called `auth status` here per manifest) prints the fingerprint.
  - `../phase-arch-design.md §"Edge cases"` row 1 — `available()==False` → operator runs `codegenie auth set-anthropic-key`.
- **Phase ADRs:**
  - `../ADRs/0013-api-key-store-env-var-refused.md` — ADR-P4-013 §Consequences — `codegenie auth set-anthropic-key` is the documented setup path; `codegenie auth fingerprint` returns `blake3(key)[:8]` for operator key identification.
- **Source design:** `../final-design.md §"Components" #11` — operator interaction model.
- **Existing code:**
  - `src/codegenie/cli.py` (from S1-06) — `auth` subcommand group exists as a stub (`--help` prints + exit 2). Wire the two verbs under it without restructuring the group.
  - `src/codegenie/llm/secrets/key_store.py` (from S2-04) — `ApiKeyStore.available()` and `read()`; this story adds a `write(key: str)` method scoped the same way (callable from CLI module, not from arbitrary code).
  - `tests/unit/cli/` — Click `CliRunner` patterns already established by Phase 0/1/2 CLI stories.

## Goal

Wire `codegenie auth set-anthropic-key` (reads the key from stdin or a `--from-file` path; writes to the platform store; emits success without echoing the key) and `codegenie auth status` (prints whether a key is present and its `blake3(key)[:8]` fingerprint only — never the key itself), with tests asserting no key bytes appear in stdout/stderr/logs/audit on either verb.

## Acceptance criteria

- [ ] `codegenie auth set-anthropic-key` accepts the key from one of: `--from-file PATH`, `--from-env VAR_NAME` (note: not `ANTHROPIC_API_KEY` to avoid the very env var the store refuses on Linux — operator picks a one-shot var like `CODEGENIE_NEW_KEY`), or interactive stdin via `click.prompt(hide_input=True)` (default when neither flag is given).
- [ ] On success the verb prints `Stored Anthropic API key (fingerprint: <8hex>).` to stdout and exits 0. Neither the key bytes nor the file path appear in any output beyond the directory containing them (path is OK; the secret bytes are not).
- [ ] On macOS the verb calls `security add-generic-password -s codegenie-anthropic -a <user> -w <key> -U` (the `-U` flag updates if present); on Linux it tries `secretstorage` first, then writes a mode-600 file at `~/.codegenie/secrets/anthropic-api-key` with `os.umask(0o077)` and `os.chmod(path, 0o600)` after write, owner = `os.geteuid()`.
- [ ] `codegenie auth status` prints exactly one line: `present: true` or `present: false`. If present, a second line `fingerprint: <8hex>`. Both lines go to stdout. Exit 0 either way (status is informational, not pass/fail).
- [ ] `tests/unit/cli/test_auth_set_key.py` runs `CliRunner` with stdin = a fake key (`sk-ant-test-fake-not-real`), captures stdout / stderr / `caplog`; asserts the fake key bytes do **not** appear anywhere. Asserts the success line contains the fingerprint and the verb exits 0.
- [ ] `tests/unit/cli/test_auth_status_fingerprint.py` runs `auth status` against a mocked `ApiKeyStore` returning the same fake key; asserts the output is exactly `present: true\nfingerprint: <8hex>\n` and the 8-hex pattern matches `r"[0-9a-f]{8}"`.
- [ ] `tests/unit/cli/test_auth_status_when_absent.py` runs against a store with `available() == False`; asserts output is exactly `present: false\n` and exit 0.
- [ ] `tests/unit/cli/test_auth_set_key_from_file.py` runs `--from-file <path>`; asserts the file path appears in the audit (`AUTH_KEY_WRITTEN` event with `source="file"`) and the key bytes do not.
- [ ] `tests/security/test_no_api_key_in_logs.py` (from S2-04) is extended to scan the new CLI test fixture log captures with the same fingerprint-pattern grep.
- [ ] `ApiKeyStore.write(key: str) -> None` is added; on Linux refuses (raises `ApiKeyEnvRefused`-style typed error) if `ANTHROPIC_API_KEY` is in the env at write time (same Linux strictness as `__init__`).
- [ ] No `print(key)`, `click.echo(key)`, or interpolation of the key into a log message exists in the CLI module (covered by the grep test).
- [ ] TDD red test exists, committed on a tagged commit, and the green commit brings it green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Write tests first (red) — `test_auth_set_key.py`, `test_auth_status_fingerprint.py`, `test_auth_status_when_absent.py`, `test_auth_set_key_from_file.py`.
2. Extend `ApiKeyStore` in `src/codegenie/llm/secrets/key_store.py` with `write(key: str) -> None`:
   - Validate `key.strip()` is non-empty and matches a permissive Anthropic key shape (`r"^sk-ant-[A-Za-z0-9_-]{20,}$"`) before any storage call — early invalid input prevents a malformed Keychain entry. Raise `ApiKeyMalformed(reason)` on mismatch.
   - On Linux, re-check env-var refusal at write time.
   - Platform-dispatch to `_write_keychain_mac(key)` / `_write_secretstorage_linux(key)` / `_write_file_linux(key)`. Try `secretstorage` first; fall back to the mode-600 file.
3. Extend `src/codegenie/cli.py` `auth` group with two new commands using `click`:
   - `@auth.command("set-anthropic-key")` with options `--from-file PATH` (mutually exclusive with `--from-env`) and `--from-env STRING`. Default: prompt with `hide_input=True`.
   - `@auth.command("status")` — instantiates `ApiKeyStore(platform=...)` (platform auto-detected via `sys.platform`); calls `available()`; if true, calls `read()` and computes `blake3(key)[:8]`.
4. The `set-anthropic-key` handler must **never** log the key — only the fingerprint. Emit `AUTH_KEY_WRITTEN` audit event (constant from S1-01; add if missing) with structured fields `(platform, source ∈ {"stdin","file","env"}, fingerprint)`.
5. Run `ruff format`, `ruff check`, `mypy --strict`, `pytest`.

## TDD plan — red / green / refactor

### Red

Test file path (representative): `tests/unit/cli/test_auth_set_key.py`

```python
# tests/unit/cli/test_auth_set_key.py
from unittest.mock import patch

from click.testing import CliRunner

from codegenie.cli import cli


FAKE_KEY = "sk-ant-fake-test-key-do-not-use-1234567890"


def test_set_key_via_stdin_does_not_echo_key(caplog):
    runner = CliRunner(mix_stderr=False)
    with patch("codegenie.llm.secrets.key_store.ApiKeyStore.write") as mock_write:
        result = runner.invoke(cli, ["auth", "set-anthropic-key"], input=f"{FAKE_KEY}\n")

    assert result.exit_code == 0
    assert FAKE_KEY not in result.stdout
    assert FAKE_KEY not in result.stderr
    for record in caplog.records:
        assert FAKE_KEY not in record.getMessage()
        for v in record.__dict__.values():
            assert FAKE_KEY not in str(v)
    mock_write.assert_called_once_with(FAKE_KEY)
    # Success line carries the fingerprint, not the key.
    assert "fingerprint:" in result.stdout
    # 8 hex chars in the fingerprint slot.
    import re
    assert re.search(r"fingerprint: [0-9a-f]{8}", result.stdout)
```

```python
# tests/unit/cli/test_auth_status_fingerprint.py
import re
from unittest.mock import patch
from click.testing import CliRunner
from codegenie.cli import cli


def test_status_present_prints_fingerprint_only():
    with patch("codegenie.llm.secrets.key_store.ApiKeyStore.available", return_value=True), \
         patch("codegenie.llm.secrets.key_store.ApiKeyStore.read",
               return_value="sk-ant-fake-test-key-do-not-use-1234567890"):
        result = CliRunner().invoke(cli, ["auth", "status"])
    assert result.exit_code == 0
    lines = result.output.strip().split("\n")
    assert lines[0] == "present: true"
    assert re.fullmatch(r"fingerprint: [0-9a-f]{8}", lines[1])
    # The key never appears.
    assert "sk-ant-" not in result.output


def test_status_absent_one_line():
    with patch("codegenie.llm.secrets.key_store.ApiKeyStore.available", return_value=False):
        result = CliRunner().invoke(cli, ["auth", "status"])
    assert result.exit_code == 0
    assert result.output == "present: false\n"
```

Run; all fail because the new verbs are not registered. Commit as red.

### Green

Wire the two verbs under the `auth` group; implement `ApiKeyStore.write`; thread the fingerprint into the success line. Minimum: the four representative tests pass; the existing `auth --help` stub still works.

### Refactor

- Move fingerprint computation to a single helper (`_key_fingerprint(key: str) -> str`) in `secrets/key_store.py` — reused by `auth status`, the audit emitter, and S2-04's `_log_key_fingerprint`.
- Add `mypy --strict` types; both Click handlers return `None`.
- Confirm `auth --help` still passes the S1-06 stub assertions; confirm exit code 2 still applies when a child verb name is unknown (`codegenie auth bogus`).
- Confirm the `--from-file PATH` handler reads with `open(path, "r", encoding="utf-8")` and strips trailing newline only — operators commonly `pbpaste > /tmp/key && codegenie auth set-anthropic-key --from-file /tmp/key`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/cli.py` | Wire `auth set-anthropic-key` and `auth status` under the existing `auth` group |
| `src/codegenie/llm/secrets/key_store.py` | Add `write(key)` + `_key_fingerprint(key)` helper |
| `src/codegenie/errors.py` | Add `ApiKeyMalformed` if not already present from S1-01 |
| `src/codegenie/logging.py` | Add `AUTH_KEY_WRITTEN` audit event constant if not present from S1-01 |
| `tests/unit/cli/test_auth_set_key.py` | Stdin path does not echo key; success line has fingerprint |
| `tests/unit/cli/test_auth_set_key_from_file.py` | `--from-file` path audited with file source |
| `tests/unit/cli/test_auth_status_fingerprint.py` | `status` present output shape |
| `tests/unit/cli/test_auth_status_when_absent.py` | `status` absent one-line output |
| `tests/security/test_no_api_key_in_logs.py` | Extend pattern scan to cover new CLI fixtures |

## Out of scope

- **`codegenie auth rotate` / `auth remove`** — not in v0.4.0 (`final-design.md §"Open questions"` deferred to Phase 16 alongside SPKI pinning).
- **Keychain access-control prompts on macOS** — the `security add-generic-password -U` flag triggers the standard OS prompt; we do not script around it (a scripted bypass would be a security regression).
- **Secret rotation cassette / E2E** — adversarial coverage of the `write` path lives in S7-06.
- **Anthropic SDK transport** — owned by S3-01.
- **`auth fingerprint` as a separate verb** — folded into `auth status` per the manifest entry (the verb name from ADR-P4-013 §Consequences is "fingerprint" but the manifest binds it to `auth status` for v0.4.0; surfacing in `status` is the agreed shape).
- **CLI completion / shell hints** — separate UX story, not Phase 4.

## Notes for the implementer

- `click.prompt(..., hide_input=True)` is the right primitive for stdin; never use `input()` directly (the TTY-echo discipline is what makes "did not echo" a true statement).
- Do not use `click.echo(f"Stored key {key}")`-shaped lines anywhere — even in error paths. The grep test in S2-04 + S7-06 catches any key-byte leak; debugging that fixture is annoying. Build the habit of using the fingerprint helper from the first commit.
- The `--from-env VAR_NAME` flag is **not** `ANTHROPIC_API_KEY`. The operator picks a one-shot variable name (e.g., `CODEGENIE_NEW_KEY`) because on Linux `ANTHROPIC_API_KEY` causes the store to refuse at `__init__` (S2-04). Document this in the verb's `--help`.
- `os.umask(0o077)` before the `os.write` then `os.chmod(path, 0o600)` after — belt-and-suspenders against process-wide umask drift. Use `os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)` rather than `open()` so the mode bits land at creation, not after.
- `subprocess.run(["security", "add-generic-password", ...], check=True, timeout=10)` — Keychain interactive prompts can stall; surface a clear error on timeout.
- The audit event `AUTH_KEY_WRITTEN` carries `source ∈ {"stdin","file","env"}` for the operator-visible record. The fingerprint is in the event — the key bytes are not.
- After landing this story, run `git log -p src/codegenie/cli.py | rg "sk-ant"` to make sure no debug print survived into a commit. The CI grep test will catch this but the local check is the cheaper feedback loop.
- The `--from-file` path: do `os.unlink(path)` after the successful write only if `--delete-source` is passed; otherwise leave the file alone. Auto-deleting an operator's temp file is too magical; the documented workflow is `pbpaste > /tmp/key && codegenie auth set-anthropic-key --from-file /tmp/key && shred /tmp/key` (operator-owned hygiene).
