# Story S1-01 — Phase 7 newtype identifiers + smart constructors

**Step:** Step 1 — Scaffold `vuln.provenance` primitive — newtypes, Provenance union, Protocol, errors, SyftSbom reader, fences
**Status:** Ready
**Effort:** M
**Depends on:** —
**ADRs honored:** ADR-0004 (the primitive lives at `src/codegenie/primitives/vuln_provenance/`; this story lands the typed vocabulary it imports), ADR-0006 (`ProvenanceAdapterId = tuple[Layer, Ecosystem]` is the registry key the dispatch tuple iterates), Phase 3 ADR-0010 / production ADR-0033 (newtype-every-domain-identifier discipline this story extends to Phase 7)

## Context

Phase 7's `Provenance` discriminated union, the `VulnProvenanceAdapter` Protocol, the `_REGISTRY`, the `assemble_provenance` free function, and every adapter all reference a small closed set of identifier newtypes (`ImageRef`, `ImageDigest`, `LayerDigest`, `RuntimeId`, `DockerStageName`, `ProvenanceAdapterId`) plus two already-Phase-3-shipped names (`CveId`, `PackageId`). Until the typed vocabulary lands with `mypy --strict` clean and a smart constructor per type, every later Step 1+ story would either fork primitives or import raw `str` — the same primitive-obsession trap production ADR-0033 names as a review-blocker. This story extends `codegenie.types.identifiers` with the six new Phase 7 names and parsers, reuses `CveId` / `PackageId` from Phase 3 verbatim, and pins the load-bearing `ImageDigest` invariant (`sha256:` prefix asserted by the smart constructor).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Data model` ("Contract — Identifier newtypes (ADR-0033)") — the canonical list of Phase 7 newtypes the primitive imports.
  - `../phase-arch-design.md §Component design §2` — `Provenance` union fields cite `ImageDigest`, `LayerDigest`, `DockerStageName`, `RuntimeId`, `PackageId`, `CveId`.
  - `../phase-arch-design.md §Component design §4` (`registry.py`) — `ProvenanceAdapterId = tuple[Layer, Ecosystem]` is the dispatch key.
  - `../phase-arch-design.md §Design patterns applied` row "Identifier types" — Newtype + Smart constructor pattern is the kernel-tier discipline; raw `str` is type-illegal at every typed boundary thereafter.
- **Phase ADRs (rules):**
  - `../ADRs/0004-vuln-provenance-primitive-home.md` — names the primitive's location; this story makes its typed surface importable.
  - `../ADRs/0006-adapter-dispatch-explicit-final-tuple.md` — names `ProvenanceAdapterId` as the registry key shape.
- **Production ADRs:**
  - `../../../production/adrs/0033-domain-modeling-discipline.md` — the parent newtype-+-smart-constructor rule.
  - `../../../production/adrs/0038-vulnerability-provenance-attribution.md` — names `ImageDigest`, `LayerDigest`, etc. as part of the `Provenance` contract.
- **Source design:**
  - `../final-design.md §Synthesis ledger` row 1 ("primitives home + newtype catalog").
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `src/codegenie/types/identifiers.py` — already exports `CveId` and `PackageId` (Phase 3 ADR-0010, lines 74 + 76 of the current file). **Do not redefine these.** Extend the module; mirror the existing docstring + `__all__` + `_NEWTYPE_REGISTRY` discipline.
  - `src/codegenie/types/parsers.py` — Phase 3's parsers (14 smart constructors). Mirror style: `parse_<x>(s: str) -> Result[<X>, ParseError]`, regex-shaped parsers route through the private `_regex_parser` helper.
  - `src/codegenie/types/errors.py` — Phase 3's `ParseError`. **Do not fork.** Import from here.
  - `src/codegenie/result.py` — canonical `Result[T, E] = Ok[T] | Err[E]`. **Do not create a parallel `Result` under `codegenie.types`.**
  - `tests/unit/types/test_identifiers_phase3.py` + `tests/unit/types/test_identifiers_phase3_mypy_negative.py` + `tests/unit/types/test_parsers_properties.py` — the precedent test shapes; this story mirrors them for Phase 7.
- **External docs:**
  - OCI image-spec digest grammar (`sha256:<64 lowercase hex>`) — the `ImageDigest` regex.

## Goal

