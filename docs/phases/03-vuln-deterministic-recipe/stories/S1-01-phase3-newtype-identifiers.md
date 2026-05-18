# Story S1-01 — Phase 3 newtype identifiers + smart constructors

**Step:** Step 1 — Scaffold packages, domain primitives, sum types, and structural CI fences
**Status:** HARDENED
**Effort:** M
**Depends on:** —
**ADRs honored:** ADR-0010 (domain-modeling discipline — newtype every domain identifier), ADR-0001 (Phase-5 contract surface needs `AttemptNumber`, `WorkflowId`, `TransformId` already typed)

## Validation notes (2026-05-18 — phase-story-validator)

This story was hardened from `Ready` → `HARDENED`. Headline changes:

- **Rule-7 conflict resolved.** Original AC-2 prescribed creating `src/codegenie/types/result.py`, but `src/codegenie/result.py` already exists (Phase-2 S1-04 canonical home, consumed by `tccm/loader.py:98`, `skills/loader.py`, `conventions/loader.py:272`). Story now reuses `codegenie.result.{Ok,Err,Result}` and ships *only* the new `ParseError` at `src/codegenie/types/errors.py`. **Do not create `src/codegenie/types/result.py`.**
- **Block-tier verification gap closed.** Original AC-4's "cross-newtype = mypy error" cited `test_identifiers_typecheck.py`, whose swap lines are commented-out prose (Phase-2 S1-05 hardened this same trap). Story now requires an *executable* subprocess-mypy meta-test (AC-4c) parametrized over every Phase-3 newtype.
- **Coverage gap closed.** Original TDD plan enumerated rejection cases for only 8 of 14 parsers; 6 had no rejection case at all. New AC-3 + AC-17 require every parser to have ≥ 1 rejection case + a Hypothesis totality + determinism property test.
- **Family-symmetric closures** mirrored from Phase-2 S1-05 validation: pairwise distinctness, `__name__` pinning, exact-set `__all__`, identity-passthrough via `__init__`, `isinstance` runtime `TypeError` pin, AST source-scan, module-purity invariant, NFKC + ASCII-only adversarial rejection for `parse_package_id` / `parse_branch_name`.
- **Rule-of-three kernel extraction** surfaced for the five regex-shaped parsers (private `_regex_parser` helper; not a registry — that would be pattern soup at this scale).
- **Arch ↔ story API drift documented:** arch pseudo-code shows `PackageId.parse(s)` classmethod; NewType cannot host classmethods, so free-function `parse_<x>(s)` is the only viable shape. Documented in Notes.

Full audit log in `_validation/S1-01-phase3-newtype-identifiers.md`.

## Context

