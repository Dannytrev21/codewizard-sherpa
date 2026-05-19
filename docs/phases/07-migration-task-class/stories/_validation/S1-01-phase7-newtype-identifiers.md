# S1-01 — Phase 7 newtype identifiers + smart constructors — Validation report

**Story:** [../S1-01-phase7-newtype-identifiers.md](../S1-01-phase7-newtype-identifiers.md)
**Validated:** 2026-05-19
**Validator pass:** `phase-story-validator` skill (first pass — no prior `_validation/` entry for Phase 7)
**Verdict:** **HARDENED** — real but fixable weaknesses found; edits applied in place; ready for `phase-story-executor`.

## Context Brief (Stage 1)

### Story snapshot
- **Goal (verbatim):** Extend `codegenie.types.identifiers` with the six Phase 7 newtypes (`ImageRef`, `ImageDigest`, `LayerDigest`, `RuntimeId`, `DockerStageName`, `ProvenanceAdapterId`) and pair each `str`-backed newtype with a smart-constructor parser returning `Result[T, ParseError]`, so every later Phase 7 story imports its typed primitives from one canonical home and `ImageDigest("sha256:...")` is the only legitimate construction path.
- **Non-goals (out-of-scope):** The `Layer` / `Ecosystem` enums (S2-01), `DistroPackage` Pydantic model (S1-02), `Provenance` discriminated union (S1-03), `VulnProvenanceAdapter` Protocol (S1-04), `SyftSbom` reader (S1-05), Phase 7 import-linter + no-`Any` fences (S1-06), full Distribution-spec `ImageRef` validation (deferred).

### Files to touch
- `src/codegenie/types/identifiers.py` — modify (extend with 5 newtypes + alias + registry rows)
- `src/codegenie/types/parsers.py` — modify (5 new smart constructors)
- `src/codegenie/types/__init__.py` — modify (re-export 6 new names)
- `tests/unit/types/test_identifiers_phase7.py` — create
- `tests/unit/types/test_identifiers_phase7_mypy_negative.py` — create
- `tests/unit/types/test_parsers_phase7_properties.py` — create

### Phase / arch constraints
- ADR-0004 — `primitives/vuln_provenance/` is the additive home; `Ecosystem` + `Layer` enums land in its `registry.py` (per `__init__.py` re-export list).
- ADR-0006 — `ProvenanceAdapterId = tuple[Layer, Ecosystem]` is the registry key; within-layer iteration is `Ecosystem`-enum-sorted (the *string values* determine order, not declaration order).
- Production ADR-0033 — every domain identifier crosses module boundaries as a `NewType`; raw `str` at typed boundaries is a review-blocker.
- Production ADR-0038 — `BaseImage` variant of the `Provenance` discriminated union carries `image_digest: ImageDigest` and `layer_digest: LayerDigest` (load-bearing sha256:-prefix invariant).

### Phase exit criteria the story contributes to
- "Every Step 1+ story imports its typed primitives from one canonical home" (Goal verbatim).
- Newtype catalog at `codegenie.types.identifiers` extends Phase 3's 22 names with Phase 7's 6 additions; `__all__` stays sorted superset.

### Prior validation history
- None — first Phase 7 story validated by this pipeline. `docs/phases/07-migration-task-class/stories/_validation/` directory created.

### Open ambiguities (Stage 1 gate)
- ⚠️ **`Ecosystem` symbol collision** — Phase 3 ships `Ecosystem = Literal[...]` (in `codegenie.types.identifiers`, 5 ecosystems: npm/pypi/maven/rubygems/gomod). Phase 7's S2-01 will introduce a *different* `Ecosystem(str, Enum)` (in `primitives/vuln_provenance/registry.py`, 6 members: NPM/YARN_BERRY/PNPM/APK/DPKG/RPM). The two are intentionally distinct (different membership; ingest-side vuln-index filter vs. dispatch key) but the story as written did not acknowledge this. **Resolution path within validator scope:** edit AC-1 to make the import path explicit, add AC-11 as a sentinel test, document the collision in `Notes for the implementer`. No need to bump to the user — the collision is real but addressable in-place via tighter ACs.

## Stage 2 — Critic findings

