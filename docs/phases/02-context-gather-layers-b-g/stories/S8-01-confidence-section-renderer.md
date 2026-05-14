# Story S8-01 — `ConfidenceSection` renderer with exhaustive `match` + `assert_never` enforcement

**Step:** Step 8 — Confidence section renderer + CI ratchet + advisory benches + Phase-3 handoff
**Status:** Ready
**Effort:** M
**Depends on:** S7-04 (`tests/adv/phase02/test_phase3_handoff_smoke.py` lands skipped + the in-memory secret-leak boundary test), S7-05 (portfolio integration sweep wired)
**ADRs honored:** 02-ADR-0006 (`IndexFreshness` sum-type location at `codegenie.indices.freshness`); 02-ADR-0009 (no `pytest-xdist` — serial); production ADR-0033 §3–4 (make illegal states unrepresentable; `assert_never` is the type-level enforcement)

## Context

`IndexFreshness` is the typed answer to commitment §2.3 — "silent staleness is the worst failure mode of the entire system" (`CLAUDE.md`, `production/design.md` §2.3). Phase 2's design ships **one consumer** of that sum type so the variant set is exercised from day 1 and a missed `case` becomes a build error rather than a runtime surprise: the **Confidence section of `CONTEXT_REPORT.md`**, rendered by `src/codegenie/report/confidence_section.py`. That module is intentionally outside `probes/` so a CONTEXT_REPORT render does not pull in the probe registry; Phase 3 adapters and Phase 8 Bundle Builder will import it without circular-dependency risk (phase-arch-design.md §"Component design" #2 §"Why not co-located").

