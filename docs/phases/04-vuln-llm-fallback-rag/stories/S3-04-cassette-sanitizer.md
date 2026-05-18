# Story S3-04 — `CassetteSanitizer` pytest-recording hooks (sanitize on record, idempotent)

**Step:** Step 3 — Ship LeafLlm Port + AnthropicLeafAdapter + EgressGuard + cassette discipline
**Status:** Ready
**Effort:** M
**Depends on:** S3-02 (`AnthropicLeafAdapter` is the first cassette source; the hooks must be in conftest *before* any cassette is recorded)
**ADRs honored:** ADR-0014 (Phase 4 — cassette discipline as security control), ADR-0005 (Phase 4 — no env-var key fallback ⇒ no env key to leak; but `Authorization` headers from `keyring`-loaded keys still need stripping)

## Context

Cassettes are checked-in source. `pytest-recording` (built on `vcrpy`) defaults to recording `Authorization` headers verbatim — one careless `pytest --record-mode=all` run leaks a contributor's Anthropic API key into `tests/cassettes/`. Per ADR-0014 §Decision, Phase 4 ships a four-layer cassette-discipline stack:

1. **Sanitize at record** — *this story*. `before_record_request` / `before_record_response` hooks strip headers + body-scan for shaped secrets.
2. **CI security scanner** — S3-05 (`tests/security/test_cassettes_clean.py`).
3. **Content-addressed manifest** — S3-05 (`cassettes.lock` BLAKE3).
4. **CODEOWNERS + nightly drift** — S3-06 + Phase 6.5.

The sanitizer is the **load-bearing first layer**: the CI scanner is the backstop, not the primary control. A cassette body that escapes the sanitizer reaches the scanner; a cassette body that escapes both reaches `cassettes.lock`; a cassette body that escapes all three reaches Phase 6.5's bench replay. The depth-of-defense ordering matters: sanitization at record means **the secret never lands on disk**, even momentarily, even on a contributor's laptop.

Per `phase-arch-design.md §Component 12`:

- Headers to strip: `Authorization`, `X-API-Key`, `Cookie`, `Set-Cookie`, `anthropic-version`. (The `anthropic-version` header is not a secret but is SDK-version-coupling that we want to strip so cassette replays don't break on SDK upgrades.)
- Body patterns to redact: `sk-ant-*` (Anthropic key prefix), `claude_*` (legacy/internal prefix), any 40+-char base64-shaped string (catches generic high-entropy tokens).
- **Sanitizer must be idempotent**: `sanitize(sanitize(x)) == sanitize(x)` — Hypothesis property.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 12 — CassetteSanitizer` — public interface (`before_record_request`/`before_record_response` hook entry points + `verify_cassette(path)` walker).
  - `../phase-arch-design.md §Goals — G11` — cassette-cleanliness CI contract.
  - `../phase-arch-design.md §Threat model` — secret hygiene + cassette-vs-reality drift.
- **Phase ADRs:**
  - `../ADRs/0014-cassette-discipline-security-control.md` §Decision — exact header list + body patterns; sanitizer drops fields silently on record.
- **Source design:** `../final-design.md §Component 13 — CassetteSanitizer`.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `tests/conftest.py` — where `pytest-recording`'s `vcr_config` fixture is wired.
  - There is no existing cassette directory; this story creates `tests/cassettes/anthropic/` (S3-02 puts the first two cassettes here).
  - The `forbidden-patterns` pre-commit hook (per repo `CLAUDE.md`) — confirm the sanitizer's regex strings do not contain forbidden patterns (`eval(`, `exec(`, etc. — they don't, but be defensive).
- **External:**
  - `pytest-recording` README / `vcrpy` `before_record_request`/`before_record_response` hook signatures — confirm the parameter shape (typically `request -> request | None` for request hooks; `response -> response | None` for response hooks).

## Goal

Land the pure-function sanitizer that strips header secrets and body-scans for shaped secrets, wire it into `tests/conftest.py` as the `vcr_config` fixture's `before_record_request`/`before_record_response` hooks, and prove via Hypothesis property that `sanitize ∘ sanitize == sanitize` — so the **first byte** any cassette ever writes is already clean.

## Acceptance criteria

### Pure sanitization

- [ ] AC-1 — `src/codegenie/fallback/cassette/sanitizer.py` exports `sanitize_request(request) -> request`, `sanitize_response(response) -> response`, `verify_cassette(path: Path) -> CassetteVerification`, and module-level `Final` constants `_FORBIDDEN_HEADERS`, `_BODY_SECRET_PATTERNS`. `__all__` is exact.
- [ ] AC-2 — `_FORBIDDEN_HEADERS: Final[frozenset[str]]` equals (case-insensitive) `{"authorization", "x-api-key", "cookie", "set-cookie", "anthropic-version"}`. Sanitization is case-insensitive on header names (HTTP header names are case-insensitive per RFC 7230).
- [ ] AC-3 — `_BODY_SECRET_PATTERNS: Final[tuple[re.Pattern[str], ...]]` includes three compiled patterns:
  - `r"sk-ant-[A-Za-z0-9_-]{20,}"` — Anthropic key prefix family.
  - `r"claude_[A-Za-z0-9_-]{20,}"` — legacy / internal prefix.
  - `r"\b[A-Za-z0-9+/]{40,}={0,2}\b"` — generic 40+-char base64-shaped (with `\b` word-boundaries so prose is unaffected).
- [ ] AC-4 — `sanitize_request(request)` returns a *new* request object (immutable input; mutation discipline) with `_FORBIDDEN_HEADERS` removed and body patterns redacted to the literal string `"[REDACTED]"`. The function is pure (no I/O, no logging side effect — sanitizer drops silently per ADR-0014 §Decision item 1).
- [ ] AC-5 — `sanitize_response(response)` mirrors `sanitize_request` for response objects (response headers stripped; response body scanned for the same patterns; `Set-Cookie` particularly important on the response side).
- [ ] AC-6 — Idempotence property (Hypothesis): for any request shape drawn from a strategy over arbitrary header dicts and arbitrary body bytes, `sanitize_request(sanitize_request(r)) == sanitize_request(r)`. Same for response. Run with at least 200 examples; max-shrink reasonable.
- [ ] AC-7 — Determinism: `sanitize_request(r) == sanitize_request(r)` (no `time.time()`, no `random`, no UUID; pure transformation).

### Cassette verification walker

- [ ] AC-8 — `verify_cassette(path: Path) -> CassetteVerification` opens the cassette (YAML), walks every interaction, and asserts:
  - No interaction's request headers contains any `_FORBIDDEN_HEADERS` key (case-insensitive).
  - No interaction's response headers contains any `_FORBIDDEN_HEADERS` key.
  - No request body or response body matches any `_BODY_SECRET_PATTERNS` regex.
  Returns `CassetteVerification(passed=True, violations=())` on clean or `CassetteVerification(passed=False, violations=tuple[Violation, ...])` enumerating each violation with `(interaction_index, kind, snippet_around_match)`. Snippet is bounded to ±20 chars to avoid logging large secrets.
- [ ] AC-9 — `CassetteVerification` is a frozen-extra-forbid Pydantic model with `passed: bool`, `violations: tuple[Violation, ...]`. `Violation` is a frozen-extra-forbid model with `interaction_index: int`, `kind: Literal["header", "body_request", "body_response"]`, `header_name: str | None`, `pattern: str | None`, `snippet: str`.

### conftest wiring (the load-bearing integration step)

- [ ] AC-10 — `tests/conftest.py` exposes a `vcr_config` fixture (per `pytest-recording` convention) that returns a dict including:
  ```python
  {
      "before_record_request": sanitize_request,
      "before_record_response": sanitize_response,
      "filter_headers": list(_FORBIDDEN_HEADERS),  # belt-and-suspenders
      "record_mode": "none",
      "cassette_library_dir": str(repo_root / "tests" / "cassettes"),
  }
  ```
  The `record_mode="none"` default means a cassette miss is a hard fail in CI (ADR-0014 §Consequences). The `make refresh-cassettes` target (S3-06) overrides to `"all"` only when explicitly invoked.
- [ ] AC-11 — Negative test: a test that calls the Anthropic SDK *without* a cassette (`record_mode="none"` in CI) hard-fails with a diagnostic pointing to `make refresh-cassettes` (the diagnostic string lives in `pytest-recording`'s error; verify it appears in the captured output).

### Live-recording opt-in

- [ ] AC-12 — `tests/conftest.py` checks the `CODEGENIE_LIVE_LLM` env var. If `CODEGENIE_LIVE_LLM=1`, the `vcr_config` fixture flips `record_mode` to `"all"`; otherwise stays at `"none"`. The default in CI is unset → `"none"`.
- [ ] AC-13 — `tests/fence/test_cassette_discipline.py` (existing-or-new) asserts `CODEGENIE_LIVE_LLM` is **unset** when CI runs the standard test suite (`make test`). The env var is set only by `make refresh-cassettes`.

### Adversarial — sanitizer corpus

- [ ] AC-14 — `tests/security/test_sanitizer_corpus.py` parametrizes over a curated corpus of 30+ "should-be-redacted" inputs:
  - `Authorization: Bearer sk-ant-real-looking-key-123abc` (header).
  - `X-API-Key: anything`, `Cookie: session=abc`, `Set-Cookie: foo=bar`, `anthropic-version: 2023-06-01` (headers).
  - Body contains `"api_key": "sk-ant-..."`, body contains `"claude_secret_xyz..."`, body contains a 60-char base64-shaped string, body has a JSON property whose *value* matches a pattern but whose *key* is innocuous.
  - Case-variants: `AUTHORIZATION`, `authorization`, `Authorization` — all stripped.
  - Sneak cases: header `X-Auth-Custom: sk-ant-...` (not in `_FORBIDDEN_HEADERS` by name, but the *value* matches a body pattern — verify the body-scanner ALSO scans header *values* not just header names). This is an ADDITIVE acceptance — sanitizer scans (a) header *names* against `_FORBIDDEN_HEADERS`, (b) header *values* against `_BODY_SECRET_PATTERNS`, (c) bodies against `_BODY_SECRET_PATTERNS`.
- [ ] AC-15 — `tests/security/test_sanitizer_corpus_negatives.py` — innocuous corpus that must **not** be redacted: random prose, JSON without secrets, headers with non-secret values like `User-Agent: codegenie/0.4`. Each verified the sanitizer is a no-op (`sanitize(x) == x`).

### Cross-cutting

- [ ] AC-16 — `mypy --strict src/codegenie/fallback/cassette/` clean. `ruff check`, `ruff format --check` clean.
- [ ] AC-17 — Module-level `_WARNING_IDS: Final[frozenset[str]] = frozenset()` (sanitizer emits no warnings — drops silently per ADR).
- [ ] AC-18 — TDD red test exists, was demonstrably failing before implementation, now green.

## Implementation outline

1. Create `src/codegenie/fallback/cassette/__init__.py` and `src/codegenie/fallback/cassette/sanitizer.py`.
2. Define `_FORBIDDEN_HEADERS`, `_BODY_SECRET_PATTERNS`, `Violation`, `CassetteVerification` at module scope.
3. Implement `sanitize_request(request)` — copy headers, drop forbidden keys, scan header values, return a new request. Use `vcr.request.Request`-compatible shape (read `vcrpy` source for the actual type).
4. Implement `sanitize_response(response)` — same shape for the response object.
5. Implement `verify_cassette(path)` — `yaml.safe_load`, iterate interactions, scan, return verification.
6. Add `vcr_config` fixture to `tests/conftest.py` (or extend existing fixture).
7. Add the `CODEGENIE_LIVE_LLM` env-var-driven `record_mode` switch.
8. Author the sanitizer-corpus tests (positive + negative).
9. Author the idempotence Hypothesis property.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/fallback/test_cassette_sanitizer.py
import re
import pytest
from hypothesis import given, strategies as st
from codegenie.fallback.cassette.sanitizer import (
    sanitize_request,
    sanitize_response,
    verify_cassette,
    _FORBIDDEN_HEADERS,
    _BODY_SECRET_PATTERNS,
)


def _make_request(headers: dict[str, str], body: bytes = b"") -> dict:
    # vcr.request.Request-like shim; adjust to actual vcrpy type
    return {"headers": headers, "body": body}


@pytest.mark.parametrize("h", ["Authorization", "authorization", "AUTHORIZATION"])
def test_authorization_header_stripped_case_insensitively(h):
    req = _make_request({h: "Bearer sk-ant-xyz", "User-Agent": "ok"})
    out = sanitize_request(req)
    assert h not in out["headers"]
    assert "User-Agent" in out["headers"]


def test_body_redacts_sk_ant_pattern():
    body = b'{"api_key": "sk-ant-real-looking-key-1234567890abcdef"}'
    req = _make_request({}, body=body)
    out = sanitize_request(req)
    assert b"sk-ant-real-looking-key" not in out["body"]
    assert b"[REDACTED]" in out["body"]


def test_innocuous_input_unchanged():
    req = _make_request({"User-Agent": "codegenie/0.4"}, body=b"hello world")
    assert sanitize_request(req) == req


@given(headers=st.dictionaries(st.text(min_size=1, max_size=30),
                               st.text(min_size=0, max_size=100), max_size=10),
       body=st.binary(max_size=500))
def test_sanitize_request_is_idempotent(headers, body):
    req = _make_request(headers, body)
    once = sanitize_request(req)
    twice = sanitize_request(once)
    assert once == twice


def test_verify_cassette_flags_unredacted_authorization(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "interactions:\n"
        "  - request:\n"
        "      headers:\n"
        "        Authorization: Bearer sk-ant-leak\n"
    )
    v = verify_cassette(bad)
    assert v.passed is False
    assert any(viol.kind == "header" for viol in v.violations)
```

### Green — make it pass

Implement `sanitizer.py` minimally. Use a `copy.deepcopy` + key-drop pattern for the header strip; use a `re.sub` with `[REDACTED]` for body redaction.

### Refactor — clean up

- Extract `_redact_body(body: bytes) -> bytes` and `_strip_headers(headers: Mapping) -> Mapping` as pure helpers.
- Confirm the `frozenset` and `tuple` of `Final` constants are hashable + immutable.
- Re-run the Hypothesis property with `max_examples=500` once; commit if stable.
- Add docstrings to the public functions naming ADR-0014.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/fallback/cassette/__init__.py` | Package marker. |
| `src/codegenie/fallback/cassette/sanitizer.py` | The sanitizer (this story's primary deliverable). |
| `tests/conftest.py` | Wire `vcr_config` fixture with the hooks + `record_mode` switch. |
| `tests/unit/fallback/test_cassette_sanitizer.py` | Unit + Hypothesis idempotence. |
| `tests/security/test_sanitizer_corpus.py` | 30+ positive redaction corpus. |
| `tests/security/test_sanitizer_corpus_negatives.py` | Innocuous corpus (no-op verification). |
| `tests/fence/test_cassette_discipline.py` | `CODEGENIE_LIVE_LLM` unset in CI assertion. |
| `pyproject.toml` | Add `pytest-recording` to dev dependencies (if not already). |

## Out of scope

- `cassettes.lock` BLAKE3 manifest (S3-05).
- `tests/security/test_cassettes_clean.py` walker (S3-05 — it *uses* `verify_cassette` from this story).
- CODEOWNERS entry (S3-06).
- `make refresh-cassettes` target (S3-06).
- Recording the first actual cassettes (S3-02 + S3-06 together).
- Nightly drift job (Phase 6.5).

## Notes for the implementer

- The sanitizer **silently drops** forbidden header values (it does **not** emit a warning per ADR-0014 §Decision). The CI scanner (S3-05) is where surfacing happens — the sanitizer is the redaction primitive.
- `pytest-recording`'s `vcr_config` fixture is the documented integration point; check the actual signature of the `before_record_*` hooks against your installed `pytest-recording` version (the parameter is `request` and return `None` to drop the interaction entirely, or `request` to keep it). For sanitization we always return the (mutated copy of the) request.
- The 40+-char base64 regex is intentionally **broad**. It will catch legitimate base64-encoded payloads (e.g., a Unicode-escaped JSON body that happens to be base64-shaped). The `\b` word-boundaries mitigate false positives; a real false-positive corpus (AC-15) drives the calibration. If the negative corpus surfaces false positives, **raise the minimum to 48** rather than weakening the pattern in some other way (Global Rule 12 — fail loud).
- The `verify_cassette(path)` walker is also used by S3-05's CI scanner; design the return type now so S3-05 can iterate violations programmatically.
- Headers are stored differently across `vcrpy` versions (sometimes a dict, sometimes a list of `(name, value)` tuples). Handle both shapes defensively — `_strip_headers` should normalize before iterating.
- The sanitizer does not need to handle gzip-encoded response bodies in Phase 4 (Anthropic responses are JSON; `vcrpy` decodes per its config). If a future SDK upgrade brings gzip-encoded responses, the sanitizer's pattern scan would miss; flag this as a follow-up if you observe it.
- For idempotence: the most common bug is double-encoding the redaction marker (`"[REDACTED]"` itself matches as base64-shaped if you're not careful). Test: a body containing `[REDACTED]` literal remains `[REDACTED]` after re-sanitization (not `[[REDACTED]REDACTED]`).
