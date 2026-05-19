# Story S1-01 — Phase 7 newtype identifiers + smart constructors

**Step:** Step 1 — Scaffold `vuln.provenance` primitive — newtypes, Provenance union, Protocol, errors, SyftSbom reader, fences
**Status:** GREEN
**Effort:** M
**Depends on:** —
**ADRs honored:** ADR-0004 (the primitive lives at `src/codegenie/primitives/vuln_provenance/`; this story lands the typed vocabulary it imports), ADR-0006 (`ProvenanceAdapterId = tuple[Layer, Ecosystem]` is the registry key the dispatch tuple iterates), Phase 3 ADR-0010 / production ADR-0033 (newtype-every-domain-identifier discipline this story extends to Phase 7)

## Validation notes (2026-05-19 — phase-story-validator HARDENED pass)

Edits relative to the as-written story, with rationale:

- **Resolved an `Ecosystem` symbol collision (Consistency / block).** Phase 3 already ships `Ecosystem = Literal["npm", "pypi", "maven", "rubygems", "gomod"]` in `codegenie.types.identifiers` (S3-02 — vuln-index lookup filter); Phase 7 will ship a *different* `Ecosystem(str, Enum)` in `primitives/vuln_provenance/registry.py` (S2-01 — dispatch key). The two symbols intentionally have different membership sets, live in different modules, and serve different purposes. The story now (a) declares this collision explicitly in `Notes for the implementer`, (b) requires the `TYPE_CHECKING`-guarded import of the Phase 7 `Ecosystem` to come from `codegenie.primitives.vuln_provenance.registry`, NOT from `codegenie.types.identifiers`, and (c) adds AC-11 — a structural test asserting the two `Ecosystem` symbols are distinct objects so cross-module accidents fail loudly.
- **Pinned the `ProvenanceAdapterId` declaration shape (Consistency / harden).** The original Implementation Outline left the runtime alias shape ambiguous (string forward refs vs. `TYPE_CHECKING` import + plain tuple). AC-1 now mandates the exact pattern: a module-level `ProvenanceAdapterId: TypeAlias = tuple["Layer", "Ecosystem"]` with the `TYPE_CHECKING`-guarded import resolving the forward references to the Phase 7 enums from `primitives/vuln_provenance/registry`.
- **Tightened the `ImageDigest` rejection matrix (Coverage / harden).** Added whitespace + DEL contamination cases (leading space, trailing newline, embedded `\x00`, `\x7f`). These are common SBOM contamination patterns and the smart-constructor boundary is the place to reject them.
- **Strengthened the `parse_image_ref` floor (Coverage / harden).** Added DEL (`\x7f`) and `\x00` to the explicit rejection set; renamed "control chars" to a precise `\x00..\x1f` + `\x7f` set; added a max-length boundary test (256 accepted, 257 rejected); added an empty-tag happy case and a multi-`:` rejection.
- **Made AC-8 docstring requirements concrete (Coverage / harden).** Phase 3's `_NEWTYPE_REGISTRY` precedent already requires both an ADR cite AND a consumer name (e.g. "Phase-3 MITRE CVE id (ADR-0010); S5-04 lockfile recipe input."). The validator changed AC-8's "or" to "and" — every entry cites at least one Phase 7 ADR (`ADR-0004` or `ADR-0006`) AND names the immediate Phase 7 consumer (e.g., `BaseImage variant`, `assemble_provenance`, `_REGISTRY`).
- **Replaced the brittle f-string template in the mypy-negative TDD snippet (Test-Quality / harden).** Phase 3 already solved this with a `_ctor_arg(name)` helper; the validator ported the same shape to Phase 7. The conditional-inside-f-string was both fragile (Python operator-precedence trap) and didn't generalise to `RuntimeId` / `DockerStageName` swaps.
- **Added a negative-control test (Test-Quality / harden).** The mypy-negative test now also asserts that *correct* usage type-checks (`test_mypy_accepts_correct_usage_phase7`). Without this, a CI environment that silently fails to find `mypy` could make every swap test pass for the wrong reason. Mirrors Phase 3's precedent.
- **Made the `__init__.py` re-export explicit as an AC (Coverage / harden).** Originally only in Implementation Outline; promoted to AC-10's identity-passthrough check + a parametrized test entry.
- **Surfaced three design-pattern observations to `Notes for the implementer` (Design-Patterns / harden, not lifted to ACs per Rule 2 — they are contextual implementation guidance, not user-observable contract).**
  1. `parse_image_digest` / `parse_layer_digest` share the regex but instantiate separate `_regex_parser` closures so error messages name the correct newtype (mirrors Phase 3's catalog of `_match` closures).
  2. `parse_image_ref`'s explicit non-regex checks are a deliberate departure from the rule-of-three regex helper (full Distribution-spec validation is deferred); the floor exists to reject obvious contamination, not to validate.
  3. The Phase 7 `Ecosystem` enum's value strings (`"apk"`, `"dpkg"`, `"npm"`, ...) will become the *sort key* for within-layer dispatch order per ADR-0006. S1-01 doesn't ship the enum, but its values must be chosen with that in mind when S2-01 lands them.
- **Explicit out-of-scope (Consistency / nit).** Added that no edits to `src/codegenie/primitives/vuln_provenance/` land in this story (S1-02+ territory).

**Verdict:** HARDENED. Full audit log at `_validation/S1-01-phase7-newtype-identifiers.md`.

## Implementation evidence (2026-05-19 — GREEN)

Every acceptance criterion is satisfied with runtime evidence below. Full attempt log at [`_attempts/S1-01-phase7-newtype-identifiers.md`](_attempts/S1-01-phase7-newtype-identifiers.md).

- **AC-1** — [`src/codegenie/types/identifiers.py:140-198`](../../../../src/codegenie/types/identifiers.py) — five `NewType` declarations + `ProvenanceAdapterId: TypeAlias = tuple["_PhVnLayer", "_PhVnEcosystem"]` under `TYPE_CHECKING` guard. Test: `test_phase7_newtype_names_pinned`, `test_provenance_adapter_id_is_tuple_alias_with_forward_refs`.
- **AC-2** — `CveId` / `PackageId` not redefined; identity-checked via `test_phase3_cve_id_and_package_id_unchanged`.
- **AC-3** — [`src/codegenie/types/parsers.py:213-292`](../../../../src/codegenie/types/parsers.py) — five smart constructors. Tests: `test_parser_happy_path[*]`, `test_image_ref_rejects[*]`, boundary tests for `RuntimeId` / `DockerStageName` (64 accepted, 65 rejected).
- **AC-4** — `test_image_digest_rejects_non_sha256[*]` covers algorithm, casing, length, charset, structure, AND contamination matrix (17 cases).
- **AC-5** — `test_phase7_pairwise_distinct` (across 30 newtypes), `test_phase7_exact_set_all`, `test_phase7_identity_passthrough`, `test_phase7_isinstance_raises_typeerror[*]` (5 cases).
- **AC-6** — `tests/unit/types/test_identifiers_phase7_mypy_negative.py` — 6 swap pairs + 1 negative-control. All 7 pass.
- **AC-7** — `tests/unit/types/test_parsers_phase7_properties.py` — Hypothesis totality (5 parsers × 100 draws), determinism (5 parsers × 100 draws), round-trip-identity (4 parsers × 100 draws).
- **AC-8** — `_NEWTYPE_REGISTRY` extended with 5 Phase 7 entries citing ADR-0004 / ADR-0006 + consumer; `test_phase7_registry_entry_cites_adr_and_consumer[*]` validates both.
- **AC-9** — `test_provenance_adapter_id_is_tuple_alias_with_forward_refs` asserts `origin=tuple`, args=(`_PhVnLayer`, `_PhVnEcosystem`). `# TODO(S2-01)` marker in test.
- **AC-10** — `src/codegenie/types/__init__.py` re-exports 6 Phase 7 names; `test_package_level_reexport_identity[*]` (6 cases) asserts identity passthrough.
- **AC-11** — `test_phase3_ecosystem_is_literal_not_enum` sentinel passes; `# TODO(S2-01)` marker in test.
- **AC-12** — `make lint-imports` green (4 kept, 0 broken); `.venv/bin/python -m mypy --strict src/codegenie/types/` → `Success: no issues found in 4 source files`; `mypy --strict src/` → 185 source files clean; `ruff check` + `ruff format --check` clean; Phase 3 + types regression suite green (326 passed).

Full Phase 7 unit/property suite: **98 passed in 2.50s**.

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

- [ ] **AC-1 — Newtype catalog + `ProvenanceAdapterId` alias shape.** `src/codegenie/types/identifiers.py` exports the six Phase 7 newtypes: `ImageRef = NewType("ImageRef", str)`, `ImageDigest = NewType("ImageDigest", str)`, `LayerDigest = NewType("LayerDigest", str)`, `RuntimeId = NewType("RuntimeId", str)`, `DockerStageName = NewType("DockerStageName", str)`. `ProvenanceAdapterId` is declared as a module-level `TypeAlias`:
  ```python
  if TYPE_CHECKING:  # pragma: no cover — forward refs for S2-01 enums
      from codegenie.primitives.vuln_provenance.registry import Ecosystem as _PhVnEcosystem
      from codegenie.primitives.vuln_provenance.registry import Layer as _PhVnLayer

  ProvenanceAdapterId: TypeAlias = tuple["_PhVnLayer", "_PhVnEcosystem"]
  ```
  Underscored aliases keep the Phase 7 `Ecosystem` distinct from the Phase 3 `codegenie.types.identifiers.Ecosystem` Literal at the symbol level (Validation Notes — Consistency / block). At runtime the alias resolves to `tuple[ForwardRef("_PhVnLayer"), ForwardRef("_PhVnEcosystem")]`; once S2-01 lands the real enums the alias resolves to `tuple[Layer, Ecosystem]` (Phase 7 registry-module `Ecosystem`, *not* the Phase 3 `types.identifiers.Ecosystem`). `__all__` is updated to the exact sorted superset (the six new Phase 7 names).
- [ ] **AC-2 — `CveId` / `PackageId` reused, not redefined.** Phase 3's existing `CveId` and `PackageId` at the same module are referenced verbatim by Phase 7 — no shadowing, no module-level rebinding, no parallel newtype. A test asserts `getattr(ids, "CveId") is the already-shipped Phase 3 NewType` (same `__name__` identity).
- [ ] **AC-3 — Smart constructors.** `src/codegenie/types/parsers.py` exports five new smart constructors, one per `str`-backed Phase 7 newtype, all pure functions returning `Result[<X>, ParseError]`:
  - `parse_image_ref(s)` — non-empty; max 256 chars (257 rejected, 256 accepted); rejects any whitespace character (per `str.isspace`); rejects all ASCII control chars `\x00..\x1f` AND `\x7f` (DEL); accepts both `registry/name[:tag]` and `name[:tag]` shapes including empty-tag (`"node:"` is *rejected*; `"node"` is accepted; multi-`:` like `"node:20:foo"` is rejected — exactly zero or one `:` allowed in the final path segment). Full Distribution-spec validation is left to a future story — this parser is a tight floor, not full grammar.
  - `parse_image_digest(s)` — `^sha256:[0-9a-f]{64}$` (lowercase hex only; **the `sha256:` prefix is asserted**); rejects uppercase, rejects other algorithms (sha512, blake3) at the type level — those would require an additive parser amendment.
  - `parse_layer_digest(s)` — same regex as `parse_image_digest` (OCI layer digests share the `sha256:` prefix grammar with image digests at the type level; semantic difference is provenance, not shape). Implementation reuses the same compiled regex but instantiates a separate `_regex_parser(...)` closure so the `Err.message` names `LayerDigest` (mirrors Phase 3's `_match`-closure-per-newtype catalog).
  - `parse_runtime_id(s)` — `^[a-z][a-z0-9_-]{0,63}$` (snake/kebab; ≤ 64 chars; e.g. `node20`, `python3-11`, `openjdk21`). Lowercase only. Boundary tests: 64-char input accepted, 65-char input rejected.
  - `parse_docker_stage_name(s)` — `^[a-z][a-z0-9_-]{0,63}$` (Dockerfile `AS <stage>` grammar; matches the Docker reference's "stage name" production; rejects leading digit, rejects uppercase per BuildKit normalisation). Boundary tests: 64-char input accepted, 65-char input rejected.
- [ ] **AC-4 — `ImageDigest` rejects non-`sha256:` prefixes + contamination.** Parametrized test covers the load-bearing invariant. Every variant has an entry in the matrix and all return `Err(ParseError(value=...))`:
  - Algorithm: `"sha512:" + "0"*128`, `"md5:" + "0"*32`, `"blake3:" + "0"*64` (other algorithms rejected at the type level).
  - Casing: `"SHA256:" + "0"*64` (uppercase prefix), `"sha256:" + "A"*64` (uppercase hex).
  - Length: `"sha256:" + "0"*63` (too short), `"sha256:" + "0"*65` (too long).
  - Charset: `"sha256:" + "g"*64` (non-hex).
  - Structure: `""` (empty), `"0"*64` (missing prefix), `":" + "0"*64` (missing algorithm), `"sha256:"` (missing hex).
  - **Contamination (added by validator — SBOM read-back patterns):** `" sha256:" + "0"*64` (leading space), `"sha256:" + "0"*64 + " "` (trailing space), `"sha256:" + "0"*64 + "\n"` (trailing newline), `"sha256:" + "0"*64 + "\x00"` (trailing NUL), `"sha256:" + "0"*32 + "\x7f" + "0"*31` (embedded DEL).
- [ ] **AC-5 — Family-symmetric closures** (mirroring Phase 3 S1-01 hardening):
  - **Round-trip:** every parser, every happy input → `Ok(value=<X>(s))`.
  - **Pairwise distinctness:** parametrized over the Phase 7 newtypes plus the existing Phase 0/1/2/3 names — every pair `(A, B)` with `A != B` satisfies `A is not B`.
  - **`__name__` pinning:** `ImageDigest.__name__ == "ImageDigest"` (etc.).
  - **Exact-set `__all__`:** `set(codegenie.types.identifiers.__all__) == EXPECTED_FULL_SET` including Phase 7's five new str-backed names.
  - **Identity passthrough via `__init__`:** `codegenie.types.ImageDigest is codegenie.types.identifiers.ImageDigest` (etc., parametrized).
  - **`isinstance` runtime `TypeError` pin:** `with pytest.raises(TypeError): isinstance("foo", ImageDigest)` (parametrized over the five new str newtypes).
- [ ] **AC-6 — Subprocess-`mypy --strict` cross-newtype rejection + negative control.** `tests/unit/types/test_identifiers_phase7_mypy_negative.py` (new) writes a temp `.py` file containing a deliberately swapped call (e.g., `def _accept_image_digest(_x: ImageDigest) -> None: ...; _accept_image_digest(LayerDigest("sha256:..."))`) and asserts `mypy --strict` exits non-zero AND the stdout contains `"incompatible type"` or `"argument"`. Parametrized over at least: `(ImageDigest, LayerDigest)`, `(LayerDigest, ImageDigest)`, `(ImageRef, ImageDigest)`, `(ImageDigest, ImageRef)`, `(RuntimeId, DockerStageName)`, `(DockerStageName, RuntimeId)` — every Phase 7 newtype appears in at least one swap pair. Constructor arguments come from a `_ctor_arg(name)` helper that returns the syntactically-correct string literal per newtype (mirrors Phase 3's `_ctor_arg`; replaces a brittle inline f-string conditional). A companion test `test_mypy_accepts_correct_usage_phase7` writes a file where each newtype is called with its own type and asserts `mypy --strict` exits zero — without this negative-control, a broken mypy installation would cause every swap test to pass for the wrong reason.
- [ ] **AC-7 — Hypothesis totality + determinism + round-trip-identity** (`tests/unit/types/test_parsers_phase7_properties.py`): for any `s: str` drawn from `hypothesis.strategies.text(max_size=300)`, every Phase 7 parser returns `isinstance(r, (Ok, Err))` and never raises; `parse_<x>(s) == parse_<x>(s)`; for `s` drawn from `hypothesis.strategies.from_regex(parser_rx, fullmatch=True)`, `parse_<x>(s).unwrap() == <X>(s)`.
- [ ] **AC-8 — Docstring registry extended.** Phase 3's `_NEWTYPE_REGISTRY` mapping gains one entry per Phase 7 newtype. Each Phase 7 entry **must** cite at least one Phase 7 ADR (`ADR-0004` or `ADR-0006`) **and** name the immediate Phase 7 consumer (mirrors Phase 3's precedent: `"Phase-3 MITRE CVE id (ADR-0010); S5-04 lockfile recipe input."`). Suggested values:
  - `"ImageRef": "Phase-7 OCI image reference (ADR-0004); BaseImageStage.ref + Dockerfile recipes."`
  - `"ImageDigest": "Phase-7 sha256:<64-hex> image digest (ADR-0004 + ADR-0006); BaseImage variant + BaseImageStage.digest."`
  - `"LayerDigest": "Phase-7 sha256:<64-hex> OCI layer digest (ADR-0004); BaseImage variant + SyftSbom layer-attribution."`
  - `"RuntimeId": "Phase-7 runtime identifier (ADR-0004); RuntimeBundled variant + runtime-bundled adapter."`
  - `"DockerStageName": "Phase-7 Dockerfile AS-stage name (ADR-0004); BaseImageStage.name + Dockerfile recipes."`

  Test asserts (a) `_NEWTYPE_REGISTRY` keys equal `__all__`, (b) every Phase 7 value names at least one Phase 7 ADR (`ADR-0004` or `ADR-0006`), AND (c) every Phase 7 value contains *some* Phase 7 consumer reference (`"BaseImage"`, `"RuntimeBundled"`, `"BaseImageStage"`, `"Dockerfile"`, `"SyftSbom"`, `"adapter"`, `"assemble_provenance"`, or `"_REGISTRY"`). The "and" between (b) and (c) is load-bearing — Phase 3 precedent enforces both.
- [ ] **AC-9 — `ProvenanceAdapterId` alias shape.** A static-only test asserts `ProvenanceAdapterId` is a `typing.TypeAlias` whose runtime `__origin__` is `tuple` and whose `__args__` are the two `ForwardRef("_PhVnLayer")` / `ForwardRef("_PhVnEcosystem")` sentinels (the underscored aliases break the name collision with the Phase 3 `Ecosystem` Literal — see AC-11). A `# TODO(S2-01)` comment in the test names the follow-up: once S2-01 lands `primitives/vuln_provenance/registry.py`, the test tightens to import those real symbols and assert `typing.get_type_hints(...)` resolves to `tuple[Layer, Ecosystem]` where `Ecosystem is codegenie.primitives.vuln_provenance.registry.Ecosystem`. Until then the test must NOT import from `primitives/vuln_provenance/` (the module does not yet exist; importing would error).
- [ ] **AC-10 — Package-level re-export discipline.** `src/codegenie/types/__init__.py` re-exports the six new Phase 7 names; `__all__` in `codegenie.types` is the exact sorted union of the prior set + Phase 7. A parametrized test asserts `getattr(codegenie.types, name) is getattr(codegenie.types.identifiers, name)` for each of `{"ImageRef", "ImageDigest", "LayerDigest", "RuntimeId", "DockerStageName", "ProvenanceAdapterId"}` (identity passthrough — already covered piecewise in AC-5, lifted here so the package-level surface is contract).
- [ ] **AC-11 — `Ecosystem` symbol-collision sentinel.** The Phase 3 `codegenie.types.identifiers.Ecosystem` Literal and the Phase 7 `codegenie.primitives.vuln_provenance.registry.Ecosystem` Enum (lands in S2-01) are *intentionally distinct symbols* with non-overlapping responsibilities. A static-only test in `tests/unit/types/test_identifiers_phase7.py` asserts that (a) `codegenie.types.identifiers.Ecosystem` exists today and is a `typing.Literal` (not an Enum), and (b) carries a `# TODO(S2-01)` comment naming the follow-up: once S2-01 lands the Phase 7 enum, the test is extended to import the Phase 7 `Ecosystem` and assert `codegenie.types.identifiers.Ecosystem is not codegenie.primitives.vuln_provenance.registry.Ecosystem`. This sentinel makes accidental cross-module imports fail loudly (Rule 12 — fail loud) and documents the collision for future readers.
- [ ] **AC-12 — Gates.** `mypy --strict src/codegenie/types/` clean; `ruff check`, `ruff format --check` clean on touched files; `make lint-imports` green; Phase 3 + Phase 0/1/2 regression suite green (no existing test weakened or skipped).
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

@pytest.mark.parametrize(
    "bad",
    [
        "",                       # empty
        " ",                      # single space
        "image name",             # embedded whitespace
        "image\tname",            # embedded tab
        "image\nname",            # embedded newline
        "image\x00name",          # embedded NUL
        "image\x7fname",          # embedded DEL
        "image\x1fname",          # embedded unit-separator (last C0 control char)
        "a" * 257,                # 257 chars — one over the floor
        "node:20:foo",            # multi-`:` — multi-tag is rejected
        "node:",                  # trailing `:` (empty tag) — rejected per AC-3
    ],
)
def test_image_ref_rejects(bad):
    r = parse_image_ref(bad)
    assert isinstance(r, Err)


def test_image_ref_max_length_boundary_accepted():
    """256 chars (the floor) is accepted; 257 is rejected (covered above)."""
    r = parse_image_ref("a" * 256)
    assert isinstance(r, Ok)


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

The subprocess-mypy meta-test goes in `tests/unit/types/test_identifiers_phase7_mypy_negative.py`. The pattern mirrors Phase 3's `test_identifiers_phase3_mypy_negative.py` — a `_ctor_arg(name)` helper provides the syntactically-correct literal per newtype, and a separate `test_mypy_accepts_correct_usage_phase7` negative-control ensures the harness itself isn't broken:

```python
from __future__ import annotations
import subprocess, sys, textwrap
from pathlib import Path
import pytest

PHASE7_STR_NEWTYPES = ("ImageRef", "ImageDigest", "LayerDigest", "RuntimeId", "DockerStageName")

# Every Phase-7 newtype appears as either A or B in ≥ 1 pair.
SWAP_PAIRS: list[tuple[str, str]] = [
    ("ImageDigest", "LayerDigest"),
    ("LayerDigest", "ImageDigest"),
    ("ImageRef", "ImageDigest"),
    ("ImageDigest", "ImageRef"),
    ("RuntimeId", "DockerStageName"),
    ("DockerStageName", "RuntimeId"),
]


def _ctor_arg(name: str) -> str:
    """Return a syntactically-correct literal-string for ``name(...)``.

    NewType constructors do NOT validate at runtime; this only needs to be a
    string. Choosing inputs that resemble each newtype's grammar keeps the
    intent of the test readable for a human reviewer.
    """
    if name in ("ImageDigest", "LayerDigest"):
        return f'"sha256:{"0" * 64}"'
    if name == "ImageRef":
        return '"node:20-alpine"'
    if name == "RuntimeId":
        return '"node20"'
    if name == "DockerStageName":
        return '"builder"'
    raise AssertionError(f"unknown Phase-7 newtype {name!r}")


@pytest.mark.parametrize("a,b", SWAP_PAIRS, ids=lambda v: v if isinstance(v, str) else "")
def test_mypy_rejects_phase7_swap(tmp_path: Path, a: str, b: str) -> None:
    src = textwrap.dedent(
        f"""
        from codegenie.types.identifiers import {a}, {b}

        def _accept_{a.lower()}(_x: {a}) -> None: ...

        _accept_{a.lower()}({b}({_ctor_arg(b)}))
        """
    )
    tmp = tmp_path / "swap.py"
    tmp.write_text(src)
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(tmp)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0, (
        f"mypy --strict accepted {a} <- {b}; stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    out = result.stdout.lower()
    assert "incompatible type" in out or "argument" in out, (
        f"mypy rejected but not for the expected reason; stdout:\n{result.stdout}"
    )


def test_mypy_accepts_correct_usage_phase7(tmp_path: Path) -> None:
    """Negative control — without this, a broken mypy harness would make every swap pass."""
    lines = ["from codegenie.types.identifiers import (", *(f"    {n}," for n in PHASE7_STR_NEWTYPES), ")", ""]
    for n in PHASE7_STR_NEWTYPES:
        lines.append(f"def _accept_{n.lower()}(_x: {n}) -> None: ...")
        lines.append(f"_accept_{n.lower()}({n}({_ctor_arg(n)}))")
    tmp = tmp_path / "ok.py"
    tmp.write_text("\n".join(lines) + "\n")
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(tmp)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, (
        f"mypy --strict rejected correct usage; stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
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

- **The `Layer` / `Ecosystem` enums** — landed by S2-01 in `src/codegenie/primitives/vuln_provenance/registry.py` (this story declares `ProvenanceAdapterId` with `TYPE_CHECKING` forward refs so S2-01 lands cleanly without a circular dependency).
- **`DistroPackage` Pydantic model** — landed by S1-02 (this story is newtypes-only).
- **`Provenance` discriminated union** — landed by S1-03.
- **`VulnProvenanceAdapter` Protocol** — landed by S1-04.
- **`SyftSbom` reader** — landed by S1-05.
- **The Phase 7 import-linter / no-`Any` fences** — landed by S1-06.
- **Full Distribution-spec `ImageRef` validation** — deferred to a future hardening story; `parse_image_ref` ships as a tight floor (control chars, whitespace, length, single-`:` rule).
- **Any edits under `src/codegenie/primitives/vuln_provenance/`** — that tree does not yet exist; S1-02 creates the directory + `__init__.py`. This story touches only `codegenie/types/identifiers.py`, `codegenie/types/parsers.py`, `codegenie/types/__init__.py`, and the three new test modules.
- **Renaming the Phase 3 `Ecosystem` Literal** — the Phase 3 and Phase 7 `Ecosystem` symbols intentionally coexist in different modules with different membership; the validator AC-11 sentinel test documents the collision but does not migrate either symbol. A future refactor (e.g., "vuln-index migrates to the Phase 7 enum") would need its own ADR.

## Notes for the implementer

- **`CveId` and `PackageId` are already in `identifiers.py`** (Phase 3 ADR-0010, lines 74 + 76). **Do not redefine them.** Phase 7 reuses them verbatim — `assemble_provenance` and every adapter import them from the same canonical home. The test in AC-2 is the structural guard against accidental shadowing.
- **The `sha256:` prefix is load-bearing.** The arch's `Provenance` union's `BaseImage` variant carries `image_digest: ImageDigest` and `layer_digest: LayerDigest`; both must be `sha256:`-prefixed at the type-system level so adapter code can't accidentally pass an untagged hex string. AC-4 is the central correctness pin — every alternative algorithm (sha512, blake3, etc.) is rejected at the smart-constructor boundary today; admitting a new algorithm requires an ADR amendment, not a parser tweak.
- **`ProvenanceAdapterId` is a tuple alias, not a `NewType`.** `NewType` over a generic `tuple[...]` is unsupported in mypy's strict mode; the arch + ADR-0006 deliberately specify `ProvenanceAdapterId = tuple[Layer, Ecosystem]`. Use `TYPE_CHECKING`-guarded forward references to break the circular dep with S2-01's `registry.py`; the AC-9 test asserts the alias shape today and contains a `# TODO(S2-01)` marker to tighten once `Layer` / `Ecosystem` land.
- **`Result` lives at `codegenie.result`.** Phase 3 S1-01 was explicit: do NOT create `src/codegenie/types/result.py`. Import `Ok` / `Err` / `Result` from `codegenie.result`. Instantiate with `Ok(value=...)` / `Err(error=...)` keyword args (the canonical Pydantic discriminator-on-`kind` idiom).
- **Mirror Phase 3's `_NEWTYPE_REGISTRY` discipline.** Each entry is a one-line docstring naming the ADR + the immediate Phase 7 consumer. The test in AC-8 enforces that every new entry cites Phase 7 ADR-0004 or ADR-0006 — drift here is silent docstring rot.
- **`mypy --strict` is the bar.** The subprocess-mypy meta-test (AC-6) catches the swap class of bugs that line-comment prose cannot. Phase 3 S1-05's validation explicitly closed this trap; do not regress to commented-out swap lines.
- **Phase 3 + Phase 0/1/2 regression suite must stay green.** This story is additive to `identifiers.py`, but any change to the Phase 3 `_NEWTYPE_REGISTRY` test fixtures or `__all__` discipline could ripple. Run `pytest tests/unit/types/ -x` after the green pass — any pre-existing test must still pass unchanged.

### Design-pattern observations (from the validator's design-patterns critic)

These are *implementation guidance* — they're not promoted to ACs because they describe internal shape (Rule 2 — three similar lines is better than premature abstraction) but they materially affect extensibility:

- **Shared regex, separate `_regex_parser` closures.** `parse_image_digest` and `parse_layer_digest` share `_SHA256_DIGEST_RX` but each instantiates its own `_image_digest_match = _regex_parser(_SHA256_DIGEST_RX, max_len=71, name="ImageDigest")` and `_layer_digest_match = _regex_parser(_SHA256_DIGEST_RX, max_len=71, name="LayerDigest")` so the `Err.message` distinguishes the two newtypes at the error boundary. This mirrors Phase 3's `_match`-closure-per-newtype catalog (`parsers.py` lines 131-144). Don't collapse them into one closure that downcasts on the calling parser.
- **`parse_image_ref` deliberately bypasses `_regex_parser`.** The floor checks (length, whitespace, control chars, `:`-count) are *not* a single regex — `parse_image_ref` is intentionally permissive and the only one of the five parsers that lives outside the regex-helper pattern. This is documented in the Implementation Outline; do not "harmonise" it by inventing a giant Distribution-spec regex (that's a deferred follow-up).
- **`Ecosystem` enum value strings become the within-layer dispatch sort key (ADR-0006).** When S2-01 lands `class Ecosystem(str, Enum): NPM = "npm"; YARN_BERRY = "yarn-berry"; PNPM = "pnpm"; APK = "apk"; DPKG = "dpkg"; RPM = "rpm"`, alphabetic sorting of the *values* produces the dispatch order `apk < dpkg < npm < pnpm < rpm < yarn-berry`. The Phase 7 npm adapter therefore dispatches *after* apk/dpkg within the BASE_IMAGE layer (irrelevant — they're in different layer-sets) but *before* yarn-berry within the APP layer (load-bearing for polyglot tiebreakers). S1-01 doesn't ship the enum, but flag this for the S2-01 implementer: the *string values*, not the declaration order, determine routing. If a different dispatch order is desired, ADR-0006 must be amended.
- **`ProvenanceAdapterId` is a `TypeAlias`, NOT a `NewType`.** `NewType` over a generic tuple is unsupported in mypy strict mode (see [mypy docs §NewType limitations](https://mypy.readthedocs.io/en/stable/more_types.html#newtypes)). The arch + ADR-0006 specify a `TypeAlias` for exactly this reason.
- **Open/Closed at the parsers boundary.** Adding a sixth Phase 7 newtype later (e.g., a hypothetical `SbomDigest`) is a *one-row* edit: `NewType` declaration + `_NEWTYPE_REGISTRY` row + smart constructor + `__all__` entry + re-export — zero edits to existing parsers, zero edits to existing tests. The existing rule-of-three regex catalog pattern (`_recipe_match`, `_signal_match`, ...) is the precedent; mirror it.