### Coverage critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| C1 | harden | AC-3 `parse_image_ref` rejects control chars `\x00-\x1f` but not `\x7f` (DEL) — common SBOM contamination | Expanded AC-3 + added DEL test case in red snippet |
| C2 | harden | AC-3 `parse_image_ref` happy-path examples don't specify tag-empty / multi-`:` behavior; ambiguous | AC-3 now explicit: zero or one `:` allowed; `"node:"` rejected; multi-`:` rejected |
| C3 | harden | AC-3 `parse_runtime_id` / `parse_docker_stage_name` missing length-boundary tests (64 / 65 chars) | Added boundary requirement to AC-3 |
| C4 | harden | AC-4 `ImageDigest` matrix missing whitespace / NUL / DEL contamination cases | Added 5 contamination cases to AC-4 |
| C5 | harden | AC-8 docstring registry asserts "ADR-0004 OR ADR-0006" — Phase 3 precedent requires both ADR AND consumer name | Strengthened AC-8 to require both, with suggested values |
| C6 | harden | AC-10 (was AC-5 sub-bullet only) — `__init__.py` re-export should be an AC not just an Impl-Outline step | Promoted to its own AC-10 |

### Test-Quality critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| T1 | block | TDD `mypy --strict` swap test uses brittle inline f-string conditional (`"sha256:" + "0"*64 if "Digest" in {b!r} else "x"`) — Python precedence trap, fragile, doesn't generalise to `RuntimeId` / `DockerStageName` | Replaced with `_ctor_arg(name)` helper mirroring Phase 3's pattern |
| T2 | block | Missing negative-control (`test_mypy_accepts_correct_usage_phase7`) — without it a broken mypy install would make every swap test pass for the wrong reason | Added; Phase 3 precedent in `test_identifiers_phase3_mypy_negative.py` |
| T3 | nit | Property test for `parse_image_digest` round-trip uses structural identity (`r.value == s`); could tighten to newtype-cast identity | Left as-is — NewType is runtime-identity to underlying type; current assertion is sufficient |
| T4 | harden | TDD plan's red test would NOT distinguish "passing `s` unwrapped" from "returning `Ok(ImageDigest(s))`" in a parser that wraps everything blindly. AC-4's matrix mutation-tests this implicitly (a blind `Ok(...)` would accept every contamination case and fail those tests) | Coverage already strong; documented mutation-resistance in validation notes |
| T5 | nit | Tests named `test_parser_happy_path` — Phase 3 used `test_phase3_*_happy`. Naming nit, not a functional concern | Left as-is — fine within Phase 7 namespace |

### Consistency critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| CO1 | block | `Ecosystem` symbol collision (Phase 3 Literal vs. Phase 7 Enum) — story silent | Documented in Validation Notes; AC-1 pins import path; AC-11 adds sentinel test; out-of-scope explicitly excludes renaming |
| CO2 | harden | AC-1 leaves runtime alias shape ambiguous (string forward refs vs. `TYPE_CHECKING` import + plain tuple) | AC-1 now mandates exact `TypeAlias` pattern with `_PhVnLayer` / `_PhVnEcosystem` underscored aliases |
| CO3 | nit | AC-3 "Lowercase only" is redundant with the regex | Left as-is (helpful prose for human reader) |
| CO4 | harden | Story silent on "no edits to `primitives/vuln_provenance/`" — could lead implementer to create the dir prematurely | Added to Out-of-scope |
| CO5 | harden | AC-8 docstring assertion logic asks "or" — precedent uses both | Strengthened to "and"; cross-referenced Phase 3 module |

### Design-Patterns critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| DP1 | nit | Story already prescribes Newtype + Smart Constructor + Functional Core | No change needed |
| DP2 | harden | `parse_image_digest` / `parse_layer_digest` should use **separate** `_regex_parser` closures sharing the same regex (so `Err.message` distinguishes them) — story said "share the constant" but ambiguous about closure shape | Added to Design-pattern observations under Notes-for-implementer |
| DP3 | harden | `parse_image_ref` deliberately bypasses the regex helper — should be explicit | Added to Design-pattern observations |
| DP4 | harden | `Ecosystem`-enum-sorted iteration (ADR-0006) depends on enum *value strings*, not declaration order — flag for S2-01 implementer | Added to Design-pattern observations |
| DP5 | nit | `ProvenanceAdapterId` is `TypeAlias` not `NewType` because mypy doesn't support `NewType[generic tuple]` | Already in Notes; added mypy docs link |
| DP6 | nit | Open/Closed extension at parsers boundary — adding a 6th newtype later is a one-row edit | Added to Design-pattern observations |

