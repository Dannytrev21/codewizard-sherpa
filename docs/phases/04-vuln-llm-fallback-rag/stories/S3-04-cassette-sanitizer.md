# Story S3-04 — `CassetteSanitizer` pytest-recording hooks (sanitize on record, idempotent)

**Step:** Step 3 — Ship LeafLlm Port + AnthropicLeafAdapter + EgressGuard + cassette discipline
**Status:** HARDENED
**Effort:** M
**Depends on:** S3-02 (`AnthropicLeafAdapter` is the first cassette source; the hooks must be in conftest *before* any cassette is recorded)
**ADRs honored:** ADR-0014 (Phase 4 — cassette discipline as security control), ADR-0005 (Phase 4 — no env-var key fallback ⇒ no env key to leak; but `Authorization` headers from `keyring`-loaded keys still need stripping)

## Validation notes

Validated: 2026-05-21 — Verdict: **HARDENED** (phase-story-validator; four critics — Coverage, Test-Quality, Consistency, Design-Patterns).
Findings addressed: 24 (1 block, 16 harden, 7 nit). No `NEEDS RESEARCH` items.

Key changes:
- **Block fixed** — `_BODY_SECRET_PATTERNS` retyped `re.Pattern[bytes]` (`rb"..."`). All four critics independently flagged that a `re.Pattern[str]` catalog cannot scan `bytes` bodies — `mypy --strict` rejects it and `re.sub` raises `TypeError`, making AC-3 / AC-4 / AC-16 mutually unsatisfiable as written.
- `verify_cassette` made **total** over the filesystem (AC-20) and split into a pure `_scan_cassette_doc` walker behind a thin I/O shell (AC-21) — it is load-bearing for S3-05's CI scanner.
- Idempotence property (AC-6) now biases its strategy toward the redaction path — the original strategy proved idempotence only on no-op inputs, so the double-encoding bug the story itself names was uncatchable.
- Header-*value* secret scanning promoted from a buried AC-14 corpus row to first-class AC-4 / AC-5 behaviour (scan surface (b)).
- AC-7 "determinism" was a tautology; now backed by a real AST purity fence (AC-23). `passed` made a derived property so a silently-passing leak (`passed=True` with violations) is unrepresentable (AC-9).
- Repo-reality corrections — `tests/conftest.py`, `tests/security/`, and the `pytest-recording` dev-dep do **not** exist yet; story now says *create*, with a suite-wide-green gate (AC-10, AC-24, AC-25).

Full audit log: [`_validation/S3-04-cassette-sanitizer.md`](_validation/S3-04-cassette-sanitizer.md)

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
- **Scan scope (validator trace).** All three patterns are applied to message **bodies** *and* surviving header **values** (AC-4 surface (b)) — broader than ADR-0014 §Decision / `phase-arch-design.md §Component 12`, which word the base64 pattern as "header values" only. The broader scope is the correct security posture and is sanctioned by `phase-arch-design.md §Goals — G11` ("blocks any header/**body** with … `sk-*`/40+-char base64"). A name-only forbidden-header allowlist cannot catch a secret carried in an unanticipated header (e.g. `X-Auth-Custom`). Recommend a one-line ADR-0014 clarification so the ADR's wording matches G11.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 12 — CassetteSanitizer` — public interface (`before_record_request`/`before_record_response` hook entry points + `verify_cassette(path)` walker).
  - `../phase-arch-design.md §Goals — G11` — cassette-cleanliness CI contract.
  - `../phase-arch-design.md §Threat model` — secret hygiene + cassette-vs-reality drift.
- **Phase ADRs:**
  - `../ADRs/0014-cassette-discipline-security-control.md` §Decision — exact header list + body patterns; sanitizer drops fields silently on record.
