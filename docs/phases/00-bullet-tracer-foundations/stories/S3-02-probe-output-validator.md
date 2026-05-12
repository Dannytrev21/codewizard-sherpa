# Story S3-02 — Pydantic `_ProbeOutputValidator` trust boundary

**Step:** Step 3 — Build the harness internals (cache, coordinator, validator, sanitizer, writer, config)
**Status:** Ready
**Effort:** S
**Depends on:** S2-05
**ADRs honored:** ADR-0010, ADR-0008

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

- [ ] `src/codegenie/coordinator/validator.py` defines `_ProbeOutputValidator(BaseModel)` with `model_config = ConfigDict(frozen=True, extra="forbid")`.
- [ ] The recursive type `JSONValue = Union[None, bool, int, float, str, list["JSONValue"], dict[str, "JSONValue"]]` is declared and used for `schema_slice: dict[str, JSONValue]`.
- [ ] `confidence` is typed `Literal["high", "medium", "low"]`. Any other value raises `pydantic.ValidationError`.
- [ ] A field-validator on `schema_slice` walks all keys recursively and raises `SecretLikelyFieldNameError` when any key matches `(?i)^.*(secret|token|password|credential|api[_-]?key|auth[_-]?token|bearer|access[_-]?key|private[_-]?key).*$`.
- [ ] `_ProbeOutputValidator` is named with a leading underscore and not exported from `coordinator/__init__.py`.
- [ ] The same compiled secret-regex is referenced (or re-imported) by `output/sanitizer.py` in S3-03 — single source of truth lives here (module-level `SECRET_FIELD_PATTERN`).
- [ ] `tests/unit/test_probe_output_validator.py` covers all four red-test behaviors below and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/coordinator/validator.py`, `pytest tests/unit/test_probe_output_validator.py -q` are clean.

## Implementation outline

1. Author `src/codegenie/coordinator/__init__.py` (empty package marker; do NOT re-export `_ProbeOutputValidator`).
2. Author `src/codegenie/coordinator/validator.py`. Import `pydantic` at module scope (the coordinator lazy-imports this module from the CLI, so the cold-start budget is preserved at the CLI level).
3. Declare `JSONValue` as a recursive `Union` via `typing.Union` + forward-ref string. Validate at runtime in Pydantic v2 (which supports recursive unions natively).
4. Declare `SECRET_FIELD_PATTERN = re.compile(r"(?i)^.*(secret|token|password|credential|api[_-]?key|auth[_-]?token|bearer|access[_-]?key|private[_-]?key).*$")` at module scope (single source for ADR-0008's defense-in-depth repeat).
5. Implement `_ProbeOutputValidator` with `schema_slice`, `confidence` fields and a `@field_validator("schema_slice")` that walks recursively, raising `SecretLikelyFieldNameError` when a key matches.
6. Write the unit tests for the four red behaviors. Run; commit failing.
7. Run; assert green.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_probe_output_validator.py`

```python
# tests/unit/test_probe_output_validator.py
from codegenie.errors import SecretLikelyFieldNameError
from pydantic import ValidationError

def test_validator_rejects_bytes_in_schema_slice():
    # arrange: schema_slice with a bytes value at a leaf.
    # act: _ProbeOutputValidator(schema_slice={"k": b"x"}, confidence="high")
    # assert: pydantic.ValidationError raised; message names the offending field.
    ...

def test_validator_rejects_callable_in_schema_slice():
    # arrange: schema_slice with a lambda at a leaf.
    # act: _ProbeOutputValidator(schema_slice={"k": (lambda: 1)}, confidence="high")
    # assert: pydantic.ValidationError raised.
    ...

def test_validator_rejects_secret_field_name():
    # arrange: schema_slice = {"github_token": "ghp_xyz"} (matches token regex)
    # act: _ProbeOutputValidator(schema_slice=..., confidence="high")
    # assert: SecretLikelyFieldNameError raised (not generic ValidationError).
    ...

def test_validator_rejects_non_literal_confidence():
    # arrange: confidence = "high_with_caveats"
    # act: _ProbeOutputValidator(schema_slice={}, confidence="high_with_caveats")
    # assert: pydantic.ValidationError raised.
    ...

def test_validator_accepts_deeply_nested_json():
    # arrange: schema_slice with nested dicts/lists of JSON primitives.
    # act: model_validate(...)
    # assert: no error; frozen model returned.
    ...

def test_validator_rejects_extra_fields():
    # arrange: model_validate({"schema_slice":{}, "confidence":"low", "rogue": 1})
    # assert: ValidationError (extra="forbid").
    ...
```