**Decision-conflict resolution (per the validator skill's priority `Consistency > Coverage > Test-Quality > Design-Patterns`):**

- CO1 (Ecosystem collision) interacts with C5/CO5 (AC-8 docstring requirements) and AC-9 (alias shape): Consistency wins — the alias shape must explicitly route to the Phase 7 `Ecosystem` via the registry module path, never via `codegenie.types.identifiers`. AC-1, AC-9, AC-11 all updated to reflect this.
- DP2 (separate closures) interacts with Rule 2 (premature abstraction): no conflict — the existing Phase 3 catalog already established the closure-per-newtype pattern (rule-of-three met).
- AC-11 (the new sentinel test) is **observable** (a runtime test of two module symbols) rather than a pattern-name mandate, so per the skill's editor rules it is properly an AC and not a Notes-only observation.

## Stage 3 — Researcher

**Skipped.** No critic finding required external research:

- Mutation-thinking for the smart constructors is already covered by the existing AC-4 contamination matrix.
- Property-based test patterns are already in use (`hypothesis.from_regex(rx, fullmatch=True)` is the canonical idiom — Phase 3 `test_parsers_properties.py` is precedent).
- The `Ecosystem` collision resolution is a project-internal decision, not a canonical pattern lookup.

## Stage 4 — Edits applied

### To `S1-01-phase7-newtype-identifiers.md`

1. **Header**: Status `Ready` → `HARDENED`. Added a `## Validation notes (2026-05-19 — phase-story-validator HARDENED pass)` block summarising every change.
2. **AC-1**: Rewrote to mandate the exact `TypeAlias` declaration with underscored `_PhVnLayer` / `_PhVnEcosystem` aliases.
3. **AC-3**: Expanded `parse_image_ref` floor (DEL, `\x00`, whitespace per `str.isspace`, single-`:` rule); added max-length boundary test; added length boundary requirements for `parse_runtime_id` / `parse_docker_stage_name`; specified separate `_regex_parser` closure for `parse_layer_digest`.
4. **AC-4**: Restructured into Algorithm / Casing / Length / Charset / Structure / Contamination buckets; added 5 contamination cases (leading space, trailing space, trailing newline, trailing NUL, embedded DEL).
5. **AC-6**: Replaced "incompatible type" assertion with a stronger compound assertion (returncode != 0 AND stdout matches); promoted `_ctor_arg(name)` helper from Phase 3; required `test_mypy_accepts_correct_usage_phase7` negative-control.
6. **AC-8**: Changed "or" → "and" — every Phase 7 registry value must cite both an ADR AND a consumer; added suggested values; added (c) consumer-reference allow-set.
7. **AC-9**: Made the alias-shape test more concrete (test asserts `__origin__` is `tuple`, `__args__` are the underscored forward refs); added a hard "must NOT import from primitives/vuln_provenance/" guard.
8. **AC-10 (NEW)**: Package-level re-export discipline lifted from Implementation Outline.
9. **AC-11 (NEW)**: `Ecosystem` symbol-collision sentinel — static test that the Phase 3 Literal exists and is distinct from the Phase 7 Enum.
10. **AC-12**: Renumbered from the original AC-10 (gates).
11. **TDD plan — Red snippet**:
    - `test_image_ref_rejects` now parametrized over 11 cases (was 5) covering whitespace, control chars, multi-`:`, empty-tag, length boundary.
    - Added `test_image_ref_max_length_boundary_accepted` (positive boundary test).
    - Replaced the `mypy` negative-test snippet with the `_ctor_arg(name)`-based version + negative control.
12. **Out-of-scope**: Added (a) explicit "no edits under `src/codegenie/primitives/vuln_provenance/`", (b) the Phase 3 `Ecosystem` Literal is *not* renamed in this story, (c) expanded ImageRef floor scope.
13. **Notes for the implementer**: Added a new "Design-pattern observations" section with 5 bullets — shared-regex / separate-closure discipline, `parse_image_ref` non-regex justification, enum-value-string dispatch ordering note for S2-01, `TypeAlias` vs `NewType` reasoning (with mypy docs link), Open/Closed-at-parsers extension precedent.

### To the codebase
None. Validator does not implement; story file is the only edited artifact.

## Final verdict: HARDENED

The story is ready for `phase-story-executor`. The key invariants the executor must respect:

1. **Read the Validation notes block first** — it summarises every change.
2. **The `ProvenanceAdapterId` import path is load-bearing** — must come from `codegenie.primitives.vuln_provenance.registry`, NOT from `codegenie.types.identifiers`.
3. **The `Ecosystem` collision is intentional** — do NOT rename either symbol within this story.
4. **AC-11's sentinel test is the structural guard against accidental re-imports** — it must stay green.
5. **The mypy negative test pattern matches Phase 3** — use `_ctor_arg(name)` and the `test_mypy_accepts_correct_usage_phase7` negative-control.

Estimated executor attempts: **1** (M-effort story, all blockers resolved, TDD plan concretely buildable from Phase 3 precedent).