- **Source design:** `../final-design.md §Component 13 — CassetteSanitizer`.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `tests/conftest.py` — **does not exist yet**; only per-subdir conftests (`tests/unit/conftest.py`, …) exist. This story creates the repo-root `tests/conftest.py` (the correct scope so the `vcr_config` fixture covers `tests/unit/fallback/` and `tests/security/`).
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
- [ ] AC-3 — `_BODY_SECRET_PATTERNS: Final[tuple[re.Pattern[bytes], ...]]` is a **single** catalog of three patterns compiled from **bytes** literals (`re.compile(rb"...")`) — message bodies are `bytes`, so a `re.Pattern[str]` catalog cannot scan them (`mypy --strict` rejects it; `re.sub` raises `TypeError`). There is exactly one catalog (no parallel str/bytes tuples): adding a shaped-secret pattern is a one-line tuple edit, zero function edits (Open/Closed). (validator: retyped from `re.Pattern[str]` — flagged by all four critics as unsatisfiable against `body: bytes`.)
  - `rb"sk-ant-[A-Za-z0-9_-]{20,}"` — Anthropic key prefix family.
  - `rb"claude_[A-Za-z0-9_-]{20,}"` — legacy / internal prefix.
  - `rb"\b[A-Za-z0-9+/]{40,}={0,2}\b"` — generic 40+-char base64-shaped run (with `\b` word-boundaries so prose is unaffected). `40` is AC-3's calibrated minimum and the **single source of truth** for the threshold: if AC-15's negative corpus surfaces a false positive, raise it (44 → 48) and update *this literal* — never weaken the pattern another way (Global Rule 12). The implementer note defers to this value.
- [ ] AC-4 — `sanitize_request(request)` returns a *new* request object and does **not** mutate the input — the input `request` is byte-for-byte unchanged after the call. It sanitizes across **three surfaces**: (a) header *names* in `_FORBIDDEN_HEADERS` are dropped (case-insensitive); (b) every *surviving* header *value* is scanned against `_BODY_SECRET_PATTERNS` and matches replaced with `[REDACTED]`; (c) the body is scanned against `_BODY_SECRET_PATTERNS` and matches replaced with the bytes marker `b"[REDACTED]"`. The function is pure (no I/O, no logging side effect — sanitizer drops silently per ADR-0014 §Decision item 1). (validator: header-value scanning promoted here from the AC-14 corpus — it was the sole source of surface (b); mutation discipline made an explicit, testable clause.)
- [ ] AC-5 — `sanitize_response(response)` mirrors `sanitize_request` across the same three surfaces for response objects (header names stripped — `Set-Cookie` particularly important on the response side; surviving header values scanned; response body scanned), returns a new object, does not mutate the input. The *only* legitimate difference between `sanitize_request` and `sanitize_response` is the request-vs-response object shape they destructure and rebuild — *what* is scanned is identical, so the scan logic lives in shared pure helpers and is never copy-pasted (see Notes for the implementer). (validator: pinned the no-copy-paste contract.)
- [ ] AC-6 — Idempotence property (Hypothesis): `sanitize_request(sanitize_request(r)) == sanitize_request(r)`, same for response. The generating strategy MUST bias toward the redaction path — `st.one_of` a plain-input branch with a branch that injects a real `sk-ant-…` / `claude_…` / 40+-char base64-shaped token into a header value and/or the body — so the property is exercised where redaction actually happened, not only on no-op inputs (random `st.text` / `st.binary` essentially never generates a secret-shaped match). Each `_BODY_SECRET_PATTERNS` member must be provably hit (an explicit `@example(...)` per pattern, or `hypothesis.event()` coverage). Run with ≥ 200 examples. Equality compares a stable structural projection (see AC-22), not raw `==` on a vcrpy object. (validator: original strategy proved idempotence only on the no-op path — the double-encoding bug the story itself names was uncatchable.)
- [ ] AC-7 — Determinism: `sanitize_request` / `sanitize_response` / `verify_cassette`'s pure core are pure transformations — no `time`, no `random`, no `uuid`, no `secrets`, no module-level mutable state. This is enforced **structurally** by the AST purity fence in AC-23, not by a value-equality assertion (which is a tautology for any pure function and cannot catch most non-determinism). (validator: a `==`-of-two-calls test could not bite an impure impl; replaced with the structural fence.)