Extend `codegenie.types.identifiers` with the six Phase 7 newtypes (`ImageRef`, `ImageDigest`, `LayerDigest`, `RuntimeId`, `DockerStageName`, `ProvenanceAdapterId`) and pair each `str`-backed newtype with a smart-constructor parser returning `Result[T, ParseError]`, so every later Phase 7 story imports its typed primitives from one canonical home and `ImageDigest("sha256:...")` is the only legitimate construction path.

## Acceptance criteria

- [ ] **AC-1 — Newtype catalog.** `src/codegenie/types/identifiers.py` exports the six Phase 7 newtypes: `ImageRef = NewType("ImageRef", str)`, `ImageDigest = NewType("ImageDigest", str)`, `LayerDigest = NewType("LayerDigest", str)`, `RuntimeId = NewType("RuntimeId", str)`, `DockerStageName = NewType("DockerStageName", str)`. `ProvenanceAdapterId` is a `type` alias of `tuple["Layer", "Ecosystem"]` declared with `TYPE_CHECKING`-guarded forward references (the `Layer` / `Ecosystem` enums land in S2-01 — this story declares only the alias shape with string forward refs so Phase 7 modules can import `ProvenanceAdapterId` without a circular dependency). `__all__` is updated to the exact sorted superset.
- [ ] **AC-2 — `CveId` / `PackageId` reused, not redefined.** Phase 3's existing `CveId` and `PackageId` at the same module are referenced verbatim by Phase 7 — no shadowing, no module-level rebinding, no parallel newtype. A test asserts `getattr(ids, "CveId") is the already-shipped Phase 3 NewType` (same `__name__` identity).
- [ ] **AC-3 — Smart constructors.** `src/codegenie/types/parsers.py` exports five new smart constructors, one per `str`-backed Phase 7 newtype, all pure functions returning `Result[<X>, ParseError]`:
  - `parse_image_ref(s)` — non-empty; max 256 chars; rejects whitespace; rejects ASCII control chars (`\x00-\x1f`); accepts both `registry/name[:tag]` and `name[:tag]` shapes (full validation is left to a future story — this parser is a tight floor, not full Distribution-spec validation).
  - `parse_image_digest(s)` — `^sha256:[0-9a-f]{64}$` (lowercase hex only; **the `sha256:` prefix is asserted**); rejects uppercase, rejects other algorithms (sha512, blake3) at the type level — those would require an additive parser amendment.
  - `parse_layer_digest(s)` — same regex as `parse_image_digest` (OCI layer digests share the `sha256:` prefix grammar with image digests at the type level; semantic difference is provenance, not shape).
  - `parse_runtime_id(s)` — `^[a-z][a-z0-9_-]{0,63}$` (snake/kebab; ≤ 64 chars; e.g. `node20`, `python3-11`, `openjdk21`). Lowercase only.
  - `parse_docker_stage_name(s)` — `^[a-z][a-z0-9_-]{0,63}$` (Dockerfile `AS <stage>` grammar; matches the Docker reference's "stage name" production; rejects leading digit, rejects uppercase per BuildKit normalisation).
- [ ] **AC-4 — `ImageDigest` rejects non-`sha256:` prefixes.** Parametrized test covers the load-bearing invariant: `"sha512:..." `, `"md5:..."`, `"SHA256:..."` (uppercase prefix), `"sha256:ABCDEF..."` (uppercase hex), `"sha256:" + "0" * 63` (wrong length), `"sha256:" + "g" * 64` (non-hex), `""` (empty), `"0" * 64` (missing prefix) all return `Err(ParseError(value=...))`. Every variant has an entry in the matrix.
- [ ] **AC-5 — Family-symmetric closures** (mirroring Phase 3 S1-01 hardening):
  - **Round-trip:** every parser, every happy input → `Ok(value=<X>(s))`.
  - **Pairwise distinctness:** parametrized over the Phase 7 newtypes plus the existing Phase 0/1/2/3 names — every pair `(A, B)` with `A != B` satisfies `A is not B`.
  - **`__name__` pinning:** `ImageDigest.__name__ == "ImageDigest"` (etc.).
  - **Exact-set `__all__`:** `set(codegenie.types.identifiers.__all__) == EXPECTED_FULL_SET` including Phase 7's five new str-backed names.
  - **Identity passthrough via `__init__`:** `codegenie.types.ImageDigest is codegenie.types.identifiers.ImageDigest` (etc., parametrized).
  - **`isinstance` runtime `TypeError` pin:** `with pytest.raises(TypeError): isinstance("foo", ImageDigest)` (parametrized over the five new str newtypes).
- [ ] **AC-6 — Subprocess-`mypy --strict` cross-newtype rejection.** `tests/unit/types/test_identifiers_phase7_mypy_negative.py` (new) writes a temp `.py` file containing a deliberately swapped call (e.g., `def _accept_image_digest(_x: ImageDigest) -> None: ...; _accept_image_digest(LayerDigest("sha256:..."))`) and asserts `mypy --strict` exits non-zero with an "incompatible type" message. Parametrized over at least the swaps `(ImageDigest, LayerDigest)`, `(ImageRef, ImageDigest)`, `(RuntimeId, DockerStageName)`, `(ImageDigest, str)` — every Phase 7 newtype appears in at least one swap pair.
- [ ] **AC-7 — Hypothesis totality + determinism + round-trip-identity** (`tests/unit/types/test_parsers_phase7_properties.py`): for any `s: str` drawn from `hypothesis.strategies.text(max_size=300)`, every Phase 7 parser returns `isinstance(r, (Ok, Err))` and never raises; `parse_<x>(s) == parse_<x>(s)`; for `s` drawn from `hypothesis.strategies.from_regex(parser_rx, fullmatch=True)`, `parse_<x>(s).unwrap() == <X>(s)`.
- [ ] **AC-8 — Docstring registry extended.** Phase 3's `_NEWTYPE_REGISTRY` mapping gains one entry per Phase 7 newtype, each value names ADR-0004 + the Phase 7 consumer (e.g. `"# ImageDigest — Phase 7 ADR-0004 + ADR-0006; sha256:<64-hex>; consumed by BaseImage variant + assemble_provenance."`). Test asserts the registry keys equal `__all__` and every Phase 7 value names `ADR-0004` or `ADR-0006`.
- [ ] **AC-9 — `ProvenanceAdapterId` alias shape.** A static-only test asserts `ProvenanceAdapterId` evaluates (under `typing.get_type_hints` with `include_extras=True`) to `tuple[Layer, Ecosystem]` at runtime (or, if the enums are stubbed as forward references, that the alias is a `typing.TupleType` whose args are the string names `"Layer"` and `"Ecosystem"`). A `# TODO(S2-01)` comment names the follow-up: once the real enums land, the test tightens to identity equality.
- [ ] **AC-10 — Gates.** `mypy --strict src/codegenie/types/` clean; `ruff check`, `ruff format --check` clean on touched files; `make lint-imports` green; Phase 3 + Phase 0/1/2 regression suite green (no existing test weakened or skipped).
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline

1. Extend `src/codegenie/types/identifiers.py`:
   - Append five `NewType` declarations: `ImageRef`, `ImageDigest`, `LayerDigest`, `RuntimeId`, `DockerStageName`.
   - Add the `ProvenanceAdapterId` type alias using a `TYPE_CHECKING` forward-reference block (`if TYPE_CHECKING: from codegenie.primitives.vuln_provenance.registry import Layer, Ecosystem` — note S2-01 lands the real module; until then use string forward refs `tuple["Layer", "Ecosystem"]`).
   - Extend `_NEWTYPE_REGISTRY` with five new rows naming ADR-0004 / ADR-0006.
   - Extend `__all__` (sorted) with the six new names.
2. Extend `src/codegenie/types/parsers.py`:
   - Append five `parse_<x>` functions returning `Result[<X>, ParseError]`.
   - Reuse `_regex_parser` for `parse_runtime_id` / `parse_docker_stage_name` (those are pure regex-shaped — cross the rule-of-three threshold).
   - `parse_image_digest` and `parse_layer_digest` share a private `_SHA256_DIGEST_RX: Final = re.compile(r"^sha256:[0-9a-f]{64}$")` constant; both call through `_regex_parser` if the helper supports identical-regex-different-newtype calls, else add a thin per-newtype wrapper.
   - `parse_image_ref` does explicit length + control-char + whitespace checks (not a single regex — full Distribution-spec validation is deferred).
3. Update `src/codegenie/types/__init__.py` to re-export the six new names (identity passthrough).
4. Land tests (red-first; see TDD plan below).
5. Run `mypy --strict src/codegenie/types/` and `make check` locally; verify Phase 3 regression suite stays green.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/unit/types/test_identifiers_phase7.py`

```python
from __future__ import annotations

import pytest

from codegenie.result import Err, Ok
from codegenie.types.errors import ParseError
from codegenie.types.identifiers import (
    CveId,           # Phase 3 — must still be importable from same home
    DockerStageName,
    ImageDigest,
    ImageRef,
    LayerDigest,
    PackageId,       # Phase 3 — must still be importable from same home
    RuntimeId,
)
from codegenie.types.parsers import (
    parse_docker_stage_name,
    parse_image_digest,
    parse_image_ref,
    parse_layer_digest,
    parse_runtime_id,
)


# --- Happy paths (AC-3) ------------------------------------------------------

@pytest.mark.parametrize(
    "parser,good,wrapper",
    [
        (parse_image_ref, "cgr.dev/chainguard/node:latest", ImageRef),
        (parse_image_ref, "node:20-alpine", ImageRef),
        (parse_image_digest, "sha256:" + "0" * 64, ImageDigest),
        (parse_layer_digest, "sha256:" + "a" * 64, LayerDigest),
        (parse_runtime_id, "node20", RuntimeId),
        (parse_runtime_id, "openjdk21", RuntimeId),
        (parse_docker_stage_name, "builder", DockerStageName),
        (parse_docker_stage_name, "test-runner", DockerStageName),
    ],
)
def test_parser_happy_path(parser, good, wrapper):
    r = parser(good)
    assert isinstance(r, Ok)
    assert r.value == wrapper(good)


# --- ImageDigest sha256: prefix asserted (AC-4) ------------------------------

@pytest.mark.parametrize(
    "bad",
    [
        "sha512:" + "0" * 128,                   # wrong algorithm
        "md5:" + "0" * 32,                       # wrong algorithm
        "SHA256:" + "0" * 64,                    # uppercase prefix
        "sha256:" + "A" * 64,                    # uppercase hex
        "sha256:" + "0" * 63,                    # too short
        "sha256:" + "0" * 65,                    # too long
        "sha256:" + "g" * 64,                    # non-hex
        "",                                      # empty
        "0" * 64,                                # missing prefix
        ":" + "0" * 64,                          # missing algorithm
        "sha256:",                               # missing hex
    ],
)
def test_image_digest_rejects_non_sha256(bad):
    r = parse_image_digest(bad)
    assert isinstance(r, Err)
    assert r.error.value == bad


# --- ImageRef floor (AC-3) ---------------------------------------------------

@pytest.mark.parametrize("bad", ["", " ", "image\x00name", "a" * 257, "image name"])
def test_image_ref_rejects(bad):
    r = parse_image_ref(bad)
    assert isinstance(r, Err)


# --- Phase 3 newtypes still importable from same home (AC-2) -----------------

def test_phase3_cve_id_and_package_id_unchanged():
    """Phase 7 must not shadow Phase 3 CveId / PackageId."""
    import codegenie.types.identifiers as ids
    assert ids.CveId.__name__ == "CveId"
    assert ids.PackageId.__name__ == "PackageId"
    # The Phase 7 catalog augments Phase 3; the existing names are the same objects.
    assert "CveId" in ids.__all__
    assert "PackageId" in ids.__all__


# --- Catalog identity invariants (AC-5) --------------------------------------

PHASE7_STR_NEWTYPES = {
    "ImageRef", "ImageDigest", "LayerDigest", "RuntimeId", "DockerStageName",
}


def test_phase7_newtype_names_pinned():
    import codegenie.types.identifiers as ids
    for name in PHASE7_STR_NEWTYPES:
        nt = getattr(ids, name)
        assert nt.__name__ == name


def test_phase7_pairwise_distinct():
    import codegenie.types.identifiers as ids
    names = sorted(PHASE7_STR_NEWTYPES | {"CveId", "PackageId"})
    objs = [getattr(ids, n) for n in names]
    for i, a in enumerate(objs):
        for b in objs[i + 1 :]:
            assert a is not b


def test_phase7_identity_passthrough():
    import codegenie.types as pkg
    import codegenie.types.identifiers as ids
    for name in PHASE7_STR_NEWTYPES:
        assert getattr(pkg, name) is getattr(ids, name)


@pytest.mark.parametrize("name", sorted(PHASE7_STR_NEWTYPES))
def test_phase7_isinstance_raises_typeerror(name):
    import codegenie.types.identifiers as ids
    nt = getattr(ids, name)
    with pytest.raises(TypeError):
        isinstance("foo", nt)  # type: ignore[arg-type]


# --- Docstring registry (AC-8) ----------------------------------------------

def test_phase7_registry_entries_cite_adr():
    from codegenie.types.identifiers import _NEWTYPE_REGISTRY
    for name in PHASE7_STR_NEWTYPES:
        doc = _NEWTYPE_REGISTRY[name]
        assert doc.strip()
        assert "ADR-0004" in doc or "ADR-0006" in doc, (
            f"{name} docstring must cite Phase 7 ADR-0004 or ADR-0006"
        )
```

State why it fails: `ImportError` — the five Phase 7 newtypes and their parsers don't exist yet in `codegenie.types.identifiers` / `codegenie.types.parsers`.

The subprocess-mypy meta-test goes in `tests/unit/types/test_identifiers_phase7_mypy_negative.py`:

```python
import subprocess, sys, textwrap
from pathlib import Path
import pytest

SWAP_PAIRS = [
    ("ImageDigest", "LayerDigest"),
    ("ImageRef", "ImageDigest"),
    ("RuntimeId", "DockerStageName"),
    ("DockerStageName", "RuntimeId"),
    ("ImageDigest", "ImageRef"),
]


@pytest.mark.parametrize("a,b", SWAP_PAIRS)
def test_mypy_rejects_phase7_swap(tmp_path: Path, a: str, b: str) -> None:
    src = textwrap.dedent(
        f"""
        from codegenie.types.identifiers import {a}, {b}

        def _accept_{a.lower()}(_x: {a}) -> None: ...

        _accept_{a.lower()}({b}("sha256:" + "0" * 64 if "Digest" in {b!r} else "x"))
        """
    )
    tmp = tmp_path / "swap.py"
    tmp.write_text(src)
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(tmp)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "incompatible" in result.stdout.lower() or "argument" in result.stdout.lower()
```

Property tests in `tests/unit/types/test_parsers_phase7_properties.py`:

```python
import pytest
from hypothesis import given, strategies as st
from codegenie.result import Err, Ok
from codegenie.types import parsers as P

PHASE7_PARSERS = [
    P.parse_image_ref, P.parse_image_digest, P.parse_layer_digest,
    P.parse_runtime_id, P.parse_docker_stage_name,
]


@pytest.mark.parametrize("parser", PHASE7_PARSERS, ids=lambda p: p.__name__)
@given(s=st.text(max_size=300))
def test_total(parser, s):
    try:
        r = parser(s)
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"{parser.__name__}({s!r}) raised {type(e).__name__}: {e!r}")
    assert isinstance(r, (Ok, Err))


