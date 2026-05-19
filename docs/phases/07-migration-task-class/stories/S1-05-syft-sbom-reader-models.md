# Story S1-05 — `SyftSbom` Pydantic reader

**Step:** Step 1 — Scaffold `vuln.provenance` primitive — newtypes, Provenance union, Protocol, errors, SyftSbom reader, fences
**Status:** GREEN
**Effort:** S
**Depends on:** S1-01
**ADRs honored:** ADR-0004 (the SBOM reader lives under `src/codegenie/primitives/vuln_provenance/syft_reader.py`; this story's AC-7 implicitly amends ADR-0004 §Consequences by re-exporting `SyftArtifact` + `SyftLocation` in addition to `SyftSbom` — consumer adapters need typed annotation access), Phase 2 deliberate-decision carry-forward (`extra="allow"` on the SBOM surface — this is the *single* exception to the "everything is `extra="forbid"`" rule), production ADR-0038 (the contract names `SyftSbom` + `SyftArtifact` + `SyftLocation`; `locations[].layerID` is the load-bearing field), ADR-0004 §Consequences smart-constructor-bypass fence (no `model_construct()` call sites under the primitive tree; this story plants the per-file structural assertion since `syft_reader.py` is the deserialization surface most likely to attract such a shortcut)

## Validation notes (2026-05-19 — phase-story-validator pass)

Verdict: **HARDENED**. Edits in this pass:

- **AC-4 strengthened** — round-trip claim was asserted in prose but not by test. Added an explicit `model_dump_json` re-validation step and a follow-up parse to prove unknown fields survive the full encode → decode → encode cycle. Mutation note: an impl that silently dropped unknown fields on serialization would now fail.
- **AC-3 strengthened** — multi-location artifact case added (real syft outputs commonly carry several `locations[]` entries per artifact). The `first-non-empty-layerID-wins` invariant the adapters depend on is purely an adapter-side concern (S4-02 / S4-03), but this story's model contract must at minimum admit + iterate `len(locations) > 1` without surprise.
- **AC-2.5 (new) — empty-SBOM happy path** — promoted from implicit (it was hiding inside AC-2) to an explicit positive constraint; `SyftSbom.model_validate({"artifacts": []})` is a legitimate state the adapters call sites must handle.
- **AC-8.5 (new) — no `model_construct()` call sites** — ADR-0004 §Consequences names this fence at the primitive-tree level; this story plants the per-file structural assertion because `syft_reader.py` is the file most likely to attract a `model_construct(...)` shortcut (it's the deserialization surface). AST-walk fence in the existing module-purity test file.
- **TDD plan** — added concrete test bodies for module-purity (was named, not specified), multi-location round-trip, unknown-fields lossless round-trip, and `model_construct` AST fence. Executor no longer has to invent any test body.
- **Notes-for-implementer** — recorded two deferred design-pattern opportunities (`frozen=True`, `LayerID` newtype) with the *why-we-don't-now* rationale so the executor doesn't silently add either; recorded the Hypothesis property-test option as an optional hardening hint (deferred — single fixture + multi-location case is sufficient mutation pressure for this story).

Conflict resolution log:
- *Coverage* asked for an "every conceivable extra-field shape" property test; *Consistency* + Rule 2 said "single realistic fixture plus targeted unknown-field cases is enough for a types-only story". Consistency-wins-over-coverage: surfaced as a Notes hint, not promoted to AC. The S4-04 AST fence is the load-bearing structural defense; this story does not need to recapitulate it.
- *Design-Patterns* asked for `frozen=True` to make post-deserialization mutation a `ValidationError`. *Consistency* + Rule 2 said "no caller mutates `SyftSbom`; adding frozen=True now is premature abstraction". Consistency wins; recorded as an evaluated-and-rejected alternative in Notes so the executor doesn't add it silently and so a future story can revisit if a mutation site appears.

Full report: `_validation/S1-05-syft-sbom-reader-models.md`.

## Context

The `NpmVulnProvenanceAdapter` (S3-02), `AlpineVulnProvenanceAdapter` (S4-02), and `sbom_verifier.py` (S4-01) all read a syft-generated SBOM to attribute a CVE to a layer. The SBOM schema is upstream-controlled and evolves; making it strict (`extra="forbid"`) at the Pydantic boundary would fail any deserialization the moment syft ships a new field. The arch + Phase 2 deliberate decision: **`SyftSbom` is the one tolerated `dict[str, Any]`-like surface** — `model_config = ConfigDict(extra="allow")`. Defense is at the *consumer* boundary: every adapter reads only known fields (`locations[].layerID`, `name`, `version`), enforced by S4-04's AST-walk fence (`test_alpine_adapter_reads_known_fields_only.py`).

This story lands the three Pydantic models — `SyftSbom`, `SyftArtifact`, `SyftLocation` — with the `extra="allow"` discipline and the known-field shape pinned. Critic Gap-3 (SBOM byte-level trust beyond layer attribution) is mitigated structurally: even if syft's JSON adds malicious-looking fields, `extra="allow"` admits them silently as `dict[str, Any]` payload inside the model, and the adapter-side fence (landed in S4-04) blocks any adapter from recursing into them.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §1` — `from .syft_reader import SyftSbom` in the primitive's public surface.
  - `../phase-arch-design.md §Data model` "Internal — SBOM (Phase 2 deliberate extra='allow')" block — names the three models + `model_config = ConfigDict(extra="allow")` + `layerID` as load-bearing.
  - `../phase-arch-design.md §Gap analysis §Gap 3` — "SBOM byte-level trust beyond layer attribution" — mitigation is read-known-fields-only at adapters; this story plants the load-bearing field shape.
  - `../phase-arch-design.md §Edge cases` row 1 — poisoned `locations[].layerID` flows through `sbom_verifier.py` (S4-01) → `Unknown(reason="sbom_layer_attribution_absent")`.
  - `../phase-arch-design.md §Anti-patterns avoided` — "Untyped `dict[str, Any]`: SyftSbom carries extra='allow' deliberately."
- **Phase ADRs:**
  - `../ADRs/0004-vuln-provenance-primitive-home.md` — Consequences clause: `syft_reader.py` is a module under the primitive.
- **Production ADRs:**
  - `../../../production/adrs/0038-vulnerability-provenance-attribution.md` — the contract this story makes loadable.
- **Source design:**
  - `../final-design.md §Synthesis ledger` — "SyftSbom: extra='allow' + adapter-side known-fields-only fence" (Phase 2 carry-forward).
- **Existing code:**
  - Existing Pydantic models under `src/codegenie/probes/` — read the established `model_config = ConfigDict(...)` style. The vast majority use `extra="forbid"`; this story is one of the few deliberate `extra="allow"` exceptions.
  - `src/codegenie/primitives/vuln_provenance/types.py` (from S1-02/S1-03) — `_Frozen` base. **Do NOT subclass `_Frozen`** here — the SBOM models need `extra="allow"`, which is the inverse posture. Declare a separate base or no base.
- **External docs:**
  - Anchore Syft JSON schema — the upstream contract this reader consumes. The fields this story names are `name`, `version`, `locations[].path`, `locations[].layerID`. Everything else flows through `extra="allow"`.

## Goal

Land three Pydantic models under `src/codegenie/primitives/vuln_provenance/syft_reader.py` — `SyftSbom`, `SyftArtifact`, `SyftLocation` — with `model_config = ConfigDict(extra="allow")`, the four known fields (`SyftArtifact.name`, `SyftArtifact.version`, `SyftLocation.path`, `SyftLocation.layerID`) declared with proper types, and a deserialization round-trip happy-path test pinning a minimal syft JSON shape. **No reader function, no I/O** — this story is models-only.

## Acceptance criteria

- [ ] **AC-1 — Three models, `extra="allow"`.** `src/codegenie/primitives/vuln_provenance/syft_reader.py` declares:
  ```python
  from pydantic import BaseModel, ConfigDict

  class SyftLocation(BaseModel):
      model_config = ConfigDict(extra="allow")
      path: str
      layerID: str | None = None   # load-bearing — read by Alpine/Distroless adapters

  class SyftArtifact(BaseModel):
      model_config = ConfigDict(extra="allow")
      name: str
      version: str
      locations: list[SyftLocation] = []

  class SyftSbom(BaseModel):
      model_config = ConfigDict(extra="allow")
      artifacts: list[SyftArtifact] = []
  ```
  Note: the arch §Data model also shows `source: SyftSource`, `distro: SyftDistro | None`, `descriptor: dict[str, Any]` — those are **deferred** to a future story (the manifest is unambiguous: this story ships *only* the three core models and the four known fields; richer parsing waits for first consumer demand). A `# TODO(future)` comment in the file names the deferral.
- [ ] **AC-2 — `extra="allow"` admits unknown fields.** Test: `SyftSbom.model_validate({"artifacts": [], "spdx_version": "2.3", "unknown_field": [1, 2, 3]})` succeeds (does not raise). The unknown fields are silently admitted; accessing them via `__pydantic_extra__` works but is NOT a tested affordance (adapters never reach into `__pydantic_extra__` — S4-04 plants the AST fence).
- [ ] **AC-2.5 — Empty-SBOM happy path is an explicit, positive state.** `SyftSbom.model_validate({"artifacts": []})` succeeds; `sbom.artifacts == []` and `len(sbom.artifacts) == 0` both hold. Likewise `SyftArtifact.model_validate({"name": "x", "version": "1"})` yields `art.locations == []`. The adapter side relies on these defaults — an impl that made `artifacts` or `locations` mandatory would silently break realistic syft outputs.
- [ ] **AC-3 — Known fields are typed and validated.** Test matrix:
  - `SyftArtifact(name="openssl", version="3.0.7")` → ok; `locations` defaults to `[]`.
  - `SyftArtifact(name=None, version="3.0.7")` → `ValidationError` (`name` is `str`, not optional).
  - `SyftLocation(path="/usr/bin/openssl", layerID="sha256:abc...")` → ok.
  - `SyftLocation(path="/usr/bin/openssl")` → ok; `layerID` defaults to `None`.
  - `SyftLocation(path=None)` → `ValidationError`.
  - **Multi-location artifact.** `SyftArtifact.model_validate({"name": "x", "version": "1", "locations": [{"path": "/a", "layerID": "sha256:aaa"}, {"path": "/b", "layerID": "sha256:bbb"}, {"path": "/c"}]})` yields three `SyftLocation` instances; iteration order matches input order (Pydantic preserves list order); the third has `layerID is None`. Real syft outputs frequently carry multiple `locations[]` per artifact; the model contract must admit + preserve them.
- [ ] **AC-4 — Round-trip via realistic JSON snippet, including unknown-field preservation.** A fixture under `tests/fixtures/syft/minimal_alpine.json` (small — < 1 KB) carries a syft JSON shape with one artifact, one location, one `layerID`, plus 2-3 unknown top-level fields (`schema`, `descriptor`, `source`). The test performs a full encode → decode → encode cycle:
  1. `sbom1 = SyftSbom.model_validate_json(raw)` — succeeds.
  2. `dump1 = sbom1.model_dump(mode="json")` — produces a dict that contains both the known fields (`artifacts[0].name == "openssl"`, `artifacts[0].locations[0].layerID == "sha256:abc123"`) **and** the unknown top-level fields (`"schema"`, `"descriptor"`, `"source"` all present).
  3. `sbom2 = SyftSbom.model_validate(dump1)` — succeeds; `sbom2.artifacts[0].locations[0].layerID == sbom1.artifacts[0].locations[0].layerID`.

  **Mutation note:** an impl that silently dropped unknown fields on serialization (e.g., used `model_dump(exclude_unset=True)` internally or set `model_config = ConfigDict(extra="ignore")`) would pass AC-2 but fail AC-4. AC-4 is the structural defense against such drift.
- [ ] **AC-5 — `layerID` is load-bearing.** A dedicated test pins the field name (not `layer_id`, not `LayerID`) — the syft JSON uses camelCase. A renaming would silently break adapter resolution.
  ```python
  def test_location_layer_id_field_name():
      loc = SyftLocation.model_validate({"path": "/x", "layerID": "sha256:abc"})
      assert loc.layerID == "sha256:abc"
      # And NOT via snake_case:
      with pytest.raises(AttributeError):
          loc.layer_id  # type: ignore[attr-defined]
  ```
- [ ] **AC-6 — Module-level `_KNOWN_LOCATION_FIELDS` catalog.** A `Final[frozenset[str]] = frozenset({"path", "layerID"})` declared at module top so S4-04's AST-walk fence can import it and use it as the source-of-truth allowlist when verifying adapters read only known fields. The same pattern exists for `_KNOWN_ARTIFACT_FIELDS = frozenset({"name", "version", "locations"})`. **This is the seam S4-04 fences against.**
- [ ] **AC-7 — `vuln_provenance/__init__.py` re-exports.** `from codegenie.primitives.vuln_provenance import SyftSbom, SyftArtifact, SyftLocation` succeeds. (The internal catalogs `_KNOWN_*_FIELDS` are NOT re-exported — they're module-private; tests/fences read them via direct-module import.)
- [ ] **AC-8 — Module purity.** AST-walk test on `syft_reader.py` asserts imports are a subset of `{__future__, typing, pydantic}`. No filesystem I/O, no logging, no sibling imports — the reader is types-only at this stage. (Test body in TDD plan.)
- [ ] **AC-8.5 — No `model_construct()` call sites in `syft_reader.py`.** ADR-0004 §Consequences calls out a fence against `model_construct()` use inside the primitive tree (it is the smart-constructor bypass that would let an adapter skip Pydantic validation and feed adapter logic an unvalidated dict). `syft_reader.py` is the deserialization surface most likely to attract such a shortcut. An AST-walk test in `tests/unit/primitives/vuln_provenance/test_syft_reader_module_purity.py` asserts no `Call` node in this file has `attr == "model_construct"`. (Test body in TDD plan.)
- [ ] **AC-9 — Gates.** `mypy --strict src/codegenie/primitives/vuln_provenance/` clean; `ruff check`, `ruff format --check` clean; `make lint-imports` green; Phase 0/1/2/3 + Phase 5/6.5 regression suite green.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline

1. Create `src/codegenie/primitives/vuln_provenance/syft_reader.py`:
   - Imports: `from __future__ import annotations`; `from typing import Final`; `from pydantic import BaseModel, ConfigDict`.
   - Module-level `_KNOWN_LOCATION_FIELDS: Final[frozenset[str]] = frozenset({"path", "layerID"})`.
   - Module-level `_KNOWN_ARTIFACT_FIELDS: Final[frozenset[str]] = frozenset({"name", "version", "locations"})`.
   - `SyftLocation`, `SyftArtifact`, `SyftSbom` classes, each `model_config = ConfigDict(extra="allow")`.
2. Update `src/codegenie/primitives/vuln_provenance/__init__.py` to re-export `SyftSbom`, `SyftArtifact`, `SyftLocation`.
3. Land fixture `tests/fixtures/syft/minimal_alpine.json`:
   ```json
   {
     "schema": "syft-2.3",
     "source": {"type": "image", "target": "alpine:3.18"},
     "descriptor": {"name": "syft", "version": "1.0.0"},
     "artifacts": [
       {
         "name": "openssl",
         "version": "3.0.7-r0",
         "locations": [
           {"path": "/usr/bin/openssl", "layerID": "sha256:abc123"}
         ]
       }
     ]
   }
   ```
4. Land tests (red-first).
5. Run `mypy --strict` + `make check`.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/unit/primitives/vuln_provenance/test_syft_reader.py`

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from codegenie.primitives.vuln_provenance import (
    SyftArtifact,
    SyftLocation,
    SyftSbom,
)
from codegenie.primitives.vuln_provenance import syft_reader as sr


FIXTURE = Path("tests/fixtures/syft/minimal_alpine.json")


# --- extra="allow" admits unknown fields (AC-2) ------------------------------

def test_syft_sbom_admits_unknown_fields():
    payload = {
        "artifacts": [],
        "spdx_version": "2.3",
        "unknown_field": [1, 2, 3],
    }
    sbom = SyftSbom.model_validate(payload)
    assert sbom.artifacts == []


def test_syft_artifact_admits_unknown_fields():
    artifact = SyftArtifact.model_validate({
        "name": "openssl",
        "version": "3.0.7",
        "cpes": ["cpe:2.3:a:openssl:openssl:3.0.7:*:*:*:*:*:*:*"],  # unknown
        "purl": "pkg:apk/alpine/openssl@3.0.7-r0?distro=alpine-3.18",  # unknown
    })
    assert artifact.name == "openssl"
    assert artifact.locations == []


# --- Known fields validated (AC-3) -------------------------------------------

@pytest.mark.parametrize("bad", [
    {"name": None, "version": "1"},
    {"name": "x", "version": None},
    {"version": "1"},  # missing name
    {"name": "x"},     # missing version
])
def test_syft_artifact_rejects_invalid(bad):
    with pytest.raises(ValidationError):
        SyftArtifact.model_validate(bad)


@pytest.mark.parametrize("bad", [
    {"path": None},
    {},  # missing path
])
def test_syft_location_rejects_invalid(bad):
    with pytest.raises(ValidationError):
        SyftLocation.model_validate(bad)


# --- layerID field name pinned (AC-5) ----------------------------------------

def test_location_layer_id_field_name_is_camelcase():
    loc = SyftLocation.model_validate({"path": "/x", "layerID": "sha256:abc"})
    assert loc.layerID == "sha256:abc"
    with pytest.raises(AttributeError):
        loc.layer_id  # type: ignore[attr-defined]


def test_location_layer_id_optional():
    loc = SyftLocation.model_validate({"path": "/x"})
    assert loc.layerID is None


# --- Empty / minimal SBOM happy path (AC-2.5) --------------------------------

def test_empty_sbom_validates():
    sbom = SyftSbom.model_validate({"artifacts": []})
    assert sbom.artifacts == []
    assert len(sbom.artifacts) == 0


def test_artifact_default_empty_locations():
    art = SyftArtifact.model_validate({"name": "x", "version": "1"})
    assert art.locations == []


# --- Multi-location artifact (AC-3 extension) --------------------------------

def test_artifact_admits_multiple_locations_preserving_order():
    art = SyftArtifact.model_validate({
        "name": "x",
        "version": "1",
        "locations": [
            {"path": "/a", "layerID": "sha256:aaa"},
            {"path": "/b", "layerID": "sha256:bbb"},
            {"path": "/c"},
        ],
    })
    assert [loc.path for loc in art.locations] == ["/a", "/b", "/c"]
    assert [loc.layerID for loc in art.locations] == ["sha256:aaa", "sha256:bbb", None]


# --- Round-trip realistic fixture (AC-4) -------------------------------------

def test_minimal_alpine_fixture_round_trips():
    raw = FIXTURE.read_text()
    sbom = SyftSbom.model_validate_json(raw)
    assert len(sbom.artifacts) == 1
    art = sbom.artifacts[0]
    assert art.name == "openssl"
    assert art.locations[0].layerID == "sha256:abc123"
    # Unknown top-level fields are admitted, but we don't assert their shape.
    payload = json.loads(raw)
    assert "schema" in payload  # pre-condition: fixture has unknowns


def test_unknown_fields_survive_full_encode_decode_encode_cycle():
    """Full round-trip — known AND unknown fields must survive `model_dump` →
    re-validate. An impl that secretly used `extra='ignore'` or `exclude_unset=True`
    would pass AC-2 but fail this — that's the mutation defense AC-4 anchors."""
    raw = FIXTURE.read_text()
    sbom1 = SyftSbom.model_validate_json(raw)
    dump1 = sbom1.model_dump(mode="json")
    # Known fields preserved
    assert dump1["artifacts"][0]["name"] == "openssl"
    assert dump1["artifacts"][0]["locations"][0]["layerID"] == "sha256:abc123"
    # Unknown top-level fields preserved
    for unknown_key in ("schema", "descriptor", "source"):
        assert unknown_key in dump1, f"unknown field {unknown_key!r} dropped on dump"
    # And a second decode succeeds idempotently
    sbom2 = SyftSbom.model_validate(dump1)
    assert sbom2.artifacts[0].locations[0].layerID == sbom1.artifacts[0].locations[0].layerID


# --- Known-field catalog (AC-6) ----------------------------------------------

def test_known_location_fields_pinned():
    assert sr._KNOWN_LOCATION_FIELDS == frozenset({"path", "layerID"})


def test_known_artifact_fields_pinned():
    assert sr._KNOWN_ARTIFACT_FIELDS == frozenset({"name", "version", "locations"})
```

#### Module-purity + smart-constructor-bypass fence (AC-8 + AC-8.5)

Test file path: `tests/unit/primitives/vuln_provenance/test_syft_reader_module_purity.py`

```python
from __future__ import annotations

import ast
from pathlib import Path

from typing import Final

SYFT_READER: Final[Path] = Path("src/codegenie/primitives/vuln_provenance/syft_reader.py")
_ALLOWED_TOP_LEVEL_IMPORTS: Final[frozenset[str]] = frozenset({"__future__", "typing", "pydantic"})


def _parse() -> ast.Module:
    return ast.parse(SYFT_READER.read_text())


def test_syft_reader_imports_are_minimal():
    """AC-8 — types-only module. Imports must be a subset of
    {__future__, typing, pydantic}. Adding stdlib or sibling imports is a
    surface-widening change that must be surfaced via a follow-up story
    (e.g., when a real I/O reader lands)."""
    tree = _parse()
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            seen.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                seen.add(alias.name.split(".")[0])
    unexpected = seen - _ALLOWED_TOP_LEVEL_IMPORTS
    assert not unexpected, f"unexpected imports in syft_reader.py: {unexpected!r}"


def test_syft_reader_has_no_model_construct_call_sites():
    """AC-8.5 — ADR-0004 §Consequences fences against `model_construct()`
    inside the primitive tree (smart-constructor bypass). `syft_reader.py`
    is the deserialization surface most likely to attract this shortcut;
    pin the absence structurally rather than relying on review discipline."""
    tree = _parse()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr != "model_construct", (
                f"`model_construct` call at line {node.lineno} — use "
                "`model_validate(...)` instead. ADR-0004 §Consequences."
            )
```

State why it fails: `ImportError` — `codegenie.primitives.vuln_provenance.syft_reader` and the three models don't exist. Also `FileNotFoundError` for the fixture.

### Green — make it pass
- Create `syft_reader.py` with the three models + the two `_KNOWN_*_FIELDS` `Final` constants.
- Create the fixture file at `tests/fixtures/syft/minimal_alpine.json` (well-formed JSON shown in the implementation outline).
- Extend `vuln_provenance/__init__.py` to re-export `SyftSbom`, `SyftArtifact`, `SyftLocation`.

### Refactor — clean up
- Module docstring naming ADR-0004 and the Phase 2 deliberate-extra-"allow"-decision.
- Each class carries a one-line docstring: `SyftSbom` ("upstream syft schema; extra='allow' admits unknown fields; adapters read only `_KNOWN_*_FIELDS`"), `SyftArtifact`, `SyftLocation`.
- Confirm `_KNOWN_*_FIELDS` are module-private (leading underscore) so S4-04's fence imports them via direct module import, not via `__all__`.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/primitives/vuln_provenance/syft_reader.py` | NEW — 3 Pydantic models + 2 `_KNOWN_*_FIELDS` catalogs. |
| `src/codegenie/primitives/vuln_provenance/__init__.py` | Extend re-exports with `SyftSbom`, `SyftArtifact`, `SyftLocation`. |
| `tests/fixtures/syft/minimal_alpine.json` | NEW — well-formed minimal syft JSON fixture (≤ 1 KB) for round-trip test. |
| `tests/unit/primitives/vuln_provenance/test_syft_reader.py` | NEW — anchors TDD red. |
| `tests/unit/primitives/vuln_provenance/test_syft_reader_module_purity.py` | NEW — AST-walk module-purity fence on `syft_reader.py` imports. |

## Out of scope

- **`SyftSource`, `SyftDistro`, `descriptor: dict[str, Any]`** — deferred until a Phase 7 consumer needs them. The current adapter set reads `locations[].layerID`, `name`, `version` only.
- **`sbom_verifier.py` cross-check function** — landed by S4-01.
- **`AlpineVulnProvenanceAdapter` / `NpmVulnProvenanceAdapter`** — landed by S4-02 / S3-02; this story is the model contract they consume.
- **The "adapters read only known fields" AST-walk fence** — landed by S4-04 (consumes this story's `_KNOWN_*_FIELDS` catalogs).
- **Reading SBOMs from disk** — the arch's reader is models-only; the future I/O surface (parse from file, parse from `docker syft` stdout) is deferred until a consumer needs it.
- **`extra="forbid"` posture** — explicitly inverted here per the arch + Phase 2 deliberate decision.

## Notes for the implementer

- **`extra="allow"` is deliberate and load-bearing.** This is the ONE exception in the Phase 7 primitive tree to the `extra="forbid"` default. The arch + Phase 2 decision + critic anti-pattern row all confirm it. Defense is at the consumer boundary (adapters) via S4-04's AST-walk fence, NOT at the model boundary. Do NOT "fix" this to `extra="forbid"` — it would break every real-world syft JSON the moment syft ships a new field.
- **Do NOT subclass `_Frozen`.** The `_Frozen` base from S1-02 has `frozen=True, extra="forbid"` — the opposite posture. Declare these models as `BaseModel` directly with an explicit `model_config = ConfigDict(extra="allow")`. (Mutability vs immutability is a separate axis; today the SBOM models are immutable-by-convention, not by Pydantic config — the JSON-deserialize path is the only construction site.)
- **`layerID` is camelCase, not snake_case.** Syft's JSON schema is camelCase for this field. Pydantic by default uses the Python attribute name as the JSON key; pinning the attribute name as `layerID` is what makes round-trip work. AC-5 is the structural guard. Do NOT add a Pydantic alias or `model_validator` to translate to `layer_id` — adapters expect `layerID`.
- **`_KNOWN_*_FIELDS` are the source of truth for S4-04.** Module-private, `frozenset`, `Final`. S4-04's AST-walk fence imports them and asserts no adapter reads a field outside the catalog. Adding a new known field is a two-line change here + a one-line update in the fence test. Do NOT inline the field set in adapters — that would force a multi-file change every time the catalog grows.
- **`Final` discipline matches Phase 1/2 convention.** Module-level catalogs (`_GENERATOR_HEADER_MARKERS`, `_REFLECTION_QUERIES`, `_LOCKFILE_PRECEDENCE`) are `Final[frozenset[...]]` or `Final[tuple[...]]` — never `list` or `set` (mutable). Mirror.
- **No I/O in this story.** No `Path.read_text()` inside the module, no logging, no subprocess. The module is types-only. The fixture is only consumed in tests. The future "read from disk" function lives elsewhere when it's needed.
- **Adapters will pass `SyftSbom` instances to `assemble_provenance(... , sbom=sbom)`** per the Protocol shape from S1-04. The forward-reference `"SyftSbom"` in S1-04's `protocols.py` resolves to *this story's* class once S1-04's `from __future__ import annotations` + `get_type_hints` chain runs. Verify after both land: a quick smoke test that the forward reference resolves.
- **Phase 3 regression suite stays green.** This story does not touch any Phase 3 file. If a regression appears, the cause is likely an `import-linter` contract that did not yet admit `codegenie.primitives.vuln_provenance` — surface as follow-up; S1-06 lands the proper contracts.

### Evaluated-and-rejected design-pattern alternatives (per validator)

These are surfaced so the executor does not silently adopt them and so a future story can revisit if the triggering condition appears. **None of them are ACs for this story.**

- **`frozen=True` on `SyftSbom` / `SyftArtifact` / `SyftLocation`.** *Considered:* it would make any post-deserialization mutation a `ValidationError`, hardening the "data shapes don't permit illegal combinations a defensive reader has to check" commitment beyond what `extra="allow"` alone delivers. *Rejected here* per Rule 2 (Simplicity First) — no caller in the current Phase 7 set mutates an `SyftSbom`; the adapters consume it read-only, and `sbom_verifier.py` (S4-01) is also read-only. Adopting `frozen=True` now is premature abstraction. *Re-open if:* any consumer ever needs to construct a mutated copy (`.model_copy(update=...)`) — at that point `frozen=True` is a clarifying constraint, not a free hardening.
- **`LayerID` newtype.** *Considered:* `layerID: str` is structurally indistinguishable from arbitrary strings; a `NewType("LayerID", str)` would prevent confusion at the type level (e.g., accidentally passing a `path` where a `layerID` is expected at the adapter boundary). *Rejected here* per rule-of-three: only two consumers (Alpine S4-02 + Distroless S4-03) read this field today; the per-call-site readability cost of a newtype wrapper exceeds the safety gain. *Re-open if:* a third consumer reads `layerID` (e.g., a future runtime-bundled adapter or a sandbox-side trust check) — that's the rule-of-three threshold and the newtype pays for itself.
- **Hypothesis property-based fuzz over the unknown-field topology.** *Considered:* a `@given(st.dictionaries(...))` test could fuzz the `extra="allow"` surface and verify any random unknown-field shape round-trips through `model_dump`. *Rejected here* per scope and Rule 2 — the single realistic fixture + the multi-location case + the explicit unknown-fields round-trip test (AC-4) collectively exert enough mutation pressure for a types-only story. The S4-04 AST fence on the consumer side is the structural defense; this story does not need to recapitulate it. *Re-open if:* a real-world syft schema drift incident slips through these tests in a later phase — then Hypothesis pays back its cost.
- **Smart-constructor "narrow view".** *Considered:* a `SyftSbom.minimal_view() -> _SyftSbomMinimal` projection that re-validates into a frozen `extra="forbid"` subset, so adapters can *only* see the known fields. *Rejected here* per Rule 2 and because the S4-04 AST-walk fence already enforces "adapters read only `_KNOWN_*_FIELDS`" structurally — adding a runtime narrow-view projection is belt-and-suspenders for a Phase 7 invariant. *Re-open if:* the AST fence proves too brittle (e.g., catches a refactor that's actually correct) — at that point a runtime projection is the next step.