The renderer is what makes the discipline *real*: `mypy --warn-unreachable` is enabled per-module on `codegenie.report/**` via the `pyproject.toml` override that landed in S1-11. A removed `case` arm against any `IndexFreshness` variant must produce a CI build error — verified in this story by deliberately removing a `case` locally, confirming `mypy` fails, and capturing that smoke check in the Step 8 PR-review checklist (Implementation risk #4).

This story is the type-level enforcement of B2's load-bearing role. Without it, every other guardrail in this phase (the `stale-scip` adversarial, the freshness registry, the per-module mypy overrides) is decoration around a sum type nobody pattern-matches on.

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
  - `src/codegenie/indices/freshness.py` (S1-01) — `Fresh | Stale(reason: StaleReason)`; `StaleReason = CommitsBehind | DigestMismatch | CoverageGap | IndexerError`. The `__all__` and `Literal[...]` `kind` discriminators are the only thing the renderer pattern-matches against.
  - `src/codegenie/probes/layer_b/index_health.py` (S4-01) — emits one `IndexFreshness` per index source; renderer reads from `ProbeOutput.schema_slice["freshness"]` shape defined there.
  - `src/codegenie/output/writer.py` (Phase 0 + S3-03) — the writer is the only path from `ProbeOutput` to disk; the renderer runs *after* the writer's atomic `os.replace` (process view step 7), reading the just-written `repo-context.yaml` is not the choice — the renderer takes the in-memory merged envelope and emits `CONTEXT_REPORT.md`.
  - `pyproject.toml` (S1-11) — `[[tool.mypy.overrides]]` block with `module = ["codegenie.report.*"]` and `warn_unreachable = true`. This story is the first module under `codegenie.report/**`; the override only fires once code lands here.

## Goal

Implement `src/codegenie/report/__init__.py` and `src/codegenie/report/confidence_section.py` as the **only Phase-2 consumer** of `IndexFreshness`. The renderer pattern-matches on every `IndexFreshness` variant with `case` arms exhaustive over `Fresh | Stale(CommitsBehind|DigestMismatch|CoverageGap|IndexerError)` and a final `case _:` that calls `typing.assert_never(...)`. The renderer takes the merged-and-sanitized envelope (the same one the writer just persisted) and produces a `CONTEXT_REPORT.md` string with a "Confidence" section whose row order is deterministic (sorted by `index_name`), whose `Fresh` rows render as `[OK] <index_name> · indexed_at=<iso>`, and whose `Stale` rows render with a human-readable reason derived per-variant. The writer invokes the renderer once per gather; `CONTEXT_REPORT.md` is written atomically (`.tmp` → `os.replace`) alongside `repo-context.yaml`.

Critically: with `mypy --warn-unreachable` enabled per-module on `codegenie.report.*` (S1-11), **removing any `case` arm produces a `[unreachable]` build error** at the `assert_never(value)` line in CI. This is the type-level enforcement of B2's load-bearing role. The Step 8 PR-review checklist requires deliberately removing a `case` once and confirming the CI build fails (Implementation risk #4).

## Acceptance criteria

- [ ] **AC-1 (module surface).** `src/codegenie/report/__init__.py` exports `ConfidenceSectionRenderer` and `render_confidence_section`. `src/codegenie/report/confidence_section.py` contains both. `__all__` is closed. No imports from `codegenie.probes.*` (renderer must not pull the probe registry — phase-arch-design.md §"Component design" #2 §"Why not co-located"). The only Phase-2 dependencies are `codegenie.indices.freshness` and stdlib (`typing.assert_never`, `datetime.datetime.isoformat`).
- [ ] **AC-2 (exhaustive `match` over every `IndexFreshness` variant).** `render_confidence_section` contains a single `match value:` statement over an `IndexFreshness` input with arms for `Fresh(...)` and `Stale(reason=CommitsBehind(...))`, `Stale(reason=DigestMismatch(...))`, `Stale(reason=CoverageGap(...))`, `Stale(reason=IndexerError(...))`. The final arm is `case _: assert_never(value)`. `tests/unit/report/test_confidence_section.py::test_exhaustive_match_every_variant` constructs one of each variant and asserts the rendered string contains the variant-specific marker; the test list is built by enumerating `Fresh, CommitsBehind, DigestMismatch, CoverageGap, IndexerError` programmatically, so a sixth variant added to `freshness.py` without a corresponding `case` is caught both here *and* by mypy.
- [ ] **AC-3 (`mypy --warn-unreachable` enforces exhaustiveness — CI build error on removed `case`).** With S1-11's per-module override active on `codegenie.report.*`, deliberately deleting any `case` arm from `confidence_section.py` causes `mypy --strict --warn-unreachable` to report a `[unreachable]` error at the `assert_never(value)` line. Verification ritual: open a scratch branch, delete the `case Fresh(...):` arm, run `mypy src/codegenie/report/`, confirm non-zero exit with `[unreachable]` in stderr, revert. This ritual is recorded as a Step 8 PR-review checklist item (Implementation risk #4). The story's `_attempts/S8-01.md` log captures the ritual's `mypy` stderr snapshot for audit.
- [ ] **AC-4 (deterministic row order + format).** Rows are sorted by `index_name` ASCII-lexicographic. `Fresh(indexed_at)` renders as `- [OK] <index_name> · indexed_at=<iso8601-UTC-Z>`. `Stale(CommitsBehind(n, last_indexed))` renders as `- [STALE] <index_name> · commits_behind=<n> · last_indexed=<8-hex-short-sha-OR-iso>`. `Stale(DigestMismatch(expected, actual))` renders `digest_mismatch · expected=<8-hex>… · actual=<8-hex>…`. `Stale(CoverageGap(files_indexed, files_in_repo))` renders `coverage_gap · indexed=<n>/<m>`. `Stale(IndexerError(message))` renders `indexer_error · <message>` (message is already secret-redacted at writer chokepoint per S3-01/3-02; renderer does NOT re-sanitize). `tests/unit/report/test_confidence_section.py::test_row_format_per_variant` golden-locks one example of each.
- [ ] **AC-5 (renderer never crashes on `IndexFreshness` shape; surfaces malformed slice as one row).** If the merged envelope contains a slice whose `freshness` field fails Pydantic validation against `IndexFreshness` (defense in depth — should not happen given writer chokepoint), the renderer emits a single `- [STALE] <index_name> · indexer_error · slice_malformed:<ValidationError-summary>` row and continues with the next index. Validated by `tests/unit/report/test_confidence_section.py::test_malformed_slice_does_not_crash`. The render does not raise.
- [ ] **AC-6 (writer integration — atomic `.tmp` → `os.replace`).** `src/codegenie/output/writer.py` calls `render_confidence_section(merged_envelope)` exactly once per gather, after `repo-context.yaml` is persisted, and writes the result to `.codegenie/context/CONTEXT_REPORT.md` via the same `.tmp` → `os.replace` discipline. Integration test `tests/integration/test_writer_renders_confidence_section.py` asserts: (a) `CONTEXT_REPORT.md` exists post-gather; (b) it contains a `## Confidence` heading; (c) it contains at least one row per `IndexFreshness` emitted by `IndexHealthProbe`; (d) the file is byte-identical across two back-to-back runs against the same fixture (modulo deterministic timestamps already governed by the golden regen-script exclusions).
- [ ] **AC-7 (`mypy --strict` + per-module override green).** `mypy --strict src/codegenie/report/` passes with the per-module `warn_unreachable = true` override active. `ruff check src/codegenie/report/ tests/unit/report/` and `ruff format --check` both green.
- [ ] **AC-8 (no probe-registry import; renderer composes by data, not inheritance).** `python -c "import codegenie.report.confidence_section; import sys; assert not any(m.startswith('codegenie.probes') for m in sys.modules)"` exits 0 when run after a fresh import. Enforced by `tests/unit/report/test_confidence_section.py::test_no_probe_registry_import`. This is the structural guarantee from phase-arch-design.md §"Component design" #2 §"Why not co-located".

## Out of scope

- Rendering anything other than the **Confidence section** — `CONTEXT_REPORT.md` may have other sections in later phases; Phase 2 only commits to the Confidence section. The top-of-file `# CONTEXT_REPORT — <repo_path>` heading is a one-liner; deeper structure waits.
- Localization, emoji styling, terminal-color escape codes. The renderer outputs ASCII Markdown only.
- Re-redacting `IndexerError.message` — secret redaction is the writer chokepoint's job (S3-01/3-02/3-03). The renderer trusts the slice.
- Adding new `IndexFreshness` variants — the variant set is frozen by 02-ADR-0006 and was decided in S1-01. A fifth `StaleReason` requires an ADR amendment, not an edit here.
- Phase 3 plugin-side rendering. Phase 3 may layer `AdapterConfidence` over `IndexFreshness` in bundle metadata (phase-arch-design.md §"Integration with Phase 3"); that's a Phase 3 concern.

## Files to touch

**New:**

- `src/codegenie/report/__init__.py` — re-exports `ConfidenceSectionRenderer`, `render_confidence_section`; closed `__all__`.
- `src/codegenie/report/confidence_section.py` — the renderer. ~150 LOC.
- `tests/unit/report/__init__.py` — empty package init.
- `tests/unit/report/test_confidence_section.py` — unit tests AC-2, AC-4, AC-5, AC-8.
- `tests/integration/test_writer_renders_confidence_section.py` — integration test AC-6.

**Modified:**

- `src/codegenie/output/writer.py` — one new call site: after `repo-context.yaml` `os.replace`, call `render_confidence_section(envelope)` and write to `.codegenie/context/CONTEXT_REPORT.md` via the same atomic pattern. The writer's existing chokepoint (`RedactedSlice` input) is unchanged.

**Untouched (DO NOT EDIT):**

- `src/codegenie/indices/freshness.py` — the variant set is frozen by ADR-0006.
- `src/codegenie/probes/layer_b/index_health.py` — the producer; the consumer reads from `ProbeOutput.schema_slice`, never imports the probe.
- Any `src/codegenie/probes/**/*.py` file. Renderer must not depend on the registry.

## TDD plan — red / green / refactor

**RED (failing tests committed first):**

1. `tests/unit/report/test_confidence_section.py::test_exhaustive_match_every_variant` — enumerates `[Fresh(now), Stale(CommitsBehind(3, "abc12345")), Stale(DigestMismatch("aa"*32, "bb"*32)), Stale(CoverageGap(8, 10)), Stale(IndexerError("scip_unavailable"))]`, passes each into `render_confidence_section({"idx_a": fresh, "idx_b": stale_cb, ...})`, asserts the output string contains each variant's marker (`[OK]`, `commits_behind=`, `digest_mismatch`, `coverage_gap`, `indexer_error`). Fails red because `render_confidence_section` does not exist.
2. `test_row_format_per_variant` — locks one rendered line per variant against an inline-golden string. Fails red.
3. `test_row_order_deterministic` — `render_confidence_section({"b": ..., "a": ..., "c": ...})` row order is `a, b, c`. Fails red.
4. `test_malformed_slice_does_not_crash` — passes a `dict` with a bad shape; asserts the function returns (no `raise`) and the row contains `slice_malformed`. Fails red.
5. `test_no_probe_registry_import` — imports `codegenie.report.confidence_section` in a clean subinterpreter / fresh `sys.modules` snapshot, asserts no `codegenie.probes` module loaded as a side effect. Fails red.
6. `tests/integration/test_writer_renders_confidence_section.py::test_context_report_md_written_atomically` — runs `codegenie gather` against `tests/fixtures/portfolio/minimal-ts`, asserts `.codegenie/context/CONTEXT_REPORT.md` exists, contains `## Confidence`, contains at least one `[OK]` or `[STALE]` row, and is byte-identical across two consecutive runs. Fails red — writer does not call the renderer.

**GREEN (minimum code to pass):**

1. Create `src/codegenie/report/__init__.py` with closed `__all__`.
2. Implement `render_confidence_section(envelope: dict) -> str`:
   - Extract every `freshness` value across the envelope's index slices into `dict[str, IndexFreshness]` (Pydantic `model_validate`; on `ValidationError` synthesize an `IndexerError("slice_malformed:" + str(e))`).
   - Sort keys ASCII.
   - For each `(name, value)`, render one row via a `match value:` with five `case` arms + a `case _: assert_never(value)`.
   - Return the joined Markdown string with leading `## Confidence\n\n`.
3. `ConfidenceSectionRenderer` is a thin class wrapper exposing `.render(envelope)` → `render_confidence_section(envelope)` for the diagram alignment; both are exported.
4. Edit `src/codegenie/output/writer.py` to call the renderer after `repo-context.yaml` `os.replace` and write to `CONTEXT_REPORT.md` via `.tmp` → `os.replace`.

**REFACTOR:**

- Extract per-variant row-format helpers (`_fresh_row`, `_commits_behind_row`, ...) only if the inline arms exceed 5 lines each. Keep the `match` statement flat — exhaustiveness is the point.
- Confirm `mypy --strict --warn-unreachable src/codegenie/report/` is clean.
- **Run the AC-3 ritual:** delete the `case Fresh(...):` arm, run `mypy`, confirm `[unreachable]` error at `assert_never(value)`, capture stderr to `_attempts/S8-01.md`, revert.
- `ruff format`; ensure no `# type: ignore` in this module.

## Notes for the implementer

- **Read S1-01 first.** The `IndexFreshness` variant set + `Literal[...]` discriminators are non-negotiable; if you find yourself wanting to add a sixth `StaleReason`, stop — that requires an ADR amendment per phase-arch-design.md §"Integration with Phase 3" guarantee #2.
- **The renderer is the type-level proof that `mypy --warn-unreachable` is correctly configured.** If during AC-3's ritual `mypy` does *not* fail on a removed `case`, the per-module override in `pyproject.toml` is broken — fix the config (S1-11 territory) rather than weakening this story.
- **The renderer takes the merged envelope, not the persisted file.** Reading `repo-context.yaml` back from disk would re-parse YAML the writer just emitted; the in-memory envelope is the source of truth (matches process view step 7).
- **Do not add `secrets_redacted_count` to this story.** That is S8-02's territory (CLI summary line). This story's renderer concerns itself only with `IndexFreshness`.
- **Do not parallelize the `CONTEXT_REPORT.md` write with the `repo-context.yaml` write.** Writer atomicity is `repo-context.yaml` first (the canonical artifact), `CONTEXT_REPORT.md` second (the human-readable companion). If the renderer raises (it shouldn't — AC-5), the writer logs `report.confidence_section.render_failed` and continues; `repo-context.yaml` is intact.
- **`assert_never` import:** `from typing import assert_never` is Python 3.11+; both Python versions Phase 2 supports include it without `typing_extensions` (CI matrix Python 3.11 *and* 3.12 per High-level-impl.md Step 8 done criterion #3).
- **No emoji in `CONTEXT_REPORT.md` per user convention** (`CLAUDE.md` global Rule 11 — match codebase conventions; the codebase is ASCII-only).
- **Phase 0 fence stays green:** the renderer imports nothing from `anthropic`/`openai`/`langgraph`/`httpx`/`requests`/`socket`. Trivially.
- **CODEOWNERS:** `src/codegenie/report/**` does NOT need CODEOWNERS gating — only `ProbeContext` (S1-09) is gated.
