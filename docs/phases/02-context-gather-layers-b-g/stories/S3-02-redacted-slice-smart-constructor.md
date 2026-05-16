# Story S3-02 — `RedactedSlice` smart constructor private to `redact_secrets`

**Step:** Step 3 — Plant `SecretRedactor` + `RedactedSlice` smart constructor at the writer chokepoint
**Status:** Ready
**Effort:** S
**Depends on:** S3-01 (the redactor body that uses `RedactedSlice` as its return type), S1-11 (Done — `forbidden-patterns` script extended with the `model_construct` rule scoped to `_PHASE2_BANNED_PACKAGES` via the `applies_when` predicate; `"output"` is in that frozenset on master)
**ADRs honored:** 02-ADR-0010 (`RedactedSlice` smart constructor at the writer boundary — the Gap-4 typed-defense ladder), 02-ADR-0005 (no plaintext persistence — the runtime defense this story upgrades to a type-level defense), [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md) (newtype + smart-constructor discipline applied at the I/O boundary, not the wire-type boundary)

## Validation notes (phase-story-validator, 2026-05-15)

Verdict: **HARDENED**. The draft was structurally sound — `RedactedSlice` as a frozen Pydantic model with three fields, validator-enforced 8-hex fingerprint format, `findings_count >= len(fingerprints)` invariant, `model_construct` ban via S1-11, and the threefold-defense framing all trace cleanly to 02-ADR-0010, 02-ADR-0005, and `phase-arch-design.md §"Gap analysis & improvements" Gap 4`. But the draft carried **three BLOCK-severity bugs** in prescribed code/contracts (it would not run as written) and **eight harden-tier gaps** that would have let plausibly-wrong implementations slip past the executor's Validator pass. Edits applied:

