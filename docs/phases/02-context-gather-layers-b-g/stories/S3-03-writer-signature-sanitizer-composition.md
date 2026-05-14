# Story S3-03 — Writer signature tightening + sanitizer composition + `secrets_redacted_count` log field

**Step:** Step 3 — Plant `SecretRedactor` + `RedactedSlice` smart constructor at the writer chokepoint
**Status:** Ready
**Effort:** S
**Depends on:** S3-02 (`RedactedSlice` model; this story imports it for the writer signature), S3-01 (`redact_secrets` body that produces the `RedactedSlice`; composition order pins this story's mock-spy test)
**ADRs honored:** 02-ADR-0010 (`RedactedSlice` smart constructor at the writer boundary — type-level "redactor was called"), 02-ADR-0005 (no plaintext persistence — the chokepoint discipline this story finishes), 02-ADR-0008 (no event stream in Phase 2 — `secrets_redacted_count` is one new structured-log field, not an event-stream subscription)

## Context

S3-01 lands `redact_secrets` returning `tuple[RedactedSlice, list[SecretFinding]]`. S3-02 lands the `RedactedSlice` model with `frozen=True, extra="forbid"`, fingerprint format validators, and the `model_construct` ban. **Both prior stories are inert until the writer accepts `RedactedSlice` — without the signature tightening, the runtime defense (02-ADR-0005) holds but the type-level defense (02-ADR-0010) does not.** This story is the closing edge: the writer's public signature changes from `dict[str, JSONValue]` to `RedactedSlice`, the `OutputSanitizer.scrub` pipeline gains an explicit composition order (Phase 0's field-name regex + `JSONValue` tree walk **before** `redact_secrets`) documented in the module docstring and verified by a mock-spy test, and `src/codegenie/logging.py` gains one new structured-log field — `secrets_redacted_count: int` — emitted at the writer chokepoint so a 0-count run is grep-able for auditors.

The composition order matters for a non-obvious reason. Phase 0's field-name regex scrubs keys like `"aws_access_key"`, `"github_token"`, `"password"` (replacing their values with `<REDACTED>`). Phase 0's `JSONValue` tree walk enforces depth caps and rejects oversized payloads. Running `redact_secrets` after both means: (a) the field-name-scrubbed values are already `<REDACTED>` strings and the regex pass on them is cheap and idempotent; (b) the depth cap has already rejected hostile payloads; (c) the slice that reaches `redact_secrets` is guaranteed well-formed `JSONValue`. The reverse order would make `redact_secrets` see unguarded depth and field-name scrubbing would then operate on already-redacted values — same effect but the ordering invariant becomes unobservable. The chosen order is documented and verified, not just chosen.

The mock-spy test (`test_sanitizer_composition.py`) constructs an `OutputSanitizer.scrub` invocation where each of the three composed passes is wrapped with a spy that records its call-time index; the test asserts the recorded sequence is `[field_name_regex, json_value_tree_walk, redact_secrets]`. A reorder regression (e.g., a contributor moving `redact_secrets` to the front for "consistency with field-name scrubbing") flips the recorded order and fails the build.

The writer signature tightening is a contract-surface narrowing. The previous Phase-0 signature accepted `dict[str, JSONValue]`. The new signature accepts only `RedactedSlice`. This is a one-way narrowing: the call site (the sanitizer pipeline) is the only caller; mypy `--strict` catches any other call site that passes a raw `dict`. The `mypy`-only `reveal_type` test (`test_writer_signature.py`) is a `# type: ignore[arg-type]`-free file that calls the writer with a raw `dict` and asserts mypy reports `error: Argument 1 ... has incompatible type "dict[str, Any]"; expected "RedactedSlice"`. The test runs in CI as a `mypy --strict` invocation against the file and asserts a non-zero exit + the expected error message.