Production ADR-0033 commits the system to newtypes on every domain identifier; Phase 3 is the first phase where this discipline lands across a *plugin contract*, so the catalog of typed primitives must exist before any orchestrator, plugin, registry, recipe engine, event log, or scorer code references one. The critic flagged this in `critique.md §Design-pattern critiques §Missed patterns`: a `WorkflowId ↔ BundleId` swap at any call site is a runtime bug `mypy --strict` cannot catch when both are raw `str`. This story lands the 14 Phase-3-new newtypes and pairs each with a smart constructor returning `Result[T, ParseError]` so external-boundary parsers (YAML manifests, CVE feeds, branch-name validators) have one typed entry point per ID.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C3` — `Concrete` carries a raw `str`; call sites wrap with the Phase-3 newtypes this story ships.
  - `../phase-arch-design.md §Component design C5` — `AttemptSummary.attempt: AttemptNumber`, `ApplyContext.workflow_id: WorkflowId`; S1-04 lands the models, this story lands the types they import.
  - `../phase-arch-design.md §Component design C4` — `TransformId = blake3(diff_bytes)` newtype.
  - `../phase-arch-design.md §Data model` and §Design patterns applied row 4 (Newtype pattern) — the catalog is exhaustive.
  - **Note on arch pseudo-code:** `PackageId.parse(s)` / `BranchName.parse(s)` are illustrated as classmethod-on-type in the arch §Data model block. `NewType` cannot host classmethods (it is a runtime-identity function over `str`). The implementation ships free functions `parse_<x>(s) -> Result[<X>, ParseError]`. The pseudo-code mixes Pydantic-class smart constructors (`PluginScope.parse`, owned by S1-02) and NewType smart constructors in one example block.
- **Phase ADRs:**
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — names every newtype this story must land; smart-constructor convention; `BranchName.parse` regex `^[a-z0-9/_.-]+$`.
  - `../ADRs/0001-ship-phase5-contract-surface-by-name.md` — `_validate_stage6` consumers expect `WorkflowId`/`TransformId`/`AttemptNumber` already typed; Phase 5 amends behavior, not shape.
- **Production ADRs:**
  - `../../../production/adrs/0033-domain-modeling-discipline.md` — the parent rule this story instantiates for Phase 3.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `src/codegenie/result.py` — **canonical `Result[T, E] = Ok[T] | Err[E]` home** (Phase-2 S1-04). Frozen Pydantic discriminated union on `kind`. Re-use; do not fork. Consumers: `tccm/loader.py:98`, `skills/loader.py:230,300,392`, `conventions/loader.py:272`.
  - `src/codegenie/types/identifiers.py` — Phase 2's pattern (`NewType` + module-level `__all__` + docstring naming the owning ADR). Extend, don't rewrite.
  - `tests/unit/types/test_identifiers.py` — round-trip + distinctness shape (5 newtypes). Mirror for the 14 Phase-3 additions, **plus** the family-symmetric closures the Phase-2 S1-05 validation added in remediation (pairwise distinctness, exact-set `__all__`, etc.).
  - `tests/unit/types/test_identifiers_typecheck.py` — **the broken pattern** (commented-out swap lines). Phase-2 S1-05 validation flagged this as block-tier; the executable subprocess-mypy meta-test replaces it. **Do not extend this file with more commented-out lines.**
  - `src/codegenie/tccm/loader.py:98` — first canonical consumer of `Result`: `def load(self, path: Path) -> Result[TCCM, TCCMLoadError]:` — pattern is `(success-type, error-type)`. Mirror.
  - `src/codegenie/probes/node_build_system.py` — precedent for an upstream-owned enum that `identifiers.py` re-exports rather than redefines (`PackageManager`); a related concern when adding `PackageId`/`PrimitiveName`.
- **Prior validation history:**
  - `../../02-context-gather-layers-b-g/stories/_validation/S1-05-identifiers-newtypes.md` — every family-symmetric closure this story mirrors comes from there.

## Goal

Extend `codegenie.types.identifiers` with the 14 Phase-3 newtypes and pair each one with a smart-constructor wrapper returning `Result[T, ParseError]`, so every later Step 1 story (and every downstream Phase 3 module) imports its typed primitives from one canonical home.

## Acceptance criteria

### Catalog + module shape

- [ ] AC-1 — `src/codegenie/types/identifiers.py` exports `PluginId`, `RecipeId`, `TransformId`, `WorkflowId`, `EventId`, `CveId`, `PackageId`, `BranchName`, `BlobDigest`, `RegistryUrl`, `SignalKind`, `PrimitiveName`, `TransformKind`, `AttemptNumber` — each `NewType(<Name>, str)` or `NewType(<Name>, int)` (only `AttemptNumber` is `int`).
- [ ] AC-2 — **No `src/codegenie/types/result.py` is created.** `Result`, `Ok`, `Err` are imported from `codegenie.result` (the canonical Phase-2 S1-04 home). `src/codegenie/types/errors.py` is a *new* file that exports `ParseError` only — a frozen Pydantic `BaseModel` (`model_config = ConfigDict(frozen=True, extra="forbid")`) with two fields `message: str` and `value: str`. No other public names.
- [ ] AC-3 — `src/codegenie/types/parsers.py` exports 14 smart constructors, one per newtype, all pure functions returning `Result[<X>, ParseError]`:
  - `parse_plugin_id(s)` — `^[a-z][a-z0-9-]{0,63}--[a-z][a-z0-9-]{0,31}--[a-z][a-z0-9-]{0,31}$` (the `task--language--build` triple shape; max 130 chars total).
  - `parse_recipe_id(s)` — `^[a-z][a-z0-9_-]{0,63}$` (kebab/snake; ≤ 64).
  - `parse_transform_id(s)` — `^[0-9a-f]{64}$` (BLAKE3 hex, lowercase only; rejects uppercase).
  - `parse_workflow_id(s)` — `^[0-7][0-9A-HJKMNP-TV-Z]{25}$` (ULID 26-char Crockford base32).
  - `parse_event_id(s)` — `^[0-7][0-9A-HJKMNP-TV-Z]{25}$` (ULID; same shape as `WorkflowId`).
  - `parse_cve_id(s)` — `^CVE-\d{4}-\d{4,7}$` (MITRE format; bounded suffix length to reject `CVE-2024-1234567890123`).
  - `parse_package_id(s)` — `^<npm-name>@<pinned-semver>$` where `<npm-name>` matches `^(?:@[a-z0-9-_.]+/)?[a-z0-9-_.]+$` (lowercase npm rules, scope optional) and `<pinned-semver>` matches `^\d+\.\d+\.\d+(?:-[0-9A-Za-z.+-]+)?$` (pinned exact; ranges `^4.0.0`/`~4.0.0`/`>=4.0.0` rejected). NFKC normalize input first; reject any byte > 0x7F.
  - `parse_branch_name(s)` — `^[a-z0-9/_.-]+$`, length 1..200, NFKC normalize first, reject any byte > 0x7F, reject leading `.`, trailing `/`, or `//`.
  - `parse_blob_digest(s)` — `^[0-9a-f]{64}$` (algorithm-agnostic at type level; rejects uppercase hex).
  - `parse_registry_url(s)` — must start with lowercased `https://`; max length 2048; reject userinfo (`user:pass@host`); reject query string; reject fragment; host must be ASCII (no IDN); host regex `^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*$`; port optional, numeric only.
  - `parse_signal_kind(s)` — `^[a-z][a-z0-9_]*$` (snake; open registry).
  - `parse_primitive_name(s)` — `^[a-z][a-z0-9_]*$` (same shape as `SignalKind`).
  - `parse_transform_kind(s)` — `^[a-z][a-z0-9_]*$`.
  - `parse_attempt_number(n: int)` — only signature taking `int`. `Ok` iff `n > 0` and `n <= 1024` (open-registry-tier upper bound; Phase 5 retry budget is policy, not type-level; cap rejects negative-overflow + sentinel-like values).

