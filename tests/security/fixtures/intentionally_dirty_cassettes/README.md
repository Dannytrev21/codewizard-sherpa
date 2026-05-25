# Intentionally-dirty cassette fixtures (Phase 4 S3-05)

These four YAML files contain deliberately-violating payloads that prove the
`CassetteSanitizer` walker (`verify_cassette`) actually catches the four
leak shapes defined in ADR-0014:

| Fixture                                | Leak shape                                |
|----------------------------------------|-------------------------------------------|
| `with_sk_ant.yaml`                     | `Authorization: Bearer sk-ant-…` header.  |
| `with_cookie.yaml`                     | `Cookie:` header (session token).         |
| `with_body_base64.yaml`                | 60-char base64-shaped body.               |
| `with_claude_underscore_prefix.yaml`   | `claude_secret_token_…` in body.          |

## Why they live outside `tests/cassettes/`

The CI walker (`tests/security/test_cassettes_clean.py`) scans
`tests/cassettes/` and fails CI on any sanitizer violation. These fixtures
live under `tests/security/fixtures/intentionally_dirty_cassettes/` —
**outside** the walker's scan root — so the main walker stays green.

A *separate* inverted test
(`tests/security/test_scanner_catches_planted_secrets.py`) loads each
fixture and asserts `verify_cassette(fixture).passed is False`. That is the
load-bearing assurance that the scanner cannot be quietly defanged by a
refactor: if the sanitizer ever stops catching these specific leaks, the
inverted test breaks loudly.

## Pre-commit firewall posture

The `forbidden-patterns` hook in `.pre-commit-config.yaml` is scoped to
`\.py$` and explicitly excludes `tests/`, so these YAML fixtures do **not**
trip that hook (no carve-out required, no broad exclusion was added).

The `gitleaks` hook is the only other pre-commit secret-scanner. The
fixture payloads above use the literal substrings `FIXTURE-NOT-REAL`,
`FIXTURE_NOT_REAL`, and explicitly invalid-shaped tokens so gitleaks'
default rule set treats them as non-secrets. If a future gitleaks ruleset
flags one of these fixtures, scope the allowlist narrowly to this directory
path (`tests/security/fixtures/intentionally_dirty_cassettes/`) and add a
negative-control test asserting the same shape outside this directory is
still rejected.

## Maintenance

Adding a new leak shape: add a new fixture here, add it to the inverted
test's `parametrize` list. Do **not** add it to `tests/cassettes/` — that
would fail the CI walker, which is the opposite of the contract.