@pytest.mark.parametrize("parser", PHASE7_PARSERS, ids=lambda p: p.__name__)
@given(s=st.text(max_size=300))
def test_deterministic(parser, s):
    assert parser(s) == parser(s)


@given(s=st.from_regex(r"^sha256:[0-9a-f]{64}$", fullmatch=True))
def test_image_digest_round_trip(s):
    r = P.parse_image_digest(s)
    assert isinstance(r, Ok)
    assert r.value == s
```

### Green — make it pass
- Append five `NewType` lines to `src/codegenie/types/identifiers.py` and the `ProvenanceAdapterId` `TYPE_CHECKING`-guarded alias.
- Append five `parse_<x>` functions to `src/codegenie/types/parsers.py`. `parse_image_digest` / `parse_layer_digest` share `_SHA256_DIGEST_RX`. `parse_runtime_id` / `parse_docker_stage_name` route through `_regex_parser`.
- Update `_NEWTYPE_REGISTRY` (five rows naming ADR-0004 / ADR-0006).
- Update `__all__` and `codegenie/types/__init__.py` re-exports.

### Refactor — clean up
- Lift `_SHA256_DIGEST_RX` to module top with a one-line comment `# OCI image-spec digest grammar; ADR-0006`.
- Each parser carries a one-line docstring naming its boundary (`"""External boundary: BaseImageProbe slice / SyftSbom.locations[].layerID; ADR-0004."""`).
- Confirm Phase 3 parsers continue to use `_regex_parser` only (no regression of the rule-of-three discipline).
- Verify all five new parsers + `_NEWTYPE_REGISTRY` entries cite Phase 7 ADR numbers.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/types/identifiers.py` | Append 5 newtypes + `ProvenanceAdapterId` alias + 5 `_NEWTYPE_REGISTRY` rows; extend `__all__`. |
| `src/codegenie/types/parsers.py` | Append 5 smart constructors; introduce `_SHA256_DIGEST_RX` constant. |
| `src/codegenie/types/__init__.py` | Re-export the 6 new names; assert identity-passthrough. |
| `tests/unit/types/test_identifiers_phase7.py` | NEW — happy/sad/distinctness/identity/docstring (anchors TDD red). |
| `tests/unit/types/test_identifiers_phase7_mypy_negative.py` | NEW — subprocess `mypy --strict` cross-newtype swap rejection. |
| `tests/unit/types/test_parsers_phase7_properties.py` | NEW — Hypothesis totality + determinism + round-trip. |

## Out of scope

- **The `Layer` / `Ecosystem` enums** — landed by S2-01 (this story declares `ProvenanceAdapterId` with `TYPE_CHECKING` forward refs so S2-01 lands cleanly without a circular dependency).
- **`DistroPackage` Pydantic model** — landed by S1-02 (this story is newtypes-only).
- **`Provenance` discriminated union** — landed by S1-03.
- **`VulnProvenanceAdapter` Protocol** — landed by S1-04.
- **`SyftSbom` reader** — landed by S1-05.
- **The Phase 7 import-linter / no-`Any` fences** — landed by S1-06.
- **Full Distribution-spec `ImageRef` validation** — deferred to a future hardening story; `parse_image_ref` ships as a tight floor (control chars, whitespace, length).

## Notes for the implementer

- **`CveId` and `PackageId` are already in `identifiers.py`** (Phase 3 ADR-0010, lines 74 + 76). **Do not redefine them.** Phase 7 reuses them verbatim — `assemble_provenance` and every adapter import them from the same canonical home. The test in AC-2 is the structural guard against accidental shadowing.
- **The `sha256:` prefix is load-bearing.** The arch's `Provenance` union's `BaseImage` variant carries `image_digest: ImageDigest` and `layer_digest: LayerDigest`; both must be `sha256:`-prefixed at the type-system level so adapter code can't accidentally pass an untagged hex string. AC-4 is the central correctness pin — every alternative algorithm (sha512, blake3, etc.) is rejected at the smart-constructor boundary today; admitting a new algorithm requires an ADR amendment, not a parser tweak.
- **`ProvenanceAdapterId` is a tuple alias, not a `NewType`.** `NewType` over a generic `tuple[...]` is unsupported in mypy's strict mode; the arch + ADR-0006 deliberately specify `ProvenanceAdapterId = tuple[Layer, Ecosystem]`. Use `TYPE_CHECKING`-guarded forward references to break the circular dep with S2-01's `registry.py`; the AC-9 test asserts the alias shape today and contains a `# TODO(S2-01)` marker to tighten once `Layer` / `Ecosystem` land.
- **`Result` lives at `codegenie.result`.** Phase 3 S1-01 was explicit: do NOT create `src/codegenie/types/result.py`. Import `Ok` / `Err` / `Result` from `codegenie.result`. Instantiate with `Ok(value=...)` / `Err(error=...)` keyword args (the canonical Pydantic discriminator-on-`kind` idiom).
- **Mirror Phase 3's `_NEWTYPE_REGISTRY` discipline.** Each entry is a one-line docstring naming the ADR + the immediate Phase 7 consumer. The test in AC-8 enforces that every new entry cites Phase 7 ADR-0004 or ADR-0006 — drift here is silent docstring rot.
- **`mypy --strict` is the bar.** The subprocess-mypy meta-test (AC-6) catches the swap class of bugs that line-comment prose cannot. Phase 3 S1-05's validation explicitly closed this trap; do not regress to commented-out swap lines.
- **Phase 3 + Phase 0/1/2 regression suite must stay green.** This story is additive to `identifiers.py`, but any change to the Phase 3 `_NEWTYPE_REGISTRY` test fixtures or `__all__` discipline could ripple. Run `pytest tests/unit/types/ -x` after the green pass — any pre-existing test must still pass unchanged.