### Verification — distinctness, naming, exports, identity (family-symmetric, from Phase-2 S1-05)

- [ ] AC-4a — **Round-trip:** for every newtype `X` and every happy-path string `s`, `parse_<x>(s) == Ok(value=X(s))`.
- [ ] AC-4b — **Rejection:** every parser has ≥ 1 parametrized deliberately-bad input → `Err(ParseError(value=the_bad_input))`. The rejection table covers (at minimum) the M1–M14 mutations from the validation report: lowercase CVE id, uppercase BlobDigest hex, `http://` registry URL, `user@host` userinfo, query/fragment, semver range, partial semver, U+200B and U+FEFF and full-width digits in `parse_branch_name`/`parse_package_id`, `AttemptNumber` ∈ {`0`, `-1`, `-2**31`, `"1"` (str-not-int)}, `SignalKind` uppercase.
- [ ] AC-4c — **Cross-newtype substitution = mypy error, executed in CI:** `tests/unit/types/test_identifiers_phase3_mypy_negative.py` writes a temp `.py` file containing `from codegenie.types.identifiers import WorkflowId, TransformId; def _accept_workflow(_x: WorkflowId) -> None: ...; _accept_workflow(TransformId("...")),` subprocess-invokes `mypy --strict <tmp>.py`, and asserts (a) non-zero exit, (b) the expected `error: Argument 1 to "_accept_workflow"` substring in stdout. Parametrized over **every** Phase-3 newtype pair (≥ 14 distinct swap cases). The existing `tests/unit/types/test_identifiers_typecheck.py` with commented-out swap lines is **not** the test of record for AC-4c.
- [ ] AC-5 — `mypy --strict src/codegenie/types/` clean; the new modules (`errors.py`, `parsers.py`) and the extended `identifiers.py` are included in the existing strict surface.
- [ ] AC-6 — `ruff check`, `ruff format --check` clean on touched files.
- [ ] AC-7 — Module-level `__all__` is sorted; docstring on each newtype names ADR-0010 and the immediate Phase 3 consumer (e.g., `"# WorkflowId — landed for S1-04 ApplyContext + S6-04 RemediationOrchestrator."`).
- [ ] AC-8 — TDD plan's red test exists, committed, green.
- [ ] AC-9 — **`__name__` pinning:** for every newtype `X` in the catalog, `getattr(ids, "X").__name__ == "X"`. Catches `WorkflowId = NewType("Workflow_Id", str)` typos that would silently mislabel in mypy error messages and stack traces.
- [ ] AC-10 — **Pairwise distinctness:** parametrized test over all 14 Phase-3 newtypes plus the 7 Phase-0/1/2 names (`IndexId`, `SkillId`, `TaskClassId`, `IndexName`, `ProbeId`, `Language`, `ConventionId`) — every pair `(A, B)` with `A != B` satisfies `A is not B`. Catches `WorkflowId = TransformId = NewType("Id", str)` aliasing.
- [ ] AC-11 — **Exact-set `__all__`:** `set(codegenie.types.identifiers.__all__) == EXPECTED_PHASE2_NAMES | EXPECTED_PHASE3_NAMES` (exact equality, not `⊇`). Catches stowaway exports (`re`, `NewType` leaks).
- [ ] AC-12 — **Identity passthrough through `__init__`:** for every new name `X`, `codegenie.types.X is codegenie.types.identifiers.X` (parametrized; rejects accidental re-wrapping or string-assignment in `__init__.py`).
- [ ] AC-13 — **`isinstance` runtime TypeError pin:** for every new newtype `X`, `with pytest.raises(TypeError): isinstance("foo", X)`. Pins the documented `NewType`-is-not-a-class footgun so a future contributor doesn't add silent `isinstance` checks.
- [ ] AC-14 — **NFKC + ASCII-only adversarial:** `parse_package_id` and `parse_branch_name` reject (parametrized): NUL byte (`"\x00"`), zero-width space (`"​"`), zero-width no-break space (`"﻿"`), full-width digit (`"１"`), NFKC-equivalent homoglyphs. Input is NFKC-normalized *before* regex match; post-normalization any byte > 0x7F → `Err`.
- [ ] AC-15 — **Docstring discipline (machine-verified):** `src/codegenie/types/identifiers.py` carries a module-level `_NEWTYPE_REGISTRY: Final[Mapping[str, str]]` with one entry per newtype mapping `name → one-line docstring naming ADR + consumer story`. Test asserts `_NEWTYPE_REGISTRY.keys() == set(__all__)` and every value is non-empty + names `ADR-0010`. Removes the per-newtype-comment convention's drift risk.
- [ ] AC-16 — **Module purity (AST source-scan):** `tests/unit/types/test_module_purity.py` AST-walks `errors.py` and `parsers.py`; asserts the `import` set is exactly `{__future__, typing, re, unicodedata, pydantic, codegenie.result, codegenie.types.identifiers}` (no logger, no fs, no sibling packages). Mirrors S1-05 module-purity precedent.
- [ ] AC-17 — **Hypothesis property tests** (`tests/unit/types/test_parsers_properties.py`):
  - **Totality:** for any `s: str` drawn from `hypothesis.strategies.text()` (and any `n: int` for `parse_attempt_number`), the parser returns `isinstance(r, (Ok, Err))` and *never raises* (wrap in `try/except Exception: pytest.fail(...)`).
  - **Determinism:** `parse_<x>(s) == parse_<x>(s)` for any drawn input (catches non-deterministic regex / Pydantic mutability bugs).
  - **Round-trip identity for happy inputs:** for `s` drawn from `hypothesis.strategies.from_regex(parser_rx, fullmatch=True)`, `parse_<x>(s).unwrap() == <X>(s)`. Run on the 13 str-parsers.
