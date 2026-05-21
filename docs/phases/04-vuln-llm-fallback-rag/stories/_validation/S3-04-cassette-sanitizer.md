# Validation report: S3-04 — `CassetteSanitizer` pytest-recording hooks

**Validated:** 2026-05-21
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S3-04 ships the load-bearing first layer of ADR-0014's cassette-discipline stack: a
pure-function sanitizer that strips secret HTTP headers and body-scans for shaped
secrets, wired into a new `tests/conftest.py` as `pytest-recording`
`before_record_request`/`before_record_response` hooks, plus a `verify_cassette`
walker that S3-05's CI scanner will reuse.

The story was already detailed and well-traced. Four critics (Coverage, Test-Quality,
Consistency, Design-Patterns) ran in parallel. They converged — independently — on one
**block**: AC-3 declared `_BODY_SECRET_PATTERNS` as `re.Pattern[str]`, but bodies are
`bytes` (AC-4, the TDD red test, and AC-6's `st.binary` strategy). A `str` regex cannot
scan `bytes`; `mypy --strict` (AC-16) rejects it and `re.sub` raises `TypeError` — making
AC-3 / AC-4 / AC-16 mutually unsatisfiable as written. The block has a clean in-place fix
(retype the catalog to `re.Pattern[bytes]` with `rb"..."` literals), so the verdict is
HARDENED, not RESCUE.

Beyond the block, the critics found ~20 genuine harden/nit issues: the idempotence
property only ever exercised the no-op path (random inputs never generate a secret);
`verify_cassette` was not total over the filesystem (it would crash S3-05's directory
walk on the first stub cassette); header-*value* secret scanning lived only as a buried
AC-14 corpus row rather than a first-class behaviour; AC-7 "determinism" was a tautology
with no enforcement; `passed` was a redundant field permitting a silently-passing leak;
and three repo-reality facts were stale (`tests/conftest.py`, `tests/security/`, and the
`pytest-recording` dev-dep do not yet exist). All were fixed in place.

## Findings by critic

### Coverage critic

- **F1 (block)** — AC-3/AC-4 type mismatch: `re.Pattern[str]` cannot scan `bytes` bodies; AC-3/AC-4/AC-16 mutually unsatisfiable.
- **F2 (block)** — No AC for non-UTF-8/binary bodies, yet AC-6's strategy draws `st.binary()` (invalid UTF-8) — a `.decode()` impl crashes the property.
- **F3 (block)** — `verify_cassette` has no ACs for malformed/empty/missing-key/zero-interaction cassettes; S3-05's directory-walking CI scanner would hard-crash on the first stub.
- **F4 (harden)** — AC-6 idempotence property almost never exercises the redaction path (random text/bytes ≈ never secret-shaped).
- **F5 (harden)** — `==` equality in AC-15 / no-op tests is unverifiable for the real `vcr.request.Request` (no value-`__eq__`).
- **F6 (harden)** — AC-11 negative test unsatisfiable within scope (depends on the not-yet-built Anthropic SDK call site + S3-06's diagnostic string).
- **F7 (harden)** — `tests/conftest.py` does not exist; AC-10/AC-12 "exposes/extend" wording misleading; root-conftest blast radius ungated.
- **F8 (harden)** — AC-14(c) header-value scanning is a third behaviour pinned only by one adversarial-corpus row, not by core ACs.
- **F9 (harden)** — No AC pins the real request/response object shape; every TDD test uses a `dict` shim.
- **F10 (nit)** — base64 false-positive calibration ("raise minimum to 48") conflicts with AC-3's hard-coded `{40,}`.

### Test-Quality critic

- **F1 (block)** — AC-6 idempotence only exercises the no-op path; the named double-encoding bug is uncatchable.
- **F2 (harden)** — AC-7 "determinism" is a tautology for any pure function; replace with a `tests/fence/` AST purity check (repo precedent: `test_engines_pure_helpers.py`).
- **F3 (block)** — `re.Pattern[str]` vs `bytes` bodies; the redaction test errors rather than fails meaningfully; `st.binary` decode crashes.
- **F4 (harden)** — No test proves a multi-secret body redacts *all* occurrences (a `replace`-first-match impl passes).
- **F5 (harden)** — `test_innocuous_input_unchanged` satisfied by a total no-op sanitizer; positive/negative corpus split off into separate files, not load-bearing in the red phase.
- **F6 (block)** — `verify_cassette` red test only covers a header violation; body-violation and clean-pass paths untested (a body-blind or always-fail walker passes).
- **F7 (harden)** — AC-14 header-value sneak case has no dedicated red test.
- **F8 (harden)** — The double-encoding `[REDACTED]`-stability case is prose only, not a test.
- **F9 (harden)** — AC-4 "immutable input" mutation discipline has no falsifying test (an in-place `.pop()` impl passes).
- **F10 (harden)** — `_make_request` dict shim diverges from the real vcrpy `Request`; ACs may pass against a fiction.
- **F11 (nit)** — AC-13 env-only check is an environment-dependent vacuous pass; add a `Makefile` static parse.
- **F12 (nit)** — AC-11 asserts a third-party error string — brittle to a library bump, blind to a codegenie regression.
- **F13 (nit)** — base64 `\b` word-boundary shrink-into-match idempotence edge case unverified.

### Consistency critic

- **F1 (harden)** — base64-on-body scan is broader than ADR-0014 §Decision wording, but `phase-arch-design.md §G11` explicitly backs "any header/**body**"; the drift is undocumented — add a trace + recommend an ADR-0014 clarification.
- **F2 (harden)** — `tests/conftest.py` does not exist; "(or extend existing fixture)" wording is dead and misleading; root scope must be stated.
- **F3 (block)** — `re.Pattern[str]` vs `body: bytes` — an unsatisfiable contradiction inside the ACs themselves.
- **F4 (nit, confirmation)** — Files-to-touch matches arch component layout (`src/codegenie/fallback/cassette/`); S3-05 walker correctly deferred.
- **F5 (nit, confirmation)** — Silent-drop commitment honoured (AC-4, AC-17, `_WARNING_IDS = frozenset()`).
- **F6 (harden)** — `pytest-recording` absent from `pyproject.toml`; "(if not already)" hedge risks a skipped add; should be an explicit dev-dep AC.
- **F7 (nit)** — `tests/security/` does not exist; story creates a new top-level test subtree without saying so.
- **F8 (harden)** — AC-14 header-value scanning is an ADR/arch extension labelled "ADDITIVE" but not traced.
- **F9 (nit, confirmation)** — All ACs trace to a source; no orphans.

### Design-Patterns critic

- **F1 (block)** — `re.Pattern[str]` cannot scan `bytes` — one bytes catalog + a normalize boundary; do NOT ship parallel str/bytes tuples (duplicate catalog breaks Open/Closed).
- **F2 (harden)** — `verify_cassette` tangles file I/O with the pure scan walk; extract a pure `_scan_cassette_doc` (functional core / imperative shell — repo precedent `test_engines_pure_helpers.py`).
- **F3 (harden)** — `passed` is a redundant field permitting the illegal state `passed=True` with violations; make it a computed property.
- **F4 (harden)** — `_normalize_headers` adapter should contain the dict-vs-list vcrpy header-shape divergence; keep the concrete `vcr.request.Request` type out of the public signature.
- **F5 (harden)** — `sanitize_request`/`sanitize_response` ~90% duplication; the refactor needs *three* pure helpers (header-value scan needs its own), not two.
- **F6 (nit)** — `Violation`'s optional `header_name`/`pattern` permit illegal combos; add a `@model_validator` rather than over-engineering a per-kind sum type (Rule 2).
- **F7 (harden)** — AC-4/AC-7 "pure"/"deterministic" are prose; add an AST-walking purity fence (`tests/fence/`).
- **F8 (nit, confirmation)** — `_FORBIDDEN_HEADERS`/`_BODY_SECRET_PATTERNS` as iterated `Final` catalogs are the correct Open/Closed pattern; pin "membership-test only, no name-matching".

## Conflict resolutions

- **base64 scope (Consistency F1 vs the implied "match the ADR literally").** ADR-0014 §Decision and arch §Component 12 word the base64 pattern as "header values"; `phase-arch-design.md §G11` words it as "any header/**body**". Consistency wins (source of truth) — and the two sources disagree, with G11 the broader and more security-correct reading. Resolution: keep the broad body+header-value scan, add an explicit trace note to §Context, recommend an ADR-0014 wording clarification. No narrowing.
- **base64 threshold (Coverage F10 wants AC-3 ↔ note agreement; Test-Quality keeps `{40,}`).** Resolution: AC-3 is made the single source of truth at `{40,}`, with the calibration path (raise to 44/48 if AC-15's negative corpus bites) owned by AC-3; the implementer note defers to it. Keeps consistency with ADR-0014/G11's "40+-char" wording.
- **`Violation` sum type (Design F6 illegal-states vs Rule 2 simplicity).** Rule 2 wins over Design-Patterns: a full per-kind sum type is over-engineering for a test-only diagnostic. Resolution: single `Violation` model + a `@model_validator` coupling check — surfaced in Notes for the implementer and folded into AC-9, not a new type hierarchy.
- **Duplicate findings.** The `re.Pattern[str]`-vs-`bytes` block was raised by all four critics (Coverage F1, Test-Quality F3, Consistency F3, Design F1) — merged into one edit on AC-3 (Consistency is the recorded authority; the fix is Design-Patterns' single-bytes-catalog shape).

## Edits applied

1. **Status** → `HARDENED`. Added a `## Validation notes` block under the header.
2. **AC-3** — retyped `_BODY_SECRET_PATTERNS` to `Final[tuple[re.Pattern[bytes], ...]]` with `rb"..."` literals; declared a single catalog (no parallel str/bytes tuples); made `{40,}` the single source of truth for the threshold. *(block — Coverage F1 / Test-Quality F3 / Consistency F3 / Design F1; nit — Coverage F10)*
3. **AC-4** — added the no-mutation clause and the explicit three-scan-surface contract (header names, surviving header values, body); bytes marker `b"[REDACTED]"`. *(Coverage F8, Test-Quality F7/F9, Consistency F8)*
4. **AC-5** — mirrored the three-surface contract; pinned the no-copy-paste / shared-helper requirement. *(Design F5)*
5. **AC-6** — idempotence strategy must bias toward the redaction path; each pattern provably hit; structural-projection equality. *(Coverage F4, Test-Quality F1)*
6. **AC-7** — "determinism" now backed by the AC-23 AST fence instead of a tautological `==` check. *(Test-Quality F2, Design F7)*
7. **AC-8** — added header-value scanning and the explicit clean / empty-cassette pass. *(Coverage F8, Test-Quality F6)*
8. **AC-9** — `passed` made a derived property (illegal `passed=True`-with-violations now unrepresentable); `kind` gained `header_value` + `unreadable`; added the kind/field-coupling `@model_validator`. *(Design F3/F6, Coverage F3)*
9. **AC-10** — states the story *creates* the new repo-root `tests/conftest.py`. *(Coverage F7, Consistency F2)*
10. **AC-11** — rescoped to a behaviour-level cassette-miss assertion; no longer pins a third-party string or requires the unbuilt SDK call site. *(Coverage F6, Test-Quality F12)*
11. **AC-13** — added the `Makefile` static-parse assertion alongside the env check. *(Test-Quality F11)*
12. **AC-19–AC-25 added** — binary-body totality; `verify_cassette` filesystem totality; pure `_scan_cassette_doc`; real-vcrpy-type contract + `_normalize_headers`; `tests/fence/test_sanitizer_purity.py`; `pytest-recording` dev-dep gate; root-conftest suite-wide-green gate. *(Coverage F2/F3/F9, Test-Quality F2/F10, Consistency F6/F7, Design F2/F4/F7)*
13. **TDD plan** — idempotence strategy rewritten with a redaction-biased generator; 11 additional failing-first tests added (multi-secret body, header-value sneak case, no-mutation, `[REDACTED]`-stability, non-UTF-8 body, body/clean/total `verify_cassette`, pure `_scan_cassette_doc`, real-`vcr.request.Request`, per-pattern idempotence). *(Test-Quality F4/F5/F8/F13)*
14. **Implementation outline / Refactor / Files-to-touch** — pyproject step added; four pure helpers + `_scan_cassette_doc`; new fence file row; `tests/security/` `__init__.py` noted; bytes marker in the Green step.
15. **§Context / §References** — added the base64 scope-trace bullet; corrected the `tests/conftest.py` "Existing code" reference. *(Consistency F1/F2)*
16. **Notes for the implementer** — added a Design-pattern guidance block (functional core/imperative shell, three pure helpers, adapter containment for vcrpy types, bytes-catalog scanning of str header values, single `Violation` model, Open/Closed catalog discipline). *(Design F2/F4/F5/F6/F8)*

## Verdict rationale

**HARDENED.** The story's goal, scope, and traceability were sound — no RESCUE conditions
(the goal does not contradict the phase arch; every AC traces to ADR-0014 / G11 / a
CLAUDE.md convention). The one block-severity finding (str-vs-bytes pattern typing) has a
direct, mechanical in-place fix and was applied. The remaining ~20 findings were genuine
hardenings — most consequentially, turning the idempotence property, the three scan
surfaces, mutation discipline, and `verify_cassette` totality from prose/AC-bullets into
falsifiable red tests, so an autonomous executor is now forced through them rather than
able to ship technically-passing-but-wrong code.

## Recommended next step

`phase-story-executor` to implement S3-04. Note for the executor: S3-04 depends on S3-02
(`AnthropicLeafAdapter` — the first cassette source); the sanitizer hooks must be in
`tests/conftest.py` before any cassette is recorded. AC-13's "sole setter" clause is
partially deferred until S3-06 lands `make refresh-cassettes`.