The `secrets_redacted_count` log field is the audit grep-ability invariant. Phase 2 final-design Open Q 3 is closed by 02-ADR-0008 ("no event stream") — Phase 2 adds **one** structured-log field at one call site, not an event-bus subscription. The field's value is `len(findings)` from the `redact_secrets` return tuple, captured at the writer call-site (the only place both `RedactedSlice` and the `list[SecretFinding]` are simultaneously in scope). A 0-count run emits `secrets_redacted_count=0` — grep-friendly for the auditor who needs "did this run find any secrets?". The CLI summary line (count + file:line list) is touched in S8-02 (`ConfidenceSection` renderer is the Phase-2 consumer of `IndexFreshness`; the CLI summary is one layer up); this story emits the log field at the writer; the CLI consumes it.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Sequence — secret-redaction flow"` (line ~420) — the composition order: `OutputSanitizer.scrub` → field-name regex → `JSONValue` tree walk → `redact_secrets` → writer.
  - `../phase-arch-design.md §"Component design" #4 SecretRedactor` — the writer-chokepoint discipline, the in-memory findings list policy.
  - `../phase-arch-design.md §"Harness engineering" → "Logging strategy"` (line ~783) — Phase 2 adds **one** log field at the writer: `secrets_redacted_count` (int), so a 0-count run is grep-able. Phase 0 `codegenie/logging.py` is otherwise unchanged.
  - `../phase-arch-design.md §"Gap analysis & improvements" Gap 4` — the writer signature tightening from `dict` to `RedactedSlice`; type-level "redactor was called".
- **Phase 2 ADRs:**
  - `../ADRs/0010-redacted-slice-smart-constructor-at-writer-boundary.md` — Consequences section names "the writer signature change is a contract surface shift requiring a coordinated edit across all callers (one — the sanitizer pipeline)".
  - `../ADRs/0005-secret-findings-no-plaintext-persistence.md` — Consequences section names the composition: "field-name regex (Phase 0) → `JSONValue` tree walk (Phase 0) → `redact_secrets` (Phase 2). One chokepoint."
  - `../ADRs/0008-no-event-stream-in-phase-2.md` — the structured-log-field-only rationale; `secrets_redacted_count` is the one field this story adds.
- **Source design:**
  - `../final-design.md §"Anti-patterns avoided" #5` — `model_construct` bypass (verified by S3-02; this story does not regress it).
- **Existing code (Phase 0 + Phase 1 on master):**
  - `src/codegenie/output/writer.py` — Phase 0; current signature `write_envelope(slice_: dict[str, JSONValue], ...) -> Path`. This story tightens to `write_envelope(slice_: RedactedSlice, ...) -> Path`.
  - `src/codegenie/output/sanitizer.py` — Phase 0 `OutputSanitizer.scrub`; this story documents composition order in module docstring; the body composes `_field_name_regex_pass(slice_) -> _json_value_tree_walk_pass(slice_) -> redact_secrets(slice_, probe_name)` and returns the `RedactedSlice` to the writer.
  - `src/codegenie/logging.py` — Phase 0 `structlog` factory; this story adds `secrets_redacted_count` as a documented field-name constant.
  - **Phase 0 contract-freeze:** `tests/unit/test_probe_contract.py` snapshots `Probe` ABC, `OutputSanitizer.scrub` signature, `run_allowlisted` signature. The `scrub` signature is unchanged (still `scrub(slice_: dict[str, JSONValue], ...) -> ...` at the public interface; the return type may tighten — see implementer note). The **writer** signature tightens; the writer is not part of the contract-freeze snapshot per Phase 0 ADRs (verify against the actual snapshot file at implementation time).
- **Phase 1 shape calibration:**
  - `docs/phases/01-context-gather-layer-a-node/stories/S1-02-safe-json-parser.md §"AC-13/14"` — structured-event emission via `structlog.testing.capture_logs()`; the same pattern applies to the `secrets_redacted_count` field assertion in AC-9 below.

## Goal

Tighten the writer's public signature, finalize and document the `OutputSanitizer.scrub` composition order, and emit the `secrets_redacted_count` log field at the writer chokepoint:

