# Story S3-02 — Pydantic `_ProbeOutputValidator` trust boundary

**Step:** Step 3 — Build the harness internals (cache, coordinator, validator, sanitizer, writer, config)
**Status:** Done — 2026-05-13 (phase-story-executor attempt 1, GREEN — see [`_attempts/S3-02.md`](_attempts/S3-02.md))

## Evidence

- Implementation: [`src/codegenie/coordinator/__init__.py`](../../../../src/codegenie/coordinator/__init__.py) (empty package marker), [`src/codegenie/coordinator/validator.py`](../../../../src/codegenie/coordinator/validator.py) (`JSONValue`, `SECRET_FIELD_PATTERN`, `_ProbeOutputValidator`, iterative `_walk_and_enforce`).
- Tests: [`tests/unit/test_probe_output_validator.py`](../../../../tests/unit/test_probe_output_validator.py) — 85 parametrized cases covering AC-1 .. AC-19.
- Test run: `pytest tests/unit/test_probe_output_validator.py` → 85 passed. Full suite: 294 passed, 1 skipped (mkdocs). Coverage 94.18% > 85% gate.
- Lint/types: `ruff check .` clean, `ruff format --check .` clean, `mypy --strict src/codegenie/` clean.
- Deviation: AC-4's literal "loc MUST include the offending key" is preserved as `errors()[0]["ctx"]["key"]` + `["path"]` rather than tuple-extended `loc` (Pydantic v2 `@field_validator` doesn't expose loc beyond the field name; tests pin `ctx["error"]` instead). See attempt log for details.
**Effort:** S
**Depends on:** S2-05
**ADRs honored:** ADR-0010, ADR-0008, ADR-0007

## Validation notes

Validated: 2026-05-13
Verdict: HARDENED
Findings addressed: 28 total (8 block, 17 harden, 3 nit) across Coverage / Test-Quality / Consistency critics. Zero `NEEDS RESEARCH` tags.

Changes applied:
- AC-4 rewritten to reflect Pydantic v2 wrapping reality — `pydantic.ValidationError` is raised with `errors()[0]["ctx"]["error"]` (or `ValidationError.__cause__`) carrying the `SecretLikelyFieldNameError` (Test-Quality F1, Consistency F2). Resolves internal contradiction between AC-4 / TDD test 3 / implementer note line 136.
- AC-7 wording fixed: "all listed red/green behaviors below" — was "four red-test behaviors" while TDD lists 8+ tests (Coverage F3, Consistency F3).
- AC-9..AC-19 appended:
  - AC-9 `model_validate(asdict(probe_output))` round-trip works for a real `ProbeOutput` constructed in the test (Coverage F1, Test-Quality F7).
  - AC-10 `validator.py` does NOT import `ProbeOutput` from `probes/base.py` — preserves ADR-0007 dataclass-contract seam (Consistency F7).
  - AC-11 secret-shaped key buried at depth ≥ 3 (incl. inside a `list` of dicts) raises (Coverage F5, Test-Quality F5, Consistency F4).
  - AC-12 `bytes` value buried at depth ≥ 2 raises — explicit ADR-0010 §Consequences requirement (Consistency F4, Coverage F6).
  - AC-13 `bool` round-trips as `bool` not `int` — Pydantic v2 `Union` ordering check (Consistency F6).
  - AC-14 empty `schema_slice = {}` is accepted — Phase 0 `LanguageDetectionProbe` edge case (Coverage F10).
  - AC-15 `SECRET_FIELD_PATTERN` exists at module scope as a compiled `re.Pattern` — `S3-03` will import this name (Coverage F9, Consistency F8).
  - AC-16 non-string `schema_slice` keys (`int`, `tuple`) raise — JSON-representable contract (Coverage F8).
  - AC-17 importing `codegenie.coordinator` does NOT pull `pydantic` into `sys.modules` — preserves the cold-start fence (Consistency F5).
  - AC-18 frozenness is actively asserted — mutating an instance attribute raises `ValidationError` (Test-Quality F6).
  - AC-19 recursive walker survives depth 200 without `RecursionError` (caller-side resilience; iterate or cap depth) (Coverage F10, Test-Quality F5).
- TDD plan rewritten end-to-end with mutation-resistant snippets:
  - Parametrized forbidden-type matrix (`bytes`, lambda, `tuple`, `set`, `datetime`, `Path`, `Decimal`, custom-object, `float('nan')`, `float('inf')`) (Test-Quality F3).
  - Parametrized secret-regex alternatives — every alternative in the ADR-0010 regex gets its own row (Test-Quality F4).
  - Parametrized confidence negative-space (`""`, `"HIGH"`, `"unknown"`, trailing-space, `None`, integer) (Test-Quality F9).
  - Error-locus pinning: every `ValidationError` assertion pins `errors()[0]["loc"]` and `["type"]` to prevent "any-error-passes" mutants (Test-Quality F2).
  - Nested-depth tests for both bytes-value and secret-key (Test-Quality F5, Coverage F5/F6).
  - `model_validate(asdict(probe_output))` round-trip test (Test-Quality F7, Coverage F1).
  - Frozenness mutation test (Test-Quality F6).
  - Lazy-import test asserts `pydantic` is not pulled by `import codegenie.coordinator` (Consistency F5).