### Cassette verification walker

- [ ] AC-8 — `verify_cassette(path: Path) -> CassetteVerification` reads the cassette (YAML), walks every interaction, and flags:
  - any request- or response-header *name* in `_FORBIDDEN_HEADERS` (case-insensitive);
  - any surviving header *value* matching `_BODY_SECRET_PATTERNS`;
  - any request or response *body* matching `_BODY_SECRET_PATTERNS`.
  Returns a `CassetteVerification` with an **empty** `violations` tuple on a clean cassette (and on a cassette whose `interactions` list is empty), or a populated `violations` tuple enumerating each violation as `(interaction_index, kind, header_name|pattern, snippet)`. Snippet is bounded to ±20 chars around the match to avoid logging large secrets. (validator: header-value scanning + the explicit clean / empty-cassette pass added — the original AC only covered header-name and body, and never pinned the clean-pass result.)
- [ ] AC-9 — `CassetteVerification` is a frozen-extra-forbid Pydantic model whose only data field is `violations: tuple[Violation, ...]`; `passed` is a **derived property** equal to `not violations` — the model cannot represent the illegal state `passed=True` alongside a non-empty `violations` (a silently-passing leak — the worst failure mode for a security control). `Violation` is a frozen-extra-forbid model with `interaction_index: int`, `kind: Literal["header", "header_value", "body_request", "body_response", "unreadable"]`, `header_name: str | None`, `pattern: str | None`, `snippet: str`. A Pydantic `@model_validator(mode="after")` enforces the kind/field coupling (`kind` in `{"header","header_value"}` ⇒ `header_name` set; the `body_*` kinds ⇒ `pattern` set) so a nonsense `Violation` cannot be constructed. (validator: `passed` was a redundant field — made a computed property; `kind` gained `header_value` and `unreadable`; coupling validator added.)

### conftest wiring (the load-bearing integration step)

