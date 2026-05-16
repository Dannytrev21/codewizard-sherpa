# Validation report — S3-02 `RedactedSlice` smart constructor private to `redact_secrets`

**Story:** [`../S3-02-redacted-slice-smart-constructor.md`](../S3-02-redacted-slice-smart-constructor.md)
**Validated:** 2026-05-15
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

The story ships `src/codegenie/output/redacted_slice.py` with the `RedactedSlice` Pydantic model — `frozen=True, extra="forbid"`, three fields (`slice: dict[str, JSONValue]`, `findings_count: int`, `fingerprints: list[str]`), an 8-lowercase-hex format validator, and a `findings_count >= len(fingerprints)` model invariant. The threefold structural-defense framing (runtime via S3-01; type-system via this module + S3-03 signature; source-level via S7-04 inspect test) traces cleanly to 02-ADR-0010, 02-ADR-0005, production ADR-0033, and `phase-arch-design.md §"Gap analysis & improvements" Gap 4`.

The draft was structurally sound — no RESCUE-tier findings — but carried **three BLOCK-severity prescription bugs** (it would not have compiled or run as written) and **eight harden-tier coverage / test-quality gaps** that would have let plausibly-wrong implementations slip past the executor's Validator pass. Fourteen edits applied in place; story is ready for `phase-story-executor`. Stage 3 research skipped (no `NEEDS RESEARCH` findings — every gap was answerable from arch + ADR-0005 + ADR-0010 + production ADR-0033 + S1-11 / S3-01 sibling validation precedent + verified live source on master).

The three BLOCK bugs:

