# Story S8-01 — `ConfidenceSection` renderer with exhaustive `match` + `assert_never` enforcement

**Step:** Step 8 — Confidence section renderer + CI ratchet + advisory benches + Phase-3 handoff
**Status:** HARDENED
**Effort:** M
**Depends on:** S7-04 (`tests/adv/phase02/test_phase3_handoff_smoke.py` lands skipped + the in-memory secret-leak boundary test), S7-05 (portfolio integration sweep wired)
**ADRs honored:** 02-ADR-0006 (`IndexFreshness` sum-type location at `codegenie.indices.freshness`); 02-ADR-0009 (no `pytest-xdist` — serial); 02-ADR-0005 (no plaintext secret persistence — extends to renderer-constructed strings); 02-ADR-0010 (RedactedSlice smart constructor at writer boundary — renderer reads `RedactedSlice.slice` only); production ADR-0033 §3–4 (make illegal states unrepresentable; `assert_never` is the type-level enforcement)

## Validation notes

Validated: 2026-05-18
Verdict: HARDENED
Findings addressed: 23 total — 4 blocks, 14 hardens, 5 nits (deferred to Notes-for-implementer)

Changes applied:
- **AC-1** narrowed — `ConfidenceSectionRenderer` class dropped; only `render_confidence_section` exported. (Design-Patterns DP-3 + Test-Quality TQ-11 + Coverage COV-10 — premature class wrapper with no state, no precedent in `output/writer.py` for stateless renderer classes. Rule 2 / Rule 11.)
- **AC-2** strengthened — exhaustiveness over the *nested* `IndexFreshness | StaleReason` shape (two `assert_never` sites) to match the established Phase-2 idiom in `src/codegenie/probes/layer_b/index_health.py:239-279` (`_derive_confidence`, `_last_indexed_at`). Per-row negative-space assertion added — each row contains its own variant's marker AND no other variant's marker. (Design-Patterns DP-1 + Test-Quality TQ-1; Rule 11.)
- **AC-3** rewritten — repo-wide `[tool.mypy] warn_unreachable = true` (set in Phase 0 S1-02, verified by S1-11's `tests/unit/test_mypy_warn_unreachable_fixture.py`) is the load-bearing setting; this story inherits it. The manual stderr-snapshot ritual is retained as a Step-8 PR-review checklist item BUT exercised at BOTH nesting levels (outer `Fresh`/`Stale` removal AND inner `StaleReason` removal — DP-7). (Consistency CON-1 + Test-Quality TQ-5 + Design-Patterns DP-7. The "S1-11 per-module override fires once code lands here" narrative was factually wrong — `warn_unreachable` is global, not per-module.)
- **AC-4** strengthened — deterministic order is now byte-pinned via `re.findall` against the FULL emitted row sequence (not just position-comparisons on three ASCII-lowercase names). Three discriminating fixtures added covering ASCII-lex-vs-casefold, numeric-vs-lexicographic, and full-sequence order. Naive-datetime, long `IndexerError.message`, and `last_indexed` non-SHA cases pinned. (Test-Quality TQ-2 + Coverage COV-6.)
- **AC-5** REWRITTEN (block) — `IndexerError("slice_malformed:" + str(e))` removed. The renderer emits a sentinel `IndexerError(message="slice_malformed")` (stable identifier matching `freshness.py:73-80`'s contract) and routes the `ValidationError` details to a structlog event `report.confidence_section.slice_malformed` with structured fields (`index_name`, `error_count`, `first_loc`). The Markdown row reads `- [STALE] <name> · indexer_error · slice_malformed`. **Negative-space test added:** an envelope whose malformed slice contains a secret-shaped value (e.g., `AKIA…`) must NOT produce that value in the rendered row. (Consistency CON-3 + Design-Patterns DP-2 + Coverage COV-3 — protects 02-ADR-0005 / 02-ADR-0010 plaintext-secret invariant; preserves `IndexerError.message` smart-constructor contract.)
- **AC-6** rewritten — writer integration is **already wired** in `src/codegenie/output/writer.py:138-156, 233-239` (`_publish_context_report(envelope.slice, output_dir)`). This story's AC-6 now verifies the existing call site exercises the renderer that lands here. The renderer's input type is pinned: `Mapping[str, Any]` (the post-redaction `RedactedSlice.slice`, NOT a raw envelope dict) — preserves 02-ADR-0010's chokepoint. Byte-identical-across-runs requires producer time-source freezing (sub-bullet added). Row-count assertion strengthened to `len(rows) == len(envelope[..][index_health])` — kills the empty-renderer mutant. (Coverage COV-2 + Consistency CON-2 + CON-4 + Test-Quality TQ-6.)
- **AC-7** narrative corrected — `mypy --strict src/codegenie/report/` passes; `warn_unreachable` is repo-wide, not per-module. (Consistency CON-1.)
- **AC-8** strengthened — denylist extended to `{codegenie.probes, codegenie.coordinator, codegenie.cache, codegenie.adapters, codegenie.tccm}`; `subprocess.run(..., check=False)` so import failure is visible (TQ-4). (Coverage COV-7 + Test-Quality TQ-4.)
- **AC-9** ADDED — empty-envelope and zero-registered-indices paths emit `## Confidence\n\n_No index sources registered._\n` (placeholder text); test pins the exact body. Closes the lazy-impl "always emit empty heading" gap. (Coverage COV-4 + Test-Quality TQ-6.)
- **AC-10** ADDED — duplicate `index_name` upstream raises `ValueError`; writer catches via the existing `try/except Exception` in `_publish_context_report` (writer.py:148-156) and logs `report.confidence_section.render_failed` without aborting `repo-context.yaml`. Fail-loud per Rule 12. (Coverage COV-5.)
- **AC-11** ADDED — renderer is pure: AST-walking test asserts no `open`, `print`, `Path.write_text`, no `import logging`, no `import structlog`, no `import os`, no `import pathlib` from the renderer module. Closes the silent-side-effect drift gap. (Design-Patterns DP-8 + CLAUDE.md "Functional core / imperative shell".)
- **AC-12** ADDED — secrets in malformed-slice values do NOT leak. Negative-test: a slice containing `IndexerError(message="AKIA1234567890ABCDEF")` (test-fixture-shaped) renders the value verbatim (trusts the slice, AC-4 contract), BUT a malformed slice whose offending value is AWS-key-shaped renders ONLY `slice_malformed` — the offending input value never reaches the row. (Consistency CON-3 + Test-Quality TQ-10.)
- **AC-13** ADDED — property-based metamorphic test (Hypothesis): adding/removing an index never alters the rendering of the other indices; each row's marker set isolates its variant. (Test-Quality TQ-7.)
- **Notes-for-implementer** extended — registry-of-formatters anti-pattern documented (DP-6); writer-vs-CLI wiring rationale pinned to writer.py (DP-5); newtype erasure at slice boundary noted (DP-9).

Full audit log: `_validation/S8-01-confidence-section-renderer.md`.

## Context

`IndexFreshness` is the typed answer to commitment §2.3 — "silent staleness is the worst failure mode of the entire system" (`CLAUDE.md`, `production/design.md` §2.3). Phase 2's design ships **one consumer** of that sum type so the variant set is exercised from day 1 and a missed `case` becomes a build error rather than a runtime surprise: the **Confidence section of `CONTEXT_REPORT.md`**, rendered by `src/codegenie/report/confidence_section.py`. That module is intentionally outside `probes/` so a CONTEXT_REPORT render does not pull in the probe registry; Phase 3 adapters and Phase 8 Bundle Builder will import it without circular-dependency risk (phase-arch-design.md §"Component design" #2 §"Why not co-located").

The renderer is what makes the discipline *real*: `mypy warn_unreachable = true` is set repo-wide in `pyproject.toml [tool.mypy]` (Phase 0 S1-02; verified by S1-11's `tests/unit/test_mypy_warn_unreachable_fixture.py`). A removed `case` arm against any `IndexFreshness` variant must produce a CI build error — verified at BOTH nesting levels (outer `Fresh | Stale` and inner `StaleReason`) in the Step 8 PR-review checklist (Implementation risk #4). The S1-11 automated mypy fixture test is the load-bearing evidence; the ritual in this story is the human-readable confirmation.

This story is the type-level enforcement of B2's load-bearing role. Without it, every other guardrail in this phase (the `stale-scip` adversarial, the freshness registry, repo-wide mypy `warn_unreachable`) is decoration around a sum type nobody pattern-matches on.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #2` (`IndexFreshness` sum type — variant set, `__all__`, smart constructor, "why not co-located").
  - `../phase-arch-design.md §"Logical view"` (class diagram: `ConfidenceSectionRenderer.render(slices) -> str` with `<<Phase 2 — only consumer of IndexFreshness in Phase 2>>` annotation; `ConfidenceSectionRenderer --> IndexFreshness : pattern-matches`).
  - `../phase-arch-design.md §"Process view"` — sequence step 7: *"`CR-->>WR: CONTEXT_REPORT.md`"* (renderer runs after writer's atomic `os.replace`).
  - `../phase-arch-design.md §"Reading guide"` — "New types (`IndexFreshness`, ...) live in their own packages and are imported, not inherited from kernel ABCs."
- **Phase ADRs:**
  - `../ADRs/0006-index-freshness-sum-type-location.md` — names `codegenie.indices.freshness` as the module; consumer is `codegenie.report.confidence_section`.
- **Production ADRs:**
  - `../../../production/adrs/0033-domain-modeling-discipline.md` §3 ("make illegal states unrepresentable") + §4 (sum types + `assert_never`).
- **Source design:**
  - `../final-design.md §"Phase-2-internal consumer"` (lines ~207) — explicitly names this renderer as the closer for shared blind spot #1 (sum-type-without-a-consumer).
  - `../final-design.md §"Synthesis ledger"` row "mypy --warn-unreachable rollout" — per-module config on `codegenie.{indices, probes/index_health.py, report, adapters, tccm}/**` is the resolved decision.
- **Existing code (Phase 2 contract from earlier steps — DO NOT WEAKEN):**
  - `src/codegenie/indices/freshness.py` (S1-01) — `Fresh | Stale(reason: StaleReason)`; `StaleReason = CommitsBehind | DigestMismatch | CoverageGap | IndexerError`. The `__all__` and `Literal[...]` `kind` discriminators are the only thing the renderer pattern-matches against. `IndexerError.message` is documented as "a stable identifier — not a free-form human string" (lines 73-80); AC-5 must preserve that.
  - `src/codegenie/probes/layer_b/index_health.py` (S4-01) — emits one `IndexFreshness` per index source serialized via `model_dump(mode="json")` (line ~370). The renderer receives a JSON dict at `envelope.slice["probes"]["index_health"]["index_health"][<index_name>]["freshness"]` and re-validates via `TypeAdapter(IndexFreshness).validate_python(...)`. **Established two-level `match` precedent:** `_derive_confidence` (lines 239-279) and `_last_indexed_at` use outer `match value: case Fresh()/case Stale(reason=r):` then inner `match r:` over `StaleReason`; the renderer MUST mirror this shape per Rule 11.
  - `src/codegenie/output/writer.py` (Phase 0 + S3-03; renderer integration at lines 138-156 + 233-239) — `_publish_context_report(envelope.slice, output_dir)` is the call site; it invokes `codegenie.report.render_confidence_section` on the post-redaction `RedactedSlice.slice` (a `dict`) and atomically publishes `CONTEXT_REPORT.md` via the same `.tmp → fsync → os.replace` discipline as `repo-context.yaml`. The renderer's input type is therefore `Mapping[str, Any]`, NOT `RedactedSlice`. The writer's existing `try/except Exception` around the call (line 152) logs `report.confidence_section.render_failed` and continues — `repo-context.yaml` is unaffected if the renderer raises.
  - `pyproject.toml` (Phase 0 S1-02 + S1-11 verification) — `[tool.mypy] warn_unreachable = true` is set **repo-wide** at the top-level `[tool.mypy]` block (line 172), NOT in a `[[tool.mypy.overrides]]` block. The renderer module is therefore covered by inheritance. S1-11's `tests/unit/test_mypy_warn_unreachable_fixture.py` automates the "incomplete `match` → mypy fails" invariant against an `IndexFreshness` fixture; this story does NOT duplicate that test.
  - `tests/unit/test_mypy_warn_unreachable_fixture.py` (S1-11 AC-5) — already automates the AC-3 invariant against an incomplete `match: IndexFreshness`. AC-3's manual ritual is documentation of human-readable confirmation for the PR-review checklist, NOT a duplicate automation.

## Goal

Implement `src/codegenie/report/__init__.py` and `src/codegenie/report/confidence_section.py` as the **only Phase-2 consumer** of `IndexFreshness`. The renderer pattern-matches on the typed sum using the established Phase-2 nested-`match` idiom (mirror `_derive_confidence` / `_last_indexed_at` in `probes/layer_b/index_health.py:239-279`): an outer `match value:` over `Fresh | Stale(reason)` with `case _: assert_never(value)`, and an inner `match reason:` over `CommitsBehind | DigestMismatch | CoverageGap | IndexerError` with `case _: assert_never(reason)`. The renderer accepts `Mapping[str, Any]` (the post-redaction `RedactedSlice.slice` produced by the writer's chokepoint per 02-ADR-0010), re-validates the per-index `freshness` JSON dicts via `pydantic.TypeAdapter(IndexFreshness).validate_python(...)`, and produces a `CONTEXT_REPORT.md` string with a "Confidence" section whose row order is deterministic (ASCII-lex sorted by `index_name`), whose `Fresh` rows render as `- [OK] <index_name> · indexed_at=<iso8601-UTC-Z>`, and whose `Stale` rows render with a per-variant suffix. The writer is **already wired** (writer.py:138-156, 233-239) to call this renderer; this story implements the renderer module the writer imports.

Critically: with `[tool.mypy] warn_unreachable = true` set repo-wide (Phase 0 S1-02; pyproject.toml line 172), **removing any `case` arm at either nesting level produces a `[unreachable]` build error** at the corresponding `assert_never(...)` line in CI. This is the type-level enforcement of B2's load-bearing role. The Step 8 PR-review checklist requires deliberately removing a `case` arm at BOTH the outer level (one `case` from `Fresh | Stale`) AND the inner level (one `case` from `StaleReason`) and confirming CI fails each time (Implementation risk #4).

## Acceptance criteria

- [ ] **AC-1 (module surface).** `src/codegenie/report/__init__.py` exports `render_confidence_section` only (closed `__all__ = ["render_confidence_section"]`). `src/codegenie/report/confidence_section.py` contains the function. No `ConfidenceSectionRenderer` class — Rule 2 (no abstractions for single-use code); no precedent in `output/` for a stateless renderer class. **Forbidden imports** (asserted by AC-8): `codegenie.probes.*`, `codegenie.coordinator.*`, `codegenie.cache.*`, `codegenie.adapters.*`, `codegenie.tccm.*`. Permitted Phase-2 dependencies: `codegenie.indices.freshness`, `pydantic`, and stdlib (`typing.assert_never`, `datetime`, `re`). (validator: narrowed — class wrapper dropped per DP-3/TQ-11/COV-10; denylist tightened per COV-7.)

- [ ] **AC-2 (exhaustive nested `match` over `IndexFreshness`).** `render_confidence_section` invokes a two-level `match` mirroring `probes/layer_b/index_health.py:239-279`: outer `match value:` over `Fresh` and `Stale(reason=r)` with `case _: assert_never(value)`; inner `match r:` over `CommitsBehind`, `DigestMismatch`, `CoverageGap`, `IndexerError` with `case _: assert_never(r)`. **Both** `assert_never` arms are required. Tests assert: (a) every variant's marker appears on the row keyed by *its own* index name and not on any other row (per-row negative-space — kills the "single-row-with-all-markers" mutant); (b) row count equals the input dict size for a 5-variant fixture (`out.count("- [OK]") == 1` AND `out.count("- [STALE]") == 4`). (validator: hardened — original ACE-2 passed for a degenerate impl emitting all five markers in one row; DP-1 mandates the established nested idiom.)

- [ ] **AC-3 (mypy `warn_unreachable` enforces exhaustiveness at both levels).** Repo-wide `[tool.mypy] warn_unreachable = true` (pyproject.toml L172) covers `codegenie.report.*` by inheritance — there is NO per-module override; the global setting is the load-bearing one (verified by S1-11's `tests/unit/test_mypy_warn_unreachable_fixture.py`). The automated invariant is already covered by S1-11; this story adds a **two-pass** human-readable PR-review ritual:
  - (a) Delete one `case` arm from the outer `match value:` (e.g., `case Fresh(indexed_at=ts):`). Run `mypy src/codegenie/report/`. Confirm non-zero exit with `[unreachable]` at `assert_never(value)`. Capture stderr to `_attempts/S8-01.md`. Revert.
  - (b) Delete one `case` arm from the inner `match r:` (e.g., `case CommitsBehind(...):`). Run `mypy src/codegenie/report/`. Confirm non-zero exit with `[unreachable]` at `assert_never(reason)`. Capture stderr to `_attempts/S8-01.md`. Revert.
  (validator: rewritten — "per-module override" narrative was factually wrong per CON-1; nested-match ritual added per DP-7.)

- [ ] **AC-4 (deterministic row order + per-variant format, byte-pinned).** Rows are ASCII-lex sorted by `index_name`. Format pins (each test asserts exact substring match on a single line):
  - `Fresh(indexed_at)` → `- [OK] <index_name> · indexed_at=<iso8601-UTC-Z>`. Naive (timezone-unaware) datetime: renderer emits `slice_malformed` row instead (AC-5 path) — preserves invariant that the `Z` suffix is present iff the timestamp is UTC-aware.
  - `Stale(CommitsBehind(n, last_indexed))` → `- [STALE] <index_name> · commits_behind=<n> · last_indexed=<first-8-chars>` (`last_indexed[:8]` — rendered verbatim, no SHA validation; arbitrary strings pass through; test asserts a non-SHA string is rendered as `last_indexed[:8]` unmodified).
  - `Stale(DigestMismatch(expected, actual))` → `- [STALE] <index_name> · digest_mismatch · expected=<first-8-chars>… · actual=<first-8-chars>…`.
  - `Stale(CoverageGap(files_indexed, files_in_repo))` → `- [STALE] <index_name> · coverage_gap · indexed=<files_indexed>/<files_in_repo>`.
  - `Stale(IndexerError(message))` → `- [STALE] <index_name> · indexer_error · <message>` where `message` longer than 200 chars is truncated to `message[:200] + "…"`.
  Determinism tests: (a) full row sequence pinned via `re.findall(r"^- \[(?:OK|STALE)\] (\S+) ", out, re.M) == sorted(input.keys())` — catches reverse-sort, casefold-sort, hash-sort mutants; (b) ASCII-lex fixture `{"B": ..., "a": ..., "C": ...}` proves code-point order, not case-insensitive; (c) `{"idx10": ..., "idx2": ..., "idx1": ...}` proves lex, not natural-sort. **Output endings:** `out.endswith("\n")` and `"\n\n\n" not in out`. Renderer does NOT re-sanitize (AC-12 verifies). (validator: hardened — original position-comparison test passed under three lowercase ASCII fixtures by coincidence; TQ-2 + COV-6.)

- [ ] **AC-5 (defense-in-depth on malformed slice — sentinel only, no error-detail leak into typed slice).** If a per-index slice's `freshness` field fails `TypeAdapter(IndexFreshness).validate_python(...)`, the renderer **constructs `IndexerError(message="slice_malformed")`** (a stable identifier per `freshness.py:73-80`; **NOT** `"slice_malformed:" + str(e)`), routes it through the standard `Stale(reason=IndexerError(...))` arm, and emits the row `- [STALE] <index_name> · indexer_error · slice_malformed`. The structured error detail (error_count, first_loc) is emitted to a structlog event `report.confidence_section.slice_malformed` with fields `index_name`, `error_count`, `first_loc` — **never** into the Markdown row, **never** as part of the typed `IndexerError.message`. (validator: REWRITTEN block-severity — original `str(e)` synthesis violated `IndexerError.message` smart-constructor contract per DP-2/COV-3 and risked leaking unredacted offending-value content past 02-ADR-0005/02-ADR-0010 chokepoints per CON-3.)

- [ ] **AC-6 (writer integration verified; renderer takes `Mapping[str, Any]`, not RedactedSlice).** The writer integration is already in place at `src/codegenie/output/writer.py:138-156, 233-239`: `_publish_context_report(envelope.slice, output_dir)` invokes `codegenie.report.render_confidence_section` on the post-redaction dict and atomically publishes `CONTEXT_REPORT.md`. **Renderer signature**: `def render_confidence_section(envelope_slice: Mapping[str, Any]) -> str`. It locates per-index freshness JSON dicts at `envelope_slice["probes"]["index_health"]["index_health"][<index_name>]["freshness"]` and re-validates each via `TypeAdapter(IndexFreshness).validate_python(...)`. Integration test `tests/integration/test_writer_renders_confidence_section.py` asserts:
  - (a) `CONTEXT_REPORT.md` exists post-gather and `output_dir / "CONTEXT_REPORT.md.tmp"` does NOT exist (atomic publish).
  - (b) `CONTEXT_REPORT.md` starts with the exact line `## Confidence`.
  - (c) **Row count equals** `len(envelope_slice["probes"]["index_health"]["index_health"])` AND every input index_name appears in exactly one row. (kills the empty-renderer mutant.)
  - (d) Two back-to-back runs against the same fixture produce byte-identical `CONTEXT_REPORT.md`. **Precondition:** the producer's `Fresh.indexed_at` source is deterministic for the fixture (either the fixture pre-seeds a stale-only state with no `Fresh` rows, or the integration test patches `IndexHealthProbe`'s time source via `monkeypatch`). If determinism cannot be achieved, the byte-identical sub-assertion is replaced with a regex-mask comparison on `indexed_at=\d{4}-\d{2}-\d{2}T...`.
  (validator: rewritten — original AC ambiguous on whether `render_confidence_section(merged_envelope)` took a dict or `RedactedSlice`; writer is already wired; row-count and time-source determinism pinned per COV-2/CON-2/CON-4/TQ-6.)

- [ ] **AC-7 (mypy + ruff green).** `mypy --strict src/codegenie/report/` passes; repo-wide `warn_unreachable = true` is honored (no `[[tool.mypy.overrides]]` block silences it for this module). `ruff check src/codegenie/report/ tests/unit/report/` and `ruff format --check` both green. (validator: narrative corrected — `warn_unreachable` is repo-wide, not per-module.)

- [ ] **AC-8 (renderer-import side-effect denylist — subprocess clean import).** Importing `codegenie.report.confidence_section` in a fresh Python subprocess (`subprocess.run([sys.executable, "-c", script], check=False)`) loads NO module under any of `{codegenie.probes, codegenie.coordinator, codegenie.cache, codegenie.adapters, codegenie.tccm, codegenie.output.sanitizer}`. The subprocess test asserts `proc.returncode == 0` first (so ImportError surfaces as a meaningful failure, not a masked `CalledProcessError`), then the denylist check. Structural guarantee from phase-arch-design.md §"Component design" #2 §"Why not co-located"; extended per Phase 2 commitment that the renderer composes by data, not by registry coupling. (validator: hardened — denylist tightened per COV-7; `check=False` per TQ-4.)

- [ ] **AC-9 (empty / no-IndexHealth-slice path renders placeholder).** When `envelope_slice` has no `probes.index_health.index_health` key, OR that key is an empty dict, OR every per-index slice is malformed, the renderer returns exactly:
  ```
  ## Confidence

  _No index sources registered._
  ```
  (with a trailing newline). Tests pin this body byte-for-byte for: (a) `envelope_slice == {}`, (b) `envelope_slice == {"probes": {}}`, (c) `envelope_slice == {"probes": {"index_health": {"index_health": {}}}}`. (validator: added — closes the "always-emit-empty-heading" mutant gap per COV-4 + TQ-6.)

- [ ] **AC-10 (duplicate `index_name` upstream — fail loud, writer recovers).** If the upstream slice contains structurally-duplicate index_name keys (impossible via dict but possible via merged structure or test fixture), the renderer raises `ValueError("duplicate index_name: <name>")`. The writer's existing `try/except Exception` in `_publish_context_report` (writer.py:148-156) catches, logs `report.confidence_section.render_failed` with `error=<exception type>`, and does NOT raise — `repo-context.yaml` is unaffected. Unit test asserts the renderer raises; integration test asserts the writer continues. Rule 12 — fail loud at the renderer, recover at the chokepoint. (validator: added per COV-5.)

- [ ] **AC-11 (renderer purity — AST-walking guard).** Test `tests/unit/report/test_confidence_section_purity.py::test_renderer_has_no_side_effects` parses `src/codegenie/report/confidence_section.py` via `ast.parse` and asserts: (a) no `Call` node whose target is `open`, `print`, or any `Attribute` ending in `.write` / `.write_text` / `.write_bytes`; (b) no top-level `Import` or `ImportFrom` for `logging`, `structlog`, `pathlib`, `os`, `os.path`, `sys` (except `sys` if needed for `assert_never` import in older Pythons — exempt by name), `subprocess`, `shutil`, `tempfile`. Mirrors the precedent of other Phase 2 purity tests (`grep -rn "ast.parse\|ast.walk" tests/unit/`). Pure renderer ⇒ pure unit tests ⇒ no environmental flake. (validator: added per DP-8 + CLAUDE.md "Functional core / imperative shell".)

- [ ] **AC-12 (no plaintext-secret leak via slice_malformed path — 02-ADR-0005 invariant).** Test `test_malformed_slice_does_not_leak_offending_value`: construct a malformed slice whose offending value is an AWS-key-shaped fixture (`{"freshness": {"kind": "bogus_kind", "leak_field": "AKIA1234567890ABCDEF"}}` — test fixture; gate with `# noqa: S105` if the secret-pattern hook flags it). Assert that the rendered `CONTEXT_REPORT.md` does NOT contain `AKIA1234567890ABCDEF` anywhere — only the literal `slice_malformed` sentinel. Mirror test: a *well-formed* `IndexerError(message="AKIA1234567890ABCDEF")` slice DOES render the value verbatim (the renderer trusts the redactor's prior chokepoint per AC-4). The asymmetry is the load-bearing invariant: the renderer trusts redacted slice content; the renderer NEVER constructs new strings from offending-value inputs. (validator: added per CON-3 + TQ-10 — protects 02-ADR-0005 / 02-ADR-0010.)

- [ ] **AC-13 (metamorphic property — adding/removing an index leaves other rows unchanged).** Property test `test_each_row_isolates_its_variant` (Hypothesis): generate `slices: dict[str, IndexFreshness]` from `st.dictionaries(st.text(alphabet=printable_ascii, min_size=1, max_size=16), st.sampled_from(FRESHNESS_INSTANCES), min_size=1, max_size=8)`. Assert: (a) each rendered row contains exactly one variant's marker — no cross-talk; (b) `render(slices) == render(slices | extra_slice)` *for the rows that are not the extra* (extract per-row substrings and compare); (c) row order is `sorted(slices.keys())` for every generated input. Metamorphic invariant: rendering is purely per-row + sorting; no cross-row state. (validator: added per TQ-7.)

## Out of scope

- Rendering anything other than the **Confidence section** — `CONTEXT_REPORT.md` may have other sections in later phases; Phase 2 only commits to the Confidence section. The top-of-file `# CONTEXT_REPORT — <repo_path>` heading is a one-liner; deeper structure waits.
- Localization, emoji styling, terminal-color escape codes. The renderer outputs ASCII Markdown only.
- Re-redacting `IndexerError.message` — secret redaction is the writer chokepoint's job (S3-01/3-02/3-03). The renderer trusts the slice.
- Adding new `IndexFreshness` variants — the variant set is frozen by 02-ADR-0006 and was decided in S1-01. A fifth `StaleReason` requires an ADR amendment, not an edit here.
- Phase 3 plugin-side rendering. Phase 3 may layer `AdapterConfidence` over `IndexFreshness` in bundle metadata (phase-arch-design.md §"Integration with Phase 3"); that's a Phase 3 concern.

## Files to touch

**New:**

- `src/codegenie/report/__init__.py` — re-exports `render_confidence_section`; closed `__all__ = ["render_confidence_section"]`. (No class wrapper — DP-3.)
- `src/codegenie/report/confidence_section.py` — the renderer. ~120 LOC (down from ~150 — class removed).
- `tests/unit/report/__init__.py` — empty package init.
- `tests/unit/report/test_confidence_section.py` — unit tests AC-1, AC-2, AC-4, AC-5, AC-8, AC-9, AC-10 (renderer-side raise), AC-12, AC-13.
- `tests/unit/report/test_confidence_section_purity.py` — AST-walking purity test (AC-11).
- `tests/integration/test_writer_renders_confidence_section.py` — integration test AC-6 + AC-10 (writer recovers from `ValueError`).

**Verify (already wired — DO NOT MODIFY):**

- `src/codegenie/output/writer.py` lines 138-156 + 233-239 — `_publish_context_report(envelope.slice, output_dir)` invokes the renderer. The writer's `RedactedSlice` chokepoint per 02-ADR-0010 is unchanged. AC-6's integration test exercises this call site against the renderer this story implements.

**Untouched (DO NOT EDIT):**

- `src/codegenie/indices/freshness.py` — the variant set is frozen by ADR-0006; `IndexerError.message` is documented as "a stable identifier — not a free-form human string" (lines 73-80). AC-5 preserves that contract.
- `src/codegenie/probes/layer_b/index_health.py` — the producer; the consumer reads from `ProbeOutput.schema_slice`, never imports the probe.
- `pyproject.toml` — `[tool.mypy] warn_unreachable = true` is already global (Phase 0 S1-02); do NOT add `[[tool.mypy.overrides]]` blocks for the renderer module.
- Any `src/codegenie/probes/**/*.py`, `src/codegenie/output/sanitizer.py`, `src/codegenie/adapters/**`, or `src/codegenie/tccm/**` file. Renderer must not depend on any of these (AC-8 denylist).

## TDD plan — red / green / refactor

**RED (failing tests committed first):**

1. `test_module_surface_closed` (AC-1) — `set(codegenie.report.confidence_section.__all__) == {"render_confidence_section"}`. No `ConfidenceSectionRenderer` symbol. Fails red — module does not exist.
2. `test_exhaustive_match_every_variant` (AC-2) — input dict with 5 entries, one per variant, each keyed to a distinct `index_name`. Assertions: (a) `out.count("- [OK]") == 1`; (b) `out.count("- [STALE]") == 4`; (c) for each `(name, expected_marker)` pair, the row whose first whitespace-separated token-after-`[STALE]/[OK]` equals `name` contains `expected_marker` AND does NOT contain any other variant's marker (per-row negative-space). Built by parsing `out.splitlines()` into a `{name: row}` dict via regex `^- \[(?:OK|STALE)\] (\S+) ·`.
3. `test_row_format_per_variant_fresh|commits_behind|digest_mismatch|coverage_gap|indexer_error` (AC-4) — one test per variant; each asserts the exact substring per the AC-4 format pins. `test_row_format_indexer_error_message_truncated` — `IndexerError(message="x" * 300)` renders with `message[:200] + "…"`.
4. `test_row_order_full_sequence` (AC-4) — `re.findall(r"^- \[(?:OK|STALE)\] (\S+) ·", out, re.M) == sorted(input.keys())` for three discriminating fixtures: uppercase/lowercase mix `{"B": ..., "a": ..., "C": ...}` proves code-point order; numeric `{"idx10": ..., "idx2": ..., "idx1": ...}` proves lex-not-natural. **Mutation-resistance:** would fail under `sorted(reverse=True)`, `sorted(key=str.casefold)`, `sorted(key=hash)`.
5. `test_output_endings` (AC-4) — `out.endswith("\n")` and `"\n\n\n" not in out`.
6. `test_ascii_only_no_emoji` (AC-4) — every output codepoint is ASCII OR ∈ `{"·", "…"}`.
7. `test_malformed_slice_emits_sentinel_only` (AC-5) — slice `{"freshness": {"kind": "not-a-known-kind"}}` renders `- [STALE] <name> · indexer_error · slice_malformed` and NOTHING after `slice_malformed` (regex `^- \[STALE\] \S+ · indexer_error · slice_malformed$`). Subsequent valid slice still renders correctly.
8. `test_malformed_slice_emits_structlog_event` (AC-5) — using `structlog.testing.capture_logs`, assert one `report.confidence_section.slice_malformed` event was emitted with fields `{index_name, error_count, first_loc}`. The event payload contains the diagnostic detail; the row does NOT.
9. `test_empty_envelope_renders_placeholder` (AC-9) — three sub-cases (`{}`, `{"probes": {}}`, fully-empty `index_health`) all return exactly `"## Confidence\n\n_No index sources registered._\n"` byte-for-byte.
10. `test_duplicate_index_name_raises_value_error` (AC-10) — construct an upstream-merged-shape slice with duplicate index_name keys (e.g., wrap a list-shaped sub-structure that decodes to two entries with the same key); assert `render_confidence_section(envelope)` raises `ValueError` with message matching `r"duplicate index_name: .+"`.
11. `test_no_probe_registry_import` (AC-8) — subprocess script imports `codegenie.report.confidence_section` then prints `LOADED:` + sorted modules. Parent asserts `proc.returncode == 0` first, then no module in `proc.stdout` starts with any prefix in `{"codegenie.probes", "codegenie.coordinator", "codegenie.cache", "codegenie.adapters", "codegenie.tccm", "codegenie.output.sanitizer"}`. `check=False`.
12. `test_renderer_does_not_re_sanitize` (AC-12, AC-4 negative-space) — a *well-formed* `IndexerError(message="AKIA1234567890ABCDEF")` renders verbatim (renderer trusts the redactor's prior chokepoint).
13. `test_malformed_slice_does_not_leak_offending_value` (AC-12) — malformed slice whose offending value matches AWS-key fixture; assert `"AKIA1234567890ABCDEF" not in out`.
14. `test_each_row_isolates_its_variant` (AC-13, Hypothesis property-based) — see AC-13. Hypothesis health-check `suppress_health_check=[HealthCheck.too_slow]` if needed; bounded `max_examples=200`.
15. `test_renderer_has_no_side_effects` (AC-11) — AST walk; lives in `test_confidence_section_purity.py`.
16. **Integration** `tests/integration/test_writer_renders_confidence_section.py::test_context_report_md_atomic_and_complete` (AC-6) — runs `codegenie gather` against `tests/fixtures/portfolio/minimal-ts`. Asserts:
    - `.codegenie/context/CONTEXT_REPORT.md` exists; no `.tmp` shadow.
    - `out.splitlines()[0] == "## Confidence"`.
    - `len(re.findall(r"^- \[", out, re.M)) == len(envelope_slice["probes"]["index_health"]["index_health"])`.
    - Every input `index_name` appears in exactly one row.
    - Two back-to-back runs produce byte-identical `CONTEXT_REPORT.md` (with `Fresh.indexed_at` patched to a deterministic value via `monkeypatch` on the producer's time source, OR fixture pre-seeded as stale-only).
17. **Integration** `test_writer_recovers_from_renderer_value_error` (AC-10) — patch `codegenie.report.render_confidence_section` to raise `ValueError`; assert `repo-context.yaml` still publishes successfully AND `report.confidence_section.render_failed` is logged.

All RED tests fail because `codegenie.report.confidence_section` does not yet exist.

**GREEN (minimum code to pass):**

1. Create `src/codegenie/report/__init__.py` with `__all__ = ["render_confidence_section"]` and re-export.
2. Implement `render_confidence_section(envelope_slice: Mapping[str, Any]) -> str`:
   - Locate `slices = envelope_slice.get("probes", {}).get("index_health", {}).get("index_health", {})` (empty dict if missing at any level).
   - If `slices` is empty (or non-`Mapping`), return the placeholder block from AC-9.
   - Detect duplicates upstream (the AC-10 fixture shapes); raise `ValueError("duplicate index_name: …")` before sorting.
   - For each `(name, slice_dict)` in `sorted(slices.items())`:
     - Try `freshness = TypeAdapter(IndexFreshness).validate_python(slice_dict.get("freshness"))`.
     - On `ValidationError as e`: emit `_log.warning("report.confidence_section.slice_malformed", index_name=name, error_count=len(e.errors()), first_loc=".".join(str(p) for p in e.errors()[0].get("loc", ())) or "<root>")`; set `freshness = Stale(reason=IndexerError(message="slice_malformed"))`.
     - Dispatch via outer `match value:` → inner `match value.reason:` (DP-1 / AC-2). Emit the row per AC-4 format pins.
   - Return `"## Confidence\n\n" + "\n".join(rows) + "\n"`.
3. **Do NOT** introduce a `ConfidenceSectionRenderer` class (DP-3).
4. **Do NOT** edit `pyproject.toml`'s mypy config (CON-1; warn_unreachable is already global).
5. **Do NOT** edit `src/codegenie/output/writer.py` (CON-2; already wired).

**REFACTOR:**

- Extract per-variant row-format helpers (`_fresh_row`, `_commits_behind_row`, ...) only if the inline arms exceed 5 lines each. Keep the nested `match` shape — exhaustiveness at both levels is the point.
- Confirm `mypy --strict src/codegenie/report/` is clean. (`warn_unreachable` is honored repo-wide.)
- **Run the AC-3 dual ritual:**
  - (a) Delete `case Fresh(indexed_at=...):` from the outer `match value:`. Run `mypy src/codegenie/report/`. Confirm `[unreachable]` at `assert_never(value)`. Capture stderr → `_attempts/S8-01.md`. Revert.
  - (b) Delete `case CommitsBehind(...):` from the inner `match reason:`. Run `mypy src/codegenie/report/`. Confirm `[unreachable]` at `assert_never(reason)`. Capture stderr → `_attempts/S8-01.md`. Revert.
- `ruff format`; ensure no `# type: ignore` in this module.

## Notes for the implementer

- **Read S1-01 first.** The `IndexFreshness` variant set + `Literal[...]` discriminators are non-negotiable; if you find yourself wanting to add a sixth `StaleReason`, stop — that requires an ADR amendment per phase-arch-design.md §"Integration with Phase 3" guarantee #2.

- **Mirror the established nested-match idiom** (DP-1). Read `src/codegenie/probes/layer_b/index_health.py:239-279` — the producer module already has two consumers of the same sum type (`_derive_confidence` and `_last_indexed_at`) using nested `match` with `assert_never` at BOTH levels. The renderer MUST mirror that shape. A flat 5-arm match (e.g., `case Stale(reason=CommitsBehind()):`) reduces the exhaustiveness signal — mypy may not always catch a missed inner reason through a single-level pattern over an `Annotated[Union[..], Field(discriminator=...)]` type. Two `assert_never` arms is the load-bearing structural enforcement.

- **The `assert_never` arms are the proof.** If during AC-3's ritual `mypy` does *not* fail on a removed `case`, the repo-wide `[tool.mypy] warn_unreachable = true` setting is broken — fix `pyproject.toml` (Phase 0 S1-02 territory) rather than weakening this story.

- **`IndexerError.message` is a stable identifier, not a free-form string** (DP-2). Read `src/codegenie/indices/freshness.py:73-80`. NEVER construct `IndexerError(message=f"prefix:{str(exception)}")` or similar — that erodes the smart-constructor discipline every other Phase-2/3 consumer relies on. The AC-5 path emits `IndexerError(message="slice_malformed")` (stable sentinel) and routes diagnostic detail to a structlog event. The same pattern applies to every future variant of `StaleReason`.

- **The renderer must NOT introduce a `@register_freshness_row_formatter` decorator-registry** (DP-6 — anti-pattern alert). Even though `@register_index_freshness_check` (`src/codegenie/indices/registry.py`) and `@register_dep_graph_strategy` (`src/codegenie/depgraph/`) suggest "registry is the Open/Closed answer," that pattern is correct for **producer extension** (new index sources extend by addition), and **wrong** for **consumer exhaustiveness here**. A registry-of-formatters would make an unregistered sixth variant silently no-op; the explicit `match` + `assert_never` makes it a compile-time error. This asymmetry is intentional — the producer side is open, the consumer side is closed-by-design. If a reviewer proposes "make the renderer pluggable," point them at this paragraph and at 02-ADR-0006 §Consequences.

- **The writer is already wired** (CON-2). `src/codegenie/output/writer.py:138-156` defines `_publish_context_report(envelope.slice, output_dir)`; line 239 calls it inside `Writer.write`. The renderer's import path (`from codegenie.report import render_confidence_section`) is on line 148. You do NOT edit writer.py for this story — you implement the module the writer already imports. If the import fails at runtime, the writer's `try/except Exception` (line 152) logs `report.confidence_section.render_failed` and continues; `repo-context.yaml` is unaffected.

- **Renderer input type** (DP-4). The renderer accepts `Mapping[str, Any]` (`RedactedSlice.slice` — a dict). Do NOT widen to `RedactedSlice` (would couple `codegenie.report` to `codegenie.output.redacted_slice`); do NOT narrow to a typed view object (Rule 2 — no single-use abstraction). Re-validate per-index `freshness` JSON dicts via `pydantic.TypeAdapter(IndexFreshness).validate_python(...)` at the renderer's entry — this is the typed boundary.

- **Newtype erasure at the slice boundary** (DP-9). Map keys are `str(IndexName)` — the newtype is erased at `index_health.py:369` (`results[str(name)] = ...`) deliberately. Do NOT re-promote `IndexName` inside the renderer; keep keys as `str`. (Per Rule 11; the slice boundary is the established type-erasure point.)

- **CLI-vs-writer wiring** (DP-5 — historical note). The current implementation lifts the renderer call into `_publish_context_report` *inside* `writer.py`, accepting one extra responsibility on the writer in exchange for atomicity within a single chokepoint. An alternative shape (CLI-side wiring after `writer.write()` returns) was considered; the writer-side path was chosen to keep the atomicity discipline in a single module. Do NOT relocate the call site as part of this story — change-management for that lives in a future surgical-edit story if it ever becomes necessary.

- **The renderer takes the in-memory slice, not the persisted file.** Reading `repo-context.yaml` back from disk would re-parse YAML the writer just emitted; the in-memory slice is the source of truth (matches process view step 7). The writer passes it directly.

- **Do not add `secrets_redacted_count` to this story.** That is S8-02's territory (CLI summary line). This story's renderer concerns itself only with `IndexFreshness`.

- **Do not parallelize the `CONTEXT_REPORT.md` write with the `repo-context.yaml` write.** Writer atomicity is `repo-context.yaml` first (the canonical artifact), `CONTEXT_REPORT.md` second (the human-readable companion). If the renderer raises (it shouldn't except via AC-10's `ValueError`), the writer logs `report.confidence_section.render_failed` and continues; `repo-context.yaml` is intact.

- **`assert_never` import:** `from typing import assert_never` is Python 3.11+; both Python versions Phase 2 supports include it without `typing_extensions` (CI matrix Python 3.11 *and* 3.12 per High-level-impl.md Step 8 done criterion #3).

- **No emoji in `CONTEXT_REPORT.md` per user convention** (`CLAUDE.md` global Rule 11 — match codebase conventions; the codebase is ASCII-only). Allowed non-ASCII codepoints: `·` (separator) and `…` (truncation suffix). The AC-4 ASCII test pins this set explicitly.

- **Phase 0 fence stays green:** the renderer imports nothing from `anthropic`/`openai`/`langgraph`/`httpx`/`requests`/`socket`. Trivially.

- **CODEOWNERS:** `src/codegenie/report/**` does NOT need CODEOWNERS gating — only `ProbeContext` (S1-09) is gated.
