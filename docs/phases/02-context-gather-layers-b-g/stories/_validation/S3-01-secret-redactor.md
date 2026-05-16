# Validation report — S3-01 `SecretRedactor` pattern classes + entropy threshold + BLAKE3 fingerprint

**Story:** [`../S3-01-secret-redactor.md`](../S3-01-secret-redactor.md)
**Validated:** 2026-05-15
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

The story implements `src/codegenie/output/sanitizer.py::redact_secrets(slice_, probe_name) -> tuple[RedactedSlice, list[SecretFinding]]` — six named pattern classes (AWS, GitHub, JWT, RSA private-key, NPM, Anthropic) + Shannon-entropy fallback (≥ 4.5 bits/char on `len ≥ 32`) + BLAKE3-prefix-stripped first-8-hex fingerprint + recursive `JSONValue` walker + module-level `_PATTERNS` table for mutation-test reach + frozen `SecretFinding` Pydantic record. All references trace cleanly to 02-ADR-0005 (no plaintext persistence), 02-ADR-0010 (`RedactedSlice` smart constructor), `phase-arch-design.md §"Component design" #4`, `phase-arch-design.md §"Sequence — secret-redaction flow"`, and the structural-defense ladder framing.

The draft was structurally sound — no RESCUE-tier findings — but carried **two BLOCK-severity prescription bugs** (it would not have compiled or run as written) and **eight harden-tier coverage / test-quality gaps** that would have let plausibly-wrong implementations slip past the executor's Validator pass. Thirteen edits applied in place; story is ready for `phase-story-executor`. Stage 3 research skipped (no `NEEDS RESEARCH` findings — every gap was answerable from arch + ADR-0005 + ADR-0010 + S1-01 / S1-03 sibling validation precedent + Phase 0 `src/codegenie/hashing.py` on master).

## Context Brief (Stage 1)