- Implementer notes expanded: Pydantic v2 wraps every exception inside `@field_validator` in `ValidationError`. The validator raises `SecretLikelyFieldNameError`; S3-05's coordinator dispatch unwraps via `exc.errors()[0]["ctx"]["error"]` and surfaces the typed error to the gather lifecycle (matches ADR-0010 §Consequences and arch design §Edge cases row 5).

Surfaced architectural inconsistencies (not auto-fixed — surgical scope ends at this story):
1. **Regex drift in `High-level-impl.md` Step 3 line ~94.** Names `(?i)(token|secret|password|api[_-]?key|credential|private[_-]?key|ghp_|sk-)`, which differs from ADR-0010 §Decision and this story's AC-4 (`(?i)^.*(secret|token|password|credential|api[_-]?key|auth[_-]?token|bearer|access[_-]?key|private[_-]?key).*$`). ADR-0010 is authoritative (Nygard: ADRs win over impl plan). `High-level-impl.md` should be amended to match. Out-of-band follow-up.
2. **Cross-story coupling in AC-6 / AC-15.** S3-02 lands `SECRET_FIELD_PATTERN`; S3-03's sanitizer story owns the AC that `output/sanitizer.py` imports it. AC-15 above narrows to what S3-02 can verify in isolation.

Full audit log: [_validation/S3-02-probe-output-validator.md](_validation/S3-02-probe-output-validator.md)

## Context

The probe contract (`localv2.md §4`) types `schema_slice: dict[str, Any]` — which means anything (`bytes`, `Callable`, arbitrarily nested) can land in it. ADR-0010 places a Pydantic v2 model `_ProbeOutputValidator` as the trust boundary *inside* the coordinator, between probe `run()` and `OutputSanitizer.scrub`. The validator structurally enforces the "facts, not judgments" rule (`production/design.md §2.2`) by typing `schema_slice` as a recursive `JSONValue` union — no `bytes`, no `Callable`, no `Any`. It also rejects secret-shaped field names at probe-emit time, the first line of defense in front of `OutputSanitizer`'s second-pass repeat.

This is foundational — every probe that runs in Phase 0+ flows through this validator. The dataclass `ProbeOutput` contract from §4 stays dataclass-based (per ADR-0007 / production ADR-0007); the validator is an internal coordinator detail constructed *from* the dataclass.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — Coordinator` — validator lives inside the coordinator dispatch path
  - `../phase-arch-design.md §Data model` — Pydantic envelope at the trust boundary (`JSONValue` recursive union)
  - `../phase-arch-design.md §Edge cases` row 5 — secret-shaped field-name → `SecretLikelyFieldNameError`
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0010-pydantic-probe-output-validator.md` — ADR-0010 — `_ProbeOutputValidator` shape, frozen, `extra="forbid"`, recursive `JSONValue`, secret-field regex, `Literal["high","medium","low"]`
  - `../ADRs/0008-output-sanitizer-two-pass-chokepoint.md` — ADR-0008 — sanitizer's pass-1 is the defense-in-depth repeat of the field-name regex; same secret-regex source
- **Source design:**
  - `../final-design.md §2.3` — Probe contract / Pydantic at trust boundary
  - `../final-design.md §L5` — Coherence check on the two representations (dataclass contract + Pydantic validator)
- **Existing code (if any):**
  - `src/codegenie/probes/base.py` — `ProbeOutput` dataclass (frozen by S2-02 snapshot)
  - `src/codegenie/errors.py` — `SecretLikelyFieldNameError`

## Goal

The coordinator can call `_ProbeOutputValidator.model_validate(asdict(probe_output))` and have a `bytes` / `Callable` value, a `github_token`-named key, or a non-literal `confidence` rejected with a typed error — without `_ProbeOutputValidator` ever being imported from outside the coordinator.

## Acceptance criteria

