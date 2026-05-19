# Story S8-02 — `DerivedQuery` Pydantic + TCCM `derived_queries:` additive band

**Step:** Step 8 — `DistrolessMigrationPlugin` manifest + TCCM `derived_queries:` band + plugin loader wiring
**Status:** Ready
**Effort:** M
**Depends on:** S8-01 (manifest exists so the TCCM has a plugin to belong to; not technically required by the schema edit, but the byte-edit allowlist row this story consumes is co-sequenced with the manifest's first appearance)
**ADRs honored:** Phase 7 ADR-0016 (TCCM `derived_queries:` band — primary; this story is the implementation of the ADR's Pydantic-schema half), Phase 7 ADR-0009 row #6 (the one new optional band on `src/codegenie/plugins/tccm.py` is the enumerated byte-edit), Phase 7 ADR-0004 (typed-vocabulary discipline — `DerivedQuery` is frozen + `extra="forbid"`), production ADR-0029 (TCCM `must_read` / `should_read` / `provides` / `requires` bands; the new `derived_queries:` band sits parallel without conflating evidence with computation), production ADR-0033 (sum-type / smart-constructor discipline at boundaries)

## Context

ADR-0016 introduces the additive `derived_queries:` TCCM band — the mechanism that lets a plugin declare "invoke `vuln.provenance(cve_id, package_id, image_ref)` at decision time and load the result alongside the `must_read` evidence." The ADR's load-bearing commitment is that `must_read` continues to mean "evidence to load," and `derived_queries:` is the new band for "computation to invoke." Conflating the two (the security-first lens's original proposal) violates production §2.7 progressive disclosure; the critic's roadmap-6 ruled it out.

The Pydantic shape is fixed by ADR-0016:

```python
class DerivedQuery(_Frozen):
    name: str
    compute: str           # dotted callable path, e.g. "vuln.provenance"
    args: dict[str, str]   # template strings resolved against workflow + repo context

class Tccm(BaseModel):
    must_read: list[EvidenceRef] = []
    should_read: list[EvidenceRef] = []
    provides: list[str] = []
    requires: list[str] = []
    derived_queries: list[DerivedQuery] = []   # NEW BAND
    # extra="forbid"
```

`final-design.md §Synthesis ledger departure #4` and `phase-arch-design.md §Component design §13` confirm. The story implements this against the existing `src/codegenie/plugins/tccm.py` module — the Phase 3 plugin-private TCCM that already houses `must_read` / `should_read` / `may_read` / `provides` / `requires`. The actual existing fields are `must_read: list[ContextQuery]`, `should_read: list[ContextQuery] = []`, `may_read: list[ContextQuery] = []`, `provides: dict[str, dict[str, str]] = {}`, `requires: dict[str, list[str]] = {}` — slightly different shape from the ADR's prose example. The story adds the new band **without** touching the existing fields' types.

**Arg-template syntax — pinned HERE (open question §9):** the canonical syntax is `$name.field` style — `$workflow.cve`, `$workflow.package`, `$repo.base_image`. Specifically:

- A template token starts with `$`, followed by a `^[a-z][a-z0-9_]*$` namespace, a literal `.`, then a `^[a-z][a-z0-9_]*$` field name. Regex: `^\$[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`.
- A non-template literal string (no leading `$`) is passed through verbatim as the arg value.
- Mixed strings (template prefix + literal suffix, e.g. `$workflow.cve-suffix`) are **not** supported in Phase 7. The full string is either a single token or a literal; this is the simplest grammar consistent with the e2e fixture's args.
- The two known namespaces in Phase 7 are `$workflow.*` (resolved from the orchestrator's workflow context — `cve`, `package`) and `$repo.*` (resolved from the gathered `RepoContext` — `base_image`). The set is **closed** for Phase 7; growing it is an additive ADR-0016 amendment.
- The token-vs-literal classification is a **shape check at schema-validation time** (Pydantic `field_validator`); the actual substitution happens at dispatch time in S8-03's loader. This story ships the shape check, not the substitution.

Existing TCCMs (Phase 3's `plugins/vulnerability-remediation--node--npm/tccm.yaml` once it lands, plus any Phase 2 `_reference-tccm` fixtures) must parse unchanged — `derived_queries: list[DerivedQuery] = []` default makes the band purely additive under `extra="forbid"`.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md §Component design §13 (TCCM derived_queries band)`](../phase-arch-design.md) — additive Pydantic-schema field; loader resolves `compute` to imported callable.
  - [`../phase-arch-design.md §Data model — TCCM derived-queries schema`](../phase-arch-design.md) — typed shape and band rationale.
- **Phase ADRs:**
  - [`../ADRs/0016-tccm-derived-queries-band.md`](../ADRs/0016-tccm-derived-queries-band.md) — **primary**. The shape and tradeoffs are pinned here.
  - [`../ADRs/0009-phase-7-byte-edit-allowlist-fence.md`](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) — row #6 enumerates the `tccm.py` edit. (The README labels this as row #6 in the README's row-numbering; ADR-0009 itself lists it under its own enumeration. Pin the assertion to the row the fence test files use.)
  - [`../ADRs/0004-vuln-provenance-primitive-home.md`](../ADRs/0004-vuln-provenance-primitive-home.md) — typed-vocabulary discipline.
- **Production ADRs:**
  - [`../../../production/adrs/0029-task-class-context-manifests.md`](../../../production/adrs/0029-task-class-context-manifests.md) — TCCM bands; `must_read` is evidence, not computation.
  - [`../../../production/design.md §2.7 Progressive disclosure`](../../../production/design.md) — TCCMs index evidence by path.
- **High-level impl:**
  - [`../High-level-impl.md §Step 8`](../High-level-impl.md) — Features delivered bullets 3–4.
- **Source:**
  - [`src/codegenie/plugins/tccm.py`](../../../../src/codegenie/plugins/tccm.py) — existing TCCM Pydantic model. Read end-to-end before editing.
  - Phase 3 plugin precedent at `plugins/vulnerability-remediation--node--npm/tccm.yaml` (if it has landed yet).

## Goal

Extend `src/codegenie/plugins/tccm.py` such that:

1. A new frozen Pydantic model `DerivedQuery` exists with three fields: `name: str`, `compute: str`, `args: dict[str, str]`. `frozen=True, extra="forbid"`.
2. `TCCM` gains exactly one new optional field: `derived_queries: list[DerivedQuery] = []`. **No other byte-changes** to `tccm.py`.
3. The new model validates the `compute:` value's shape (a dotted callable path: `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$` — at least one dot, snake-case throughout) at construction time. The actual callable resolution belongs to S8-03's loader; this story only validates string shape.
4. The new model validates each `args` value as either a template token (matches `^\$[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`) or a non-`$`-prefixed literal string. A mixed-prefix string like `"$workflow.cve-extra"` raises `ValidationError`.
5. Existing TCCMs that do not specify `derived_queries:` parse unchanged — the default empty list applies and no behavior changes.
6. The byte-edit allowlist fence (S5-01) increments exactly one counter (the row for `src/codegenie/plugins/tccm.py`); any other edit is a fence failure.

The plugin-loader callable resolution and the actual `vuln.provenance` wiring are **out of scope** — they ship in S8-03.

## Acceptance criteria

### A. `DerivedQuery` model exists and is frozen

- [ ] `DerivedQuery` is exported from `codegenie.plugins.tccm` (`__all__` updated; verify the existing `__all__` tuple and append `"DerivedQuery"` alphabetically).
- [ ] `model_config = ConfigDict(frozen=True, extra="forbid")`.
- [ ] Fields exactly: `name: str`, `compute: str`, `args: dict[str, str]`.
- [ ] `DerivedQuery(name="provenance", compute="vuln.provenance", args={"cve_id": "$workflow.cve"})` constructs successfully.
- [ ] `DerivedQuery(name="x", compute="x", args={})` constructs successfully (the empty-args case is the minimum valid shape).
- [ ] Mutation raises `pydantic.ValidationError` (frozen contract): `dq.name = "y"` raises.
- [ ] `DerivedQuery(name="provenance", compute="vuln.provenance", args={}, spurious_field=1)` raises `ValidationError` (extra='forbid').

### B. `compute:` shape validation

- [ ] `compute="vuln.provenance"` accepted (one dot, snake-case both sides).
- [ ] `compute="vuln.provenance.v2"` accepted (multiple dots permitted; the loader S8-03 resolves the full dotted path).
- [ ] `compute="vulnprovenance"` (no dot) rejected with `ValidationError`; the message names `compute`.
- [ ] `compute="Vuln.provenance"` (capital) rejected.
- [ ] `compute=".vuln.provenance"` (leading dot) rejected.
- [ ] `compute="vuln."` (trailing dot) rejected.
- [ ] `compute=""` (empty) rejected.
- [ ] `compute="vuln-provenance.x"` (hyphen) rejected — snake-case only.

### C. `args` template-token-vs-literal shape validation

- [ ] `{"cve_id": "$workflow.cve"}` accepted (valid template token).
- [ ] `{"image_ref": "$repo.base_image"}` accepted.
- [ ] `{"package_id": "$workflow.package"}` accepted.
- [ ] `{"literal": "alpine:3.18"}` accepted (literal — no `$` prefix).
- [ ] `{"x": "$workflow.cve-extra"}` rejected (mixed-prefix; `ValidationError` names `args` and the offending value).
- [ ] `{"x": "$workflow"}` rejected (token shape requires `.`).
- [ ] `{"x": "$"}` rejected.
- [ ] `{"x": "$workflow.CVE"}` rejected (capital in field segment).
- [ ] `{"x": "${workflow.cve}"}` rejected (braces are NOT the chosen syntax; open question §9 pins `$ns.field`).
- [ ] An args key that is not a valid snake-case identifier (e.g. `{"Bad-Key": "$workflow.cve"}`) is **accepted** by this story's schema — arg-key validation is the receiving callable's concern, not the manifest's (mirrors ADR-0016 §Tradeoffs row 4). Pin this behavior with an explicit test so a future regression doesn't silently tighten the schema.

### D. `TCCM.derived_queries` additive band

- [ ] `TCCM` model now has a field `derived_queries: list[DerivedQuery] = []`. The field is the **only** addition to the existing model; `must_read`, `should_read`, `may_read`, `provides`, `requires` fields are byte-unchanged.
- [ ] A TCCM YAML/dict without a `derived_queries:` key parses; `tccm.derived_queries == []`.
- [ ] A TCCM YAML/dict with `derived_queries: []` parses; same outcome.
- [ ] A TCCM YAML/dict with one entry parses and `tccm.derived_queries[0].compute == "vuln.provenance"`.
- [ ] The `TCCM` model's `model_config` is **unchanged** — still `frozen=True, extra="forbid"`. (Read the existing config and assert byte-identity in the test if practical.)

### E. Backward-compat — existing TCCMs parse unchanged

- [ ] A round-trip test loads each existing TCCM fixture (e.g., `docs/phases/02-context-gather-layers-b-g/_reference-tccm/tccm.yaml`, plus any Phase 3 TCCM fixtures that have landed) through the post-edit schema and confirms parse success + `derived_queries == []`.
- [ ] No existing TCCM test is deleted, disabled, or marked `xfail`.

### F. Byte-edit allowlist fence + lint gates

- [ ] `pytest tests/fence/test_phase7_no_byte_edits_to_locked_files.py` passes; the row counter for `src/codegenie/plugins/tccm.py` increments by exactly one allowed delta (the additive field + `DerivedQuery` class). The fence's diff-counting logic determines what counts as "one allowed edit" — match its convention; if it counts lines, the addition lines are within the allowed budget.
- [ ] A deliberately-planted spurious edit elsewhere in `tccm.py` (e.g., reordering an existing `must_read: list[ContextQuery]` declaration) fails the fence.
- [ ] `mypy --strict src/codegenie/plugins/tccm.py` clean.
- [ ] `ruff check src/codegenie/plugins/tccm.py` and `ruff format --check src/codegenie/plugins/tccm.py` clean.
- [ ] `make check` green.
- [ ] **Phase 3–6.5 regression suite green; `bench/vuln-remediation/` cassette replay byte-equal (ε ≤ $0.01).**

## Implementation outline

1. **Read `src/codegenie/plugins/tccm.py` end-to-end.** The existing `TCCM` model uses `list[ContextQuery]` for `must_read`/`should_read`/`may_read`. Do not touch those.
2. **Add `_TEMPLATE_TOKEN_RE` and `_DOTTED_CALLABLE_RE` module-level `Final` regexes** (mirror the precedent of `_NAMESPACE_RE`, `_IMPORT_PATH_RE`, `_PRIMITIVE_RE` in the existing module).
   - `_DOTTED_CALLABLE_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")`
   - `_TEMPLATE_TOKEN_RE = re.compile(r"^\$[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")`
   Use `Final[re.Pattern[str]]` typing (existing precedent).
3. **Add `class DerivedQuery(BaseModel)`** with the three fields and two `@field_validator` blocks:
   - `_compute_shape` — `_DOTTED_CALLABLE_RE.fullmatch(v) is None` → `raise ValueError(...)`.
   - `_args_template_or_literal` — for each value, if it starts with `$`, require `_TEMPLATE_TOKEN_RE.fullmatch(v)` else accept (literal).
4. **Add `derived_queries: list[DerivedQuery] = []`** to the existing `TCCM` model. Place it after `requires:` to match ADR-0016's prose ordering.
5. **Update `__all__`** to include `"DerivedQuery"` (alphabetically; existing tuple is `("ContextQuery", "TCCM", "TCCMParseError")` → becomes `("ContextQuery", "DerivedQuery", "TCCM", "TCCMParseError")`).
6. **Write `tests/unit/plugins/test_tccm_derived_queries.py`** — see TDD plan. Cover ACs A–E exhaustively, including backward-compat against existing TCCM fixtures.
7. **Run `pytest tests/unit/plugins/test_tccm_derived_queries.py`** — green.
8. **Run `pytest tests/fence/test_phase7_no_byte_edits_to_locked_files.py`** — green.
9. **Run `make check`** — green.

## TDD plan (red → green → refactor)

### Red — write the test file first

```python
"""S8-02 — DerivedQuery model + TCCM derived_queries band (Phase 7 ADR-0016)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from codegenie.plugins.tccm import TCCM, ContextQuery, DerivedQuery


class TestDerivedQueryShape:
    def test_minimum_valid(self) -> None:
        dq = DerivedQuery(name="provenance", compute="vuln.provenance", args={})
        assert dq.compute == "vuln.provenance"

    def test_full_valid(self) -> None:
        dq = DerivedQuery(
            name="provenance",
            compute="vuln.provenance",
            args={"cve_id": "$workflow.cve", "image_ref": "$repo.base_image"},
        )
        assert dq.args["cve_id"] == "$workflow.cve"

    def test_frozen(self) -> None:
        dq = DerivedQuery(name="x", compute="vuln.provenance", args={})
        with pytest.raises(ValidationError):
            dq.name = "y"  # type: ignore[misc]

    def test_extra_forbid(self) -> None:
        with pytest.raises(ValidationError):
            DerivedQuery(
                name="x", compute="vuln.provenance", args={}, spurious=1
            )  # type: ignore[call-arg]

    @pytest.mark.parametrize(
        "bad",
        [
            "vulnprovenance",          # no dot
            "Vuln.provenance",         # capital
            ".vuln.provenance",        # leading dot
            "vuln.",                   # trailing dot
            "",                        # empty
            "vuln-provenance.x",       # hyphen
        ],
    )
    def test_bad_compute_rejected(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            DerivedQuery(name="x", compute=bad, args={})


class TestArgsTemplateGrammar:
    @pytest.mark.parametrize(
        "value",
        [
            "$workflow.cve",
            "$workflow.package",
            "$repo.base_image",
            "alpine:3.18",      # literal
            "no-dollar",        # literal
            "",                 # literal empty
        ],
    )
    def test_accepted_values(self, value: str) -> None:
        DerivedQuery(name="x", compute="vuln.provenance", args={"k": value})

    @pytest.mark.parametrize(
        "bad",
        [
            "$workflow.cve-extra",   # mixed-prefix
            "$workflow",             # token needs dot
            "$",                     # nothing after $
            "$workflow.CVE",         # capital in field
            "${workflow.cve}",       # braces not chosen syntax
            "$.cve",                 # empty namespace
        ],
    )
    def test_rejected_values(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            DerivedQuery(name="x", compute="vuln.provenance", args={"k": bad})

    def test_args_key_is_not_validated_for_grammar(self) -> None:
        # ADR-0016 §Tradeoffs — arg names validated at callable-dispatch
        # time, not at TCCM-load time. Pin the lenient behavior.
        DerivedQuery(
            name="x", compute="vuln.provenance", args={"Bad-Key": "$workflow.cve"}
        )


class TestTCCMBackwardCompat:
    def _make_query(self) -> ContextQuery:
        return ContextQuery.create(
            "scip.refs", {"symbol": "X"}
        ).unwrap()

    def test_no_derived_queries_key_defaults_empty(self) -> None:
        tccm = TCCM(must_read=[self._make_query()])
        assert tccm.derived_queries == []

    def test_explicit_empty_list(self) -> None:
        tccm = TCCM(must_read=[self._make_query()], derived_queries=[])
        assert tccm.derived_queries == []

    def test_one_entry_parses(self) -> None:
        dq = DerivedQuery(
            name="provenance",
            compute="vuln.provenance",
            args={"cve_id": "$workflow.cve"},
        )
        tccm = TCCM(must_read=[self._make_query()], derived_queries=[dq])
        assert tccm.derived_queries[0].compute == "vuln.provenance"


class TestTCCMExtraForbidPreserved:
    def test_unknown_top_level_key_still_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TCCM(must_read=[], spurious_field=1)  # type: ignore[call-arg]
```

Run — fails because `DerivedQuery` does not exist. That's red.

### Green — minimum implementation

Add `_DOTTED_CALLABLE_RE`, `_TEMPLATE_TOKEN_RE`, `class DerivedQuery(BaseModel)`, and `derived_queries: list[DerivedQuery] = []` on `TCCM`. Re-run; all tests pass.

### Refactor

- Confirm `_DOTTED_CALLABLE_RE` and `_TEMPLATE_TOKEN_RE` are placed alongside the existing `_NAMESPACE_RE` / `_IMPORT_PATH_RE` / `_PRIMITIVE_RE` block — match the file's convention.
- Confirm the new validators raise `ValueError` (not `AssertionError`) so Pydantic wraps them into `ValidationError`. Bare `assert` is banned (`forbidden-patterns` hook); the validators are not assertion-shaped here so the rule does not bite, but spot-check.
- Re-read `__all__`; sort alphabetically.

## Files to touch

- `src/codegenie/plugins/tccm.py` — additive: `_DOTTED_CALLABLE_RE`, `_TEMPLATE_TOKEN_RE`, `class DerivedQuery`, `derived_queries` field on `TCCM`, `"DerivedQuery"` in `__all__`. Allowlist row #6 of S5-01.
- `tests/unit/plugins/test_tccm_derived_queries.py` — new test file.

## Out of scope

- Resolving `compute:` strings to actual imported callables — **S8-03** (plugin loader's responsibility).
- Substituting template tokens (`$workflow.cve` → actual CVE id) at dispatch time — **S8-03**.
- Editing `plugins/vulnerability-remediation--node--npm/tccm.yaml` to add a `derived_queries:` entry — separate concern (S3-03 or a Phase 7 follow-up; allowlist row #2 covers it).
- Writing `plugins/distroless-migration--node--npm/tccm.yaml` — **S8-04** owns the YAML content.
- Editing `src/codegenie/plugins/loader.py` — **S8-03** (allowlist row #7).
- Validating that `$workflow.cve` resolves to a real CVE at TCCM-load time — that's an orchestrator concern; S8-03 surfaces *unknown* `compute:` strings at load, not unbound template values.

## Notes for the implementer

- **The existing `tccm.py` is Phase 3's plugin-private TCCM, not the Phase 2 probe-set TCCM.** The module docstring says so explicitly: "Phase-3 plugin-private capability TCCM ... distinct from `codegenie.tccm.model.TCCM`". Phase 7 extends *this* module, not the other one.
- **Why `_Frozen` becomes `BaseModel` in this codebase:** ADR-0016 prose uses `_Frozen` as shorthand for "a frozen Pydantic BaseModel with `extra='forbid'`." The actual idiom in `tccm.py` is `BaseModel` + `model_config = ConfigDict(frozen=True, extra="forbid")`. Match the existing convention (Rule 11).
- **Why `compute:` is a string, not a `dotted_callable` newtype:** ADR-0016 keeps `compute: str` to avoid forcing a parser at TCCM-load time. The shape regex is the boundary validation; the actual `importlib` resolution lives in S8-03 where it can raise typed `PluginRejected` / `PluginImportError`.
- **Why `args: dict[str, str]` instead of `dict[str, JSONValue]`:** ADR-0016 §Tradeoffs row 4 — arg values are template strings or literal strings. Allowing `int` / `bool` would smuggle the template-vs-literal classification problem into the schema. Phase 7 keeps args as strings; the receiving callable casts as needed.
- **The chosen template syntax (`$ns.field`) is pinned HERE (open question §9).** Phase 8 may want to relax it (e.g., support `${ns.field}` for embedding in larger strings); that is an ADR-0016 amendment, not a silent grammar extension. If the implementer thinks the grammar is wrong, surface it (Rule 1 + Rule 11 disagree-loudly) — do not fork it.
- **No `derived_queries:` *content* in `tccm.yaml` ships in this story.** S8-04 writes the actual YAML for the distroless plugin. S8-02 only proves the schema accepts the shape.
- **Backward-compat against existing TCCMs:** S2 Phase 2 reference TCCM at `docs/phases/02-context-gather-layers-b-g/_reference-tccm/tccm.yaml` is a documentation artifact and may or may not parse against the Phase 3 schema. If it does, include it as a fixture in the round-trip test. If it does not (different schema entirely), surface that in Notes and rely on Phase 3 plugin fixtures instead.
- **Open question §9 closure:** record the pinned syntax in this story's Notes section so the next reader can find it without re-reading ADR-0016. The grammar regex `^\$[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` is the canonical form.
- **Coordination with S3-03:** Phase 3 plugin's `tccm.yaml` (when it lands) may want a `derived_queries:` entry too — allowlist row #2 authorizes it. This story's schema must accept that entry; the AC tests do not need to fixture it, but the schema's `derived_queries: list[DerivedQuery] = []` default ensures it works regardless of timing.