- [ ] AC-18 — **Helper extraction at rule of three:** the five regex-shaped parsers (`parse_cve_id`, `parse_branch_name`, `parse_signal_kind`, `parse_primitive_name`, `parse_transform_kind`) consume a single module-private helper `_regex_parser(rx: re.Pattern[str], *, max_len: int, name: str) -> Callable[[str], Result[str, ParseError]]` (or an equivalent closure-free direct-call helper). The helper is the only place the "regex match + length cap → `Ok(<X>(s))` | `Err(ParseError(...))`" shape exists. Observable assertion: AST-walk of `parsers.py` shows at most ONE occurrence of the substring `re.compile(...).fullmatch(` *outside* the helper's body. Adding a 6th regex parser must require zero edits to the helper.

## Implementation outline

1. Add `src/codegenie/types/errors.py`: frozen Pydantic `ParseError(message: str, value: str)`. Single class. No `Result`/`Ok`/`Err` here — those live at `codegenie.result`.
2. Extend `src/codegenie/types/identifiers.py` with the 14 newtypes. Match the existing docstring convention. Add the module-level `_NEWTYPE_REGISTRY` (AC-15).
3. Add `src/codegenie/types/parsers.py` with 14 smart constructors. The five regex-shaped parsers go through the private `_regex_parser` helper (AC-18). Each parser is a pure function: `def parse_<x>(s: str) -> Result[<X>, ParseError]: ...`. Use `Ok(value=...)` / `Err(error=...)` keyword instantiation (mirrors `tccm/loader.py` idiom — discriminator-on-`kind` requires the value/error keyword to disambiguate).
4. Update `__all__` in `src/codegenie/types/identifiers.py` (sorted, includes the 14 new types). Update `codegenie.types.__init__` to re-export the new names (and the `parsers` module surface if intended public).
5. Land `tests/unit/types/test_identifiers_phase3.py`: parametrized happy + sad paths for every parser; pairwise distinctness; `__name__` pinning; exact-set `__all__`; identity passthrough; `isinstance` TypeError; NFKC adversarial; docstring registry.
6. Land `tests/unit/types/test_identifiers_phase3_mypy_negative.py`: subprocess-`mypy --strict` over a tmp swap file; parametrized over all 14 newtypes (AC-4c).
7. Land `tests/unit/types/test_parsers_properties.py`: Hypothesis totality + determinism + round-trip-identity (AC-17).
8. Land `tests/unit/types/test_module_purity.py` (or extend an existing one): AST-walk on `errors.py` + `parsers.py` (AC-16).
9. Run `mypy --strict src/codegenie/types/` + `make check` locally.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/types/test_identifiers_phase3.py`

```python
from __future__ import annotations