1. **B1 — `JSONValue` import path wrong** (`codegenie.types` → `codegenie.parsers`). Same B2 bug closed in S3-01 (Validation note #2). The `parsers` package landed in Phase 1 S1-02; the `types` package holds identifier newtypes only.
2. **B2 — Non-existent file reference** (`src/codegenie/types.py (Phase 0)` does not exist on master). The `codegenie.types` *package* (`src/codegenie/types/identifiers.py`) carries the newtypes; `JSONValue` is in `parsers`.
3. **B3 — AC-13 prescribes a non-existent enforcement surface** ("forbidden-patterns glob includes `src/codegenie/output/**/*.py`"). S1-11 (Done, master verified) ships the path-scoping **inside** `scripts/check_forbidden_patterns.py` via a `_PHASE2_BANNED_PACKAGES: frozenset[str]` set + an `_is_under_phase2_banned_package(path) -> bool` predicate on a `Rule` dataclass's `applies_when` field — **not** a `.pre-commit-config.yaml` glob. A test asserting a glob would fail on the real surface.

Every test affected by B1/B2/B3 would have failed red on `phase-story-executor`'s first attempt for non-design reasons. The executor's three-attempt loop would have burned attempts hunting prescription bugs that S3-01 already closed for its own scope.

Eight harden-tier gaps closed: missing property-based hypothesis coverage for fingerprint format (`F3`); missing boundary-equality and zero-baseline cases for `findings_count` invariant (`F4`); missing JSON byte-stability assertion (cache-stability invariant — `F5a`); missing genuinely-nested-recursion fixture for `JSONValue` round-trip (`F5b`); missing field-declaration-order pin (`F6`); over-loose AC-12 subprocess prescription (`F1`); bare-word grep collision with this module's own docstring (`F2`); missing module-docstring programmatic-check mechanism (`F7`); missing cross-story integration with S3-01 (`F8`, mirrors S3-01 AC-33).

Three design-pattern Notes-for-implementer additions (`DP1`, `DP2`, `DP3`): `Fingerprint` newtype rule-of-three threshold (crosses at S3-03 — defer surface to S3-03 or a cross-cutting story); `RedactedSlice` closed-product-type framing (mirrors S3-01 note #12); functional-core/imperative-shell discipline (no I/O ever in `redacted_slice.py`). DP4 (module-private constructor option, rejected per the implementer note) and DP5 (`Annotated[str, Field(pattern=...)]` vs `@field_validator`, already in the notes) were verified already-present; no edits needed.

Nineteen ACs original → **twenty-six ACs** after hardening (AC-7b, AC-8b, AC-10b, AC-10c, AC-11b, AC-12b, AC-15b added; AC-2, AC-7, AC-12, AC-13, AC-14, AC-18 reworded). Implementation outline §2 rewritten with exact subprocess invocation + regex source-of-truth pin. Files-to-touch table unchanged (model + one test file). Notes-for-implementer gained a "Design patterns" subsection. Story is now ready for `phase-story-executor`.

## Context Brief (Stage 1)

### Story snapshot

- **Goal as written:** Ship `src/codegenie/output/redacted_slice.py` with the `RedactedSlice` Pydantic model such that it is `frozen=True, extra="forbid"`, has exactly three fields, validates fingerprints as 8-lowercase-hex, enforces `findings_count >= len(fingerprints)`, round-trips through `model_dump_json` / `model_validate_json`, and is the only type the writer accepts (S3-03 closes the signature edge). `model_construct` is banned by S1-11 (lands the silent-bypass closure).
- **Non-goals (from Out-of-scope):** `redact_secrets` implementation (S3-01); `OutputSanitizer.scrub` composition + ordering documentation (S3-03); writer signature tightening (S3-03); `secrets_redacted_count` log field (S3-03); `inspect`-based S7-04 boundary test; `tests/adv/phase02/test_secret_in_source.py` (S6-07) and `test_no_inmemory_secret_leak.py` (S7-04); Phase 4 RAG ingestion consumers.

### Phase 2 exit criteria touched

- **Gap 4 closed in-phase** (arch §"Gap analysis & improvements" Gap 4 — smart-constructor at the writer boundary). ✓
- **Three-rung structural defense ladder** (02-ADR-0010 + 02-ADR-0005 — runtime + type-system + source-level). ✓ (this module is the type-system rung; S7-04 is the source-level rung; S3-01 is the runtime rung).
- **`model_construct` ban surface preserved** (S1-11 already shipped the rule + predicate). ✓ (AC-12, AC-12b, AC-13 verify the live surface).
- **No plaintext in persisted artifacts — G5 invariant** (02-ADR-0005). ✓ (fingerprints are 8-hex BLAKE3, privacy-preserving by construction).
- **Open/Closed at the persisted-shape boundary.** ✓ (`RedactedSlice` is a closed product type; adding a fourth persisted field is an ADR amendment — DP2 surfaces this).

### Load-bearing commitments touched

- CLAUDE.md §"No LLM anywhere in the gather pipeline" — `redacted_slice.py` is pure model + validators, zero LLM. ✓
- CLAUDE.md §"Facts, not judgments" — the model carries fingerprints (facts) and counts (facts), not judgments. ✓
- CLAUDE.md §"Determinism over probabilism" — pure data + validators = deterministic. AC-10b pins JSON byte-stability across rounds. ✓
- CLAUDE.md §"Extension by addition" — fourth persisted field = 02-ADR-0010 amendment + new field declaration; existing fields and validators untouched. ✓ (DP2 codifies this in the story).
- CLAUDE.md §"Honest confidence" — N/A here (the model carries fingerprints, not confidence).
- 02-ADR-0010 §Decision — three-field closed product type; `RedactedSlice` carries only what may persist (the slice + count + fingerprints; **not** `list[SecretFinding]`, which is the in-memory CLI-summary path). ✓
- 02-ADR-0005 — no plaintext anywhere; this module's `fingerprints` field is the *only* secret-related persisted field, and it is privacy-preserving by construction. ✓
- Production ADR-0033 §3 — newtype + smart-constructor discipline at the I/O boundary. ✓ (`Fingerprint` newtype rule-of-three threshold crosses at S3-03 — DP1 defers).

### Open/Closed boundaries

- New *persisted field* on `RedactedSlice` → ADR amendment to 02-ADR-0010 + field declaration; the validator family stays untouched (DP2).
- New *consumer of `RedactedSlice`* → S3-03 writer is the first consumer; Phase 4 RAG ingestion is the projected second; no edits to `redacted_slice.py` for new consumers.
- New *fingerprint format* → would touch the `_FP_PATTERN` regex and the docstring (single source of truth in the validator) and `_fingerprint(...)` in S3-01; ADR amendment to 02-ADR-0010.
- Module-level `RedactedSlice` + `_FP_PATTERN` is the **monkeypatch reach** for mutation tests (parallels S3-01 AC-30 on `_PATTERNS`); no AC pins this in S3-02 because the validator behavior is verified by the validator's own tests (`hypothesis` property in AC-7b is mutation-resistant by sampling).

### Sibling-family lineage

- **2nd** secret-redaction story in Phase 2 (S3-01 → **S3-02** → S3-03 family). S3-01 ships `redact_secrets` body; this story ships the model; S3-03 tightens writer signature + composition order + log field.
- **Smart-constructor pattern pair** with S3-01 — `redact_secrets` is the convention-named factory; `RedactedSlice` is the constructed type; the threefold defense closes at lint + S7-04.
- **Closed product type discipline** parallels S1-01 (`IndexFreshness` sum type) and S1-03 (`AdapterConfidence` sum type) — extension is ADR-amendment-gated. DP2 promotes this to a Note.
- **`JSONValue` recursive alias consumer** — third in Phase 2 after S1-04 (TCCM) and S1-02 (parsers themselves). The recursive alias must round-trip through Pydantic; AC-10c adds the genuinely-nested fixture to verify.

### Rule-of-three threshold for `Fingerprint` newtype

NOT YET CROSSED IN S3-02 (this is the 2nd consumer). **S3-03 will be the third** (writer reads `slice_.fingerprints` per 02-ADR-0010 Tradeoffs row 2). DP1 defers the newtype introduction to S3-03 or a cross-cutting story landing concurrently with the audit-anchor / RAG ingest consumers.

### Prior validation history

- None for S3-02. Cross-referenced:
  - **S3-01 validation** (15 hardened ACs; `JSONValue` import-path bug B2 closed; `content_hash_bytes` API mismatch B1 closed; sibling-family lineage codified; `Fingerprint` newtype deferred at note #11).
  - **S1-11 validation** (refactored `_RULES` into `Rule` dataclass with `applies_when` predicate; `_PHASE2_BANNED_PACKAGES` frozenset is the live path-scoping mechanism; advice contract is `and`, not `or`).

### Open ambiguities

None — proceeded to Stage 2.

## Stage 2 — critic reports

### Coverage (verdict: HARDEN — 6 findings)

The 19 draft ACs cover the model shape, frozen+extra="forbid" invariants, fingerprint format, count-vs-fingerprints invariant, round-trip, `model_construct` ban, and Phase-0/1 invariants. But several edge cases and integration invariants were absent:

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| C1 | harden | AC-7 covers six scalar fingerprint-format cases; missing closure-by-property-test against the complement. Mutation-fragile: a `if fp != "00000000"` special-case slips past. | **Applied.** AC-7b added — hypothesis property test over the alphabet `"0123456789abcdef"` (accept) and over the complement (reject). |
| C2 | harden | AC-8 pins the strict-less-than rejection and a strict-greater acceptance; missing the equality boundary and the zero-baseline. A `<` vs `<=` regression slips past. | **Applied.** AC-8b added — parametrized boundary table covering `(0, [])`, `(1, ["abcdef12"])` (equality), `(3, ["abcdef12"])` (count > unique, the 02-ADR-0010 contract), and four rejection cases. |
| C3 | harden | AC-10 round-trip asserts Pydantic equality but does not pin JSON byte-stability across rounds (Phase 0 cache-stability invariant — content-addressed keys depend on this). | **Applied.** AC-10b added — `model.model_dump_json() == model.model_dump_json()` on the same instance. |
| C4 | harden | AC-10 round-trip fixture's nesting depth is unspecified; a flat one-level dict would satisfy the AC textually but would not exercise `JSONValue` recursion through Pydantic. | **Applied.** AC-10c added — fixture has ≥ 3 levels of nesting (dict → list → dict) with interleaved placeholder strings, non-secret strings, `None`, integers, and `list[str]`. |
| C5 | harden | Field declaration order in `model_dump()` is named in the implementer notes but no AC enforces it. A refactor that re-orders fields silently passes AC-11 (which only asserts the *set*). | **Applied.** AC-11b added — `list(model.model_dump().keys()) == ["slice", "findings_count", "fingerprints"]` AND `list(json.loads(model.model_dump_json()).keys()) == [...]`. |
| C6 | harden | AC-15 covers only the empty-slice happy path of `redact_secrets`. No AC exercises the cross-story integration (S3-01 emits → S3-02 validates) over the canonical secret shapes. | **Applied.** AC-15b added — parametrized over four canonical shapes (zero, one, three-distinct, same-twice); each round-trips through `model_validate(model_dump())` and asserts the three invariants. |

### Test-quality (verdict: HARDEN — 5 findings + 3 of the above reinforced)

The 19 draft tests cover happy-path construction, the `model_construct` ban, the basic invariants, and round-trip. But several mechanism choices were under-specified or mutation-fragile:

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| TQ1 | harden | AC-12 subprocess prescription is "e.g., subprocess call" — does not pin the invocation shape, the exit-code contract, or the advice-string contract (`and` per S1-11 AC-2). | **Applied.** AC-12 rewritten with the exact `subprocess.run([sys.executable, "scripts/check_forbidden_patterns.py", str(target)], ...)` invocation; assert `result.returncode >= 1`; assert stdout contains BOTH `"02-ADR-0010 §Decision"` AND `"production ADR-0033 §3"`. |
| TQ2 | harden | No negative-path test for the path-scoping predicate. A regression that broadens `applies_when` to "every Python file" passes AC-12 (the test always writes to the banned package). | **Applied.** AC-12b added — same offending content written to `tmp_path/src/codegenie/parsers/synth.py` (NOT in `_PHASE2_BANNED_PACKAGES`); MUST exit clean. |
| TQ3 | harden | AC-14 bare-word grep would false-positive on this module's own docstring (which references `model_construct` as the banned construct per AC-1). | **Applied.** AC-14 rewritten to use the same structural regex as the lint rule (`\.model_construct\s*\(|\bmodel_construct\s*=`). Source-of-truth pin via import from `scripts.check_forbidden_patterns` (or inline regex with a comment naming the source). |
| TQ4 | harden | AC-13 asserts a "forbidden-patterns glob" that does not exist on master. The path-scoping lives inside the lint script. A test asserting a glob would simply fail — BLOCK-tier on the runtime surface. (Reported as B3 above.) | **Applied.** AC-13 rewritten to import `_PHASE2_BANNED_PACKAGES` and `_is_under_phase2_banned_package` from `scripts.check_forbidden_patterns` and assert them directly. |
| TQ5 | harden | AC-2 docstring requirement names four substrings but pins no test mechanism. | **Applied.** AC-2 strengthened — `inspect.getdoc(codegenie.output.redacted_slice)` substring-matches `"Gap 4"`, `"02-ADR-0010"`, `"02-ADR-0005"`, and `"Three rungs"` (case-insensitive for the ladder framing). Mirrors S3-01 F11. |

Mutation table (would a wrong implementation slip past the original TDD plan?):

| Mutation | Original ACs | After hardening |
|---|---|---|
| `_FP_PATTERN = re.compile(r"^[0-9a-fA-F]{8}$")` (loosened to accept uppercase) | Catches via AC-7's `"ABCDEF12"` case. | Caught via AC-7 + AC-7b (hypothesis samples around the complement). |
| `if findings_count <= len(fingerprints): raise` (off-by-one) | **Slips** — AC-8 only exercises strict `<` rejection and one strict-`>` acceptance; the boundary `==` case (which must accept) is not tested. | Caught via AC-8b `(1, ["abcdef12"])` boundary case. |
| Field declaration order re-ordered to `[findings_count, slice, fingerprints]` | **Slips** — AC-11 only asserts the set of keys. | Caught via AC-11b. |
| `RedactedSlice` re-declared without `frozen=True` | Caught via AC-5. | Caught via AC-5 + AC-4. |
| `_validate_fingerprints` returns a hardcoded `["00000000"]` ignoring input | Caught via AC-10 round-trip identity. | Caught via AC-10 + AC-7b (hypothesis samples). |
| `_PHASE2_BANNED_PACKAGES` regression: `"output"` removed | **Slips** — AC-13 (glob check) fails for the wrong reason, AC-12 catches by side-effect. | Caught directly via AC-13 (frozenset membership) + AC-12 (subprocess fires). |
| S3-01 emits uppercase hex fingerprint | **Slips at S3-02 layer** — AC-15 only checks empty-slice happy path. | Caught via AC-15b cross-story integration (round-trips through validator). |
| `model_dump_json` becomes non-deterministic (e.g., dict-key order flip) | **Slips** — AC-10 asserts equality after round-trip, not byte-stability across rounds. | Caught via AC-10b. |
| `JSONValue` recursion broken at depth 3 | **Slips** — AC-10 fixture's nesting depth is unspecified. | Caught via AC-10c nested fixture. |

### Consistency (verdict: BLOCK — 3 BLOCK, 1 harden; 0 ADR conflicts)

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| CON1 (B1) | BLOCK | Implementation outline imports `from codegenie.types import JSONValue`. On master, `JSONValue` lives at `codegenie.parsers` (verified via `grep` of `src/codegenie/parsers/__init__.py` and `src/codegenie/hashing.py` neighbours). Same B2 bug closed in S3-01 (Validation note #2). | **Applied.** Implementation outline import corrected; AC-18 reworded; References block corrected (CON2). |
| CON2 (B2) | BLOCK | References line 35 cites `src/codegenie/types.py (Phase 0)` as the home of `JSONValue`. No such file exists on master. The `codegenie.types` *package* (`src/codegenie/types/identifiers.py`) carries identifier newtypes, not `JSONValue`. | **Applied.** Reference path corrected to `src/codegenie/parsers/__init__.py (Phase 1)`. |
| CON3 (B3) | BLOCK | AC-13 prescribes a `.pre-commit-config.yaml` glob (`src/codegenie/output/**/*.py`). S1-11 (Done, master verified at `scripts/check_forbidden_patterns.py:54-77,159-176`) ships the path-scoping inside the script via `_PHASE2_BANNED_PACKAGES: frozenset[str]` + `_is_under_phase2_banned_package(path) -> bool` predicate on the rule's `applies_when` field. The S1-11 Validation note #1 named this explicitly: "Path scoping lives inside the script via the rule's `applies_when` predicate, NOT in `.pre-commit-config.yaml`'s `files:`/`exclude:` regex". | **Applied.** AC-13 reframed to assert the live runtime surface — `"output" in _PHASE2_BANNED_PACKAGES` and `_is_under_phase2_banned_package(Path("src/codegenie/output/redacted_slice.py")) is True`. |
| CON4 | harden | The story references `src/codegenie/types.py (Phase 0)` and `Phase 1 already proved this` for `JSONValue` Pydantic compatibility — the latter is correct (S1-02), the former conflates with the newtype package. | **Applied.** AC-18 reworded to point to `src/codegenie/parsers/__init__.py (Phase 1, S1-02)` as the source-of-truth for `JSONValue`. |

No ADR conflicts. The story honors 02-ADR-0010 §Decision (three-field closed product type), 02-ADR-0005 (no plaintext persistence), production ADR-0033 §3 (smart-constructor discipline at the I/O boundary), and all CLAUDE.md load-bearing commitments. The implementer's note on packaging choice (sibling module vs inline) is consistent with the arch design's component-decomposition framing.

### Design patterns (verdict: HARDEN — 3 Notes-for-implementer additions; 2 verified already-present)

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| DP1 | Note | `Fingerprint` newtype rule-of-three threshold. S3-01 deferred (note #11) at one consumer. S3-02 is the second. **S3-03 will be the third** (writer reads `slice_.fingerprints` per 02-ADR-0010 Tradeoffs). Production ADR-0033 §3 names primitive obsession on cross-module identifiers as a review-blocker. **Not promoted to AC** — the format invariant is closed at the S3-02 validator; the origin invariant straddles S3-01/S3-02/S3-03 and is the natural surface for S3-03 or a follow-up cross-cutting story. | **Applied.** Notes-for-implementer §"Design patterns" — `Fingerprint` newtype deferred to S3-03 or a Phase-3-entry cross-cutting story landing concurrently with the audit-anchor / RAG ingest consumers. |
| DP2 | Note | `RedactedSlice` is a closed product type — three persisted fields by 02-ADR-0010 §Decision. Adding a fourth (e.g., `pattern_class_counts`) is an ADR amendment, parallel to `IndexFreshness` (S1-01) and `AdapterConfidence` (S1-03) variant-set extension. Mirrors S3-01 Validation note #12. | **Applied.** Notes-for-implementer §"Design patterns" — closed-product-type framing; extension is ADR-amendment-gated. |
| DP3 | Note | Functional core / imperative shell discipline. `redacted_slice.py` is pure — no I/O, no logging, no clock, no `os.environ`, no `subprocess`. Validators are pure functions over their arguments. This is the right shape for a domain-model module on the secret-redaction hot path; future contributors must not add I/O here. | **Applied.** Notes-for-implementer §"Design patterns" — explicit no-I/O constraint; `logging`/`structlog`/`Path`/`os`/`subprocess` imports at the module head are review-blockers. |
| DP4 | (verified) | Module-private constructor option (`_RedactedSlice` class with a public `RedactedSlice` type alias) was considered and explicitly rejected per the existing implementer note. The threefold defense (convention + lint + S7-04) is the chosen pattern. | No edit — already documented. |
| DP5 | (verified) | `Annotated[str, Field(pattern=...)]` vs `@field_validator`. The `field_validator` form is preferred for mutation-test reach (module-level patchable function). Already documented in the implementer notes. | No edit — already documented. |
| DP6 | Note | Smart-constructor at the I/O boundary — pattern fit. This module is the canonical implementation of the toolkit's "Smart constructor" applied at the I/O boundary (not the wire-type boundary; that's production ADR-0033's domain). | **Applied.** Notes-for-implementer §"Design patterns" — pattern-fit framing with the toolkit's named failure modes cited as closed. |

## Stage 3 — research

**Skipped.** No `NEEDS RESEARCH` findings. Every gap was answerable from the canonical sources:

- 02-ADR-0010 §Decision + §Consequences + §Tradeoffs (`RedactedSlice` design + reversibility analysis)
- 02-ADR-0005 §Decision (no plaintext persistence; the runtime defense this story upgrades)
- Production ADR-0033 §3 (smart-constructor discipline; newtype rule-of-three threshold)
- `phase-arch-design.md §"Gap analysis & improvements" Gap 4` (the smart-constructor framing)
- `scripts/check_forbidden_patterns.py` on master (the live S1-11 surface — `_PHASE2_BANNED_PACKAGES`, `_is_under_phase2_banned_package`, the `Rule` dataclass with `applies_when`)
- `src/codegenie/parsers/__init__.py` and `src/codegenie/hashing.py` on master (the actual `JSONValue` and `content_hash_bytes` locations)
- S3-01 validation report (sibling family lineage, `Fingerprint` newtype deferral, `JSONValue` import-path bug precedent)
- S1-11 validation report (forbidden-patterns mechanism, advice-contract `and` requirement, `Rule` dataclass refactor)

The hypothesis property-test pattern (AC-7b) is established in the codebase already (S1-02 uses it for `safe_json` round-trip); no external research needed.

## Stage 4 — edits applied

| # | Section | Action | Why (critic → ID) |
|---|---|---|---|
| 1 | Validation notes block | INSERTED after ADRs-honored line | Audit trail of every change |
| 2 | References — Existing code | REWORDED — `src/codegenie/parsers/__init__.py` (Phase 1) replaces `src/codegenie/types.py (Phase 0)` | Consistency CON1 / CON2 (B1, B2) |
| 3 | References — Forbidden-patterns surface | REWORDED — names `_PHASE2_BANNED_PACKAGES` + `_is_under_phase2_banned_package` + subprocess invocation contract | Consistency CON3 (B3) + Test-quality TQ4 |
| 4 | Implementation outline §1 | REWORDED — `from codegenie.parsers import JSONValue` (with comment explaining NOT `codegenie.types`) | Consistency CON1 (B1) |
| 5 | Implementation outline §2 | REWORDED — 26 ACs (not 19); exact subprocess invocation for AC-12; AC-14 uses structural regex; AC-15b cross-story integration | Test-quality TQ1, TQ3, TQ5; Coverage C6 |
| 6 | AC-2 | STRENGTHENED — programmatic `inspect.getdoc()` substring check for four required references | Test-quality TQ5 (mirrors S3-01 F11) |
| 7 | AC-7 | STRENGTHENED — added whitespace, mixed-case, non-ASCII rejections | Coverage closure |
| 8 | AC-7b | ADDED — hypothesis property test (accepts ∩ accepts^c = ∅) | Coverage C1 |
| 9 | AC-8b | ADDED — parametrized boundary table (`==` boundary, zero baseline, same-key-multiple-times) | Coverage C2 |
| 10 | AC-10 | REWORDED — `reloaded == original` (model equality) and deep slice equality | Clarity |
| 11 | AC-10b | ADDED — JSON byte-stability (`model_dump_json() == model_dump_json()`) | Coverage C3 |
| 12 | AC-10c | ADDED — nested-recursion fixture (≥3 levels) | Coverage C4 |
| 13 | AC-11 | unchanged (set-of-keys assertion) | — |
| 14 | AC-11b | ADDED — field declaration order pinned in both `model_dump()` and `model_dump_json()` | Coverage C5 |
| 15 | AC-12 | REWRITTEN — exact subprocess invocation; advice contract `and` (both substrings) | Test-quality TQ1; mirrors S1-11 AC-2 |
| 16 | AC-12b | ADDED — surgical-predicate negative-path test (write to non-banned package; assert clean exit) | Test-quality TQ2 |
| 17 | AC-13 | REWRITTEN — direct assertion against runtime surface (`_PHASE2_BANNED_PACKAGES`, `_is_under_phase2_banned_package`), NOT a `.pre-commit-config.yaml` glob | Consistency CON3 (B3) |
| 18 | AC-14 | REWRITTEN — structural regex (matches call form, not docstring prose) | Test-quality TQ3 |
| 19 | AC-15b | ADDED — cross-story integration with S3-01; four canonical shapes; round-trip through `model_validate(model_dump())` (mirrors S3-01 AC-33) | Coverage C6 |
| 20 | AC-18 | REWORDED — `src/codegenie/parsers/__init__.py (Phase 1, S1-02)` as the source-of-truth | Consistency CON4 |
| 21 | Notes for the implementer | EXPANDED — LOC budget bumped (~390 LOC); `### Design patterns` subsection added (DP1 `Fingerprint` newtype, DP2 closed product type, DP3 pure module, DP6 smart-constructor pattern fit) | Design-patterns DP1, DP2, DP3, DP6 |

Total: **3 BLOCK fixes**, **8 harden tightenings**, **7 new ACs**, **4 Notes-for-implementer additions**, **1 Validation-notes audit block**.

## Verdict justification

**HARDENED.** The story's goal, scope, and arch trace are sound — no RESCUE-tier issues (the goal is correct, the ACs do trace to the goal, the implementation outline is the right shape). The three BLOCK bugs are prescription drift (wrong import path, non-existent file reference, non-existent enforcement surface) — they would have wasted executor attempts but did not require a re-design. The eight harden-tier gaps were closeable in-place. Story is now ready for `phase-story-executor`.

A future story implementer reading this report should pay particular attention to:

- **AC-12 / AC-12b:** the subprocess invocation against `scripts/check_forbidden_patterns.py` is the live S1-11 surface (verified on master). The advice contract is `and`, not `or` — both substrings must appear in every emitted error line.
- **AC-13:** the path-scoping mechanism is the **frozenset + predicate**, not a glob in `.pre-commit-config.yaml`.
- **AC-15b:** the cross-story integration with S3-01 is load-bearing — a regression in S3-01's fingerprint format, count semantics, or dedupe logic would fail at this story's `model_validate` boundary. This is the runtime witness for the structural-defense ladder.
- **Notes-for-implementer §"Design patterns":** the `Fingerprint` newtype is deferred to S3-03 (rule-of-three crosses there). Do not retrofit it into S3-02.

Cross-references for future validators in this family:

- S3-01 validation report: `_validation/S3-01-secret-redactor.md`
- S1-11 validation report: `_validation/S1-11-forbidden-patterns-mypy-adrs.md`
- Phase arch design Gap 4: `../../phase-arch-design.md`
- 02-ADR-0010: `../../ADRs/0010-redacted-slice-smart-constructor-at-writer-boundary.md`
- 02-ADR-0005: `../../ADRs/0005-secret-findings-no-plaintext-persistence.md`
- Production ADR-0033: `../../../../production/adrs/0033-domain-modeling-discipline.md`
