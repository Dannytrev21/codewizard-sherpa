# Story S3-02 — `RedactedSlice` smart constructor private to `redact_secrets`

**Step:** Step 3 — Plant `SecretRedactor` + `RedactedSlice` smart constructor at the writer chokepoint
**Status:** Ready
**Effort:** S
**Depends on:** S3-01 (the redactor body that uses `RedactedSlice` as its return type), S1-11 (`forbidden-patterns` pre-commit extended to cover `model_construct` under `src/codegenie/output/**` — this story's typed-defense story relies on that ban)
**ADRs honored:** 02-ADR-0010 (`RedactedSlice` smart constructor at the writer boundary — the Gap-4 typed-defense ladder), 02-ADR-0005 (no plaintext persistence — the runtime defense this story upgrades to a type-level defense), [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md) (newtype + smart-constructor discipline applied at the I/O boundary, not the wire-type boundary)

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
  - `src/codegenie/types.py` (Phase 0) — `JSONValue` recursive alias used for the `slice` field type.
  - **Forbidden-patterns surface** (lands via S1-11): the Phase-2 `forbidden-patterns` config glob covers `src/codegenie/output/**`. This story's tests invoke that lint check programmatically.
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
- [ ] AC-2 — `RedactedSlice` is exported; importable as `from codegenie.output.redacted_slice import RedactedSlice`.
- [ ] AC-3 — `RedactedSlice` has exactly three public fields (`slice`, `findings_count`, `fingerprints`) and no others. A test introspects via `RedactedSlice.model_fields.keys()`.

Model invariants:

- [ ] AC-4 — `RedactedSlice.model_config["frozen"] is True` and `RedactedSlice.model_config["extra"] == "forbid"`. Asserted directly.
- [ ] AC-5 — Attempting to mutate a constructed `RedactedSlice` (`instance.findings_count = 99`) raises `pydantic.ValidationError` (frozen invariant).
- [ ] AC-6 — Constructing with an unknown field (`RedactedSlice(slice={}, findings_count=0, fingerprints=[], extra_field="x")`) raises `pydantic.ValidationError` with `extra_forbidden` (extra invariant).

Field-level validators:

- [ ] AC-7 — `fingerprints` field validator rejects any string that is not exactly 8 characters, or contains any non-hex char, or has any uppercase char. Tests cover: `len 7` rejected; `len 9` rejected; `"ABCDEF12"` (uppercase) rejected; `"12345678"` accepted; `"abcdef12"` accepted; `""` rejected; non-string element rejected by Pydantic type-checker.
- [ ] AC-8 — `findings_count` field validator rejects `findings_count < len(fingerprints)`. Test: `RedactedSlice(slice={}, findings_count=2, fingerprints=["abcdef12", "12345678", "fedcba98"])` raises `ValidationError` (3 distinct fingerprints but count is 2). `findings_count >= len(fingerprints)` is accepted (count is total findings; fingerprints are deduplicated, so count may exceed unique fingerprints when the same secret appears multiple times).
- [ ] AC-9 — `findings_count >= 0` (non-negative). `RedactedSlice(slice={}, findings_count=-1, fingerprints=[])` raises `ValidationError`.

Round-trip identity:

- [ ] AC-10 — `RedactedSlice` round-trips through `model_dump_json` / `model_validate_json` with Pydantic equality. Fixture: a populated instance with a nested `dict`/`list` `slice` containing `<REDACTED:fingerprint=…>` strings; serialize; deserialize; assert `dumped == reloaded` and `dumped.slice == original.slice`.
- [ ] AC-11 — `model_dump()` returns a `dict` with exactly the three field keys; no extras. Asserted via `set(dumped.keys()) == {"slice", "findings_count", "fingerprints"}`.

`model_construct` ban (the bypass surface this story closes):

- [ ] AC-12 — `tests/unit/output/test_redacted_slice.py::test_model_construct_banned_by_forbidden_patterns` — invokes the S1-11 `forbidden-patterns` lint hook programmatically (e.g., subprocess call to the pre-commit hook script with a temporary file containing `RedactedSlice.model_construct(slice={}, findings_count=0, fingerprints=[])`) and asserts the hook **reports a violation** with a message naming `model_construct` and `src/codegenie/output/`. **A regression that drops the ban from the glob fails this test.**
- [ ] AC-13 — The `forbidden-patterns` glob covers this exact module path. A test inspects the S1-11 config and asserts the glob includes `src/codegenie/output/**/*.py` (or equivalent broader glob).
- [ ] AC-14 — No `model_construct` calls anywhere in `src/codegenie/output/**` (positive assertion, not just the ban-fires test). A test greps the package recursively for `model_construct` and asserts zero matches.

`redact_secrets` is the only public path (runtime sanity):

- [ ] AC-15 — `tests/unit/output/test_redacted_slice.py::test_redact_secrets_returns_redacted_slice` — calls `redact_secrets({}, ProbeId("test"))` (from S3-01); asserts the first tuple element is a `RedactedSlice` instance with `findings_count == 0` and `fingerprints == []`. The structural assertion ("`redact_secrets` is the **only** function that constructs `RedactedSlice` anywhere in `src/`") is deferred to S7-04; this AC verifies the happy-path construction shape.
- [ ] AC-16 — A test asserts that a `RedactedSlice` *can* be constructed directly via the public Pydantic constructor (i.e., `RedactedSlice(slice={}, findings_count=0, fingerprints=[])` does not raise) — this is a Python-language-level reality the smart-constructor pattern accepts. The defense is **threefold**: (a) `redact_secrets` is the convention-named factory; (b) `model_construct` is banned by lint (closes the silent-bypass surface); (c) S7-04's `inspect`-based boundary test asserts no other call site constructs a `RedactedSlice` in `src/`. The convention is enforced at three rungs; AC-16 documents the residual Python-language reality.

Phase-0/1 invariants preserved:

- [ ] AC-17 — `OutputSanitizer.scrub` Phase-0 contract-freeze snapshot test (`tests/unit/test_probe_contract.py`) continues to pass — this story adds a sibling module and does not edit `scrub`.
- [ ] AC-18 — `JSONValue` recursive alias from Phase 0 is the type annotation for `RedactedSlice.slice`. Pydantic accepts the recursive alias without `# type: ignore` (Phase 1 already proved this — `JSONValue` Pydantic compatibility from S1-02).

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
   from codegenie.types import JSONValue

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
2. Write `tests/unit/output/test_redacted_slice.py` covering all 19 ACs. The `model_construct` ban test (AC-12) invokes the S1-11 pre-commit hook script (or imports the lint check function directly if S1-11 exposes one) and asserts a violation is reported on a temp file containing `RedactedSlice.model_construct(...)`. The grep test (AC-14) walks `src/codegenie/output/` and asserts zero matches for `model_construct`.
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
- **LOC budget.** Model + validators ≈ 40 LOC. Tests ≈ 200 LOC (19 ACs, several Pydantic-error pattern matches). Total ~240 LOC.