import pytest

from codegenie.result import Err, Ok
from codegenie.types.errors import ParseError
from codegenie.types.identifiers import (
    AttemptNumber, BlobDigest, BranchName, CveId, EventId,
    PackageId, PluginId, PrimitiveName, RecipeId, RegistryUrl,
    SignalKind, TransformId, TransformKind, WorkflowId,
)
from codegenie.types.parsers import (
    parse_attempt_number, parse_blob_digest, parse_branch_name,
    parse_cve_id, parse_event_id, parse_package_id,
    parse_plugin_id, parse_primitive_name, parse_recipe_id,
    parse_registry_url, parse_signal_kind, parse_transform_id,
    parse_transform_kind, parse_workflow_id,
)


# --- Happy paths (one per parser; AC-4a) ---

@pytest.mark.parametrize(
    "parser,good,wrapper",
    [
        (parse_cve_id, "CVE-2024-21501", CveId),
        (parse_branch_name, "feat/add-thing.v1", BranchName),
        (parse_blob_digest, "0" * 64, BlobDigest),
        (parse_workflow_id, "01HXX00000000000000000000Z", WorkflowId),
        (parse_event_id, "01HXX00000000000000000000Z", EventId),
        (parse_registry_url, "https://registry.npmjs.org", RegistryUrl),
        (parse_signal_kind, "build_ok", SignalKind),
        (parse_primitive_name, "subprocess_jail", PrimitiveName),
        (parse_transform_kind, "lockfile_pin", TransformKind),
        (parse_package_id, "lodash@4.17.21", PackageId),
        (parse_plugin_id, "vulnerability-remediation--node--npm", PluginId),
        (parse_recipe_id, "npm-lockfile-pin", RecipeId),
        (parse_transform_id, "a" * 64, TransformId),
    ],
)
def test_parser_happy_path(parser, good, wrapper):
    r = parser(good)
    assert isinstance(r, Ok)
    assert r.value == wrapper(good)


def test_attempt_number_happy_path():
    r = parse_attempt_number(3)
    assert isinstance(r, Ok)
    assert r.value == AttemptNumber(3)


# --- Rejection cases (AC-4b; mutation-kill matrix M1-M14 from validation report) ---

@pytest.mark.parametrize(
    "parser,bad",
    [
        (parse_cve_id, "cve-2024-21501"),                       # lowercase
        (parse_cve_id, "CVE-2024-1234567890123"),               # too long
        (parse_blob_digest, "A" * 64),                          # uppercase hex
        (parse_blob_digest, "0" * 63),                          # wrong length
        (parse_registry_url, "http://registry.npmjs.org"),      # wrong scheme
        (parse_registry_url, "https://user:pw@registry.npmjs.org"),  # userinfo
        (parse_registry_url, "https://registry.npmjs.org/?p=1"),     # query
        (parse_registry_url, "https://registry.npmjs.org/#frag"),    # fragment
        (parse_signal_kind, "BuildOk"),                          # uppercase
        (parse_primitive_name, "1leading_digit"),               # leading digit
        (parse_transform_kind, "kebab-not-snake"),              # kebab disallowed
        (parse_package_id, "lodash@4.0"),                       # partial semver
        (parse_package_id, "lodash@^4.0.0"),                    # range
        (parse_package_id, "LODASH@4.0.0"),                     # uppercase name
        (parse_package_id, "lodash"),                           # no version
        (parse_plugin_id, "vuln--node"),                        # missing third dim
        (parse_recipe_id, "Has Spaces"),                        # whitespace
        (parse_transform_id, "g" * 64),                         # non-hex
    ],
)
def test_parser_rejects(parser, bad):
    r = parser(bad)
    assert isinstance(r, Err)
    assert r.error.value == bad


@pytest.mark.parametrize("bad", ["", "feature branch", "../escape", "A" * 201, ".dotleading", "trailing/"])
def test_branch_name_rejects(bad):
    r = parse_branch_name(bad)
    assert isinstance(r, Err)
    assert r.error.value == bad


@pytest.mark.parametrize("bad", [0, -1, -(2**31), 1025])
def test_attempt_number_rejects(bad):
    r = parse_attempt_number(bad)
    assert isinstance(r, Err)