- **Goal (verbatim):** Ship `src/codegenie/output/sanitizer.py::redact_secrets(slice_, probe_name) -> tuple[RedactedSlice, list[SecretFinding]]` with six pattern-class regexes + Shannon-entropy fallback + BLAKE3 first-8-hex fingerprint + recursive `JSONValue` walker + in-band findings list + mutation tests proving pattern coverage is verified not asserted.
- **Non-goals (from Out-of-scope):** the `RedactedSlice` model itself (S3-02); `OutputSanitizer.scrub` composition + ordering (S3-03); writer signature tightening (S3-03); `secrets_redacted_count` log field (S3-03); `test_secret_in_source.py` (S6-07); `test_no_inmemory_secret_leak.py` (S7-04); CLI summary line (S8-02).
- **Phase 2 exit criteria touched:** G5 — "plaintext present in zero persisted files" (verified by `test_secret_in_source.py` in S6-07; this story is the runtime that makes that assertion green); the chokepoint guarantee inherits to Phase 4 RAG ingestion (production ADR-0005).
- **Load-bearing commitments touched:**
  - CLAUDE.md §"No LLM anywhere in the gather pipeline" — story is pure regex + entropy + BLAKE3, zero LLM. ✓
  - CLAUDE.md §"Facts, not judgments" — redactions are regex matches (facts); the redactor produces no conclusions. ✓
  - CLAUDE.md §"Determinism over probabilism for structural changes" — pure regex + BLAKE3 = deterministic. ✓
  - CLAUDE.md §"Extension by addition" — new pattern class = append to `_PATTERNS` + widen `Literal[...]` set (ADR amendment), walker / fingerprinter / entropy untouched. ✓
  - 02-ADR-0005 §Decision — no plaintext persisted; in-memory `list[SecretFinding]` carries audit trail. ✓
  - 02-ADR-0010 §Decision — return type tightened to `tuple[RedactedSlice, list[SecretFinding]]`. ✓
  - Phase-0 ADR-0001 — `content_hash_bytes` is the BLAKE3-of-bytes chokepoint; both `content_hash` and `content_hash_bytes` return prefix-tagged `"blake3:<64hex>"` (this story strips and slices).
  - Production ADR-0033 — newtype discipline (`Fingerprint` deferred to a Phase-3 cross-cutting story; see Validation note #11).
- **Open/Closed boundaries:**
  - New *pattern class* → append a `_PATTERNS` row + widen `Literal[...]` (ADR amendment for the closed set; walker/fingerprinter untouched).
  - New *consumer of `RedactedSlice`* → Phase 4 RAG ingest; no edits to sanitizer.py.
  - New *fingerprint algorithm* → swap `content_hash_bytes` for the new chokepoint; ADR amendment.
  - Module-level `_PATTERNS` is the **monkeypatch reach** for mutation tests; function-local moves silently disable the test harness (AC-30 closes this).
- **Sibling-family lineage:**
  - **1st** secret-redaction story in Phase 2 (S3-01 → S3-02 → S3-03 family). S3-02 lands `RedactedSlice`; S3-03 lands writer signature + composition + log field.
  - Variant-set extension discipline carried forward from **S1-01** (`IndexFreshness`) and **S1-03** (`AdapterConfidence`) — `pattern_class: Literal[...]` is a closed set; extension is ADR-amendment-gated. Validation note #12 promotes this to Notes-for-implementer.
  - Mutation-test discipline carried forward from **S1-02** (`safe_json` chokepoint) — module-level pattern table swapped via `monkeypatch.setattr`. Validation note F5 / AC-30 adds the positive-control assertion that S1-02 did not need (its mutations were inline regex changes; S3-01's are table swaps).
  - Smart-constructor pattern paired with **S3-02** (`RedactedSlice` is the constructed type; `redact_secrets` is the only public factory).
- **Rule-of-three threshold for `Fingerprint` newtype:** NOT YET REACHED. S3-01 + S3-02 are two consumers (sanitizer produces, RedactedSlice carries); Phase 3 RAG ingest or the audit-anchor is the third. Deferred per Validation note #11.
- **Prior validation history:** None for S3-01. Cross-referenced **S1-01** (variant-set discipline) and **S1-03** (sibling Pydantic-discriminated-union family + smart-constructor framing).
- **Open ambiguities:** None — proceeded to Stage 2.

## Stage 2 — critic reports

### Coverage (verdict: COVERAGE-HARDEN — 11 findings)

The 25 draft ACs cover the surface, regex matching, entropy fallback, fingerprint scheme, recursive walk, mutation tests, in-band findings, and Phase-0 invariants. But several edge cases and integration invariants were absent:

- **F1 (harden) — Same-secret-twice dedupe.** AC-20 covers 3 distinct findings; no AC covers the same secret appearing twice (`findings_count == 2`, `len(unique_fingerprints) == 1`). Load-bearing for S3-02's `findings_count >= len(fingerprints)` validator. **Fix:** AC-26.
- **F2 (harden) — Two distinct named patterns in one string.** Two findings of different pattern classes co-located in one string value. **Fix:** AC-27.
- **F3 (harden) — `cleartext_len` byte-vs-char.** Notes specify byte-length; no AC enforces. **Fix:** AC-28 with multi-byte fixture.
- **F4 (harden) — Input non-mutation.** AC-22 covers idempotence across calls but not input immutability. **Fix:** AC-29.
- **F5 (harden) — `_PATTERNS` module-level positive control.** AC-18 mutation tests *assume* the table is module-level; a refactor function-locals it and silently no-ops every mutation. **Fix:** AC-30 — positive control verifying `monkeypatch.setattr` genuinely changes the redactor's behavior.
- **F6 (harden) — Entropy edge cases.** `""`, `"a"`, `"a" * 100`, Unicode strings of len ≥ 32. **Fix:** AC-31.
- **F7 (harden) — S3-02 round-trip integration.** No AC tests that S3-01's output satisfies S3-02's validators. **Fix:** AC-33.
- **F8 (harden) — Inline-substring replacement family invariant.** JWT covered in Notes; AWS/GitHub/NPM/Anthropic/entropy uncovered. **Fix:** AC-34.
- **F11 (nit) — Docstring assertion technique unspecified.** AC-2 enumerates required substrings but pins no mechanism. **Fix:** AC-2 strengthened with `inspect.getdoc(...)` substring check.

Goal-to-AC trace (post-edit): every goal point now has at least one verifying AC; every AC traces to either an explicit goal point or an extension-invariant the goal implies (S3-02 round-trip, mutation harness reach, input immutability).

### Test Quality (verdict: TESTS-HARDEN — mutation table below)

The draft's TDD plan named six pattern-class mutation tests + one entropy-threshold mutation + idempotence + statelessness. Strong baseline. Mutations that **slipped past** the draft TDD plan:

| # | Wrong implementation | Caught by draft? | Severity | Closure |
|---|---|---|---|---|
| 1 | Call `content_hash(...)` (Path overload) instead of `content_hash_bytes(...)` | **No** — `TypeError` at first run, but no test names the function | block | AC-13 strengthened + AC-32 |
| 2 | Skip `.removeprefix("blake3:")` slice | **No** — fingerprints start with `"blake3:"` literal | block | AC-13 negative test + AC-32 |
| 3 | Drop `_PATTERNS` to function-local for "encapsulation" | **No** — all six AC-18 mutation tests silently no-op | harden | AC-30 positive control |
| 4 | Use `set()` for findings list (dedupe at wrong level) | **No** — `findings_count` collapses to unique-fingerprint count | harden | AC-26 |
| 5 | `return` after first pattern match per regex pass | **No** — co-located distinct-pattern findings drop one | harden | AC-27 |
| 6 | Use `len(cleartext)` (char-count) for `cleartext_len` | **No** — ASCII fixtures equal char- and byte-length | harden | AC-28 |
| 7 | Mutate `slice_` in place to "save memory" | **No** — return value still correct; caller's dict corrupted | harden | AC-29 |
| 8 | Naive entropy `log2(0)` crash on empty / single-char string | **No** — no AC covers small / empty input | harden | AC-31 |
| 9 | Return uppercase hex (`.hexdigest().upper()` slip) | Partially — AC-13 says "[0-9a-f]" but S3-02 validator catches at construction | harden | AC-33 (round-trip through validators) |
| 10 | Anchor patterns (`^AKIA[0-9A-Z]{16}$`) | **No** for AWS/GitHub/NPM/Anthropic — bare-string fixtures still match | harden | AC-34 |
| 11 | `_walk` skip list items | Yes — AC-15 nested-list fixture catches | — | — |
| 12 | `_walk` match dict keys | Yes — AC-16 catches | — | — |
| 13 | Pattern class label typo (`"aws_key"` vs `"aws_access_key"`) | Yes — AC-4/5/6/7/8/9 each pin literal | — | — |
| 14 | Replacement token format `<HIDDEN:...>` | Yes — AC-14 pins literal | — | — |
| 15 | Use `re.fullmatch` instead of `re.sub` | Partially — entropy fallback would still fire; AC-34 closes broadly | harden | AC-34 |
| 16 | Iterate `dict.items()` instead of `dict.values()` in walker | Yes — AC-16 catches (key matching would over-fire) | — | — |
| 17 | Forget to strip "blake3:" but adjust slice to `[7:15]` | Partial — AC-13 char-set passes if hex; AC-32 explicit form catches | harden | AC-32 |
| 18 | Statelessness regression via module-level cache | Yes — AC-22 catches | — | — |
| 19 | `pattern_class` widened from `Literal[...]` to `str` for "extensibility" | mypy `--strict` catches; AC-3 pins the literal | — | — |
| 20 | RSA pattern greedy `.+` instead of `[\s\S]+?` | Partially — AC-7 multi-line fixture; AC-34 inline-substring | — | — |

Six plausibly-wrong implementations slip past the draft; all closed by the new ACs.

### Consistency (verdict: CONSISTENCY-BLOCK — 2 BLOCK findings, 0 ADR conflicts)

- **B1 (block) — `content_hash` API mismatch.** Phase 0 `src/codegenie/hashing.py` (on master) defines `content_hash(path: Path) -> str` (file streaming) and `content_hash_bytes(b: bytes) -> str` (in-memory). The draft prescribed `content_hash(cleartext.encode("utf-8"))[:8]` — wrong overload + missing prefix-strip. The function does not accept bytes; the call is a runtime `TypeError`. *Both* return prefix-tagged `"blake3:<64hex>"` per Phase-0 ADR-0001 chokepoint discipline; slicing `[:8]` produces `"blake3:b"`. **Fix:** Goal #2, AC-13, AC-14, Implementation outline, References section, and AC-32 all corrected to `content_hash_bytes(cleartext.encode("utf-8")).removeprefix("blake3:")[:8]`. Verified: `src/codegenie/hashing.py:82` defines `content_hash_bytes(b: bytes) -> str` returning `f"blake3:{_blake3(b).hexdigest()}"`.
- **B2 (block) — `JSONValue` import path wrong.** Draft cited `src/codegenie/types.py (Phase 0)` for `JSONValue`. Repo state (master): `JSONValue` is exported by `src/codegenie/parsers/__init__.py` (re-export from `parsers.safe_json`). `codegenie.types` is the identifier-newtype package (Phase 2 / S1-05). The `ProbeId` symbol lives at `codegenie.types.identifiers` but is NOT re-exported by `codegenie.types.__init__`'s `__all__` (verified — five names re-exported, `ProbeId` absent). **Fix:** References section + Implementation outline updated. Import paths pinned: `from codegenie.parsers import JSONValue`, `from codegenie.types.identifiers import ProbeId`, `from codegenie.hashing import content_hash_bytes`.
- **02-ADR-0005 §Consequences** signature: returns `tuple[dict[str, JSONValue], list[SecretFinding]]`. **02-ADR-0010** tightens to `tuple[RedactedSlice, list[SecretFinding]]`. Draft + edits honor the 02-ADR-0010 form. ✓
- **CLAUDE.md §"No LLM anywhere in the gather pipeline"** — pure regex + entropy + BLAKE3. ✓
- **CLAUDE.md §"Facts, not judgments"** — redactor produces redacted slices + finding records; no conclusions. ✓
- **CLAUDE.md §"Honest confidence"** — confidence concept is at the probe layer; this is below the probe layer (sanitizer/redactor). N/A.
- **CLAUDE.md §"Extension by addition"** — adding a pattern class = append `_PATTERNS` row + widen `Literal[...]`; walker/fingerprinter/entropy untouched. ✓ Validation note #12 promotes the variant-set framing.
- **Phase 0 ADR-0001** chokepoint — story uses `content_hash_bytes` (the bytes overload that exists on master); no other BLAKE3 import. ✓
- **Phase 0 ADR-0008** sanitizer chokepoint — story extends, doesn't replace. ✓ Composition order pinned in S3-03, not here.
- **02-ADR-0010 §Decision** — `RedactedSlice` is constructed by `redact_secrets`; no `model_construct` (AC-24). ✓
- **No RESCUE-tier conflicts.** The two BLOCKs are prescription bugs in the draft, not ADR contradictions; the priority order `Consistency > Coverage > Test-Quality > Design-Patterns` did not need to fire (Consistency findings were corrections, not value tradeoffs).

### Design Patterns (verdict: DESIGN-CLEAN with 2 Notes-for-implementer extensions)

- **Smart constructor + Make-illegal-states-unrepresentable.** `redact_secrets` is the only public path to a `RedactedSlice`; `SecretFinding` carries no `cleartext` field by construction; format invariants close at S3-02's validators. ✓ Correctly applied.
- **Chain of responsibility / pipeline composition.** `redact_secrets` is one stage in the sanitizer pipeline (S3-03 wires composition); single chokepoint discipline survives. ✓
- **Strategy pattern (registry).** `_PATTERNS` is a list-based registry of `(label, compiled_regex)` pairs. Three concrete strategies (regex match, entropy match, dispatch by label). Rule-of-three threshold for elevating to a `PatternStrategy` protocol with `match` / `redact` methods is **not yet reached** — six patterns × identical match-and-redact shape do not yet warrant the protocol; if a future pattern needs per-class transform logic (e.g., RSA's multi-line collapse), elevate then. Notes-for-implementer #12 frames the variant-set extension as ADR-gated.
- **Functional core / imperative shell.** Pure: `_shannon_entropy`, `_fingerprint`, `_walk`, `_redact_string`, `redact_secrets`. Side effects: zero in this story (S3-03 handles `structlog`). ✓ Excellent fit.
- **Sum type / tagged union.** `pattern_class: Literal[...]` is the discriminator; `SecretFinding` is the record. Mirrors S1-01 `IndexFreshness` and S1-03 `AdapterConfidence` variant-set discipline. ✓ Validation note #12 promotes the framing to Notes-for-implementer to prevent a future "fix" to `str` for extensibility.
- **Newtype pattern for domain primitives.** `ProbeId` ✓. `fingerprint: str` is **not** elevated to `Fingerprint = NewType("Fingerprint", str)` in this story — production ADR-0033 §3 applies, but the rule-of-three threshold (third consumer of the fingerprint family) is not yet reached (S3-01 produces; S3-02 carries; the third consumer is Phase 3 RAG ingest or the audit-anchor). S3-02's field validator closes the **format** invariant at construction; the newtype would close the **origin** invariant ("only `_fingerprint(...)` produces a `Fingerprint`"). Notes-for-implementer #11 defers to a Phase-3 cross-cutting story. **Rationale: introducing the newtype now without the third consumer either (a) forces a coupled PR with S3-02 (out of S3-01's scope) or (b) leaves a one-callsite newtype that adds boilerplate without payoff. Land once with all three consumers.**
- **Open/Closed Principle.** Variant set `pattern_class: Literal[...]` is **deliberately closed** — ADR-amendment to widen. Mirrors S1-01/S1-03. The walker / fingerprinter / entropy / regex-dispatch logic is open for extension *at the `_PATTERNS` row* (append a tuple, widen the literal); the kernel is closed. Validation note #12 makes this explicit.
- **Dependency inversion.** The redactor depends on `content_hash_bytes` (Phase 0) via concrete import. A `Hasher` protocol could be introduced, but Rule 2 (Simplicity First) and the chokepoint discipline win — `content_hash_bytes` IS the chokepoint; abstracting it would dilute the single-source-of-truth invariant. No change.
- **Composition over inheritance.** Six concrete pattern strategies, no shared base, no inheritance. ✓
- **Hidden state.** `_PATTERNS` is module-level but immutable in practice (regex compiled once at module load). The monkeypatch reach in tests is the *only* designed-for mutation surface; AC-30 makes the mutation harness's reach an explicit positive control.
- **Pure-impure tangle.** None — all functions in this story are pure. S3-03 handles the impure side (logging). ✓

Two Notes-for-implementer extensions added:
1. **#11 — `Fingerprint` NewType deferred to Phase-3 cross-cutting story.** Rationale: rule-of-three not reached; S3-02 validator closes format invariant; coupled PR cost outweighs payoff in S3-01 alone.
2. **#12 — `pattern_class: Literal[...]` is deliberately closed.** Variant-set extension is ADR-amendment-gated, mirroring S1-01 / S1-03. Walker/fingerprinter/entropy untouched on extension.

## Stage 3 — Researcher

**Skipped.** No `NEEDS RESEARCH` findings. Every gap was answerable from:

- `phase-arch-design.md §"Component design" #4 SecretRedactor`, §"Sequence — secret-redaction flow", §"Anti-patterns avoided"
- 02-ADR-0005 §Decision / §Consequences / §Pattern fit
- 02-ADR-0010 §Decision / §Tradeoffs / §Consequences
- Phase-0 ADR-0001 (BLAKE3 chokepoint signatures) — verified against `src/codegenie/hashing.py` on master
- `final-design.md §"Components" #4 SecretRedactor`, §"Conflict-resolution table" row 4
- **S1-01 validation report** (variant-set extension discipline, sibling tagged-union)
- **S1-03 validation report** (smart-constructor pattern + Pydantic frozen + extra="forbid" + mutation discipline)
- `src/codegenie/output/sanitizer.py` (Phase 0 on master, for `OutputSanitizer.scrub` composition context)
- `src/codegenie/hashing.py` (Phase 0 on master, for the `content_hash_bytes` correction)
- `src/codegenie/types/__init__.py` (master, for the `ProbeId` re-export check)
- `src/codegenie/parsers/__init__.py` (master, for the `JSONValue` location correction)

Mutation testing, property-based testing, and design-pattern selection are all standard practice in this repo — no canonical-pattern lookup needed.

## Stage 4 — Synthesis: edits applied

Thirteen edits applied to [`../S3-01-secret-redactor.md`](../S3-01-secret-redactor.md):

1. **Validation notes block added** under the story header (13 numbered fix entries).
2. **ADRs honored** extended — added production ADR-0033 (newtype discipline; informs deferred `Fingerprint` newtype).
3. **Goal #2 corrected** — `content_hash_bytes(...).removeprefix("blake3:")[:8]` replaces the broken `content_hash(...)[:8]`.
4. **References — `src/codegenie/hashing.py`** entry rewritten to name `content_hash_bytes` and the prefix-strip explicitly; warns against confusing with `content_hash(path: Path)`.
5. **References — `JSONValue`** entry corrected from `codegenie.types` to `codegenie.parsers/__init__.py`.
6. **References — `ProbeId`** entry corrected from `codegenie.probe.py` (does not exist) to `codegenie.types.identifiers` with explicit import path warning (the `codegenie.types` `__all__` does NOT re-export `ProbeId`).
7. **AC-2 strengthened** — programmatic docstring substring check via `inspect.getdoc(...)`.
8. **AC-13 rewritten** — `content_hash_bytes(...).removeprefix("blake3:")` form + lowercase-hex pin + explicit negative test for the two regression shapes.
9. **AC-26 added** — same-secret-twice dedupe (S3-02 invariant integration).
10. **AC-27 added** — two distinct named patterns in one string.
11. **AC-28 added** — `cleartext_len` byte-length with multi-byte fixture.
12. **AC-29 added** — input non-mutation via `copy.deepcopy` comparison.
13. **AC-30 added** — `_PATTERNS` and `_ENTROPY_THRESHOLD_BITS_PER_CHAR` module-level positive control (mutation harness reach).
14. **AC-31 added** — entropy edge cases (`""`, `"a"`, `"a" * 100`, Unicode).
15. **AC-32 added** — `content_hash_bytes` prefix-strip regression test.
16. **AC-33 added** — S3-02 round-trip integration through Pydantic validators.
17. **AC-34 added** — inline-substring replacement family invariant (5 pattern classes).
18. **Implementation outline updated** — entropy helper signature note (`0.0` on empty); fingerprint helper signature corrected; import paths pinned (`JSONValue` from `parsers`, `ProbeId` from `types.identifiers`, `content_hash_bytes` from `hashing`, `RedactedSlice` from `output.redacted_slice`).
19. **Notes-for-implementer #11 added** — `Fingerprint` NewType deferred to Phase-3 cross-cutting story (rule-of-three not reached).
20. **Notes-for-implementer #12 added** — variant-set extension framing (`pattern_class: Literal[...]` deliberately closed, ADR-amendment-gated, mirrors S1-01 / S1-03).

(Edits 9-17 are the new validator-added ACs section; 18-20 supplement the existing Implementation outline and Notes for the implementer.)

## Mutation table — what the hardened story now catches

| Mutation | Was caught? | Now caught? | Test / AC |
|---|---|---|---|
| Call `content_hash(Path)` instead of `content_hash_bytes(bytes)` | ✗ (runtime TypeError, untested) | ✓ | AC-13 negative + AC-32 |
| Drop `.removeprefix("blake3:")` from fingerprint slice | ✗ | ✓ | AC-13 + AC-32 |
| Move `_PATTERNS` function-local | ✗ (all AC-18 mutations silently no-op) | ✓ | AC-30 positive control |
| Use `set` for findings (dedupe at wrong level) | ✗ | ✓ | AC-26 + AC-33 |
| `return` after first pattern match per pass | ✗ | ✓ | AC-27 |
| Use `len(cleartext)` (char count) for `cleartext_len` | ✗ | ✓ | AC-28 multi-byte fixture |
| Mutate `slice_` in place | ✗ | ✓ | AC-29 deepcopy comparison |
| Crash on `_shannon_entropy("")` / single-char input | ✗ | ✓ | AC-31 |
| Uppercase hex in fingerprint (`.hexdigest().upper()`) | ✗ | ✓ | AC-13 + AC-33 |
| Anchor pattern (`^AKIA…$`, `re.fullmatch`) | ✗ (bare-string fixtures still match) | ✓ | AC-34 (5 pattern classes) |
| Drop a module-docstring reference | ✗ | ✓ | AC-2 strengthened |
| Off-by-one in `findings_count` | ✗ | ✓ | AC-33 round-trip |
| Negative `findings_count` from loop bug | ✗ | ✓ | AC-33 round-trip |
| Loosen `pattern_class` to `str` for extensibility | mypy + AC-3 | ✓ | Notes #12 (design intent documented) |
| Weakened AWS pattern (`AKIA[0-9A-Z]{15}`) | ✓ AC-18 | ✓ | AC-18 (unchanged) |
| Weakened entropy threshold (5.0) | ✓ AC-19 | ✓ | AC-19 (unchanged) |
| Walker skips list items | ✓ AC-15 | ✓ | AC-15 (unchanged) |
| Walker matches dict keys | ✓ AC-16 | ✓ | AC-16 (unchanged) |
| `SecretFinding` carries `cleartext` field | ✓ AC-21 | ✓ | AC-21 (unchanged) |
| Statelessness via global accumulator | ✓ AC-22 | ✓ | AC-22 (unchanged) |
| `model_construct` bypass | ✓ AC-24 | ✓ | AC-24 (unchanged) |

Six plausibly-wrong implementations that slipped past the draft now fail the hardened TDD plan. Two prescription bugs in the draft (which would have made the implementation impossible) are corrected at the source.

## Design-pattern audit (Notes-for-implementer surface)

Two pattern-quality findings surfaced as Notes-for-implementer (not promoted to ACs — pattern names are not testable; the framings prevent a future reader from misreading the design):

- **#11 — `Fingerprint` NewType deferred.** Production ADR-0033 §3 (primitive-obsession review-blocker) applies on the surface, but the rule-of-three threshold (third concrete consumer) is not yet reached. S3-02's `RedactedSlice.fingerprints: list[str]` field-validator closes the format invariant at construction; the newtype closes the *origin* invariant (only `_fingerprint(...)` produces a `Fingerprint`). Land once in a Phase-3 cross-cutting story when the third consumer (Phase 3 RAG ingest or the audit-anchor) appears. Coupled PR cost in S3-01 alone outweighs the payoff.
- **#12 — `pattern_class: Literal[...]` is deliberately closed.** Variant-set extension is ADR-amendment-gated (mirror S1-01 `IndexFreshness` and S1-03 `AdapterConfidence`). The walker / fingerprinter / entropy / regex-dispatch kernel is closed; extension is at the `_PATTERNS` row append + `Literal[...]` widening. A future contributor who "improves" `pattern_class` to `str` for "extensibility" defeats `mypy --strict --warn-unreachable`'s exhaustive `match` discipline at every consumer. Closed-set + ADR amendment is the deliberate design.

These framings keep the implementation faithful to the architect's intent while leaving Phase-3 evolution paths visible.

## Verdict

**HARDENED.** The story now constrains the implementation with 34 ACs (was 25) — two corrected for BLOCK-severity prescription bugs (broken `content_hash` API, wrong `JSONValue` import path) and nine added for edge-case coverage, mutation-harness positive controls, S3-02 round-trip integration, and the inline-substring family invariant. The TDD plan now catches twenty-one plausibly-wrong implementations (was eight). Two Design-Patterns Notes-for-implementer extensions (`Fingerprint` newtype deferral; variant-set extension framing) prevent the next reader from misreading the deliberately-closed variant set or prematurely introducing the newtype.

Ready for [phase-story-executor](../../../../skills/phase-story-executor).