1. **B1 (BLOCK) — `JSONValue` import path wrong.** Draft prescribed `from codegenie.types import JSONValue` (Implementation outline line 116). Phase 1 actually places `JSONValue` at `src/codegenie/parsers/__init__.py` (re-exported from `parsers.safe_json`); `codegenie.types` is a package holding identifier newtypes only. Same B2 bug closed in S3-01 (Validation note #2). **Fix:** References line 35 corrected to `src/codegenie/parsers/__init__.py`; Implementation outline import corrected to `from codegenie.parsers import JSONValue`; AC-18 source-of-truth pinned to the parsers package.
2. **B2 (BLOCK) — Non-existent file reference.** References block named `src/codegenie/types.py (Phase 0)` as the home of `JSONValue`. No such file exists; the `codegenie.types` package (`src/codegenie/types/identifiers.py`) carries the newtypes. **Fix:** Reference path corrected; "Phase 0" wording corrected to "Phase 1" (the `parsers` package landed in S1-02).
3. **B3 (BLOCK) — AC-13 prescribes a non-existent enforcement surface.** Draft asserted "the `forbidden-patterns` glob includes `src/codegenie/output/**/*.py` (or equivalent broader glob)". S1-11 (Done, master verified) shipped the path-scoping **inside** `scripts/check_forbidden_patterns.py` via a `_PHASE2_BANNED_PACKAGES: frozenset[str]` set + an `_is_under_phase2_banned_package(path) -> bool` predicate on a `Rule` dataclass's `applies_when` field — **not** a `.pre-commit-config.yaml` glob. A test asserting a glob would fail on the real surface. **Fix:** AC-13 reframed to assert `"output" in _PHASE2_BANNED_PACKAGES` and `_is_under_phase2_banned_package(Path("src/codegenie/output/redacted_slice.py")) is True` (the actual runtime predicate). A regression that drops `"output"` from the frozenset fails this test.
4. **F1 (harden) — AC-12 subprocess prescription too loose.** Draft said "subprocess call to the pre-commit hook script with a temporary file" but did not pin the invocation shape or the advice-string contract. S1-11 hardened the advice contract to `and` (both `02-ADR-0010 §Decision` AND `production ADR-0033 §3` substrings must appear in every emitted error line). **Fix:** AC-12 tightened: `subprocess.run([sys.executable, "scripts/check_forbidden_patterns.py", str(temp_file)], capture_output=True, text=True)` against a file written under `tmp_path/src/codegenie/output/synth.py` containing `RedactedSlice.model_construct(slice={}, findings_count=0, fingerprints=[])`; assert exit code ≥ 1; assert stdout contains BOTH `02-ADR-0010 §Decision` AND `production ADR-0033 §3` (the contract is `and`, mirroring S1-11 AC-2). Also AC-12b added: a negative-path test writing the same offending content under `tmp_path/src/codegenie/parsers/synth.py` (NOT in `_PHASE2_BANNED_PACKAGES`) MUST exit zero — pinning that the surgical predicate is honored.
5. **F2 (harden) — AC-14 bare-word grep collides with this module's own docstring.** Draft said "test greps the package recursively for `model_construct` and asserts zero matches". But this module's docstring (AC-1) explicitly references `model_construct` as the banned construct — the bare-word grep would false-positive on the docstring. **Fix:** AC-14 rewritten to use the **same structural regex** as the lint rule (`re.compile(r"\.model_construct\s*\(|\bmodel_construct\s*=")`) — matches the call form, not the prose mention. The test imports `_PATTERN_MODEL_CONSTRUCT` directly from `scripts.check_forbidden_patterns` (or copies the regex verbatim) so a regression that loosens the regex in the script flips this test too.
6. **F3 (harden) — AC-7 missing property-based coverage for fingerprint format.** Draft listed six scalar cases (`len 7`, `len 9`, uppercase, hex, accepted, empty); coverage is reasonable but mutation-fragile — a regression that special-cases (e.g., `if fp != "00000000"`) silently passes. **Fix:** AC-7b added — hypothesis property test: `@given(st.text(alphabet="0123456789abcdef", min_size=8, max_size=8))` → accepted; `@given(st.text(...).filter(lambda s: not re.fullmatch(r"^[0-9a-f]{8}$", s)))` → rejected. Pins the *closure* of the rule against the *complement*.
7. **F4 (harden) — AC-8 missing boundary cases (`==` and zero-baseline).** Draft pins the inequality `findings_count < len(fingerprints)` rejection and the strict `>` acceptance. Missing: `findings_count == len(fingerprints)` (boundary equality) and `findings_count == 0, fingerprints == []` (zero-baseline). A regression that misplaces a `<=` for a `<` would silently pass without the boundary case. **Fix:** AC-8b added — parametrized over `(findings_count, fingerprints)` ∈ {(0, []), (1, ["abcdef12"]), (3, ["abcdef12"]), (3, ["abcdef12", "12345678", "fedcba98"])} → all accept; ((-1, []), (0, ["abcdef12"]), (1, ["abcdef12", "12345678"])) → all reject.
8. **F5 (harden) — AC-10 round-trip missing JSON-determinism and nested-recursion.** Draft asserts Pydantic equality but does not pin: (a) `model_dump_json()` output is **byte-for-byte identical** across two successive calls on the same instance (cache stability; same invariant Phase 0 cache layer relies on for content-addressed keys); (b) the `slice` field carries genuinely **nested** `JSONValue` (dict-of-list-of-dict with `<REDACTED:fingerprint=…>` placeholder strings inside), not a flat dict — the recursive alias has to actually round-trip through Pydantic. **Fix:** AC-10b added — `assert model.model_dump_json() == model.model_dump_json()` (byte-stability); AC-10c added — round-trip fixture has at least three levels of nesting with placeholder strings interleaved with non-secret strings, lists, and `None` values.
9. **F6 (harden) — Missing field declaration order assertion.** Notes name "Field order matters for JSON serialization … Declare `slice` first, then `findings_count`, then `fingerprints` — readers of `repo-context.yaml` see the slice payload at the top". AC-11 asserts the keys *set* but not the *order*. A regression that re-orders the field declarations (e.g., a refactor moving `findings_count` first for "consistency with sibling models") silently passes. **Fix:** AC-11b added — `list(model.model_dump().keys()) == ["slice", "findings_count", "fingerprints"]` AND `list(json.loads(model.model_dump_json()).keys()) == [...]` (Pydantic preserves declaration order in both JSON output and Python `dict` output).
10. **F7 (harden) — AC-2 module-docstring assertion mechanism unspecified.** Draft requires the docstring to name specific references but pins no test mechanism. Same F11 gap closed in S3-01. **Fix:** AC-2 strengthened — programmatic check via `inspect.getdoc(codegenie.output.redacted_slice)` substring-matches the required references (`Gap 4`, `02-ADR-0010`, `02-ADR-0005`, and the three-rung-ladder framing). A regression that drops any of the four substrings fails the assertion.
11. **F8 (harden) — Cross-story integration with S3-01 unasserted.** S3-01 ships `redact_secrets` returning `tuple[RedactedSlice, list[SecretFinding]]`. S3-02's invariants (`findings_count >= len(fingerprints)`, fingerprints match `^[0-9a-f]{8}$`, `findings_count >= 0`) must hold by construction on every output of `redact_secrets`. AC-15 covers only the happy-path empty-slice. **Fix:** AC-15b added — parametrized cross-story integration test (mirrors S3-01 AC-33): feed `redact_secrets` slices with {0 secrets, 1 secret, 3 distinct secrets, 2-of-same-fingerprint (same key twice)} → assert the returned `RedactedSlice` round-trips through `RedactedSlice.model_validate(model.model_dump())` and all three model invariants hold. Single integration test that fails red if S3-01 ever emits uppercase hex, off-by-one counts, or non-deduplicated fingerprints.
12. **DP1 (Note) — `Fingerprint` newtype rule-of-three threshold crossed at S3-03.** S3-01 deferred this (Validation note #11) at one consumer (sanitizer.py). S3-02 is the second (`RedactedSlice.fingerprints: list[str]`). S3-03 is the third (writer reads `slice_.fingerprints` for the persisted shape per 02-ADR-0010 Tradeoffs row 2). Production ADR-0033 §3 names primitive obsession on cross-module identifiers as a review-blocker. **Fix:** Notes-for-implementer §"Design patterns" added — `Fingerprint = NewType("Fingerprint", str)` recommended for an S3-03 follow-up amendment (or a Phase-3-entry cross-cutting story landing concurrently with the audit-anchor / RAG ingest consumers). S3-02 closes the *format* invariant by validator; the *origin* invariant (only `_fingerprint(...)` produces a `Fingerprint`) is S3-03's surface. **Not promoted to AC** in this story — the format closure is sufficient at this layer; the origin closure straddles three modules.
13. **DP2 (Note) — `RedactedSlice` is a closed product type.** Three persisted fields is the 02-ADR-0010 §Decision contract. Adding a fourth persisted field (e.g., a `pattern_class_counts: dict[Literal["aws","github",...], int]` for telemetry) is an **ADR amendment**, not a "we'll just add another field". Mirrors S3-01 Validation note #12 (variant-set extension framing). **Fix:** Notes-for-implementer §"Closed product type" added — extension is ADR-amendment-gated; the closed set is the deliberate design.
14. **DP3 (Note) — Functional core / imperative shell discipline.** `redacted_slice.py` is **pure** — no I/O, no logging, no side effects, no filesystem reads. The validators are pure functions over their arguments. This is the right shape for a domain-model module that sits on the secret-redaction hot path; future contributors must not add I/O here. **Fix:** Notes-for-implementer §"Pure module" added — explicit no-I/O constraint; reads of `logging.py`, `os.environ`, `Path`, `subprocess` are all out.

Stage 3 research **skipped** — no `NEEDS RESEARCH` findings. Every gap was answerable from arch + ADRs (02-ADR-0005, 02-ADR-0010, production ADR-0033) + verified live source (`src/codegenie/parsers/__init__.py`, `src/codegenie/hashing.py`, `scripts/check_forbidden_patterns.py` on master) + S3-01 / S1-11 sibling validation precedent.

Coverage critic: HARDEN (6 findings — F3, F4, F5, F6, F8 closed; AC-11/Field order added as F6). Test-quality critic: HARDEN (5 findings — F1, F2, F3, F8 closed; mutation table shows three plausibly-wrong implementations would have slipped past the original TDD plan, all closed below). Consistency critic: three BLOCK findings (B1, B2, B3), zero ADR conflicts. Design-pattern critic: three nits surfaced as Notes-for-implementer (`Fingerprint` newtype DP1 deferred; closed-product-type framing DP2; pure-module discipline DP3). Nineteen ACs original → **twenty-six ACs** after hardening (AC-7b, AC-8b, AC-10b, AC-10c, AC-11b, AC-12b, AC-15b added; AC-2, AC-12, AC-13, AC-14 reworded).

Ready for [phase-story-executor](../../../../skills/phase-story-executor).

## Context

02-ADR-0005 commits Phase 2 to persisting zero plaintext secrets: `SecretRedactor` (S3-01) intercepts every string, replaces matched secrets with `<REDACTED:fingerprint=BLAKE3_8>`, and returns an in-memory `list[SecretFinding]` for the CLI summary that is never persisted. The synthesis defends the chokepoint at the *pipeline* layer — `OutputSanitizer.scrub` calls `redact_secrets`, then writes.

But the critic (`phase-arch-design.md §"Gap analysis & improvements" Gap 4`) named the residual gap: if `redact_secrets` returns `tuple[dict[str, JSONValue], list[SecretFinding]]`, the caller is responsible for not persisting the findings list. **A future contributor could thread the findings into a debug log, an audit-anchor extra field, or a CONTEXT_REPORT debug section, and silently leak plaintext fingerprints** (or worse, plaintext if a contributor "improves" the return type). The discipline is enforced by code review, not by types — exactly the failure mode the toolkit's smart-constructor pattern was named to prevent (`design-patterns-toolkit.md §"Smart constructor"` failure mode: "every caller has to remember to call `.validate()` afterward. They won't.").

This story closes Gap 4 by applying the smart-constructor pattern at the redaction boundary. `RedactedSlice` is a frozen Pydantic model whose construction path is exactly one: `redact_secrets`. The model carries three fields — the redacted slice itself, the count of replacements, and the deduplicated 8-hex fingerprint list. **The fingerprint list is the *only* secret-related field that may appear in persisted artifacts** (BLAKE3 first-8-hex is privacy-preserving by construction). The in-memory `list[SecretFinding]` is returned alongside the `RedactedSlice` as a separate tuple element; the writer (S3-03) accepts only the `RedactedSlice`, never the findings list — making "redactor was called" type-checkable.

The bypass surface to close is Pydantic's `model_construct` — Pydantic's documented escape hatch that skips validation. S1-11 extends the Phase-0 `forbidden-patterns` pre-commit hook to ban `model_construct` under `src/codegenie/{indices,tccm,skills,conventions,adapters,depgraph,output}/**`. This story relies on that ban; the test asserts the ban fires on a deliberately-incorrect PR by invoking the lint check programmatically and confirming a violation is reported.

The structural test that asserts `RedactedSlice.__init__` is the only public factory and `redact_secrets` is the only call site is **deferred to S7-04** (Gap-5 boundary test via `inspect` — same shape Phase 0 already uses for `forbidden-patterns`). This story lands the model + the runtime guarantees (round-trip identity, no plaintext in `fingerprints`, immutability via `frozen=True`); the source-level structural test is one phase-2 story later in the dependency chain (the `inspect`-based boundary test reaches every Phase-2 module — landing it before all the Phase-2 probes ship would force a re-write).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Gap analysis & improvements" Gap 4` — the smart-constructor framing, the proposed model shape, the ~20-LOC estimate, and the writer-signature tightening that S3-03 lands.
  - `../phase-arch-design.md §"Anti-patterns avoided"` — `model_construct()` bypass; the `forbidden-patterns` ban is the enforcement.
  - `../phase-arch-design.md §"Component design" #4 SecretRedactor` — the return-shape source-of-truth (after 02-ADR-0010 tightening: `tuple[RedactedSlice, list[SecretFinding]]`).
- **Phase 2 ADRs:**
  - `../ADRs/0010-redacted-slice-smart-constructor-at-writer-boundary.md` — the full design and structural-defense rationale; reversibility (Medium-high — reverting dissolves into review-enforcement, which is what this ADR closes).
  - `../ADRs/0005-secret-findings-no-plaintext-persistence.md` — the runtime defense this story upgrades to a type-level defense; the *structural ladder* framing (runtime + type-system + invariant test, all three rungs).
- **Source design:**
  - `../final-design.md §"Components" #4 SecretRedactor` — original tuple return shape; this story implements the 02-ADR-0010-tightened shape.
  - `../final-design.md §"Departures from all three inputs" #4` — explicit departure from encryption-at-rest theatre.
- **Existing code:**
  - `src/codegenie/output/sanitizer.py` — S3-01 lands `redact_secrets` here; this story creates the sibling `redacted_slice.py` module that S3-01's body imports. (Alternatively, the model lives inside `sanitizer.py` itself — see the implementer note on packaging choice.)
  - `src/codegenie/parsers/__init__.py` (Phase 1) — `JSONValue` recursive alias used for the `slice` field type. Imported as `from codegenie.parsers import JSONValue`. **NOT** `codegenie.types` (that package holds identifier newtypes only; `JSONValue` lives in `parsers`).
  - **Forbidden-patterns surface** (landed via S1-11, Status: Done): `scripts/check_forbidden_patterns.py` ships the `model_construct` rule scoped to `_PHASE2_BANNED_PACKAGES: frozenset[str]` (currently `{"indices", "tccm", "skills", "conventions", "adapters", "depgraph", "output"}`) via an `_is_under_phase2_banned_package(path) -> bool` predicate on the rule's `applies_when` field. Path-scoping lives **inside the script**, NOT in `.pre-commit-config.yaml`. Tests invoke `python scripts/check_forbidden_patterns.py <path>` as a subprocess; the script exits non-zero when the rule fires; the advice string contains BOTH `02-ADR-0010 §Decision` AND `production ADR-0033 §3` (S1-11 AC-2 hardened this to `and`, not `or`).
- **Phase 1 shape calibration:**
  - `docs/phases/01-context-gather-layer-a-node/stories/S1-04-jsonc-parser.md` (or any Phase-1 Pydantic-model story) — `frozen=True, extra="forbid"` discipline; round-trip identity test pattern via `model_dump_json` / `model_validate_json`.

## Goal

Ship `src/codegenie/output/redacted_slice.py` with the `RedactedSlice` Pydantic model such that:

1. The model is `frozen=True, extra="forbid"` — instances are immutable; unknown fields are rejected at construction.
2. The model has exactly three fields: `slice: dict[str, JSONValue]`, `findings_count: int`, `fingerprints: list[str]`.
3. The `fingerprints` field validator rejects any string that is not exactly 8 lowercase hex characters — **the persisted shape carries fingerprints only, never plaintext**.
4. The `findings_count` field validator rejects any value where `findings_count < len(fingerprints)` (fingerprints are deduplicated; count is the total findings, so `findings_count >= len(fingerprints)` is the invariant).
5. The model round-trips through `model_dump_json` / `model_validate_json` with structural identity (Pydantic equality holds, `JSONValue` recursion is preserved).
6. `model_construct` is forbidden under `src/codegenie/output/**` by the `forbidden-patterns` pre-commit (S1-11); a test invokes the lint hook against a deliberately-incorrect snippet that calls `RedactedSlice.model_construct(...)` and asserts the hook reports a violation. **`redact_secrets` (S3-01) is the only public path to a `RedactedSlice` instance.**
7. The structural test asserting "`redact_secrets` is the only call site that constructs a `RedactedSlice`" is **deferred to S7-04** (documented in this story's "Out of scope" + "Notes for the implementer"); this story lands the model and the type-level / lint-level defenses, not the source-level `inspect` boundary test.

## Acceptance criteria

Module / surface:

- [ ] AC-1 — `src/codegenie/output/redacted_slice.py` exists; module docstring references `phase-arch-design.md §"Gap analysis & improvements" Gap 4`, 02-ADR-0010, and 02-ADR-0005. The docstring names the structural-ladder framing ("Three rungs: runtime — `SecretRedactor` replaces cleartext inline (02-ADR-0005); type-system — writer accepts only `RedactedSlice` (02-ADR-0010, this module); source-level — `redact_secrets` is the only call site (deferred to S7-04)").
- [ ] AC-2 — `RedactedSlice` is exported; importable as `from codegenie.output.redacted_slice import RedactedSlice`. **Programmatic docstring check:** a test imports the module and asserts `inspect.getdoc(codegenie.output.redacted_slice)` contains all four substrings: `"Gap 4"`, `"02-ADR-0010"`, `"02-ADR-0005"`, and `"Three rungs"` (or `"three-rung"` — case-insensitive substring match for the ladder framing). A regression that drops any of the four substrings fails the assertion.
- [ ] AC-3 — `RedactedSlice` has exactly three public fields (`slice`, `findings_count`, `fingerprints`) and no others. A test introspects via `RedactedSlice.model_fields.keys()`.

Model invariants:

- [ ] AC-4 — `RedactedSlice.model_config["frozen"] is True` and `RedactedSlice.model_config["extra"] == "forbid"`. Asserted directly.
- [ ] AC-5 — Attempting to mutate a constructed `RedactedSlice` (`instance.findings_count = 99`) raises `pydantic.ValidationError` (frozen invariant).
- [ ] AC-6 — Constructing with an unknown field (`RedactedSlice(slice={}, findings_count=0, fingerprints=[], extra_field="x")`) raises `pydantic.ValidationError` with `extra_forbidden` (extra invariant).

Field-level validators:

- [ ] AC-7 — `fingerprints` field validator rejects any string that is not exactly 8 characters, or contains any non-hex char, or has any uppercase char. Tests cover: `len 7` rejected; `len 9` rejected; `"ABCDEF12"` (uppercase) rejected; `"12345678"` accepted; `"abcdef12"` accepted; `""` rejected; non-string element rejected by Pydantic type-checker. Whitespace-padded (`"abcdef12 "`) rejected; mixed-case (`"aBcDeF12"`) rejected; non-ASCII (`"abcdef1ñ"`) rejected.
- [ ] AC-7b — *Property-based mutation-resistance* — using `hypothesis`: (a) `@given(st.text(alphabet="0123456789abcdef", min_size=8, max_size=8))` → every drawn fingerprint is accepted (one-element list, full-list, and inside a 10-element list); (b) `@given(st.text(alphabet=string.printable, min_size=0, max_size=20).filter(lambda s: re.fullmatch(r"^[0-9a-f]{8}$", s) is None))` → every drawn non-fingerprint is rejected with `ValidationError`. Pins the *closure* of the rule (accepts ∩ accepts^c = ∅). A regression that special-cases a magic value (e.g., `if fp != "00000000"`) is caught by hypothesis sampling around the closure boundary.
- [ ] AC-8 — `findings_count` field validator rejects `findings_count < len(fingerprints)`. Test: `RedactedSlice(slice={}, findings_count=2, fingerprints=["abcdef12", "12345678", "fedcba98"])` raises `ValidationError` (3 distinct fingerprints but count is 2). `findings_count >= len(fingerprints)` is accepted (count is total findings; fingerprints are deduplicated, so count may exceed unique fingerprints when the same secret appears multiple times).
- [ ] AC-8b — *Boundary cases* — parametrized over `(findings_count, fingerprints)`:
  - **Accepted:** `(0, [])` (zero baseline); `(1, ["abcdef12"])` (equality boundary); `(3, ["abcdef12"])` (same key three times — count > unique fingerprints, the 02-ADR-0010 contract); `(3, ["abcdef12", "12345678", "fedcba98"])` (equality with three distinct fingerprints).
  - **Rejected:** `(0, ["abcdef12"])` (count zero but one fingerprint — strict-less-than failure); `(1, ["abcdef12", "12345678"])` (count one but two fingerprints); `(-1, [])` (negative count, redundant with AC-9 but exercised through this same test path).
  - A regression that misplaces `<=` for `<` (or vice versa) is caught by the equality-boundary case `(1, ["abcdef12"])` which must accept and `(0, ["abcdef12"])` which must reject.
- [ ] AC-9 — `findings_count >= 0` (non-negative). `RedactedSlice(slice={}, findings_count=-1, fingerprints=[])` raises `ValidationError`.

Round-trip identity:

- [ ] AC-10 — `RedactedSlice` round-trips through `model_dump_json` / `model_validate_json` with Pydantic equality. Fixture: a populated instance with a nested `dict`/`list` `slice` containing `<REDACTED:fingerprint=…>` strings; serialize; deserialize; assert `reloaded == original` (Pydantic `__eq__` over the model) and `reloaded.slice == original.slice` (dict equality preserves nested structure).
- [ ] AC-10b — *JSON byte-stability* — `model.model_dump_json() == model.model_dump_json()` for the same instance, across two successive calls (cache-stability invariant; Phase 0 cache keys are content-addressed and depend on this). A regression to a non-deterministic field-ordering or floating-point formatting flip is caught here.
- [ ] AC-10c — *Nested-recursion fixture* — the round-trip fixture in AC-10 carries genuine `JSONValue` recursion: at least three levels of nesting (dict → list → dict), with `<REDACTED:fingerprint=…>` placeholder strings interleaved with non-secret strings (e.g., `"node_version": "20.11.1"`), `None`, integers, and a `list[str]`. The recursive alias must round-trip through Pydantic without losing structure (verified by deep `==` on the loaded `.slice` against the original `dict`).
- [ ] AC-11 — `model_dump()` returns a `dict` with exactly the three field keys; no extras. Asserted via `set(dumped.keys()) == {"slice", "findings_count", "fingerprints"}`.
- [ ] AC-11b — *Field declaration order pinned* — `list(model.model_dump().keys()) == ["slice", "findings_count", "fingerprints"]` AND `list(json.loads(model.model_dump_json()).keys()) == ["slice", "findings_count", "fingerprints"]`. Pydantic preserves declaration order in both Python `dict` and JSON output. Readers of `repo-context.yaml` and downstream `model_dump_json` consumers see the slice payload first, then the count, then the fingerprints. A regression that re-orders the field declarations (e.g., a refactor placing `findings_count` first for "consistency") fails this assertion.

`model_construct` ban (the bypass surface this story closes):

- [ ] AC-12 — `tests/unit/output/test_redacted_slice.py::test_model_construct_banned_by_forbidden_patterns` — **exact subprocess invocation** of the S1-11 script:
  1. Write a synthetic file to `tmp_path/src/codegenie/output/synth.py` containing exactly `RedactedSlice.model_construct(slice={}, findings_count=0, fingerprints=[])\n` (the predicate inspects `Path.parts`, so the path under `tmp_path` must contain `src/codegenie/output/` as parent segments).
  2. Invoke `result = subprocess.run([sys.executable, "scripts/check_forbidden_patterns.py", str(target)], capture_output=True, text=True, cwd=<repo_root>)`.
  3. Assert `result.returncode >= 1` (script exit code is the hit-count, 1..255).
  4. Assert `result.stdout` contains BOTH literal substrings `"02-ADR-0010 §Decision"` AND `"production ADR-0033 §3"` (the `and` contract S1-11 AC-2 hardened — both names appear in every emitted error line). Assert `result.stdout` also contains `"model_construct"` (the rule label).
  5. **A regression that drops `"output"` from `_PHASE2_BANNED_PACKAGES`, weakens the `applies_when` predicate, or loosens the advice contract fails this test.**
- [ ] AC-12b — *Surgical-predicate negative path* — write the same offending content to `tmp_path/src/codegenie/parsers/synth.py` (`"parsers"` is NOT in `_PHASE2_BANNED_PACKAGES`) and run the script with the same invocation. Assert `result.returncode == 0` (clean exit) AND `result.stdout` is empty (no rule emitted). Pins that the `applies_when` predicate is surgical — a regression that broadens it to "every Python file" would emit a hit here and fail this AC.
- [ ] AC-13 — *Direct assertion against the runtime surface* (NOT a `.pre-commit-config.yaml` glob — that is not where the path-scoping lives on master). A test imports the live constants from the lint script:
  ```python
  from scripts.check_forbidden_patterns import _PHASE2_BANNED_PACKAGES, _is_under_phase2_banned_package
  assert "output" in _PHASE2_BANNED_PACKAGES
  assert _is_under_phase2_banned_package(Path("src/codegenie/output/redacted_slice.py")) is True
  assert _is_under_phase2_banned_package(Path("src/codegenie/output/sanitizer.py")) is True
  assert _is_under_phase2_banned_package(Path("src/codegenie/parsers/safe_json.py")) is False
  ```
  A regression that drops `"output"` from the frozenset, or that changes the predicate to a stricter glob (e.g., `output/redacted_slice.py` only), is caught here.
- [ ] AC-14 — No actual `model_construct(...)` *call sites* in `src/codegenie/output/**` (positive assertion; complements the ban-fires test in AC-12). The test **uses the same structural regex** as the lint rule — `re.compile(r"\.model_construct\s*\(|\bmodel_construct\s*=")` — so it matches the call form but NOT the prose mention in this module's own docstring. Implementation: import `_PATTERN_MODEL_CONSTRUCT` from `scripts.check_forbidden_patterns` if exposed, otherwise inline the same regex verbatim with a comment naming the source. Walk every `.py` file under `src/codegenie/output/`; assert zero `pattern.search` hits across the entire body of every file. A regression that loosens the regex in the script is automatically reflected here (single-source-of-truth via the import).

`redact_secrets` is the only public path (runtime sanity):

- [ ] AC-15 — `tests/unit/output/test_redacted_slice.py::test_redact_secrets_returns_redacted_slice` — calls `redact_secrets({}, ProbeId("test"))` (from S3-01); asserts the first tuple element is a `RedactedSlice` instance with `findings_count == 0` and `fingerprints == []`. The structural assertion ("`redact_secrets` is the **only** function that constructs `RedactedSlice` anywhere in `src/`") is deferred to S7-04; this AC verifies the happy-path construction shape.
- [ ] AC-15b — *Cross-story integration with S3-01 (mirrors S3-01 AC-33)* — parametrized test feeding `redact_secrets` slices with the four canonical shapes:
  1. **Zero secrets** — `{"node_version": "20.11.1"}` → expect `findings_count == 0`, `fingerprints == []`.
  2. **One secret** — `{"env": "AKIAIOSFODNN7EXAMPLE"}` → expect `findings_count == 1`, `len(fingerprints) == 1`.
  3. **Three distinct secrets** — slice containing two distinct AWS keys + one GitHub token in three different string-leaf positions → expect `findings_count == 3`, `len(set(fingerprints)) == 3`.
  4. **Same-fingerprint-twice (deduplication invariant)** — same AWS key appearing in two distinct string leaves → expect `findings_count == 2`, `len(fingerprints) == 1` (the 02-ADR-0010 contract: count is total findings, fingerprints are deduplicated, `findings_count >= len(fingerprints)`).
  For each case, **round-trip the returned `RedactedSlice`** through `RedactedSlice.model_validate(returned.model_dump())` and assert all three model invariants hold (8-hex format, `findings_count >= len(fingerprints)`, `findings_count >= 0`). A regression where S3-01 emits uppercase hex, off-by-one counts, or non-deduplicated fingerprints would fail at the `model_validate` boundary — this AC is the structural-defense ladder's runtime witness.
- [ ] AC-16 — A test asserts that a `RedactedSlice` *can* be constructed directly via the public Pydantic constructor (i.e., `RedactedSlice(slice={}, findings_count=0, fingerprints=[])` does not raise) — this is a Python-language-level reality the smart-constructor pattern accepts. The defense is **threefold**: (a) `redact_secrets` is the convention-named factory; (b) `model_construct` is banned by lint (closes the silent-bypass surface); (c) S7-04's `inspect`-based boundary test asserts no other call site constructs a `RedactedSlice` in `src/`. The convention is enforced at three rungs; AC-16 documents the residual Python-language reality.

Phase-0/1 invariants preserved:

- [ ] AC-17 — `OutputSanitizer.scrub` Phase-0 contract-freeze snapshot test (`tests/unit/test_probe_contract.py`) continues to pass — this story adds a sibling module and does not edit `scrub`.
- [ ] AC-18 — `JSONValue` recursive alias from Phase 1 (`src/codegenie/parsers/__init__.py`, S1-02) is the type annotation for `RedactedSlice.slice`. Imported as `from codegenie.parsers import JSONValue` (NOT from `codegenie.types`). Pydantic accepts the recursive alias without `# type: ignore` (S1-02 proved this).

Toolchain:

- [ ] AC-19 — `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files. `mypy --strict` accepts the recursive `JSONValue` field annotation without `# type: ignore`.

## Implementation outline

1. Create `src/codegenie/output/redacted_slice.py`:
   ```python
   """RedactedSlice — smart-constructor at the writer boundary (02-ADR-0010).

   Three-rung structural defense:
       1. Runtime: SecretRedactor replaces cleartext inline (02-ADR-0005).
       2. Type-system: writer accepts only RedactedSlice (this module).
       3. Source-level: redact_secrets is the only construction call site
          (deferred to S7-04, inspect-based boundary test).

   `model_construct` is banned under src/codegenie/output/** by the S1-11
   forbidden-patterns pre-commit. `redact_secrets` (S3-01) is the only
   convention-named factory.
   """
   from __future__ import annotations
   import re
   from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
   from codegenie.parsers import JSONValue  # NOT codegenie.types — JSONValue lives in parsers (verified on master)

   _FP_PATTERN = re.compile(r"^[0-9a-f]{8}$")

   class RedactedSlice(BaseModel):
       model_config = ConfigDict(frozen=True, extra="forbid")

       slice: dict[str, JSONValue]
       findings_count: int = Field(ge=0)
       fingerprints: list[str]

       @field_validator("fingerprints")
       @classmethod
       def _validate_fingerprints(cls, v: list[str]) -> list[str]:
           for fp in v:
               if not _FP_PATTERN.fullmatch(fp):
                   raise ValueError(
                       f"fingerprint must be exactly 8 lowercase hex chars; got {fp!r}"
                   )
           return v

       @model_validator(mode="after")
       def _count_ge_unique_fingerprints(self) -> RedactedSlice:
           if self.findings_count < len(self.fingerprints):
               raise ValueError(
                   f"findings_count ({self.findings_count}) must be >= "
                   f"len(fingerprints) ({len(self.fingerprints)})"
               )
           return self
   ```
2. Write `tests/unit/output/test_redacted_slice.py` covering all 26 ACs (the 19 originals + AC-7b, AC-8b, AC-10b, AC-10c, AC-11b, AC-12b, AC-15b added by the validator). The `model_construct` ban test (AC-12) invokes `subprocess.run([sys.executable, "scripts/check_forbidden_patterns.py", str(target)], capture_output=True, text=True)` against a temp file written to `tmp_path/src/codegenie/output/synth.py` (the predicate inspects `Path.parts`) and asserts: (a) `result.returncode >= 1`; (b) `result.stdout` contains BOTH `"02-ADR-0010 §Decision"` AND `"production ADR-0033 §3"`. AC-12b runs the same invocation against `tmp_path/src/codegenie/parsers/synth.py` (NOT in `_PHASE2_BANNED_PACKAGES`) and asserts a clean exit. The structural-regex test (AC-14) walks `src/codegenie/output/` using `re.compile(r"\.model_construct\s*\(|\bmodel_construct\s*=")` — NOT a bare-word grep (would false-positive on this module's own docstring). Property tests (AC-7b) use `hypothesis`. Cross-story integration (AC-15b) calls `redact_secrets` from S3-01 and round-trips the returned `RedactedSlice` through `model_validate(model_dump())`.
3. Do **not** edit `sanitizer.py` in this story — S3-01 imports `RedactedSlice` from this module.
4. Do **not** edit `writer.py` in this story — S3-03 tightens the signature.

## Out of scope

- The `SecretRedactor` / `redact_secrets` implementation (S3-01) — this story is the model; S3-01 is the function that constructs it.
- `OutputSanitizer.scrub` composition + ordering documentation (S3-03).
- Writer signature tightening from `dict[str, JSONValue]` to `RedactedSlice` (S3-03).
- `secrets_redacted_count` log field at the writer (S3-03).
- `inspect`-based boundary test asserting `redact_secrets` is the **only** call site that constructs a `RedactedSlice` in `src/` (S7-04 — Gap-5 closure). This story is the type-level + lint-level defense; the source-level structural test lands later in the dependency chain.
- `tests/adv/phase02/test_secret_in_source.py` (S6-07) and `tests/adv/phase02/test_no_inmemory_secret_leak.py` (S7-04) — both depend on this story but are out of scope here.
- Any Phase 4 consumer of `RedactedSlice` (RAG ingestion path inheriting the type-system guarantee per 02-ADR-0010 Consequences).

## Notes for the implementer

- **Packaging choice — sibling module vs inline in `sanitizer.py`.** The manifest pins `src/codegenie/output/redacted_slice.py` (sibling module). Rationale: the `forbidden-patterns` glob is broader than one file; `sanitizer.py` already houses the regex pattern table, the entropy threshold, the walker, and the `SecretFinding` model from S3-01; splitting the data class into its own module keeps `sanitizer.py` focused on the redaction logic and the model focused on the typed shape. **Do not inline.** If the executor argues for inlining on simplicity, the answer is the structural-defense framing — the model is the load-bearing type; isolating it makes the dependency graph (S3-01 imports `RedactedSlice` from `redacted_slice.py`; S3-03 writer imports the same) explicit.
- **`findings_count` vs `len(fingerprints)`.** Findings are total replacements (each match is one finding); fingerprints are deduplicated. A slice that contains the same AWS key twice has `findings_count == 2` and `len(fingerprints) == 1`. The model invariant is `findings_count >= len(fingerprints)`. Document in the model docstring.
- **Field order matters for JSON serialization.** Pydantic preserves declaration order in `model_dump`. Declare `slice` first, then `findings_count`, then `fingerprints` — readers of `repo-context.yaml` see the slice payload at the top, the count next, the fingerprints last. A test asserts the dump order (AC-11 covers the keys; an additional implementer-discretion assertion can pin order).
- **`model_construct` ban verification.** The most realistic test invokes the S1-11 pre-commit hook script as a subprocess against a temp file with the offending content. If S1-11 ships the ban as a `ruff` custom rule, the test invokes `ruff check --select <rule-id>` against the temp file. If S1-11 ships a Python AST scanner, the test imports the scanner function and calls it. The story leaves the exact mechanism to S1-11; this story's test asserts the violation is reported, not the implementation of the lint.
- **The `RedactedSlice` constructor remains public.** Python has no truly-private constructor. The smart-constructor pattern is **convention + lint + source-level structural test**, threefold. AC-16 acknowledges this reality: a contributor *can* `RedactedSlice(slice={}, findings_count=0, fingerprints=[])` directly today; the defense is the lint ban on `model_construct` (which is the silent-bypass) plus the S7-04 boundary test (which asserts no other call site does this in `src/`). The third rung — making `RedactedSlice.__init__` literally inaccessible — would require a Pydantic plugin or a separate module-private `_RedactedSlice` class with a public type alias, both higher-cost than the threefold convention defense. Do not over-engineer.
- **No `Annotated` for `fingerprints` type.** Use the `@field_validator` form (shown in implementation outline) — clearer than `Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{8}$")]` for a list-of-validated-strings, and easier to mutation-test (the validator function is patchable for testing).
- **`JSONValue` recursive alias.** Phase 0 ADR-0008 defines `JSONValue` as `bool | int | float | str | None | list["JSONValue"] | dict[str, "JSONValue"]`. Pydantic accepts this with `from __future__ import annotations` enabled (S1-02 already proved this). If a mypy regression appears, the workaround is `RedactedSlice.model_rebuild()` — but Phase 1 has not hit that case; expect it to work cleanly.
- **The `redact_secrets` return type is `tuple[RedactedSlice, list[SecretFinding]]`.** S3-01 owns the function; this story owns the model. The tuple split is the load-bearing 02-ADR-0010 contract: the `RedactedSlice` is what the writer accepts; the `list[SecretFinding]` is the CLI-summary-only audit trail. Do not collapse them; do not put `SecretFinding` on the `RedactedSlice`.
- **LOC budget.** Model + validators ≈ 40 LOC. Tests ≈ 350 LOC (26 ACs after hardening, several Pydantic-error pattern matches, hypothesis property tests, subprocess calls to the lint script, cross-story integration with `redact_secrets`). Total ~390 LOC.

### Design patterns

- **`Fingerprint` newtype — rule-of-three threshold crosses at S3-03.** This story is the **second** consumer of the 8-hex fingerprint string (S3-01 produces; S3-02 validates and carries via `RedactedSlice.fingerprints`). S3-03 will be the third (writer reads `slice_.fingerprints` for the persisted shape per 02-ADR-0010 Tradeoffs row 2). Production ADR-0033 §3 names primitive obsession on cross-module identifiers as a review-blocker. **Do not introduce the newtype in this story** — the format invariant is closed at the validator (this layer), and the origin invariant (only `_fingerprint(...)` produces a `Fingerprint`) straddles three modules — its natural home is an S3-03 follow-up amendment ADR or a Phase-3-entry cross-cutting story that lands concurrently with the third consumer. Surface the opportunity in the S3-03 story prose if you discover the third consumer cleanly; do not retrofit S3-02.
- **Closed product type — `RedactedSlice` has exactly three persisted fields by design.** Adding a fourth (e.g., `pattern_class_counts: dict[Literal["aws","github",...], int]` for telemetry, or `entropy_floor_hits: int` for tuning) is an **ADR amendment to 02-ADR-0010**, not a "we'll just add another field". The Decision section names `slice`, `findings_count`, and `fingerprints` as the contract; widening that set is the same shape as widening `IndexFreshness` (S1-01) or `AdapterConfidence` (S1-03) — closed sum/product types whose extension is gated by review and an ADR. Mirrors S3-01 Validation note #12 (variant-set extension framing).
- **Pure module — `redacted_slice.py` is a functional core.** No I/O, no logging, no filesystem reads, no `os.environ`, no `subprocess`, no `time` (no clock dependency). The validators are pure functions over their arguments. This is the right shape for a domain-model module on the secret-redaction hot path: it is testable without fixtures, monkeypatch-free, and trivially mock-free at every consumer. Future contributors must not add I/O here — if a need arises ("log every fingerprint generation"), the logging belongs in S3-01 (sanitizer) or S3-03 (writer), not in this module. A regression that imports `logging`, `structlog`, `Path`, `os`, or `subprocess` at the top of `redacted_slice.py` is a review-blocker per this Note.
- **Smart constructor at the I/O boundary — pattern fit.** This module is the canonical implementation of the toolkit's "Smart constructor" pattern applied at the **I/O boundary** (not the wire-type boundary; that's production ADR-0033's domain). The pattern's named failure mode ("every caller has to remember to call `.validate()` afterward — they won't") is closed structurally: the writer's signature *only* accepts `RedactedSlice`, and the only convention-named factory is `redact_secrets`. The toolkit's secondary failure mode ("schema before consumer — the model is designed in isolation from the consumer that has to use it") is avoided because the consumer (the writer) already exists in Phase 0 and is the load-bearing type-check site (S3-03 tightens its signature).