# --- NFKC + ASCII-only adversarial (AC-14) ---

@pytest.mark.parametrize(
    "parser,bad",
    [
        (parse_branch_name, "feat​branch"),    # zero-width space
        (parse_branch_name, "﻿branch"),         # BOM
        (parse_branch_name, "feat\x00branch"),       # NUL
        (parse_package_id, "lodash​@4.17.21"),  # ZWS in name
        (parse_package_id, "lodash@１.0.0"),     # full-width digit (NFKC -> "1.0.0" but still rejects pre-normalization)
    ],
)
def test_adversarial_unicode_rejected(parser, bad):
    r = parser(bad)
    assert isinstance(r, Err)


# --- Catalog + identity invariants (AC-9, AC-10, AC-11, AC-12, AC-13) ---

PHASE3_NAMES = {
    "PluginId", "RecipeId", "TransformId", "WorkflowId", "EventId", "CveId",
    "PackageId", "BranchName", "BlobDigest", "RegistryUrl", "SignalKind",
    "PrimitiveName", "TransformKind", "AttemptNumber",
}
PHASE2_NAMES = {
    "ConventionId", "IndexId", "IndexName", "Language", "PackageManager",
    "ProbeId", "SkillId", "TaskClassId",
}


def test_newtype_names_pinned():
    import codegenie.types.identifiers as ids
    for name in PHASE3_NAMES:
        nt = getattr(ids, name)
        assert nt.__name__ == name, f"{name!r} has __name__={nt.__name__!r}"


def test_pairwise_distinct():
    import codegenie.types.identifiers as ids
    all_names = sorted(PHASE2_NAMES | PHASE3_NAMES - {"PackageManager"})  # PM is not a NewType
    objs = [getattr(ids, n) for n in all_names]
    for i, a in enumerate(objs):
        for b in objs[i + 1 :]:
            assert a is not b


def test_all_is_exact_set():
    import codegenie.types.identifiers as ids
    assert set(ids.__all__) == PHASE2_NAMES | PHASE3_NAMES


def test_identity_passthrough_via_init():
    import codegenie.types as pkg
    import codegenie.types.identifiers as ids
    for name in PHASE3_NAMES:
        assert getattr(pkg, name) is getattr(ids, name)


@pytest.mark.parametrize("name", sorted(PHASE3_NAMES - {"AttemptNumber"}))
def test_isinstance_raises_typeerror(name):
    import codegenie.types.identifiers as ids
    nt = getattr(ids, name)
    with pytest.raises(TypeError):
        isinstance("foo", nt)  # type: ignore[arg-type]


# --- Docstring registry (AC-15) ---

def test_newtype_registry_matches_all():
    from codegenie.types.identifiers import _NEWTYPE_REGISTRY, __all__
    assert set(_NEWTYPE_REGISTRY.keys()) == set(__all__)
    for name, doc in _NEWTYPE_REGISTRY.items():
        assert doc.strip(), f"{name} has empty docstring"
        assert "ADR-0010" in doc, f"{name} docstring missing ADR-0010 citation"
```

State why it fails: `ImportError` — `codegenie.types.errors`, `codegenie.types.parsers`, and the 14 new names in `identifiers.py` don't exist.

The subprocess-mypy meta-test goes in `tests/unit/types/test_identifiers_phase3_mypy_negative.py`:

```python
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# Pairs swap (accepts_<A>) with a value of type <B>; mypy --strict must reject.
SWAP_PAIRS = [
    ("WorkflowId", "TransformId"),
    ("WorkflowId", "EventId"),
    ("TransformId", "BlobDigest"),
    ("CveId", "PackageId"),
    ("PluginId", "RecipeId"),
    ("BranchName", "RegistryUrl"),
    ("SignalKind", "PrimitiveName"),
    ("SignalKind", "TransformKind"),
    ("AttemptNumber", "WorkflowId"),   # int-vs-str swap
    ("PrimitiveName", "TransformKind"),
    ("RecipeId", "TransformId"),
    ("EventId", "PluginId"),
    ("PackageId", "BranchName"),
    ("RegistryUrl", "BlobDigest"),
]


@pytest.mark.parametrize("a,b", SWAP_PAIRS)
def test_mypy_rejects_cross_newtype_swap(tmp_path: Path, a: str, b: str) -> None:
    src = textwrap.dedent(
        f"""
        from codegenie.types.identifiers import {a}, {b}

        def _accept_{a.lower()}(_x: {a}) -> None: ...

        _accept_{a.lower()}({b}({'1' if b == 'AttemptNumber' else '"x"'}))
        """
    )
    tmp = tmp_path / "swap.py"
    tmp.write_text(src)
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(tmp)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0, f"mypy --strict accepted {a} <- {b}; output:\n{result.stdout}"
    assert "incompatible type" in result.stdout.lower() or "argument" in result.stdout.lower(), (
        f"mypy rejected but not for the expected reason; stdout:\n{result.stdout}"
    )