- [ ] AC-10 — This story **creates** a new repo-root `tests/conftest.py` (none exists today — only per-subdir conftests) exposing a `vcr_config` fixture (per `pytest-recording` convention) that returns a dict including:
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
- [ ] AC-11 — Negative test: a test wired through the `vcr_config` fixture that triggers an HTTP interaction with **no** matching cassette under `record_mode="none"` hard-fails (raises `vcr`'s cassette-miss error — `CannotOverwriteExistingCassetteException` or equivalent). The test asserts the *behaviour* (a cassette miss is a hard failure), not the exact wording of `pytest-recording`'s error string — that string is third-party and outside this story's ownership, so pinning it would make the test brittle to a library bump while not catching a codegenie regression. The operator-facing `make refresh-cassettes` pointer is wired in S3-06; if a codegenie-owned diagnostic is added, assert against *that*. (validator: original AC required the not-yet-built Anthropic SDK call site and pinned a third-party error string — rescoped to an in-scope, behaviour-level assertion.)

### Live-recording opt-in

- [ ] AC-12 — `tests/conftest.py` checks the `CODEGENIE_LIVE_LLM` env var. If `CODEGENIE_LIVE_LLM=1`, the `vcr_config` fixture flips `record_mode` to `"all"`; otherwise stays at `"none"`. The default in CI is unset → `"none"`.
- [ ] AC-13 — `tests/fence/test_cassette_discipline.py` (new) asserts `CODEGENIE_LIVE_LLM` is **unset** in the current process AND — because an env check passes vacuously on any runner where the var merely happens to be unset — statically parses the `Makefile` to assert the `test` target's recipe does not set `CODEGENIE_LIVE_LLM`. Once S3-06 lands `make refresh-cassettes`, the fence additionally asserts that target is the sole setter. The static check fails deterministically when the contract is violated, independent of ambient environment. (validator: added the Makefile static assertion — an env-only check was an environment-dependent vacuous pass.)

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

### Body & filesystem totality (validator-added)

- [ ] AC-19 — `_redact_body` accepts arbitrary `bytes` — including non-UTF-8 / binary sequences (`b"\xff\xfe\x00…"`) — and never raises. Because `_BODY_SECRET_PATTERNS` are bytes patterns (AC-3), no decode step is needed; a binary body with no pattern match is returned byte-for-byte unchanged. A test feeds `body=b"\xff\xfe\x00sk-ant-" + b"A"*30` and asserts the secret is redacted and the call does not raise. (validator: added — AC-6's strategy draws `st.binary`, which yields invalid UTF-8; the contract was unspecified, and a `.decode("utf-8")` impl would crash the property.)
- [ ] AC-20 — `verify_cassette` is **total** over the filesystem: a non-existent path, an empty file, content that is not valid YAML, and a cassette missing the top-level `interactions` key each return a `CassetteVerification` carrying a single `Violation(kind="unreadable", …)` — never an uncaught `FileNotFoundError` / `TypeError` / `KeyError` / `yaml.YAMLError`. A cassette with `interactions: []` returns a clean (empty-`violations`) verification. Load-bearing: S3-05's CI scanner walks a directory and must not crash on the first stub or corrupt cassette. (validator: added — `verify_cassette` had ACs only for the well-formed happy path.)

### Functional core / imperative shell (validator-added)

- [ ] AC-21 — The interaction-walk + violation-enumeration logic lives in a **pure** helper — `_scan_cassette_doc(doc: Mapping[str, object]) -> tuple[Violation, ...]` — that takes an already-parsed cassette document and performs no file I/O. `verify_cassette(path)` is the thin imperative shell (read file → `yaml.safe_load` → `_scan_cassette_doc` → wrap) and is the *only* function in `sanitizer.py` that touches `Path` / `open` / `yaml`. A unit test exercises `_scan_cassette_doc` on an in-memory `dict` with zero temp files. (validator: added — `verify_cassette` tangled I/O with the pure scan; the pure core is also what S3-05 reuses.)

### vcrpy object contract (validator-added)

- [ ] AC-22 — `sanitize_request` / `sanitize_response` accept the real `vcr.request.Request` / response objects, not only the `dict` shim used in the unit TDD plan. A single `_normalize_headers` helper absorbs both vcrpy header storage shapes (a `dict` and a list of `(name, value)` tuples) in one place. At least one integration test constructs an actual `vcr.request.Request` with an `Authorization` header and a secret-bearing body, runs it through the hook, and asserts header dropped + body redacted. Equality / no-op assertions compare a stable structural projection (e.g. a `(sorted-headers, body)` tuple) because `vcr.request.Request` does not guarantee value-`__eq__`. The public function signatures are typed against a module-owned structural shape, not the imported `vcr.request.Request`, so a vcrpy version bump does not ripple into the contract. (validator: added — every unit test used a `dict` shim; the load-bearing real-type round-trip was never asserted.)

### Structural defenses & dependencies (validator-added)

- [ ] AC-23 — `tests/fence/test_sanitizer_purity.py` (new) is an AST-walking fence — modelled on `tests/fence/test_engines_pure_helpers.py` + `test_engines_no_module_state.py` — asserting: (a) the pure helpers (`_normalize_headers`, `_strip_headers`, `_redact_header_values`, `_redact_body`, `_scan_cassette_doc`) reference no `random` / `time` / `uuid` / `secrets` / `logging` and call no bare `open`; (b) `sanitizer.py` holds no module-level mutable non-`Final` state; (c) `verify_cassette` is the only function referencing `Path` / `open` / `yaml`. The fence carries a planted-positive check (a deliberately impure snippet the scanner must catch) so the fence itself is mutation-resistant. (validator: added — AC-4 / AC-7 purity was prose only; the repo mandates a `tests/fence/` defense for every new `src/codegenie/` submodule.)
- [ ] AC-24 — `pytest-recording` is added to the **dev** dependency group of `pyproject.toml` (not the runtime closure — `tests/unit/test_pyproject_fence.py` polices the runtime closure; `pytest-recording` is dev-only and permitted there, so this does not trip the LLM-SDK fence). AC-10–AC-13 depend on its `vcr_config` fixture existing. (validator: added — the dependency add was a parenthetical "if not already" in Files-to-touch, not a verifiable gate; `pytest-recording` is absent from `pyproject.toml` today.)
- [ ] AC-25 — Creating the new repo-root `tests/conftest.py` does not break collection or fixture resolution anywhere: `make test` is green suite-wide after the change, and the new `vcr_config` fixture name shadows no existing per-subdir fixture. `tests/security/` is a new directory created by this story and follows the sibling-directory convention (an `__init__.py` to match `tests/fence/`, which carries one). (validator: added — a root conftest is visible to all ~2,300 tests; the structural blast radius needed a gate.)

## Implementation outline

1. Add `pytest-recording` to the `[dev]` dependency group in `pyproject.toml` (AC-24).
2. Create `src/codegenie/fallback/cassette/__init__.py` and `src/codegenie/fallback/cassette/sanitizer.py`.
3. Define `_FORBIDDEN_HEADERS` (frozenset) and the single bytes-typed `_BODY_SECRET_PATTERNS` tuple, plus `Violation` / `CassetteVerification` (with `passed` a derived property and a kind/field-coupling validator), at module scope.
4. Implement the pure helpers — `_normalize_headers`, `_strip_headers`, `_redact_header_values`, `_redact_body`, `_scan_cassette_doc` — then `sanitize_request` / `sanitize_response` as thin adapters over them, and `verify_cassette(path)` as the thin I/O shell over `_scan_cassette_doc` (total over the filesystem — AC-20).
5. Create the new repo-root `tests/conftest.py` with the `vcr_config` fixture and the `CODEGENIE_LIVE_LLM`-driven `record_mode` switch.
6. Add `tests/fence/test_sanitizer_purity.py` (AC-23) and `tests/fence/test_cassette_discipline.py` (AC-13).
7. Author the sanitizer-corpus tests (positive + negative) under the new `tests/security/` directory.
8. Author the idempotence Hypothesis property with the redaction-biased strategy.

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


# Bias the strategy toward the redaction path — random text/bytes
# essentially never contains a secret-shaped match, so an unbiased
# strategy proves idempotence only on the no-op path (AC-6).
_secretish = st.sampled_from([
    b"sk-ant-" + b"A" * 30,
    b"claude_" + b"B" * 30,
    b"QUFBQ" + b"C" * 50 + b"==",          # 40+-char base64-shaped
])
_body_st = st.one_of(
    st.binary(max_size=500),
    st.builds(lambda j, s: j + s, st.binary(max_size=200), _secretish),
)


@given(headers=st.dictionaries(st.text(min_size=1, max_size=30),
                               st.text(min_size=0, max_size=100), max_size=10),
       body=_body_st)
def test_sanitize_request_is_idempotent(headers, body):
    req = _make_request(headers, body)
    once = sanitize_request(req)
    twice = sanitize_request(once)
    assert once == twice  # compare a structural projection for real Request objs


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

Additional red tests (same unit file unless noted) — each written failing-first; together they make the no-op-vs-over-redaction sandwich and the three scan surfaces falsifiable, not prose:

- `test_body_redacts_all_occurrences` — a body with **two** distinct `sk-ant-…` strings and one 60-char base64 run; assert none of the three originals survive and `out["body"].count(b"[REDACTED]") == 3`. Kills a `replace`-first-match impl that `re.sub` (global) would not.
- `test_secret_in_non_forbidden_header_value_is_redacted` — `_make_request({"X-Auth-Custom": "Bearer sk-ant-" + "A"*30})`; assert the header *name* survives (not in `_FORBIDDEN_HEADERS`) but its *value* is `[REDACTED]`. Pins scan-surface (b) — the AC-14 "sneak case" promoted to a named red test.
- `test_sanitize_does_not_mutate_input` — build `req` with an `Authorization` header; `before = copy.deepcopy(req)`; call `sanitize_request(req)`; assert `req == before`. Mirror for `sanitize_response`. Kills an in-place `.pop()` impl that AC-4's "new object" clause would otherwise not catch.
- `test_redacted_marker_is_stable` — `sanitize_request(_make_request({}, body=b"prefix [REDACTED] suffix"))` returns the body unchanged; and re-sanitizing a body that contained a real secret yields `b"[[REDACTED]" not in twice["body"]`. The concrete form of the implementer note's double-encoding warning.
- `test_redacts_non_utf8_body` — `body=b"\xff\xfe\x00sk-ant-" + b"A"*30`; assert the secret is redacted and the call does not raise (AC-19).
- `test_verify_cassette_flags_body_violation` — a cassette with `sk-ant-…` in a request body → `passed is False`, a `Violation(kind="body_request")`; the same in a response body → `kind="body_response"`. Kills a headers-only walker.
- `test_verify_cassette_clean_passes` — a fully-clean cassette and a cassette with `interactions: []` → `v.passed is True and v.violations == ()`. Kills an always-`passed=False` walker.
- `test_verify_cassette_is_total` — non-existent path, empty file, non-YAML content, and a cassette missing `interactions` each return a `CassetteVerification` with a single `kind="unreadable"` violation and never raise (AC-20).
- `test_scan_cassette_doc_is_pure` — call `_scan_cassette_doc` on an in-memory `dict` (no temp file); assert it returns the expected `tuple[Violation, ...]` (AC-21).
- `test_sanitize_accepts_real_vcr_request` (integration) — construct an actual `vcr.request.Request`; round-trip through `sanitize_request`; assert header dropped + body redacted (AC-22).
- Property `test_idempotence_hits_every_pattern` — extends the idempotence property with an explicit `@example(...)` per `_BODY_SECRET_PATTERNS` member so each redaction branch is provably exercised (AC-6).

### Green — make it pass

Implement `sanitizer.py` minimally. Use a `copy.deepcopy` + key-drop pattern for the header strip; use `re.sub` with the **bytes** marker `b"[REDACTED]"` and the bytes-typed `_BODY_SECRET_PATTERNS` for body redaction; scan surviving header values by encoding them to bytes for the same patterns.

### Refactor — clean up

- Extract **four** pure helpers — `_normalize_headers` (absorb the dict-vs-list vcrpy header-shape divergence in one place), `_strip_headers` (drop forbidden names), `_redact_header_values` (scan surviving values), `_redact_body(body: bytes) -> bytes` — so `sanitize_request` / `sanitize_response` are thin adapters with no copy-pasted scan loop. Extract `_scan_cassette_doc` as the pure walker behind `verify_cassette`.
- Confirm `_BODY_SECRET_PATTERNS` iteration appears in no function body other than the shared helper (no duplicated scan loop across request/response).
- Confirm the `frozenset` and `tuple` of `Final` constants are hashable + immutable.
- Re-run the Hypothesis property with `max_examples=500` once; commit if stable.
- Add docstrings to the public functions naming ADR-0014.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/fallback/cassette/__init__.py` | Package marker. |
| `src/codegenie/fallback/cassette/sanitizer.py` | The sanitizer (this story's primary deliverable). |
| `tests/conftest.py` | **New file** — repo-root conftest; `vcr_config` fixture + `record_mode` switch (AC-10, AC-25). |
| `tests/unit/fallback/test_cassette_sanitizer.py` | Unit + Hypothesis idempotence + the validator-added red tests. |
| `tests/security/test_sanitizer_corpus.py` | 30+ positive redaction corpus (new `tests/security/` dir + `__init__.py`). |
| `tests/security/test_sanitizer_corpus_negatives.py` | Innocuous corpus (no-op / no-over-redaction verification). |
| `tests/fence/test_cassette_discipline.py` | `CODEGENIE_LIVE_LLM` unset + `Makefile` static assertion (AC-13). |
| `tests/fence/test_sanitizer_purity.py` | AST purity fence for `sanitizer.py` (AC-23). |
| `pyproject.toml` | Add `pytest-recording` to the `[dev]` dependency group (AC-24). |

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
- For idempotence: the most common bug is double-encoding the redaction marker (`"[REDACTED]"` itself matches as base64-shaped if you're not careful). Test: a body containing `[REDACTED]` literal remains `[REDACTED]` after re-sanitization (not `[[REDACTED]REDACTED]`). `[REDACTED]` (10 chars, contains `[` `]`) does not match the `[A-Za-z0-9+/]{40,}` class, so it is safe — but `test_redacted_marker_is_stable` pins it anyway.

### Design-pattern guidance (validator-added)

- **Functional core / imperative shell.** `verify_cassette(path)` is the *only* impure function — it reads the file and `yaml.safe_load`s it. All scan logic lives in the pure `_scan_cassette_doc(doc) -> tuple[Violation, ...]` (AC-21) and the four pure helpers. This mirrors the repo's `transforms/engines/` discipline (`apply` is the only impure surface; `_build_*`/`_map_*` carry the logic) and is what makes the AC-23 fence applicable. S3-05's CI scanner reuses `_scan_cassette_doc` against in-memory documents — design the return type for programmatic iteration now.
- **Three pure helpers, not two.** The original refactor named two helpers; scan-surface (b) (header *values*) needs its own — `_redact_header_values` — or the value-scan loop gets copy-pasted into both `sanitize_request` and `sanitize_response`. The only legitimate divergence between the two public functions is the object shape they destructure/rebuild.
- **Adapter containment for vcrpy types.** vcrpy's `Request` shape is a moving target (headers are a `dict` in some versions, a list of `(name, value)` tuples in others). `_normalize_headers` absorbs that in one place; no other function shape-branches on header storage. Do not let the concrete `vcr.request.Request` type leak into the public signatures — type them against a module-owned structural shape so a vcrpy bump does not ripple into the contract (adapter / anti-corruption boundary).
- **Bytes catalog scans `str` header values too.** `_BODY_SECRET_PATTERNS` is bytes-typed (bodies are bytes). Header values are `str`; `_redact_header_values` encodes each value (`value.encode("utf-8", "surrogatepass")`), scans with the one bytes catalog, decodes back — one catalog, no parallel str/bytes tuple to keep in sync.
- **`Violation` stays one model.** A full per-kind sum type (`HeaderViolation`/`BodyViolation`/…) is over-engineering for a test-only diagnostic consumed by one CI scanner (Rule 2). Keep the single `Violation` with the `kind` discriminator; the `@model_validator(mode="after")` (AC-9) closes the illegal-field-combination hole with ~6 lines and zero new types. If a later phase grows a fourth violation kind with diverging fields, *that* is the rule-of-three trigger to revisit a proper sum type.
- **Catalogs stay Open/Closed.** The only operation against `_FORBIDDEN_HEADERS` is a membership test on the lowercased header name (`name.lower() in _FORBIDDEN_HEADERS`); the only operation against `_BODY_SECRET_PATTERNS` is `for pat in _BODY_SECRET_PATTERNS`. No function may name-match a specific header — that re-introduces control-flow coupling. Adding `proxy-authorization` later must be a one-line frozenset row.