- [ ] AC-1: `src/codegenie/coordinator/validator.py` defines `_ProbeOutputValidator(BaseModel)` with `model_config = ConfigDict(frozen=True, extra="forbid")`.
- [ ] AC-2: The recursive type `JSONValue = Union[None, bool, int, float, str, list["JSONValue"], dict[str, "JSONValue"]]` is declared with `bool` *before* `int` (Pydantic v2 `Union` ordering — see AC-13) and used for `schema_slice: dict[str, JSONValue]`. `JSONValue` is module-level public so S3-03's sanitizer can re-use the type.
- [ ] AC-3: `confidence` is typed `Literal["high", "medium", "low"]`. Any other value raises `pydantic.ValidationError`; the error's `errors()[0]["loc"]` equals `("confidence",)` and `["type"]` equals `"literal_error"`.
- [ ] AC-4: A `@field_validator("schema_slice")` walks **every key at every nesting depth** (dicts and dicts inside lists) and raises `SecretLikelyFieldNameError` when any key matches `(?i)^.*(secret|token|password|credential|api[_-]?key|auth[_-]?token|bearer|access[_-]?key|private[_-]?key).*$`. Pydantic v2 wraps that raise into a `pydantic.ValidationError`; the wrapped typed error MUST be retrievable via `exc.errors()[0]["ctx"]["error"]` (Pydantic's standard surface for validator-raised exceptions) **OR** via `exc.__cause__` — whichever shape Pydantic v2.7+ produces for non-`ValueError` exceptions raised in a field validator. The error's `errors()[0]["loc"]` MUST include the key that triggered the match (e.g., `("schema_slice", "github_token")` or `("schema_slice", "a", "b", "auth_token")` for depth-3). (validator: rewrote AC-4 — Test-Quality F1, Consistency F2; resolves internal contradiction with implementer-notes line 136.)
- [ ] AC-5: `_ProbeOutputValidator` is named with a leading underscore. `src/codegenie/coordinator/__init__.py` is empty (no re-export) **and** `_ProbeOutputValidator` is NOT named in `coordinator/__init__.__all__`. An explicit unit test asserts `not hasattr(codegenie.coordinator, "_ProbeOutputValidator")` after `import codegenie.coordinator`. (validator: made AC-5 mechanically verifiable — Coverage F4.)
- [ ] AC-6: The compiled `SECRET_FIELD_PATTERN` is declared at module scope (see AC-15). S3-03's sanitizer (separate story) will import this same constant — single source of truth for ADR-0008's defense-in-depth repeat pass. (validator: split into AC-6 + AC-15 — Consistency F8.)
- [ ] AC-7: `tests/unit/test_probe_output_validator.py` covers all behaviors listed in the TDD plan below (≥ 14 test cases after parameter expansion) and is green. (validator: was "four red-test behaviors" — Coverage F3, Consistency F3.)
- [ ] AC-8: `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/coordinator/validator.py`, and `pytest tests/unit/test_probe_output_validator.py -q` are clean.
- [ ] AC-9: `_ProbeOutputValidator.model_validate(dataclasses.asdict(probe_output))` succeeds for a real, valid `ProbeOutput` dataclass instance constructed in the test (mirrors the goal's exact call shape and the coordinator's S3-05 dispatch). The validator must accept a dict that contains **only** the two declared keys `{"schema_slice", "confidence"}` — i.e., S3-05 will project `asdict(...)` down to those two keys before calling `model_validate`. The story's responsibility ends at making `model_validate({"schema_slice": ..., "confidence": ...})` work with `extra="forbid"`; S3-05 owns the projection. (validator: added — Coverage F1/F2, Test-Quality F7, Consistency F7.)
- [ ] AC-10: `src/codegenie/coordinator/validator.py` does **NOT** import `ProbeOutput` (or any other name) from `codegenie.probes.base` or `codegenie.probes`. The validator and the dataclass contract are decoupled per ADR-0007 + ADR-0010 §Decision line 33. Verified by inspecting `validator.py`'s module-level imports in a unit test (parse via `ast.parse(...)`). (validator: added — Consistency F7.)
- [ ] AC-11: A secret-shaped key buried at depth ≥ 3 (including inside a `list[dict]` mid-path, e.g., `{"a": {"b": [{"auth_token": "x"}]}}`) raises a `pydantic.ValidationError` whose wrapped `errors()[0]["ctx"]["error"]` is `SecretLikelyFieldNameError` and whose `loc` includes the buried key. (validator: added — Coverage F5, Test-Quality F5, Consistency F4.)
- [ ] AC-12: A `bytes` (or any non-`JSONValue`) value at depth ≥ 2 (e.g., `{"a": [{"b": b"x"}]}`) is rejected with a `pydantic.ValidationError`. (validator: added — ADR-0010 §Consequences line 52 named requirement; Coverage F6, Consistency F4.)
- [ ] AC-13: A `bool` leaf round-trips as `bool`, not `int` — i.e., `_ProbeOutputValidator(schema_slice={"k": True}, confidence="high").schema_slice["k"] is True` and `type(...) is bool`. This pins Pydantic v2 `Union` member-ordering. (validator: added — Consistency F6.)
- [ ] AC-14: An empty `schema_slice={}` is accepted (Phase 0 `LanguageDetectionProbe` and Phase 1+ probes may legitimately emit `{}` when a layer detects nothing). (validator: added — Coverage F10.)
- [ ] AC-15: `SECRET_FIELD_PATTERN` is defined at module scope as a `re.Pattern[str]` (compiled once via `re.compile(...)`). The compiled object is importable: `from codegenie.coordinator.validator import SECRET_FIELD_PATTERN`. (validator: added — Coverage F9.)
- [ ] AC-16: Non-string `schema_slice` keys (`int`, `tuple`, `bytes`) raise `pydantic.ValidationError` — JSON / YAML cannot represent them, so the trust-boundary rejects them. (validator: added — Coverage F8.)
- [ ] AC-17: After `import codegenie.coordinator`, `pydantic` is NOT in `sys.modules`. (Validates that `coordinator/__init__.py` is empty and that `validator.py` is *not* imported at package-init time — preserves the CLI cold-start fence per `phase-arch-design.md §CLI` line 419.) The test snapshot/restores `sys.modules` to avoid contaminating other tests. (validator: added — Consistency F5.)
- [ ] AC-18: A frozen-model mutation attempt raises `pydantic.ValidationError` — `_ProbeOutputValidator(schema_slice={}, confidence="high").confidence = "low"` raises. (validator: added — Test-Quality F6; mirrors the local idiom in `tests/unit/test_audit_models.py::test_frozen_mutation_raises` per Rule 11.)
- [ ] AC-19: The recursive key-walker MUST NOT raise `RecursionError` on inputs of nesting depth ≤ 200. (Implement with an iterative stack-based walker, or assert sufficient `sys.setrecursionlimit` headroom in a comment + test.) (validator: added — Coverage F10, Test-Quality F5; preserves the coordinator's "never re-raise from validator" failure-isolation contract.)

## Implementation outline

1. Author `src/codegenie/coordinator/__init__.py` (empty package marker; do NOT re-export `_ProbeOutputValidator`).
2. Author `src/codegenie/coordinator/validator.py`. Import `pydantic` at module scope (the coordinator lazy-imports this module from the CLI, so the cold-start budget is preserved at the CLI level).
3. Declare `JSONValue` as a recursive `Union` via `typing.Union` + forward-ref string. Validate at runtime in Pydantic v2 (which supports recursive unions natively).
4. Declare `SECRET_FIELD_PATTERN = re.compile(r"(?i)^.*(secret|token|password|credential|api[_-]?key|auth[_-]?token|bearer|access[_-]?key|private[_-]?key).*$")` at module scope (single source for ADR-0008's defense-in-depth repeat).
5. Implement `_ProbeOutputValidator` with `schema_slice`, `confidence` fields and a `@field_validator("schema_slice")` that walks recursively, raising `SecretLikelyFieldNameError` when a key matches.
6. Write the unit tests for the four red behaviors. Run; commit failing.
7. Run; assert green.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file path: `tests/unit/test_probe_output_validator.py`

Every `pytest.raises(ValidationError)` block MUST pin `errors()[0]["loc"]` and `errors()[0]["type"]` to defeat the "any-validation-error-passes" mutant (Test-Quality F2). Every multi-instance assertion is parametrized to defeat single-instance mutants (Test-Quality F3, F4, F9).

```python
# tests/unit/test_probe_output_validator.py
"""Pydantic _ProbeOutputValidator trust boundary — see ADR-0010, ADR-0008.

Test taxonomy (verifies AC-1 .. AC-19):
- structural shape (AC-1, AC-2, AC-13, AC-14)
- forbidden-type rejection at any depth (AC-2, AC-12, AC-16)
- confidence Literal enforcement (AC-3)
- secret-field-name rejection at any depth (AC-4, AC-11, AC-15)
- forbidden extras (AC-1 with extra="forbid")
- frozenness (AC-1, AC-18)
- ADR-0007 seam — validator decoupled from dataclass (AC-10)
- coordinator-shaped call (AC-9)
- packaging — privacy + lazy import (AC-5, AC-17)
- recursion safety (AC-19)
"""
from __future__ import annotations

import ast
import dataclasses
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from codegenie.coordinator.validator import (
    SECRET_FIELD_PATTERN,
    _ProbeOutputValidator,
)
from codegenie.errors import SecretLikelyFieldNameError


# -----------------------------------------------------------------------------
# AC-2 / AC-12 / AC-16 — forbidden values rejected at depth, regardless of type
# -----------------------------------------------------------------------------
class _CustomObj:  # arbitrary non-JSON-representable class
    pass

FORBIDDEN_LEAVES = [
    pytest.param(b"x", id="bytes"),
    pytest.param(bytearray(b"x"), id="bytearray"),
    pytest.param(lambda: 1, id="callable-lambda"),
    pytest.param((1, 2), id="tuple"),
    pytest.param({1, 2}, id="set"),
    pytest.param(frozenset({1}), id="frozenset"),
    pytest.param(datetime(2026, 5, 13), id="datetime"),
    pytest.param(Path("/tmp"), id="path"),
    pytest.param(Decimal("1.0"), id="decimal"),
    pytest.param(_CustomObj(), id="custom-object"),
]

@pytest.mark.parametrize("bad_leaf", FORBIDDEN_LEAVES)
def test_forbidden_leaf_at_top_level_rejected(bad_leaf):
    """AC-2: every non-JSONValue type is structurally unrepresentable."""
    with pytest.raises(ValidationError) as ei:
        _ProbeOutputValidator(schema_slice={"k": bad_leaf}, confidence="high")
    assert ei.value.errors(), "ValidationError must carry at least one error"
    # locus must include schema_slice (defeats "raise for any reason" mutant)
    locs = {tuple(e["loc"][:1]) for e in ei.value.errors()}
    assert ("schema_slice",) in locs, f"expected schema_slice in {locs}"

@pytest.mark.parametrize("bad_leaf", FORBIDDEN_LEAVES[:3])  # bytes / bytearray / callable
def test_forbidden_leaf_at_depth_2_rejected(bad_leaf):
    """AC-12: deeply-nested bytes/callable rejection — ADR-0010 §Consequences."""
    with pytest.raises(ValidationError) as ei:
        _ProbeOutputValidator(
            schema_slice={"a": [{"b": bad_leaf}]},
            confidence="high",
        )
    locs = {tuple(e["loc"][:1]) for e in ei.value.errors()}
    assert ("schema_slice",) in locs


# AC-2/AC-13/AC-14 — permitted shapes accepted
PERMITTED_INPUTS = [
    pytest.param({}, id="empty"),                                              # AC-14
    pytest.param({"k": None}, id="null"),
    pytest.param({"k": True}, id="bool-true"),
    pytest.param({"k": False}, id="bool-false"),
    pytest.param({"k": 1}, id="int"),
    pytest.param({"k": 1.5}, id="float"),
    pytest.param({"k": "s"}, id="string"),
    pytest.param({"k": []}, id="empty-list"),
    pytest.param({"k": {}}, id="empty-dict"),
    pytest.param({"a": {"b": [{"c": [1, None, "x", True]}]}}, id="deeply-nested-json"),
]

@pytest.mark.parametrize("slice_", PERMITTED_INPUTS)
def test_permitted_inputs_round_trip(slice_):
    """AC-2, AC-13, AC-14 — JSONValue closure accepts JSON-representable shapes."""
    m = _ProbeOutputValidator(schema_slice=slice_, confidence="medium")
    assert m.schema_slice == slice_

def test_bool_round_trips_as_bool_not_int():
    """AC-13: Pydantic v2 Union member-ordering — bool MUST precede int."""
    m = _ProbeOutputValidator(schema_slice={"k": True}, confidence="high")
    assert m.schema_slice["k"] is True
    assert isinstance(m.schema_slice["k"], bool)
    # mutation killer: if Union order is [int, bool, ...], True is coerced to 1
    assert type(m.schema_slice["k"]) is bool  # noqa: E721


# -----------------------------------------------------------------------------
# AC-3 — confidence Literal enforcement
# -----------------------------------------------------------------------------
INVALID_CONFIDENCES = [
    pytest.param("", id="empty-string"),
    pytest.param("HIGH", id="uppercase"),
    pytest.param("High", id="titlecase"),
    pytest.param("high ", id="trailing-space"),
    pytest.param("high_with_caveats", id="extended"),
    pytest.param("unknown", id="extra-value"),
    pytest.param("n/a", id="other"),
    pytest.param(None, id="none"),
    pytest.param(1, id="int"),
    pytest.param(["high"], id="list-wrap"),
]
@pytest.mark.parametrize("bad", INVALID_CONFIDENCES)
def test_confidence_rejects_non_literal(bad):
    with pytest.raises(ValidationError) as ei:
        _ProbeOutputValidator(schema_slice={}, confidence=bad)
    errs = ei.value.errors()
    assert any(tuple(e["loc"]) == ("confidence",) for e in errs), errs
    # at least one error type names literal mismatch (defeats "any-error-passes")
    assert any(e["type"] in ("literal_error", "string_type", "string_pattern_mismatch") for e in errs), errs

@pytest.mark.parametrize("good", ["high", "medium", "low"])
def test_confidence_accepts_each_literal(good):
    _ProbeOutputValidator(schema_slice={}, confidence=good)  # must not raise


# -----------------------------------------------------------------------------
# AC-4 / AC-11 / AC-15 — secret-field-name rejection at any depth
# -----------------------------------------------------------------------------
# every alternative in ADR-0010's regex, plus a casing/separator variant per alternative
SECRET_KEYS = [
    pytest.param("secret", id="secret"),
    pytest.param("client_secret", id="contains-secret"),
    pytest.param("token", id="token"),
    pytest.param("github_token", id="contains-token"),
    pytest.param("password", id="password"),
    pytest.param("DB_PASSWORD", id="password-upper"),
    pytest.param("credential", id="credential"),
    pytest.param("aws_credentials", id="credentials-plural"),
    pytest.param("api_key", id="api_key-underscore"),
    pytest.param("api-key", id="api-key-hyphen"),
    pytest.param("apikey", id="apikey-no-separator"),
    pytest.param("API_KEY", id="api_key-upper"),
    pytest.param("auth_token", id="auth_token"),
    pytest.param("auth-token", id="auth-token-hyphen"),
    pytest.param("bearer", id="bearer"),
    pytest.param("Authorization_bearer", id="bearer-mixed"),
    pytest.param("access_key", id="access_key"),
    pytest.param("access-key", id="access-key-hyphen"),
    pytest.param("private_key", id="private_key"),
    pytest.param("ssh_private_key", id="private_key-prefixed"),
]

def _unwrap_typed_error(exc: ValidationError) -> Exception | None:
    """Pydantic v2 wraps validator exceptions; surface the original.

    Tries the documented surfaces in order: errors()[i]["ctx"]["error"], then
    __cause__. Either is acceptable per AC-4. Returns None if neither carries
    a typed error (which is itself an assertion failure for our purposes).
    """
    for e in exc.errors():
        ctx = e.get("ctx") or {}
        if isinstance(ctx.get("error"), Exception):
            return ctx["error"]
    return exc.__cause__

@pytest.mark.parametrize("secret_key", SECRET_KEYS)
def test_secret_key_at_top_level_rejected(secret_key):
    with pytest.raises(ValidationError) as ei:
        _ProbeOutputValidator(schema_slice={secret_key: "v"}, confidence="high")
    typed = _unwrap_typed_error(ei.value)
    assert isinstance(typed, SecretLikelyFieldNameError), (
        f"expected SecretLikelyFieldNameError; got {type(typed).__name__}: {typed}"
    )

@pytest.mark.parametrize("secret_key", SECRET_KEYS[:5])  # spot-check at depth
def test_secret_key_at_depth_3_via_list_rejected(secret_key):
    """AC-11: walker recurses through dicts AND through list-of-dicts."""
    with pytest.raises(ValidationError) as ei:
        _ProbeOutputValidator(
            schema_slice={"a": {"b": [{secret_key: "v"}]}},
            confidence="high",
        )
    typed = _unwrap_typed_error(ei.value)
    assert isinstance(typed, SecretLikelyFieldNameError)

@pytest.mark.parametrize("benign_key", ["tokenize_result", "decryption_steps", "tokens_used"])
def test_benign_keys_containing_substring_are_still_rejected(benign_key):
    """ADR-0010 §Tradeoffs: regex has false positives; that's the contract — fail loud."""
    with pytest.raises(ValidationError):
        _ProbeOutputValidator(schema_slice={benign_key: 1}, confidence="high")

@pytest.mark.parametrize("safe_key", ["language", "stack", "build_system", "ci_provider", "files"])
def test_non_secret_keys_accepted(safe_key):
    _ProbeOutputValidator(schema_slice={safe_key: "v"}, confidence="high")  # must not raise

def test_secret_field_pattern_is_compiled_at_module_scope():
    """AC-15: S3-03 will import this symbol — pin its presence and shape."""
    import re
    assert isinstance(SECRET_FIELD_PATTERN, re.Pattern)
    # spot-check every alternative the ADR enumerates
    for canonical in ("secret","token","password","credential","api_key",
                      "auth_token","bearer","access_key","private_key"):
        assert SECRET_FIELD_PATTERN.search(canonical), canonical


# -----------------------------------------------------------------------------
# AC-1 — extra="forbid" + frozen
# -----------------------------------------------------------------------------
def test_extra_field_rejected():
    with pytest.raises(ValidationError) as ei:
        _ProbeOutputValidator.model_validate(
            {"schema_slice": {}, "confidence": "low", "rogue": 1}
        )
    errs = ei.value.errors()
    assert any(e["type"] == "extra_forbidden" for e in errs), errs
    assert any(tuple(e["loc"]) == ("rogue",) for e in errs), errs

def test_frozen_model_mutation_raises():
    """AC-18: frozenness actively verified — mirrors test_audit_models idiom."""
    m = _ProbeOutputValidator(schema_slice={}, confidence="high")
    with pytest.raises(ValidationError):
        m.confidence = "low"  # type: ignore[misc]


# -----------------------------------------------------------------------------
# AC-16 — non-string keys
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("bad_key", [1, 1.5, (1, 2), b"x", None, True])
def test_non_string_keys_rejected(bad_key):
    with pytest.raises(ValidationError):
        _ProbeOutputValidator(schema_slice={bad_key: "v"}, confidence="high")


# -----------------------------------------------------------------------------
# AC-9 — coordinator-shaped call: model_validate(asdict(probe_output))
# -----------------------------------------------------------------------------
def test_model_validate_from_asdict_round_trip():
    """AC-9: the goal's exact call shape works for a real ProbeOutput dataclass.

    S3-05 will project the asdict() down to {schema_slice, confidence} before
    calling model_validate (since extra='forbid'); the story's responsibility
    is to make that two-key projection round-trip cleanly.
    """
    from codegenie.probes.base import ProbeOutput
    po = ProbeOutput(
        schema_slice={"language": "typescript", "files": 12},
        raw_artifacts=[],
        confidence="high",
        duration_ms=42,
        warnings=[],
        errors=[],
    )
    projected = {k: v for k, v in dataclasses.asdict(po).items()
                 if k in ("schema_slice", "confidence")}
    m = _ProbeOutputValidator.model_validate(projected)
    assert m.schema_slice == {"language": "typescript", "files": 12}
    assert m.confidence == "high"


# -----------------------------------------------------------------------------
# AC-10 — validator.py does not import ProbeOutput from probes.base
# -----------------------------------------------------------------------------
def test_validator_module_does_not_import_from_probes_base():
    """AC-10: preserves the ADR-0007 dataclass-contract seam."""
    src = Path(__file__).resolve().parent.parent.parent / "src" / "codegenie" / "coordinator" / "validator.py"
    tree = ast.parse(src.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert not mod.startswith("codegenie.probes"), (
                f"validator.py must not import from codegenie.probes (ADR-0007 seam); got: from {mod} import ..."
            )


# -----------------------------------------------------------------------------
# AC-5 + AC-17 — privacy and lazy-import
# -----------------------------------------------------------------------------
def test_validator_not_exported_from_coordinator_package(monkeypatch):
    """AC-5: importing codegenie.coordinator does not expose _ProbeOutputValidator."""
    for mod in list(sys.modules):
        if mod.startswith("codegenie.coordinator"):
            monkeypatch.delitem(sys.modules, mod, raising=False)
    import codegenie.coordinator as pkg
    assert not hasattr(pkg, "_ProbeOutputValidator")
    assert "_ProbeOutputValidator" not in getattr(pkg, "__all__", ())

def test_importing_coordinator_does_not_pull_pydantic(monkeypatch):
    """AC-17: cold-start fence — pydantic stays out of sys.modules until S3-05 dispatches."""
    for mod in list(sys.modules):
        if mod.startswith(("codegenie.coordinator", "pydantic")):
            monkeypatch.delitem(sys.modules, mod, raising=False)
    import codegenie.coordinator  # noqa: F401
    assert "pydantic" not in sys.modules


# -----------------------------------------------------------------------------
# AC-19 — recursion safety
# -----------------------------------------------------------------------------
def test_deeply_nested_dict_does_not_recursion_error():
    """AC-19: depth 200 must validate cleanly — no RecursionError leaks."""
    deepest: object = "leaf"
    for _ in range(200):
        deepest = {"x": deepest}
    # must not raise RecursionError; either accepts or rejects via ValidationError
    try:
        _ProbeOutputValidator(schema_slice={"root": deepest}, confidence="high")
    except ValidationError:
        pass  # acceptable: structural rejection
    except RecursionError:  # pragma: no cover — failure mode
        pytest.fail("recursive walker overflowed Python's stack at depth 200")
```

Run; confirm `ImportError` on `from codegenie.coordinator.validator import ...`. Commit failing.

### Green — make it pass

Land `src/codegenie/coordinator/__init__.py` (empty file). Land `src/codegenie/coordinator/validator.py` with:

1. `JSONValue = Union[None, bool, int, float, str, list["JSONValue"], dict[str, "JSONValue"]]` (order matters — `bool` precedes `int` so `True` doesn't coerce to `1`; AC-13).
2. `SECRET_FIELD_PATTERN = re.compile(r"(?i)^.*(secret|token|password|credential|api[_-]?key|auth[_-]?token|bearer|access[_-]?key|private[_-]?key).*$")` at module scope (AC-15).
3. `_ProbeOutputValidator(BaseModel)` with `model_config = ConfigDict(frozen=True, extra="forbid")`, fields `schema_slice: dict[str, JSONValue]` and `confidence: Literal["high","medium","low"]`.
4. `@field_validator("schema_slice")` that walks **iteratively** (stack-based; deque or list) over every dict key at every depth and through every `list` mid-path. Raises `SecretLikelyFieldNameError(<offending-key>)` on first match (Pydantic v2 will wrap it in `ValidationError`). Iterative walker is the load-bearing implementation choice — defends AC-19.
5. Module docstring cites ADR-0010 §Decision, ADR-0008 §Decision (defense-in-depth), and explains the dataclass-vs-Pydantic seam.

**Pydantic v2 wrapping contract** (critical — Test-Quality F1, Consistency F2): inside a `@field_validator`, raising `SecretLikelyFieldNameError` (a `CodegenieError` subclass, NOT a `ValueError`) is wrapped by Pydantic into a `ValidationError`. The typed error is recoverable via either `exc.errors()[0]["ctx"]["error"]` or `exc.__cause__`. The unit test's `_unwrap_typed_error` helper tries both surfaces; the green-path implementation just `raise SecretLikelyFieldNameError(key)` — no manual wrapping. S3-05's coordinator dispatch will use the same unwrap surface to surface the typed error to the gather lifecycle event.

### Refactor — clean up

- Module docstring cites ADR-0010 §Decision, ADR-0008 §Decision, and explains the dataclass-vs-Pydantic seam (the `model_validate(asdict(...))` dispatch shape per the goal).
- Inline comment on `SECRET_FIELD_PATTERN` notes: "S3-03's `output/sanitizer.py` imports this same constant — single source of truth for ADR-0008's defense-in-depth repeat pass."
- Inline comment above `JSONValue` notes: "`bool` precedes `int` deliberately — Pydantic v2 `Union` ordering; otherwise `True` coerces to `1`."
- `_ProbeOutputValidator` has `model_config = ConfigDict(frozen=True, extra="forbid")` — both are load-bearing.
- The iterative `_walk_keys` helper is module-private (leading underscore) and not exported.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/coordinator/__init__.py` | New — empty package marker |
| `src/codegenie/coordinator/validator.py` | New — `_ProbeOutputValidator`, `JSONValue`, `SECRET_FIELD_PATTERN` |
| `tests/unit/test_probe_output_validator.py` | New — covers all AC-1 .. AC-19 behaviors (≥ 14 test cases after parameter expansion) |

## Out of scope

- **Coordinator dispatch path** (calling the validator post-`probe.run()`) — handled by S3-05.
- **Sanitizer's defense-in-depth repeat pass** — handled by S3-03; imports `SECRET_FIELD_PATTERN` from this module.
- **Schema-validator (Draft 2020-12 envelope check)** — already landed in S2-05 (`schema/validator.py`); this is a different validator (JSON Schema, not Pydantic).
- **Confidence aggregation / Trust-Aware gate logic** — Phase 5+ (`phase-arch-design.md §Agentic best practices`).

## Notes for the implementer

- The dataclass `ProbeOutput` (frozen by S2-02 snapshot) is the *contract*. The Pydantic validator is *internal*. **Do not edit `probes/base.py`** — that's a contract violation per ADR-0007. AC-10 mechanically enforces that `validator.py` does not import from `codegenie.probes`.
- The validator MUST work via `model_validate(<dict>)` because that is how S3-05's coordinator dispatch calls it (`_ProbeOutputValidator.model_validate(asdict(probe_output))` is the goal-statement call shape, projected by the coordinator to the two fields the validator declares — AC-9). Tests cover both the kwargs constructor and the `model_validate({...})` shape.
- Pydantic v2's recursive `Union` works without `model_rebuild()` for simple forward-refs, but you may need `model_rebuild()` if mypy complains. Run `mypy --strict` early. **`bool` MUST precede `int`** in the `Union` — Pydantic v2 uses left-to-right member matching for `Union`, and `bool` is a subclass of `int`, so `int` first would coerce `True` to `1` and silently drop type identity. AC-13 pins this.
- The secret-field regex MUST be a single shared constant (`SECRET_FIELD_PATTERN`) — duplicating it in S3-03 risks drift. The defense-in-depth model in ADR-0008 explicitly says "same regex, two passes." S3-03's sanitizer story owns the AC that confirms the import.
- **The field-validator's walker MUST be iterative**, not recursive (AC-19). Use a `collections.deque` or a list-as-stack to walk dicts/lists, yielding every key encountered. A naive recursive walker will overflow Python's stack on adversarial deep-nesting inputs and raise `RecursionError` — which is *not* a `ValidationError` and breaks the coordinator's failure-isolation contract (`phase-arch-design.md §Edge cases` row 1: "coordinator catches everything into `ProbeOutput(errors=[...])`" — but the validator's contract is to raise *only* `ValidationError`).
- **Pydantic v2 wrapping** (resolves the AC-4/test-3/note-line-136 contradiction from the original story): inside a `@field_validator`, raising any exception (including non-`ValueError` typed errors like `SecretLikelyFieldNameError`) gets caught by Pydantic and wrapped into a `ValidationError`. The original exception is retrievable via `exc.errors()[0]["ctx"]["error"]` and/or `exc.__cause__`. The story's raise is just `raise SecretLikelyFieldNameError(key_name)`. S3-05's coordinator dispatch will use the same unwrap surface to surface the typed error to the `probe.fail` lifecycle event with `error_type="secret-field"`.
- `_ProbeOutputValidator` is imported **only** from `src/codegenie/coordinator/coordinator.py` (which lands in S3-05). The leading underscore is the social signal; AC-5 + AC-17 mechanically enforce that `import codegenie.coordinator` does not expose the validator and does not pull `pydantic`. An import-linter rule may be added in a follow-up if drift appears.
- **Surfaced inconsistency for follow-up (not in this story's scope):** `docs/phases/00-bullet-tracer-foundations/High-level-impl.md` Step 3 line ~94 names a *different* secret regex (`(?i)(token|secret|password|api[_-]?key|credential|private[_-]?key|ghp_|sk-)`) than ADR-0010 / this story's AC-4. ADR-0010 is authoritative. If the implementer encounters the impl-plan regex first, ignore it and use the AC-4 regex.