```

The Hypothesis property tests go in `tests/unit/types/test_parsers_properties.py`:

```python
from __future__ import annotations

import re
import pytest
from hypothesis import given, strategies as st

from codegenie.result import Err, Ok
from codegenie.types import parsers as P

ALL_STR_PARSERS = [
    P.parse_plugin_id, P.parse_recipe_id, P.parse_transform_id,
    P.parse_workflow_id, P.parse_event_id, P.parse_cve_id,
    P.parse_package_id, P.parse_branch_name, P.parse_blob_digest,
    P.parse_registry_url, P.parse_signal_kind,
    P.parse_primitive_name, P.parse_transform_kind,
]


@pytest.mark.parametrize("parser", ALL_STR_PARSERS, ids=lambda p: p.__name__)
@given(s=st.text(max_size=300))
def test_total_function(parser, s):
    try:
        r = parser(s)
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"{parser.__name__}({s!r}) raised {type(e).__name__}: {e!r}")
    assert isinstance(r, (Ok, Err))


@pytest.mark.parametrize("parser", ALL_STR_PARSERS, ids=lambda p: p.__name__)
@given(s=st.text(max_size=300))
def test_deterministic(parser, s):
    assert parser(s) == parser(s)


@given(s=st.from_regex(r"^CVE-\d{4}-\d{4,7}$", fullmatch=True))
def test_cve_id_round_trip(s):
    r = P.parse_cve_id(s)
    assert isinstance(r, Ok)
    assert r.value == s


@given(n=st.integers(min_value=1, max_value=1024))
def test_attempt_number_round_trip(n):
    r = P.parse_attempt_number(n)
    assert isinstance(r, Ok)
    assert r.value == n