1. `src/codegenie/output/writer.py::write_envelope` accepts **only** `RedactedSlice` (the type system rejects raw `dict[str, JSONValue]` at the writer's public surface; mypy `--strict` catches the violation).
2. `src/codegenie/output/sanitizer.py::OutputSanitizer.scrub` composition order is pinned: Phase 0's field-name regex pass → Phase 0's `JSONValue` tree-walk pass → `redact_secrets` (S3-01). The order is documented in the module docstring and verified by a mock-spy test asserting the spies recorded the three call-times in the expected order.
3. `src/codegenie/logging.py` declares a module-level field-name constant (`SECRETS_REDACTED_COUNT_FIELD: Final[str] = "secrets_redacted_count"`) and the writer's structlog `.info("envelope.written", ..., **{SECRETS_REDACTED_COUNT_FIELD: len(findings)})` call emits the field. A zero-count run emits `secrets_redacted_count=0` — explicitly, not omitted.
4. A `mypy --strict` test file (`tests/unit/output/test_writer_signature.py::test_writer_refuses_raw_dict_at_typecheck`) invokes `mypy --strict` against a snippet that calls `write_envelope(raw_dict, …)` and asserts mypy reports `error: Argument 1 ... has incompatible type "dict[...]"; expected "RedactedSlice"`. The test runs in CI; a regression that broadens the signature back to `dict` makes this test fail.

## Acceptance criteria

Writer signature tightening:

- [ ] AC-1 — `src/codegenie/output/writer.py::write_envelope` signature is `write_envelope(slice_: RedactedSlice, ...) -> Path` (preserving the other parameters from Phase 0 — `output_dir`, `probe_name`, etc.). A `reveal_type` snippet under `tests/unit/output/test_writer_signature.py` asserts `reveal_type(write_envelope.__annotations__["slice_"])` corresponds to `RedactedSlice`.
- [ ] AC-2 — `tests/unit/output/test_writer_signature.py::test_writer_refuses_raw_dict_at_typecheck` — runs `mypy --strict` against a tiny snippet (`from codegenie.output.writer import write_envelope; write_envelope({}, ...)`) and asserts: (a) mypy exit code is non-zero; (b) stdout contains `incompatible type` and `expected "RedactedSlice"`. The mypy subprocess invocation lives in the test; the snippet may be inline or in a fixture file under `tests/unit/output/_fixtures/`.
- [ ] AC-3 — Runtime: passing a raw `dict` to `write_envelope` raises `TypeError` (Pydantic validation error at the writer's first use of `slice_.findings_count` — or earlier if the writer narrows via `isinstance(slice_, RedactedSlice)`). The runtime-rejection layer complements the type-check-time rejection; document the chosen mechanism in the writer's docstring.

Sanitizer composition order:

- [ ] AC-4 — `src/codegenie/output/sanitizer.py` module docstring documents the composition order: "**Composition order:** Phase-0 field-name regex pass → Phase-0 `JSONValue` tree-walk pass → `redact_secrets` (Phase 2, 02-ADR-0005). The order is load-bearing: the field-name regex normalizes known-key values to `<REDACTED>` before `redact_secrets` runs, so the regex pass sees only well-formed `JSONValue` (depth-capped) input. Reordering would not change semantic output but would lose the depth-cap-before-regex invariant. Verified by `test_sanitizer_composition.py`."
- [ ] AC-5 — `tests/unit/output/test_sanitizer_composition.py::test_scrub_invokes_passes_in_order` — wraps each of the three composed passes with a `Mock(wraps=original)` spy; calls `OutputSanitizer.scrub(...)`; asserts the recorded call sequence is `[field_name_regex_pass, json_value_tree_walk_pass, redact_secrets]`. Each spy records `time.monotonic_ns()` at entry; the test asserts strictly increasing timestamps in the expected order.
- [ ] AC-6 — A reordering mutation surfaces. The test includes a parametrized "mutation" variant: a `monkeypatch.setattr(sanitizer, "_PASSES", [redact_secrets, _field_name_regex, _json_value_tree_walk])` reorder; the test asserts the **non-mutated** order is still verified by the spy chain (i.e., the mutation test is the negative form of AC-5 — under the mutation, the assertion fails).
- [ ] AC-7 — `OutputSanitizer.scrub` returns the `RedactedSlice` (the final pass's return shape) and the writer receives it directly. No tuple, no extra adapter. Test: `scrub` return type annotation is `RedactedSlice`; the writer's call-site accepts the `scrub` return directly.

`secrets_redacted_count` log field:

- [ ] AC-8 — `src/codegenie/logging.py` exports `SECRETS_REDACTED_COUNT_FIELD: Final[str] = "secrets_redacted_count"` as a module-level constant. The writer imports the constant by name; no string literal at the call site (regression-resistance — a typo in the field name is caught at import time).
- [ ] AC-9 — `tests/unit/output/test_writer_logs_secrets_redacted_count.py::test_count_field_emitted_on_zero_count` — gathers a fixture repo with no secrets; asserts `structlog.testing.capture_logs()` records one event whose fields contain `secrets_redacted_count=0` at the writer call-site. A 0-count run is **not** silent.
- [ ] AC-10 — `tests/unit/output/test_writer_logs_secrets_redacted_count.py::test_count_field_emitted_on_nonzero_count` — gathers a fixture repo with three seeded secrets (e.g., two AWS keys + one entropy hit); asserts the same event records `secrets_redacted_count=3`.
- [ ] AC-11 — The event name is grep-able (`event="envelope.written"` or similar — the existing Phase-0 writer-completion event name is preserved; this story adds the field, not the event). Test asserts the field appears on the **writer's completion event**, not on a separate redaction-only event.

Sanitizer → writer → log dataflow:

- [ ] AC-12 — The `list[SecretFinding]` returned by `redact_secrets` flows through `OutputSanitizer.scrub` to the writer (or to the writer's caller — implementer chooses; the load-bearing constraint is that the `len(findings)` value is in scope at the writer-log call). Test: a fixture repo with N secrets produces a writer-log event with `secrets_redacted_count=N` AND no `SecretFinding` data appears in any persisted artifact (the writer's only persistence is the `RedactedSlice.slice` payload, not the findings list).

Phase-0 / Phase-1 invariants preserved:

- [ ] AC-13 — Phase-0 `tests/unit/test_probe_contract.py` contract-freeze snapshot continues to pass for `OutputSanitizer.scrub` *public surface name* — the signature **may** tighten (e.g., return type from `dict` to `RedactedSlice`); document any contract-freeze adjustment in the PR description with reference to 02-ADR-0010 Consequences "the writer signature change is a contract surface shift requiring a coordinated edit across all callers (one — the sanitizer pipeline)". The writer signature is **not** part of Phase 0's frozen surface per ADR review; verify against the actual snapshot file at implementation time and, if the snapshot covers `write_envelope`, surface the diff in the PR.
- [ ] AC-14 — No `model_construct` calls anywhere in `src/codegenie/output/**` (positive assertion from S3-02 AC-14 continues to pass after this story's edits).
- [ ] AC-15 — Phase 0 `safe_yaml.load` / `safe_json.load` chokepoints are unaffected (this story does not touch the parsers layer).
- [ ] AC-16 — The Phase-2 `forbidden-patterns` glob (S1-11) covering `src/codegenie/output/**` continues to cover `writer.py`, `sanitizer.py`, and the new `redacted_slice.py` (S3-02). A regression that scopes the glob narrower is caught by S3-02 AC-13.

Toolchain:

- [ ] AC-17 — `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files. `mypy --strict` flags the raw-`dict`-to-writer snippet (AC-2) and clean-passes the `RedactedSlice`-to-writer call sites.

## Implementation outline

1. **Edit `src/codegenie/output/writer.py`:**
   - Change `write_envelope(slice_: dict[str, JSONValue], ...) -> Path` to `write_envelope(slice_: RedactedSlice, ...) -> Path`.
   - Import `RedactedSlice` from `codegenie.output.redacted_slice`.
   - Inside the writer body, read `slice_.slice` (the redacted dict payload) for serialization and `slice_.fingerprints` / `slice_.findings_count` for the persisted shape (per 02-ADR-0010 Tradeoffs — fingerprints are the only secret-related field that may appear in persisted artifacts).
   - Add the `secrets_redacted_count` structured-log emission: `logger.info("envelope.written", path=str(out_path), **{SECRETS_REDACTED_COUNT_FIELD: findings_count})`.
   - Update the writer's docstring to name 02-ADR-0010 (the signature tightening) and 02-ADR-0005 (the persistence-zero-plaintext discipline this signature enforces).
2. **Edit `src/codegenie/output/sanitizer.py`:**
   - Extend the module docstring with the composition-order paragraph (AC-4).
   - Refactor `OutputSanitizer.scrub` so the three passes are explicitly named in a module-level `_PASSES` list (or equivalent factored callable chain) that the mock-spy test can wrap. Example:
     ```python
     # passes are module-level for monkeypatch + mock-spy reach
     def _field_name_regex_pass(slice_: dict[str, JSONValue]) -> dict[str, JSONValue]: ...
     def _json_value_tree_walk_pass(slice_: dict[str, JSONValue]) -> dict[str, JSONValue]: ...
     # redact_secrets is the third pass (S3-01)

     class OutputSanitizer:
         def scrub(self, slice_: dict[str, JSONValue], probe_name: ProbeId) -> RedactedSlice:
             after_regex = _field_name_regex_pass(slice_)
             after_walk = _json_value_tree_walk_pass(after_regex)
             redacted, findings = redact_secrets(after_walk, probe_name)
             # findings flows up via a side-channel argument or return tuple — see implementer note
             return redacted
     ```
   - Decide the findings-list hand-off mechanism. Two clean options:
     - (a) `scrub` returns `tuple[RedactedSlice, list[SecretFinding]]` (mirrors `redact_secrets`); writer call site destructures.
     - (b) `scrub` returns `RedactedSlice`; the caller (`Coordinator` or writer call-site) calls `redact_secrets` *separately* — but this violates the single-chokepoint discipline (`phase-arch-design.md §"Three load-bearing properties"` #2).
     - **Pick (a).** Mirror `redact_secrets`'s tuple. Document in the docstring. The writer accepts both: `def write_envelope(slice_: RedactedSlice, findings_count: int, ...)` — the count is a separate parameter, not threaded through the model (per 02-ADR-0010's "list[SecretFinding] returned separately as tuple"). This keeps the model carrying *only* what may persist (fingerprints) and the count flowing through the explicit parameter chain.
3. **Edit `src/codegenie/logging.py`:**
   - Add `SECRETS_REDACTED_COUNT_FIELD: Final[str] = "secrets_redacted_count"`.
   - Export from the module's `__all__`.
   - Update the module docstring to reference 02-ADR-0008 (the single-log-field discipline).
4. **Write `tests/unit/output/test_writer_signature.py`** (AC-1, AC-2, AC-3):
   - `test_writer_refuses_raw_dict_at_typecheck`: subprocess `mypy --strict` against a snippet; assert exit ≠ 0 and stdout contains the expected error.
   - `test_writer_runtime_rejects_raw_dict`: pass a raw `dict` to `write_envelope` at runtime; assert `TypeError` (or whatever the chosen runtime-rejection mechanism produces).
5. **Write `tests/unit/output/test_sanitizer_composition.py`** (AC-4, AC-5, AC-6, AC-7):
   - `test_scrub_invokes_passes_in_order`: monkeypatch each `_PASSES` entry with `Mock(wraps=original)`; call `scrub`; assert call sequence and timestamps.
   - `test_reorder_mutation_fails_assertion`: the negative form — reorder `_PASSES`, run, assert the spy sequence is **not** the expected sequence.
6. **Write `tests/unit/output/test_writer_logs_secrets_redacted_count.py`** (AC-8, AC-9, AC-10, AC-11):
   - `test_count_field_emitted_on_zero_count`: end-to-end gather with no secrets; `capture_logs()`; assert event + field.
   - `test_count_field_emitted_on_nonzero_count`: end-to-end gather with seeded secrets (via S3-01's redactor under the hood); assert `secrets_redacted_count=3`.
   - `test_field_emitted_on_writer_completion_event`: assert the field appears on `event="envelope.written"`, not a separate event.
7. **Do NOT** edit `redact_secrets` itself (S3-01 owns it). **Do NOT** edit `RedactedSlice` (S3-02 owns it).

## Out of scope

- The `SecretRedactor` / `redact_secrets` body (S3-01).
- The `RedactedSlice` Pydantic model (S3-02).
- The CLI summary line (`secrets_redacted_count: <N>` + file:line list) at gather end — this story emits the log field; the CLI summary path consumes it; the summary line itself is touched in S8-02.
- `tests/adv/phase02/test_secret_in_source.py` (S6-07 — load-bearing adversarial; depends on this story landing the writer chokepoint).
- `tests/adv/phase02/test_no_inmemory_secret_leak.py` (S7-04 — `inspect`-based boundary test; asserts no `dict` reaches the writer call site in `src/`).
- Phase 4 RAG ingestion path inheriting the `RedactedSlice` type guarantee (02-ADR-0010 Consequences) — Phase 4 design concern.
- Any contract-freeze snapshot file edits beyond what is named in AC-13 (if `tests/unit/test_probe_contract.py` snapshots `write_envelope`, the diff is surfaced in the PR; if it does not, no snapshot edit is needed).

## Notes for the implementer

- **Where does the `findings_count` integer flow?** Option (a) in the implementation outline picks "explicit parameter chain": `scrub` returns `tuple[RedactedSlice, list[SecretFinding]]`; the call site destructures; `write_envelope` accepts `(slice_: RedactedSlice, findings_count: int, ...)`. This keeps `RedactedSlice` carrying only persistence-safe data (fingerprints) and the count flowing as a plain int the writer logs. **Do not** put `findings_count` on `RedactedSlice` itself for the persisted-field reason — though `RedactedSlice.findings_count` exists per S3-02 AC-3, it is the *deduplicated-or-total* count (≥ `len(fingerprints)`); the writer log emits the same value (`slice_.findings_count`) or destructures the list length (`len(findings)`). They are equal by construction (S3-01 AC-20). Use `slice_.findings_count` at the writer to keep the data path tight and import-free.
- **Mock-spy ordering test technique.** `unittest.mock.Mock(wraps=original)` preserves behavior while recording calls. `mock_obj.call_args_list` is the captured sequence; `time.monotonic_ns()` per spy at entry pins ordering. Alternative: a single shared `record: list[str]` that each spy appends its name to before calling through — simpler, equally robust.
- **The `mypy --strict` subprocess test.** Subprocess invocation of `mypy --strict <path>` is the canonical mechanism; assert `result.returncode != 0` and the expected error substring in `result.stdout`. The snippet file can be `tests/unit/output/_fixtures/raw_dict_to_writer.py` (containing the bad call) so the test is `mypy --strict tests/unit/output/_fixtures/raw_dict_to_writer.py` — clean and inspectable.
- **The `reveal_type` mechanism.** mypy honors `reveal_type(...)` calls in the source by printing the type at check time. AC-1 uses `write_envelope.__annotations__["slice_"]` (runtime introspection) — cheaper and runtime-asserted; `reveal_type` would require parsing mypy stdout, which the AC-2 subprocess test already does. Pick the runtime form for AC-1.
- **Runtime rejection of raw `dict`.** Python's type hints are not enforced at runtime. The simplest runtime defense is: the writer reads `slice_.findings_count` early in its body — passing a raw `dict` then raises `AttributeError` (`dict` has no `findings_count`). The writer can also explicitly `if not isinstance(slice_, RedactedSlice): raise TypeError(...)` for a friendlier error. Pick the explicit `isinstance` check for clarity. Document in the docstring.
- **`SECRETS_REDACTED_COUNT_FIELD` placement in `logging.py`.** The Phase 0 module is the canonical home for cross-module log-field constants (Phase 1 stories already follow this pattern — see S1-02's `probe.parser.cap_exceeded` event-name constant pattern, though that one lives in `safe_json.py`). For a writer-emitted field that may be consumed across stages (the CLI summary, the audit anchor, future Phase 4 RAG ingest), the central `logging.py` placement is correct. Single source of truth; one typo-resistant constant.
- **The "0-count is grep-able" property.** Auditors run `grep secrets_redacted_count: <log_path>` to confirm a clean run. If `secrets_redacted_count=0` is silently omitted (the field only appears when nonzero), the auditor cannot distinguish "clean run" from "log corruption" or "missing emission". Always emit the field; AC-9 pins this.
- **The writer-completion event name.** Phase 0 already emits `event="envelope.written"` (or similar) on writer success. Do **not** add a new redaction-only event — 02-ADR-0008's "no event stream" applies. The new field rides on the existing event. Inspect the Phase 0 writer for the actual event name at implementation time; the test asserts the field appears on that event, whatever its current name.
- **Coordinated edit across callers.** 02-ADR-0010 Consequences names "the writer signature change is a contract surface shift requiring a coordinated edit across all callers (one — the sanitizer pipeline)". Verify by `grep -rn "write_envelope(" src/` before and after the edit. If a second call site appears (e.g., a test fixture or a debug-write path), it is either (a) a test that must be updated to construct via `redact_secrets` or (b) a bypass that defeats the chokepoint — flag in the PR description.
- **Forbidden-patterns reach.** S1-11 covers `src/codegenie/output/**`. The new `writer.py` edits are inside that glob; this story does not introduce new banned patterns. S3-02 AC-14 (grep for `model_construct` in `src/codegenie/output/`) continues to pass.
- **LOC budget.** Writer edit ≈ 20 LOC (signature, import, runtime-isinstance, log-field emission). Sanitizer edit ≈ 30 LOC (docstring, `_PASSES` factoring, composition body). Logging edit ≈ 5 LOC (one constant + `__all__`). Tests ≈ 250 LOC across three new files. Total ~305 LOC.
- **The structural ladder, completed.** This story closes the second rung of 02-ADR-0005's three-rung structural defense: (1) runtime — `redact_secrets` replaces cleartext (S3-01); (2) type-system — writer accepts only `RedactedSlice` (this story, after S3-02); (3) source-level — `redact_secrets` is the only call site (S7-04). When this PR lands, "redactor was called" is type-checkable, not convention-enforced. Document the ladder closure in the PR description.