Run; confirm `ImportError` or `AttributeError`. Commit.

### Green — make it pass

Land `validator.py` with `JSONValue`, `_ProbeOutputValidator`, the recursive field-validator that walks dicts/lists checking keys against `SECRET_FIELD_PATTERN`. Field-validator raises `SecretLikelyFieldNameError` (subclass of `CodegenieError`) — note this is a *re-raise* of a typed error inside a `@field_validator`, not a Pydantic `ValueError`. Per ADR-0010 §Decision, the typed error surfaces to the coordinator.

### Refactor — clean up

- Module docstring cites ADR-0010 §Decision and explains the dataclass-vs-Pydantic seam.
- Inline comment on `SECRET_FIELD_PATTERN` notes that `output/sanitizer.py` imports the same constant (per ADR-0008 defense-in-depth — same regex, two passes).
- `_ProbeOutputValidator` is `model_config = ConfigDict(frozen=True, extra="forbid")` — both are load-bearing.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/coordinator/__init__.py` | New — empty package marker |
| `src/codegenie/coordinator/validator.py` | New — `_ProbeOutputValidator`, `JSONValue`, `SECRET_FIELD_PATTERN` |
| `tests/unit/test_probe_output_validator.py` | New — covers six rejection / acceptance behaviors |

## Out of scope

- **Coordinator dispatch path** (calling the validator post-`probe.run()`) — handled by S3-05.
- **Sanitizer's defense-in-depth repeat pass** — handled by S3-03; imports `SECRET_FIELD_PATTERN` from this module.
- **Schema-validator (Draft 2020-12 envelope check)** — already landed in S2-05 (`schema/validator.py`); this is a different validator (JSON Schema, not Pydantic).
- **Confidence aggregation / Trust-Aware gate logic** — Phase 5+ (`phase-arch-design.md §Agentic best practices`).

## Notes for the implementer

- The dataclass `ProbeOutput` (frozen by S2-02 snapshot) is the *contract*. The Pydantic validator is *internal*. Do not edit `probes/base.py` — that's a contract violation per ADR-0007.
- Pydantic v2's recursive `Union` works without `model_rebuild()` for simple forward-refs, but you may need `model_rebuild()` if mypy complains. Run `mypy --strict` early.
- The secret-field regex MUST be a single shared constant (`SECRET_FIELD_PATTERN`) — duplicating it in S3-03 risks drift. The defense-in-depth model in ADR-0008 explicitly says "same regex, two passes."
- The field-validator must walk *recursively*. A key at depth 5 that matches the secret regex must still raise. Use a small helper `_walk_keys(value)` and yield each key encountered.
- `SecretLikelyFieldNameError` is raised inside a Pydantic field-validator, which Pydantic wraps in its own `ValidationError`. The coordinator must catch the original or unwrap — document this expectation in the docstring, but the *raising* in this story is just `raise SecretLikelyFieldNameError(...)`. S3-05 handles the catch.
- Don't import `_ProbeOutputValidator` anywhere except `src/codegenie/coordinator/coordinator.py` (which lands in S3-05). The leading underscore is the social signal; an import-linter rule can be added in a follow-up if drift appears.