```

### Green — minimal pass

- Add `src/codegenie/types/errors.py` with `ParseError`.
- Append the 14 `NewType` lines + the `_NEWTYPE_REGISTRY` mapping to `src/codegenie/types/identifiers.py`. Update `__all__` exact.
- Add `src/codegenie/types/parsers.py` with 14 `parse_<x>` functions returning `Result`. Compose the five regex-shaped parsers through `_regex_parser` (AC-18).
- Update `src/codegenie/types/__init__.py` to re-export new names.

### Refactor

- Lift shared regex patterns to module-level `Final` constants with comment naming the spec (e.g., `_CVE_RX: Final = re.compile(r"^CVE-\d{4}-\d{4,7}$")  # MITRE CVE ID format`). Same for the ULID alphabet (`_ULID_RX`), npm name (`_NPM_NAME_RX`), pinned semver (`_PINNED_SEMVER_RX`), URL host (`_HOST_RX`).
- Docstring each parser with a one-liner naming its boundary (`"""External boundary: YAML plugin.yaml; ADR-0010."""`).
- Confirm `_regex_parser` is the only call site of `.fullmatch(` outside of the URL host check (which has its own structural validation).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/types/identifiers.py` | Append 14 newtypes; add `_NEWTYPE_REGISTRY`; update `__all__` exact. |
| `src/codegenie/types/errors.py` | NEW — `ParseError` only (no `Result`/`Ok`/`Err`; those live at `codegenie.result`). |
| `src/codegenie/types/parsers.py` | NEW — 14 smart constructors + private `_regex_parser` helper. |
| `src/codegenie/types/__init__.py` | Re-export the 14 new names; assert identity-passthrough. |
| `tests/unit/types/test_identifiers_phase3.py` | NEW — happy/sad/distinctness/identity/docstring/isinstance. |
| `tests/unit/types/test_identifiers_phase3_mypy_negative.py` | NEW — subprocess `mypy --strict` swap-rejection meta-test (AC-4c). |
| `tests/unit/types/test_parsers_properties.py` | NEW — Hypothesis totality + determinism + round-trip (AC-17). |
| `tests/unit/types/test_module_purity.py` | NEW (or extend) — AST source-scan on `errors.py` + `parsers.py` (AC-16). |

## Out of scope

- **`PluginScope` parsing** — handled by S1-02 (uses `parse_plugin_id`, `parse_*` for dim values, but the scope sum type itself ships there).
- **`AttemptSummary` / `ApplyContext` Pydantic models** — handled by S1-04.
- **Tagged-union outcome types** — handled by S1-03.
- **Fence tests asserting no raw `str` for domain IDs** — handled by S1-05 (`test_no_any_in_plugin_surface.py` covers part; a dedicated `test_no_raw_str_for_domain_ids.py` is left as a follow-up per ADR-0010 §Consequences).
- **Pickling / serialization helpers** — Pydantic on consuming models handles this; no JSON encoders here.
- **`src/codegenie/types/result.py`** — explicitly NOT created. The canonical `Result` lives at `src/codegenie/result.py` (Phase-2 S1-04).

## Notes for the implementer

- **Do NOT create `src/codegenie/types/result.py`.** It would fork the canonical `codegenie.result` (Phase-2 S1-04, consumed by `tccm/loader.py:98`, `skills/loader.py`, `conventions/loader.py:272`). This is a Rule-7 ("Surface conflicts, don't average them") and CLAUDE.md "Match the existing convention" violation. The new module is `src/codegenie/types/errors.py` containing *only* `ParseError`.
- **Instantiate `Ok(value=...)` and `Err(error=...)` with keyword arguments.** `codegenie.result.Result = Annotated[Ok[T] | Err[E], Field(discriminator="kind")]` — the discriminator on `kind` requires the value/error keyword for unambiguous Pydantic construction. Mirror the `tccm/loader.py:98` idiom.
- **`AttemptNumber` is `int`, not `str`.** Everything else in the 14 is `str`-backed. `parse_attempt_number(n: int) -> Result[AttemptNumber, ParseError]` — the only parser that takes a non-`str` argument. Open upper bound is `1024`; the rationale is "Phase 5 retry budget is policy, not type-level; a cap rejects negative-overflow + obviously-wrong sentinels". Production ADR-0014 defaults to 3 retries per gate.
- **`PackageId` is `<name>@<pinned-semver>` per npm**, not just `<name>`. The smart constructor must accept `lodash@4.17.21` and `@scope/pkg@1.0.0` (scoped) and reject `lodash` (no version), `LODASH@4.17.21` (name regex), `lodash@^4.0.0` (range), `lodash@4.0` (partial semver). Pinned exact only — Phase 3 vuln-remediation operates on fixed versions; ranges have no lookup answer.
- **`BlobDigest` is algorithm-agnostic at the type level** — both SHA-256 (64 hex) and BLAKE3 32-byte (64 hex) fit. The regex enforces 64 lowercase hex chars and nothing more. The *interpretation* (which hash algorithm) is a property of the producer (`TransformId` uses BLAKE3 per arch C4); the type kernel does not encode it.
- **`RegistryUrl` is strict-`https://` ASCII.** Reject `http://`, `javascript:`, missing scheme, userinfo (`user:pass@host`), query string, fragment, IDN. The hardened shape exists because adversarial `.npmrc` redirects are an explicit attack surface (Phase 3 E7 edge case; ADR-0001's `RegistryAllowlist`).
- **Arch ↔ NewType API drift.** `phase-arch-design.md §Data model` shows `PackageId.parse(s)` as classmethod-on-type. `NewType` cannot host classmethods (it is identity-to-`str` at runtime, no class body). Free-function `parse_<x>(s)` is the only viable shape. Do not "fix" the arch pseudo-code by introducing Pydantic wrapper classes — that would break the kernel-tier discipline. The arch §Data model mixes Pydantic-class smart constructors (`PluginScope.parse`, owned by S1-02) and NewType smart constructors in one block.
- **Helper at rule-of-three (AC-18).** Five regex-shaped parsers cross the abstraction threshold. The helper is module-private (`_regex_parser`) and consumed by exactly those five. Do NOT introduce a `@register_parser` decorator or a `ParserRegistry` — parsers are kernel-tier, closed-set, not user-extensible (rejected design-pattern finding D-F5).
- **Match the existing docstring convention** in `identifiers.py` — `_NEWTYPE_REGISTRY` formalizes the "each newtype names its ADR + consumer" practice and makes it AST-verifiable (AC-15).
- **`mypy --strict` is the bar, not pyright.** The repo has no pyright config; use mypy's `reveal_type` for diagnostic spot-checks during development. CI must execute the subprocess-mypy meta-test (AC-4c); leaving the cross-newtype assertion as commented-out prose (the broken Phase-2 S1-05 pattern) is forbidden.
- **`Language` is already in `identifiers.py`** (Phase-2 S2-01). The 14 Phase-3 names exclude it. Pairwise-distinctness test still covers it (it must not collide with any Phase-3 name).
- **Existing `IndexName` / `SkillId` / `ConventionId` newtypes** (already in `identifiers.py`) are the convention to mirror — same `NewType("X", str)` shape, same docstring style, same `__all__` discipline.
