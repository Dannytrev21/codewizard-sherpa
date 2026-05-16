# Story S3-01 — `SecretRedactor` pattern classes + entropy threshold + BLAKE3 fingerprint

**Step:** Step 3 — Plant `SecretRedactor` + `RedactedSlice` smart constructor at the writer chokepoint
**Status:** Ready
**Effort:** M
**Depends on:** S1-11 (`forbidden-patterns` extension that will later cover `model_construct` under `src/codegenie/output/**`, plus the nine new ADRs; Phase-2 ADRs 0005 + 0010 are landed)
**ADRs honored:** 02-ADR-0005 (no plaintext persistence anywhere in Phase 2), 02-ADR-0010 (`RedactedSlice` smart constructor at the writer boundary), [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md) (no LLM in gather — the chokepoint guarantee inherits to Phase 4 RAG ingestion), [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md) (newtype discipline; informs the deferred `Fingerprint` newtype — see Validation notes #11)

## Validation notes (phase-story-validator, 2026-05-15)

Verdict: **HARDENED**. The draft was structurally sound — six pattern classes + entropy fallback + BLAKE3 fingerprint + mutation-test discipline + in-band findings tuple all trace cleanly to 02-ADR-0005, 02-ADR-0010, and `phase-arch-design.md §"Component design" #4`. But the draft carried **two BLOCK-severity bugs** in prescribed code (it would not run as written) and **eight harden-tier gaps** that would have let an obviously-wrong implementation slip past the executor's Validator pass. Edits applied:

1. **B1 (BLOCK) — `content_hash` API mismatch.** Draft prescribed `codegenie.hashing.content_hash(cleartext.encode("utf-8"))[:8]`. But Phase 0's `content_hash(path: Path) -> str` takes a `Path`, not bytes — the bytes overload is `content_hash_bytes(b: bytes) -> str`. *Both* return `"blake3:<64hex>"` (prefix-tagged per Phase-0 ADR-0001). Slicing `[:8]` would yield `"blake3:b"`, not 8 hex chars. **Fix:** Goal #2, AC-13, AC-14, and the Implementation outline now name `content_hash_bytes(cleartext.encode("utf-8")).removeprefix("blake3:")[:8]`. AC-32 added as the explicit regression test for prefix-stripping (a mutation that drops `.removeprefix("blake3:")` is caught).
2. **B2 (BLOCK) — `JSONValue` import path wrong.** Draft cited `src/codegenie/types.py (Phase 0) — JSONValue recursive alias`. Phase 1 actually places `JSONValue` at `src/codegenie/parsers/__init__.py` (re-exported from `parsers.safe_json`). The `codegenie.types` package holds **identifier newtypes**, not `JSONValue`. **Fix:** References section updated; the Implementation outline now imports `from codegenie.parsers import JSONValue`. The `ProbeId` import path is pinned at `from codegenie.types.identifiers import ProbeId` (the `codegenie.types` package `__all__` re-exports the other four newtypes but not `ProbeId` as of S1-05's landing — verified against `src/codegenie/types/__init__.py` on master).
3. **F1 (harden) — Same-secret-twice dedupe invariant unasserted.** AC-20 covers "two AWS keys + one entropy hit = 3 findings" but does not cover **the same** AWS key appearing twice (`findings_count == 2`, `len(fingerprints) == 1`). This is load-bearing for S3-02's `RedactedSlice.findings_count >= len(fingerprints)` model validator. A regression that uses a `set` for findings (dedupe at finding-level instead of fingerprint-level) silently breaks the contract. **Fix:** AC-26 added.
4. **F2 (harden) — Two distinct named-pattern matches in one string unasserted.** AC-20 covers two findings of the same pattern class plus an entropy hit; no AC covers two findings of **different** named-pattern classes co-located in one string value (e.g., `"aws=AKIA…EXAMPLE github=ghp_<36>"`). A regression that `return`s after the first pattern match per pass silently passes. **Fix:** AC-27 added.
5. **F3 (harden) — `cleartext_len` byte-vs-char drift unasserted.** Notes name "byte-length, not char-length" but no AC enforces. A regression using `len(cleartext)` (char count) silently passes every ASCII test. **Fix:** AC-28 added with a multi-byte fixture (e.g., the canonical AWS key surrounded by a non-ASCII codepoint; the fixture only needs to differ in `byte_len != char_len`).
6. **F4 (harden) — Input non-mutation unasserted.** AC-22 asserts statelessness across calls but not that the *input* `slice_` dict is unmutated. A regression that mutates `slice_` in place ("save memory") would corrupt the caller's state. **Fix:** AC-29 added — verifies `slice_` survives the call by deep-equality with a pre-call `copy.deepcopy`.
7. **F5 (harden) — `_PATTERNS` module-level placement unasserted.** Implementer notes name "Pattern table at module level, not function-local" but no AC enforces. AC-18's mutation tests *require* `monkeypatch.setattr(sanitizer, "_PATTERNS", ...)` to work; a refactor that moves `_PATTERNS` function-local silently disables every mutation test (they no-op because the function-local table is never read by the patched module attribute). **Fix:** AC-30 added — verifies `_PATTERNS` and `_ENTROPY_THRESHOLD_BITS_PER_CHAR` are module-level names, and that `monkeypatch.setattr` against them genuinely changes the redactor's behavior (positive-control test for the mutation harness).
8. **F6 (harden) — Entropy edge cases unspecified.** AC-10/11/12 cover the threshold rule but not boundary conditions. A naive Shannon-entropy implementation `-sum(p * log2(p) for c, p in freq)` crashes on `log2(0)` if any iterated entry has count zero (rare but defensible to guard); empty strings, single-repeated-char strings, and Unicode-only strings of len ≥ 32 are all undefined by the draft. **Fix:** AC-31 added — pins behavior on `""`, `"a"`, `"a" * 100`, and a 64-char Unicode string. The entropy function itself never crashes; skip-the-rule semantics for `len < 32` (already in AC-12) handle the small cases.
9. **F7 (harden) — Cross-story integration with S3-02 invariants unasserted.** S3-02 lands `RedactedSlice` with validators `findings_count >= len(fingerprints)`, `findings_count >= 0`, fingerprints must match `^[0-9a-f]{8}$`. S3-01's output must satisfy all three by construction. A regression that returns uppercase hex (e.g., a `.hexdigest().upper()` slip) or an off-by-one count would fail `RedactedSlice` construction at runtime — but only if the integration is *tested*. AC-22 tests S3-01 alone; no AC tests S3-02's validators against S3-01's output. **Fix:** AC-33 added — asserts the returned `RedactedSlice` round-trips through `RedactedSlice.model_validate(model_dump())` and the three invariants hold.
10. **F8 (harden) — Secret-as-substring (inline replacement) unasserted across patterns.** Implementation Notes name the JWT inline-replacement case (`"Bearer eyJ..."` → `"Bearer <REDACTED:...>"`); no AC asserts the same property for the other five pattern classes. A regression that anchors a pattern (e.g., `^AKIA[0-9A-Z]{16}$` or uses `re.fullmatch`) silently passes simple fixtures. **Fix:** AC-34 added — covers inline-substring replacement for AWS, GitHub, NPM, Anthropic, and entropy. JWT already covered by Notes; AC-34 promotes the property to a contract across the family.
11. **F9 (nit) — `Fingerprint` NewType opportunity surfaced, deferred.** The 8-hex fingerprint string crosses module boundaries (sanitizer.py → redacted_slice.py → writer.py → log-field constant in S3-03). Production ADR-0033 §3 names primitive obsession on domain identifiers as a review-blocker. **Not promoted to an AC** in this story because the rule-of-three threshold (third concrete consumer of the family) is not yet reached in S3-01 alone, and S3-02's `RedactedSlice.fingerprints: list[str]` field validator already closes the *format* invariant at construction. **Fix:** Notes-for-implementer #11 added — `Fingerprint = NewType("Fingerprint", str)` recommended for a Phase-3 cross-cutting story when the third consumer (Phase 3 RAG ingest or the audit-anchor) lands. Closing the *origin* invariant (only `_fingerprint(...)` produces a `Fingerprint`) is a Phase-3 follow-up; this story closes the format invariant by validator.
12. **F10 (nit) — Variant-set extension framing missing.** `pattern_class: Literal[...]` is a closed set — extension is ADR-amendment-gated, mirroring S1-01 (`IndexFreshness`) and S1-03 (`AdapterConfidence`). The story did not state this explicitly; a future reader might "improve" it to `str` for "extensibility". **Fix:** Notes-for-implementer #12 added — adding a seventh pattern class is an ADR amendment, not Open/Closed. The walker / fingerprinter / entropy logic stays untouched (extension-by-addition at the `_PATTERNS` row + the `Literal[...]` set widening); the closed set is the deliberate design.
13. **F11 (nit) — Module-docstring assertion technique unspecified.** AC-2 requires the module docstring to reference specific docs but pins no test mechanism. **Fix:** AC-2 strengthened — a programmatic check via `inspect.getdoc(codegenie.output.sanitizer)` substring-matches the required references.

Coverage critic: HARDEN (11 findings). Test-quality critic: HARDEN (mutation table shows six plausibly-wrong implementations slip past the original TDD plan; all closed below). Consistency critic: two BLOCK findings (B1, B2), zero ADR conflicts. Design-pattern critic: two nits surfaced as Notes-for-implementer (Fingerprint newtype #11; variant-set framing #12). Stage 3 research skipped — every gap was answerable from arch + ADR-0005 + ADR-0010 + S1-01 / S1-03 sibling validation precedent + Phase 0 `hashing.py` source on master.

Ready for [phase-story-executor](../../../../skills/phase-story-executor).

## Context

Phase 2 introduces three sources of cleartext secret findings: `gitleaks` (walks `.git/` history for credential patterns — see S6-07), `semgrep p/secrets` (rule-pack matches over source — see S6-06), and an entropy fallback for novel credential shapes the pattern set does not name. Without a defense at the persistence boundary, those cleartext bytes flow through the Phase 0 `OutputSanitizer.scrub` (which only scrubs *known field-name patterns*, not unknown high-entropy values inside arbitrary string fields) and land verbatim in `repo-context.yaml`, every `raw/*.json`, the cache blob, and the audit anchor. 02-ADR-0005 picks the structural fix: **don't persist plaintext at all** — `SecretRedactor` intercepts every string in every `ProbeOutput.schema_slice` *before* it reaches disk, replaces matched cleartext with `<REDACTED:fingerprint=BLAKE3_8>` inline, and returns an in-memory `list[SecretFinding]` for the CLI summary that is never persisted. This story is the redactor itself — patterns, entropy fallback, fingerprint scheme, and the mutation-test discipline that makes pattern coverage a build invariant. The next two stories tighten the writer's signature (S3-02 → S3-03) so "redactor was called" is type-checkable, not convention-enforced.

The redactor sits between Phase 0's existing `OutputSanitizer.scrub` (field-name regex + `JSONValue` tree walk) and the writer. It does **not** replace the Phase 0 sanitizer; it composes after it (composition order is pinned in S3-03 and verified by mock-spy test). The pattern set is finite by intent — six named credential classes that have stable, regex-matchable shapes — with a Shannon-entropy floor (≥ 4.5 bits/char on `len ≥ 32` unknowns) as the safety net for vendor-specific token shapes the pattern set does not name. Phase-0 `codegenie.hashing.content_hash` (BLAKE3) supplies the fingerprint helper; the first 8 hex chars are persisted, which is privacy-preserving by construction (BLAKE3 first-8-hex is not reversible to the cleartext).

The load-bearing test discipline is **mutation testing**: for each pattern class, a deliberately weakened regex (e.g., `AKIA[0-9A-Z]{15}` — one fewer character) is introduced via `monkeypatch.setattr` against the redactor's pattern table; the test asserts the redactor then **fails to redact** the canonical example secret. A regression that loosens a pattern silently passes today's coverage but fails the mutation. Pattern coverage stops being asserted and starts being *verified*.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #4 SecretRedactor` — public interface (`redact_secrets(slice_, probe_name) -> tuple[dict, list[SecretFinding]]` in the doc; **superseded by 02-ADR-0010** — return type is now `tuple[RedactedSlice, list[SecretFinding]]`; the `RedactedSlice` model itself lives in S3-02), pattern list, entropy threshold, fingerprint scheme, mutation-test discipline.
  - `../phase-arch-design.md §"Gap analysis & improvements" Gap 4` — the smart-constructor framing; this story implements the redactor body; S3-02 implements the `RedactedSlice` model + the privacy of construction.
  - `../phase-arch-design.md §"Sequence — secret-redaction flow"` (line ~420) — the end-to-end flow: `gitleaks` → Pydantic → `OutputSanitizer.scrub` → `redact_secrets` → writer. **In-memory findings list is NOT persisted.**
  - `../phase-arch-design.md §"Goals" G5` — testable invariant ("plaintext in zero persisted files"). Asserted by S6-07's `test_secret_in_source.py`; this story is the runtime that makes that assertion green.
  - `../phase-arch-design.md §"Anti-patterns avoided"` — `model_construct()` bypass; this story does NOT construct `RedactedSlice` via `model_construct` and lands the build invariant in S3-02.
- **Phase 2 ADRs:**
  - `../ADRs/0005-secret-findings-no-plaintext-persistence.md` — the structural-defense rationale, full options-considered table, and the reversibility analysis (Medium — one-way by design).
  - `../ADRs/0010-redacted-slice-smart-constructor-at-writer-boundary.md` — the typed return shape this story emits.
- **Source design:**
  - `../final-design.md §"Components" #4 SecretRedactor` — the original tuple return shape; this story implements the 02-ADR-0010-tightened shape.
  - `../final-design.md §"Conflict-resolution table" row 4` — synthesis pick: structural fix (Option C) over encryption-at-rest (Option B) or inline plaintext (Option A).
  - `../final-design.md §"Failure modes & recovery" row 7` — `gitleaks` AKIA-in-git-history scenario.
- **Existing code (Phase 0 + Phase 1 on master):**
  - `src/codegenie/output/sanitizer.py` — Phase 0 `OutputSanitizer.scrub`. This story **extends** it with `redact_secrets`; composition order is the next story's job (S3-03). The existing `scrub(...)` signature is unchanged in *interface*; the body grows by composition.
  - `src/codegenie/hashing.py` (Phase 0) — **`content_hash_bytes(b: bytes) -> str`** is the BLAKE3-of-bytes chokepoint (`content_hash(path: Path)` is the file variant — do NOT confuse). **Both** return prefix-tagged `"blake3:<64hex>"` per Phase-0 ADR-0001; this story strips `"blake3:"` then slices `[:8]`. The fingerprint helper isolates this two-step.
  - `src/codegenie/errors.py` (Phase 0 + Phase 1) — markers-only invariant (`tests/unit/test_errors.py::test_subclasses_are_markers_only`). `SecretFinding` is **not** an exception; it is a Pydantic frozen model.
  - `src/codegenie/parsers/__init__.py` (Phase 1) — `JSONValue` recursive alias is exported here (NOT under `codegenie.types`, which is the identifier-newtype package). Import as `from codegenie.parsers import JSONValue`.
  - `src/codegenie/types/identifiers.py` (Phase 2 / S1-05) — `ProbeId = NewType("ProbeId", str)`. Import as `from codegenie.types.identifiers import ProbeId` (the `codegenie.types` top-level `__all__` re-exports four other newtypes but NOT `ProbeId` as of S1-05's landing — verify before adopting a re-export).
- **Phase 1 shape calibration:**
  - `docs/phases/01-context-gather-layer-a-node/stories/S1-02-safe-json-parser.md` — chokepoint pattern, parsers-layer mutation discipline, structured-event emission via `structlog.testing.capture_logs()` (this story emits `secrets_redacted_count` field — implemented in S3-03 at the writer call site, not here).

## Goal

Ship `src/codegenie/output/sanitizer.py::redact_secrets(slice_, probe_name) -> tuple[RedactedSlice, list[SecretFinding]]` (referring to the `RedactedSlice` model that S3-02 lands; this story imports it) such that:

1. Every string value in the input `slice_: dict[str, JSONValue]` is walked recursively (descending into `dict` values **and** `list` items, mirroring the Phase-1 `safe_json` depth-walker shape).
2. Each pattern-class regex (AWS, GitHub, JWT, RSA private-key block, NPM, Anthropic) replaces matches inline with `<REDACTED:fingerprint=<8hex>>` where `<8hex>` is the first 8 hex characters of `codegenie.hashing.content_hash_bytes(cleartext.encode("utf-8")).removeprefix("blake3:")`. Phase 0 `content_hash_bytes(b: bytes) -> str` is the BLAKE3-of-bytes chokepoint companion to `content_hash(path)`; **both return prefix-tagged `"blake3:<64hex>"`** per Phase-0 ADR-0001, so the `"blake3:"` prefix must be stripped before the 8-hex slice. The fingerprint helper isolates this one-liner.
3. After all pattern-class regex passes, any remaining string of `len(s) >= 32` whose Shannon entropy ≥ 4.5 bits/char is replaced with `<REDACTED:fingerprint=<8hex>>` (the entropy-fallback rule).
4. Each replacement appends a `SecretFinding(probe_name, fingerprint, pattern_class, cleartext_len)` to an in-memory `list[SecretFinding]`. **The cleartext is never stored on the `SecretFinding`.** Plaintext exists only as a local variable inside the regex-substitution callback and is discarded immediately after the fingerprint is computed.
5. The returned `RedactedSlice` carries `slice` (the redacted dict), `findings_count` (the list length), and `fingerprints` (the 8-hex strings, deduplicated and stably ordered).
6. The returned `list[SecretFinding]` is the **in-band** audit-trail consumed by the CLI summary; it is never threaded into the persisted slice.

All pattern classes are mutation-tested: a deliberately weakened regex (e.g., `AKIA[0-9A-Z]{15}` — one fewer character class) **must** cause the canonical-example test to FAIL. Pattern coverage is verified, not asserted.

## Acceptance criteria

Module / surface:

- [ ] AC-1 — `src/codegenie/output/sanitizer.py` exports `redact_secrets(slice_: dict[str, JSONValue], probe_name: ProbeId) -> tuple[RedactedSlice, list[SecretFinding]]`. The existing `OutputSanitizer.scrub` interface is **unchanged** (composition is S3-03's job).
- [ ] AC-2 — `src/codegenie/output/sanitizer.py` module docstring is extended (Phase 0 docstring preserved) to reference `phase-arch-design.md §"Component design" #4`, 02-ADR-0005, and 02-ADR-0010, and to document the entropy threshold (≥ 4.5 bits/char, `len ≥ 32`) with a one-line rationale ("Shannon-entropy floor sized against the gitleaks pattern pack; tunable per `phase-arch-design.md §"Component design" #4`"). A test programmatically asserts the docstring contains the substrings `02-ADR-0005`, `02-ADR-0010`, `4.5`, and `32` — `assert all(s in inspect.getdoc(codegenie.output.sanitizer) for s in [...])`. A regression that drops a reference is caught.
- [ ] AC-3 — `SecretFinding` is a Pydantic `frozen=True, extra="forbid"` model in `src/codegenie/output/sanitizer.py` (or a sibling module imported from it) with exactly four fields: `probe_name: ProbeId`, `fingerprint: str` (8 hex chars), `pattern_class: Literal["aws_access_key", "github_token", "jwt", "rsa_private_key", "npm_token", "anthropic_key", "entropy"]`, `cleartext_len: int`. **No `cleartext` field, no `file_line` field** (the file-line audit trail is the caller's job — gitleaks attaches it separately and never reaches the persisted artifact per 02-ADR-0005).

Pattern-class regex matching:

- [ ] AC-4 — `AKIA[0-9A-Z]{16}` matches and replaces; canonical example `AKIAIOSFODNN7EXAMPLE` is redacted to `<REDACTED:fingerprint=<8hex>>` with `pattern_class="aws_access_key"`.
- [ ] AC-5 — `ghp_[A-Za-z0-9]{36}` matches and replaces; canonical example `ghp_` + 36 alnum chars is redacted with `pattern_class="github_token"`.
- [ ] AC-6 — JWT pattern `eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+` matches and replaces; a synthetic three-part JWT with realistic base64url segments is redacted with `pattern_class="jwt"`. The regex does not match a bare `eyJabc` (must include both dots and three segments).
- [ ] AC-7 — RSA private-key block `-----BEGIN[ A-Z]*PRIVATE KEY-----[\s\S]+?-----END[ A-Z]*PRIVATE KEY-----` matches and replaces, including multi-line bodies; `pattern_class="rsa_private_key"`. The replacement collapses the entire block to a single `<REDACTED:fingerprint=<8hex>>` token (the fingerprint covers the full block bytes).
- [ ] AC-8 — `npm_[A-Za-z0-9]{36}` matches and replaces; `pattern_class="npm_token"`.
- [ ] AC-9 — `sk-ant-[A-Za-z0-9-_]{50,}` matches and replaces (length ≥ 50 to avoid short-prefix false positives); `pattern_class="anthropic_key"`.

Entropy fallback:

- [ ] AC-10 — A string of `len ≥ 32` with Shannon entropy `≥ 4.5` bits/char that does **not** match any named pattern is redacted with `pattern_class="entropy"`. Concrete example: 32+ chars of base64-url-safe random output.
- [ ] AC-11 — A string of `len ≥ 32` with Shannon entropy `< 4.5` bits/char (e.g., `"a" * 64` — entropy = 0; or English prose like `"the quick brown fox" * 4`) is **not** redacted by the entropy rule.
- [ ] AC-12 — A string of `len < 32` (e.g., a 16-char high-entropy base64 fragment) is **not** redacted by the entropy rule, even if its entropy crosses the 4.5 threshold. The length floor is the false-positive control.

Fingerprint scheme:

- [ ] AC-13 — Fingerprint is exactly the first **8** hex characters of `codegenie.hashing.content_hash_bytes(cleartext.encode("utf-8")).removeprefix("blake3:")`. A test asserts: `len(fingerprint) == 8`, every char is in `[0-9a-f]` (lowercase), identical cleartext yields identical fingerprint, distinct cleartext yields distinct fingerprint (sampled across the pattern set). **Negative test:** a regression that calls `content_hash(...)` (the `Path` overload) or skips `.removeprefix("blake3:")` is caught — both produce non-hex 8-char prefixes (the former is a `TypeError`; the latter starts with `"blake3:b"`).
- [ ] AC-14 — The replacement token format is exactly `<REDACTED:fingerprint=<8hex>>` (literal `<REDACTED:fingerprint=`, the 8-hex fingerprint, literal `>`). A `RedactedSlice.fingerprints` field contains the deduplicated, stably-ordered (insertion order) list of distinct fingerprints from this slice.

Recursive walk:

- [ ] AC-15 — The walker descends recursively into **both** `dict` values and `list` items (mirroring `safe_json._assert_depth`). A test fixture with a secret nested as `{"a": [{"b": ["AKIA…EXAMPLE"]}]}` is fully redacted.
- [ ] AC-16 — A secret appearing as a `dict` **key** is not walked into for matching (keys are typically configuration names like `"aws_access_key"` themselves — Phase 0's field-name regex already covers that surface). Only `str` *values* are matched.
- [ ] AC-17 — Non-string scalars (`int`, `float`, `bool`, `None`) are passed through unchanged. Nested types are preserved (`dict` stays `dict`, `list` stays `list`).

Mutation test (load-bearing):

- [ ] AC-18 — `tests/unit/output/test_secret_redactor.py::test_aws_key_mutation` — replaces the AWS regex in the redactor's pattern table with a deliberately weakened version (`AKIA[0-9A-Z]{15}`, one char fewer) via `monkeypatch.setattr` against the module-level pattern table, then re-runs the redactor against the canonical `AKIAIOSFODNN7EXAMPLE` and asserts the cleartext **is not** redacted (i.e., the weakened regex misses the 20-char example). **A mutation that loosens the pattern fails the build.** Mirror tests for the other five pattern classes (`test_github_token_mutation`, `test_jwt_mutation`, `test_rsa_private_key_mutation`, `test_npm_token_mutation`, `test_anthropic_key_mutation`) — each weakens its pattern (one char fewer, one delimiter dropped, one anchor removed) and asserts the canonical example slips through. The test mechanism is identical across the six; only the pattern + canonical example differ.
- [ ] AC-19 — `tests/unit/output/test_secret_redactor.py::test_entropy_threshold_mutation` — replaces the entropy threshold with `5.0` (above the chosen 4.5) and asserts a previously-redacted high-entropy 32-char base64 string is now passed through. **A drift in the entropy floor fails the build.**

In-band findings list (audit trail):

- [ ] AC-20 — `redact_secrets` returns `tuple[RedactedSlice, list[SecretFinding]]`. The `list[SecretFinding]` length equals the **total** number of replacements (each match is one finding, including entropy hits). A test asserts the count under a fixture with two AWS keys + one entropy hit = 3 findings.
- [ ] AC-21 — `SecretFinding.cleartext_len` matches the original byte length of the redacted cleartext; the cleartext itself is **not** present on the `SecretFinding` (assert via `model_dump()` keys).
- [ ] AC-22 — The function is **stateless across calls** — calling `redact_secrets` twice on the same input returns equal `RedactedSlice` objects (Pydantic equality) and equal `list[SecretFinding]` (in insertion order). No global state; no `ContextVar`; no module-level findings accumulator.

Phase-0 / Phase-1 invariants preserved:

- [ ] AC-23 — `OutputSanitizer.scrub` Phase-0 contract-freeze snapshot test (`tests/unit/test_probe_contract.py`) continues to pass — the existing `scrub` signature is unchanged in this story (S3-03 tightens the writer's signature one layer up).
- [ ] AC-24 — No `model_construct` calls anywhere in this story's code. The `forbidden-patterns` pre-commit (S1-11) covers `src/codegenie/output/**`; this story does not introduce a violation. (S3-02 lands the `RedactedSlice` model that this story imports; this story does not construct it via `model_construct`.)

Validator-added: edge cases, integration, and mutation-harness positive controls:

- [ ] AC-26 — **Same-secret-twice dedupe invariant.** A fixture with the *same* canonical AWS key appearing twice (`{"a": "AKIAIOSFODNN7EXAMPLE", "b": "AKIAIOSFODNN7EXAMPLE"}`) yields `findings_count == 2`, `len(returned_slice.fingerprints) == 1`. This is the load-bearing invariant for S3-02's `findings_count >= len(fingerprints)` validator; a regression that uses a `set` for findings (dedupe at the wrong level) silently breaks the contract.
- [ ] AC-27 — **Two distinct named patterns in one string.** A fixture with an AWS key and a GitHub token co-located in one string value (`"aws=AKIAIOSFODNN7EXAMPLE github=ghp_<36 alnum>"`) yields two findings (`pattern_class` values `"aws_access_key"` and `"github_token"`) and two distinct fingerprints. A regression that exits after the first pattern match per pass is caught.
- [ ] AC-28 — **`cleartext_len` is byte-length, not char-length.** Fixture: a cleartext that differs in byte-length vs. char-length (e.g., a synthetic high-entropy 32+-char string with one 3-byte UTF-8 codepoint mixed in, or surround the canonical AWS key with a non-ASCII codepoint that the pattern match excludes). Assert `SecretFinding.cleartext_len == len(matched_cleartext.encode("utf-8"))` and (for the multi-byte fixture) `cleartext_len != len(matched_cleartext)`. A regression using `len(cleartext)` (char count) is caught.
- [ ] AC-29 — **Input is not mutated.** `slice_before = copy.deepcopy(slice_in); redact_secrets(slice_in, probe); assert slice_in == slice_before`. A regression that mutates `slice_` in place is caught. Combined with AC-22 (idempotence across calls), this pins both stateless-across-calls and immutable-input.
- [ ] AC-30 — **`_PATTERNS` and `_ENTROPY_THRESHOLD_BITS_PER_CHAR` are module-level names** (positive control for the mutation harness). Asserts: (a) `getattr(sanitizer, "_PATTERNS")` returns a `list`; (b) `getattr(sanitizer, "_ENTROPY_THRESHOLD_BITS_PER_CHAR")` returns a `float`; (c) `monkeypatch.setattr(sanitizer, "_PATTERNS", [])` causes a subsequent `redact_secrets` call against `"AKIAIOSFODNN7EXAMPLE"` to *NOT* redact the AWS key (the patched empty table is genuinely consulted). A regression that moves the table function-local fails (c) — the mutation harness is broken if (c) fails, and that's the load-bearing positive control AC-18/AC-19 depend on.
- [ ] AC-31 — **Entropy edge cases.** `_shannon_entropy("")` returns `0.0` (or a sentinel; whichever the implementation picks — pin one). `_shannon_entropy("a")` returns `0.0`. `_shannon_entropy("a" * 100)` returns `0.0`. `_shannon_entropy(some_64_char_unicode_string)` returns a finite float without crash. The entropy function itself never raises `ValueError` / `ZeroDivisionError` / `OverflowError`. The skip-the-rule semantics for `len < 32` (already in AC-12) handle the small-string cases; this AC pins that the entropy function is total over `str`.
- [ ] AC-32 — **`content_hash_bytes` prefix-strip regression test.** Calls `_fingerprint(b"sentinel")` and asserts the returned 8-char string is all `[0-9a-f]` (lowercase) and is exactly `content_hash_bytes(b"sentinel")[7:15]` (the slice past the `"blake3:"` prefix). A regression that drops `.removeprefix("blake3:")` produces `"blake3:b"` and fails the all-hex assertion.
- [ ] AC-33 — **S3-02 round-trip integration.** The `RedactedSlice` returned by `redact_secrets` survives `RedactedSlice.model_validate(returned.model_dump())` (Pydantic round-trip through validators). Assert all three S3-02 invariants hold on every test fixture: (i) every fingerprint matches `^[0-9a-f]{8}$`; (ii) `findings_count >= len(fingerprints)`; (iii) `findings_count >= 0`. A regression in S3-01 that violates any of these (uppercase hex slip; off-by-one count; negative count from a buggy loop) fails at runtime — this AC moves the failure into the test suite where the executor's Validator catches it before merge.
- [ ] AC-34 — **Inline-substring replacement across pattern classes.** Fixtures embed each named pattern inside a longer string (e.g., `"prefix-AKIAIOSFODNN7EXAMPLE-suffix"`, `"Authorization: token ghp_<36>"`, `"NPM_TOKEN=npm_<36>"`, `"X-Anthropic-Key: sk-ant-<50+>"`, `"random-prefix-<32+chars-high-entropy>-suffix"`). Each fixture's redacted output preserves the prefix/suffix and replaces only the matched substring with `<REDACTED:fingerprint=…>`. JWT is already covered by Notes-for-implementer; AC-34 promotes the property to a contract across the family. A regression that anchors a pattern (e.g., `^AKIA…$` or `re.fullmatch`) is caught.

Toolchain:

- [ ] AC-25 — `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files. `mypy --strict` accepts the recursive `JSONValue` walker without `# type: ignore`.

## Implementation outline

1. Add to `src/codegenie/output/sanitizer.py` (extending Phase 0's existing module — the existing `OutputSanitizer.scrub` is untouched):
   - Import `RedactedSlice` from `src/codegenie/output/redacted_slice.py` (lands in S3-02 — this story is paired with S3-02; the executor lands them as a single PR, or S3-02 lands first and this story imports).
   - Define `SecretFinding` Pydantic `frozen=True, extra="forbid"` (four fields per AC-3).
   - Define a module-level pattern table:
     ```python
     _PATTERNS: list[tuple[Literal[...], re.Pattern[str]]] = [
         ("aws_access_key",    re.compile(r"AKIA[0-9A-Z]{16}")),
         ("github_token",      re.compile(r"ghp_[A-Za-z0-9]{36}")),
         ("jwt",               re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")),
         ("rsa_private_key",   re.compile(r"-----BEGIN[ A-Z]*PRIVATE KEY-----[\s\S]+?-----END[ A-Z]*PRIVATE KEY-----")),
         ("npm_token",         re.compile(r"npm_[A-Za-z0-9]{36}")),
         ("anthropic_key",     re.compile(r"sk-ant-[A-Za-z0-9_-]{50,}")),
     ]
     _ENTROPY_THRESHOLD_BITS_PER_CHAR: float = 4.5
     _ENTROPY_MIN_LEN: int = 32
     ```
     The table is module-level (not function-local) so `monkeypatch.setattr` can swap entries for AC-18 mutation tests.
   - Implement `_shannon_entropy(s: str) -> float` — stdlib `math.log2`, char-frequency dict, single-pass. Guard against empty input (return `0.0`); the formula `-sum(p * log2(p) for p in freqs.values())` is naturally total over non-empty `str` because `p > 0` for every entry in the frequency dict. Pin this in AC-31.
   - Implement `_fingerprint(cleartext: str) -> str` — `content_hash_bytes(cleartext.encode("utf-8")).removeprefix("blake3:")[:8]`. The `"blake3:"` prefix is mandatory per Phase-0 ADR-0001; stripping then slicing isolates the two-step in one helper so AC-32's regression test pins the exact form.
   - Imports: `from codegenie.parsers import JSONValue` (NOT `codegenie.types`); `from codegenie.types.identifiers import ProbeId` (the `codegenie.types` top-level does NOT re-export `ProbeId` as of S1-05); `from codegenie.hashing import content_hash_bytes`; `from codegenie.output.redacted_slice import RedactedSlice` (lands in S3-02 — see Notes for implementer #10).
   - Implement `_redact_string(s: str, probe_name: ProbeId, findings_out: list[SecretFinding]) -> str` — applies each `_PATTERNS` regex with `re.sub` whose `repl` is a closure that computes the fingerprint, appends a `SecretFinding`, and returns the `<REDACTED:fingerprint=…>` token; after all patterns, checks the entropy rule on the **remaining** string (i.e., the post-regex string) and replaces if the rule fires (the entropy check sees `<REDACTED:fingerprint=…>` tokens but those are short and below the 32-char floor; documented in implementer note).
   - Implement `_walk(node: JSONValue, probe_name: ProbeId, findings_out: list[SecretFinding]) -> JSONValue` — recursive dispatch on `isinstance(node, str|dict|list)`; calls `_redact_string` on strings; recurses into `dict.values()` and `list` items; passes through scalars.
   - Implement the public `redact_secrets(slice_, probe_name) -> tuple[RedactedSlice, list[SecretFinding]]`:
     ```python
     findings: list[SecretFinding] = []
     redacted: dict[str, JSONValue] = _walk(slice_, probe_name, findings)  # type: ignore[assignment]
     fingerprints = list(dict.fromkeys(f.fingerprint for f in findings))  # dedupe, preserve order
     return (
         RedactedSlice(
             slice=redacted,
             findings_count=len(findings),
             fingerprints=fingerprints,
         ),
         findings,
     )
     ```
2. Write `tests/unit/output/test_secret_redactor.py` covering all 25 ACs. Mutation tests use `monkeypatch.setattr(sanitizer, "_PATTERNS", [...weakened...])` and `monkeypatch.setattr(sanitizer, "_ENTROPY_THRESHOLD_BITS_PER_CHAR", 5.0)`.
3. No edits to `OutputSanitizer.scrub` in this story — composition order is S3-03.
4. No edits to `writer.py` in this story — signature tightening is S3-03.

## Out of scope

- The `RedactedSlice` Pydantic model itself (S3-02) — this story imports it.
- `OutputSanitizer.scrub` composition + ordering documentation (S3-03).
- Writer signature tightening (S3-03).
- `secrets_redacted_count` log field at the writer (S3-03).
- `tests/adv/phase02/test_secret_in_source.py` (S6-07 — load-bearing adversarial; depends on this story landing first).
- `tests/adv/phase02/test_no_inmemory_secret_leak.py` (S7-04 — `inspect`-based boundary test; Gap 5 closure).
- CLI summary line (`secrets_redacted_count: <N>` + file:line list) — this story returns the findings list; the CLI summary path consumes it; the CLI summary itself is touched in S3-03 / S8-02.

## Notes for the implementer

- **Pattern table at module level, not function-local.** AC-18 mutation tests require `monkeypatch.setattr(sanitizer, "_PATTERNS", [...weakened...])`. A function-local pattern table makes mutation testing impossible. Document the invariant in the module docstring.
- **Entropy threshold rationale in the module docstring.** AC-2 requires the docstring to name 4.5 bits/char + `len ≥ 32` and a one-line rationale. The threshold is empirically chosen against the gitleaks pattern pack — document the source (Phase 2 final-design Conflict-resolution table row 4 — Option C synthesis). A future tune is a docstring + AC-19 threshold change; the mutation test makes drift visible.
- **Cleartext lifetime.** The cleartext appears as the match group inside the `re.sub` callback. Compute the fingerprint, append the `SecretFinding`, return the replacement token. **Do not** stash the cleartext anywhere — not in a debug log, not in a `print`, not on the `SecretFinding`. Rule 12 (Fail loud) applies inverted: do not silently retain.
- **`re.sub` callback construction.** Use `re.sub(pattern, _make_repl(probe_name, pattern_class, findings_out), s)` where `_make_repl` returns a closure. Each match invokes the closure exactly once; the closure side-effects `findings_out` and returns the replacement token. The closure captures `probe_name`, `pattern_class`, and the findings list — no other state.
- **JWT regex anchor discipline.** The JWT pattern matches anywhere in the string (no `^`/`$`). A typical JWT appears in a JSON value as `"Authorization: Bearer eyJ..."`. The regex finds the JWT substring and replaces it inline (the `"Authorization: Bearer "` prefix is preserved). Test fixture covers this.
- **RSA block is multi-line.** The pattern uses `[\s\S]+?` (non-greedy any-char-including-newline) between BEGIN and END. A test fixture must contain a multi-line RSA block (synthesized — never a real key).
- **The entropy rule sees post-regex strings.** After all six pattern regexes run, the remaining string may contain `<REDACTED:fingerprint=…>` tokens. Those tokens are short (under 32 chars) and below the `len ≥ 32` floor — the entropy rule will not fire on them. Document this composition invariant in the `_redact_string` docstring.
- **Stable fingerprint ordering for `RedactedSlice.fingerprints`.** Use `list(dict.fromkeys(f.fingerprint for f in findings))` — `dict.fromkeys` deduplicates and preserves insertion order (guaranteed by Python 3.7+). A test asserts that two semantically-identical inputs produce identical `RedactedSlice.fingerprints` (AC-22).
- **`SecretFinding.cleartext_len` is the int byte-length, not char-length.** Use `len(cleartext.encode("utf-8"))`. Multi-byte secrets are rare (most credential schemes are ASCII) but the byte-length is the auditor-friendly measure.
- **`pattern_class` is a `Literal[...]` not an enum.** Cheaper at the Pydantic boundary; `mypy --strict` enforces exhaustiveness if a future story uses `match` over the literal.
- **The `RedactedSlice` import.** S3-02 lands `src/codegenie/output/redacted_slice.py` with the model. This story imports it. If the executor lands S3-02 and S3-01 in one PR, the import path is correct; if S3-02 lands first, the import lands cleanly. The two stories are tightly coupled by design; the validator may merge them into a single attempt log.
- **No LLM, no shell, no subprocess.** This is a pure regex + entropy + BLAKE3 pass. Total LOC budget ~150 (pattern table, walker, fingerprint helper, entropy helper, `redact_secrets`, `SecretFinding` model). The mutation test file is ~200 LOC (one mutation per pattern class + entropy threshold + composition + walker + cleartext-lifetime assertions).
- **#11 — `Fingerprint = NewType("Fingerprint", str)` is deferred.** Production ADR-0033 §3 names primitive-obsession on domain identifiers as a review-blocker pattern; the 8-hex fingerprint qualifies on the surface (crosses ≥ 2 module boundaries: sanitizer → redacted_slice → writer → log-field constant). The validator considered promoting `Fingerprint` to a `NewType` in this story but **deferred** because (a) the rule-of-three threshold (third concrete consumer of the family) is not reached until Phase 3 (RAG ingest or audit-anchor); (b) S3-02's `RedactedSlice.fingerprints: list[str]` field-validator already closes the *format* invariant (`^[0-9a-f]{8}$`) at construction; (c) introducing the newtype now without the third consumer would either (i) require S3-02 to type `fingerprints: list[Fingerprint]` (forcing the executor to land it in a coupled PR) or (ii) leave a one-callsite newtype that adds boilerplate without payoff. A Phase-3 cross-cutting story should land `Fingerprint` once and propagate the type to all consumers — the *origin* invariant ("only `_fingerprint(...)` produces a `Fingerprint`") closes then. This story uses `str` deliberately; the format invariant is the structural defense.
- **#12 — `pattern_class: Literal[...]` is a deliberately closed variant set.** Adding a seventh pattern class (e.g., `"slack_webhook"`, `"gcp_service_account_key"`) is an **ADR amendment**, not Open/Closed. The closed set mirrors the variant-set-extension discipline ratified in S1-01 (`IndexFreshness`) and S1-03 (`AdapterConfidence`): the walker / fingerprinter / entropy logic stays untouched (extension-by-addition is at the `_PATTERNS` row append), and the `Literal[...]` widens by ADR-amendment so `mypy --strict` with `--warn-unreachable` enforces exhaustive `match` discipline at every consumer. A future contributor who "loosens" `pattern_class` to `str` for "extensibility" defeats this exhaustiveness check; the design intent is the closed set + ADR amendment, not Open/Closed. Document in the module docstring.
