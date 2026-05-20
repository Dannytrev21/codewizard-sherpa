# Story S9-04 — `BenchReplayable` events + Phase 6.5 backfill hook

**Step:** Step 9 — CI gates, import-linter contracts, performance baselines, bench backfill hook
**Status:** HARDENED
**Effort:** M (was S — hardening revealed real additional surface: the synthesized case directory must carry `input/` + `expected/` subdirs and a Phase-6.5-schema-conformant `case.toml`, the payload gains a `commit_sha` field, and the orchestrator emit site needs a parametrized unit test over all five exit paths)
**Depends on:** S6-01 (`WorkflowSpanningEvent` union + `bench_replayable` literal), S6-04 (`RemediationOrchestrator.run` — the emit site this story extends), S8-01 (the 10-fixture portfolio), S8-02 (`run_remediate_against_fixture` harness), S9-02, S9-03
**ADRs honored:** ADR-0005 (two-stream event log — `bench_replayable` is the eighth literal in `WorkflowSpanningEvent.event_type`; the spanning stream is the seed source for Phase 6.5's backfill, per ADR §Consequences "The spanning stream is the seed source for Phase 6.5's `BenchReplayable` events — `codegenie eval backfill` reads it directly"), ADR-0011 (honest framing — the runbook must say what evidence the operator can verify and what they cannot)

## Validation notes

Validated: 2026-05-20
Verdict: HARDENED
Findings: 33 across 4 critics (Coverage 12, Test-Quality 8, Consistency 6, Design-Patterns 7) — 9 tagged `block`, all with clear in-place fixes; ~25 distinct issues after de-duplication, all addressed.

The story's *goal* (ship the `BenchReplayablePayload` schema + a mechanical-synthesis integration test + a runbook) is sound and traces to G9. The *implementation prescription* was underspecified for that goal in three load-bearing ways, all now corrected:

1. **The prescribed `case.toml` shape contradicted the Phase 6.5 schema it claims to satisfy.** The Green step wrote `[case]\ncve_id=…\nexpected_diff_sha256=…`; Phase 6.5's `case.toml` schema (`final-design.md` §"`case.toml` schema", ~line 274) is `case_id, task_class, disposition, difficulty, source, commit_sha, added_at, last_validated_at` (+ optional `cassette_*`), and the case directory also requires `input/` and `expected/` subdirs. The synthesized cases would have been rejected wholesale by Phase 6.5's loader. AC-3 and the TDD plan now produce the real schema.
2. **The payload could not mechanically populate the required `BenchCase` fields.** `commit_sha` (required for non-curated cases) had no source in the payload, and `added_at`/`last_validated_at` had no deterministic source. AC-1 now adds `commit_sha`; the synthesizer now takes the event so timestamps come from `WorkflowSpanningEvent.timestamp` (deterministic, not wall-clock).
3. **The red test never validated a synthesized `case.toml` against the contract** — it asserted only that ≥10 directories existed. A synthesizer writing empty files would have passed. The red test now loads every `case.toml` through the vendored Phase 6.5 `BenchCase` shape and asserts conformance.

Other hardening: `transform_diff_bytes_sha256`/`recipe_id` typed consistently as `… | None` (was an unresolved `""`-sentinel-vs-`None` choice — `BlobDigest` is a 64-hex type, so `""` is an illegal value); the emit site pinned to `model_dump(mode="json", exclude_none=True)` so no `None` value lands in the arch-typed `WorkflowSpanningEvent.payload` dict; exact event count (one per workflow, no double-emit); `sys.modules` LLM check rewritten as a before/after delta scoped to the synthesis step; an orchestrator parametrized unit test over all five exit paths; `case_id` folds in `workflow_id` to avoid collisions on empty-diff outcomes; E10 mischaracterization corrected. Design opportunities (pure/impure split, `Final`-dict catalog, typed event reads, no `CommitSha` newtype) are in **Notes for the implementer**.

Full audit log: `_validation/S9-04-bench-replayable-backfill-hook.md`

## Context

Goal G9 (`phase-arch-design.md §Goals`) commits Phase 3 to making Phase 6.5's backfill **mechanical**: "Every workflow emits `BenchReplayable` on the spanning event stream carrying input-snapshot fingerprint + `Transform.diff_bytes_sha256`. Phase 6.5's `codegenie eval backfill` lifts 10 cases mechanically." The mechanical part is load-bearing: if a human has to write LLM prompts to extract bench cases from Phase 3 runs, Phase 6.5 ships months late and the cases drift from the runs they came from.

The payload must carry exactly enough that Phase 6.5's `loader.py` (see `docs/phases/06.5-per-task-class-eval-harness/final-design.md §Architecture — loader.py: bench/{tc}/cases/ → tuple[BenchCase, ...]`) can synthesize a `BenchCase` without re-running anything. **The bar for "exactly enough" is concrete: every *required* field of Phase 6.5's `case.toml` schema must be mechanically derivable from the payload + the enclosing `WorkflowSpanningEvent` envelope.** That schema (`final-design.md` §"`case.toml` schema", ~line 274) is `case_id, task_class, disposition, difficulty, source, commit_sha, added_at, last_validated_at` (+ optional `cassette_path`/`cassette_blake3`), and each case directory additionally has `input/` and `expected/` subdirs (`final-design.md` §Architecture; the loader raises if `input/` is missing). Mapping each `case.toml` field to its source:

| `BenchCase` / `case.toml` field | Mechanically derived from |
|---|---|
| `case_id` | `sha256(input_snapshot_sha256 + transform_diff_bytes_sha256 + workflow_id)[:16]` — `workflow_id` folded in so two empty-diff `not_applicable` outcomes do not collide |
| `task_class` | constant `"vuln-remediation"` |
| `disposition` | `outcome_kind` → `{validated: positive, failed: negative, not_applicable: ambiguous, requires_human_review: ambiguous}` (all four pinned) |
| `difficulty` | constant `"backfill-unrated"` — a documented mechanical default; a curator or Phase 6.5's `eval backfill` may refine it later (no difficulty signal exists in a Phase 3 run; inventing one would violate the mechanical-not-inference rule) |
| `source` | constant `"outcome-ledger-derived"` — the spanning stream *is* the outcome ledger |
| `commit_sha` | `BenchReplayablePayload.commit_sha` — **required because `source != "curated"`**; carried explicitly (see field list below) |
| `added_at` / `last_validated_at` | the enclosing `WorkflowSpanningEvent.timestamp` — deterministic, not wall-clock |

The `BenchReplayablePayload` therefore carries:

- **`input_snapshot_sha256`** — the BLAKE3 hash over the repo snapshot Phase 3 saw (the exact `RepoSnapshot.sha256` Phase 2 computed). Written into `input/input-pointer.toml`; it lets Phase 6.5 reconstruct the input by name without re-snapshotting.
- **`transform_diff_bytes_sha256`** — the hash over the diff bytes the transform produced. The ground-truth diff Phase 6.5's rubric scores future system outputs against; written under `expected/`. **`None` when there is no transform** (`not_applicable` / `requires_human_review` / `failed`).
- **`commit_sha`** — the git HEAD SHA of the repo Phase 3 analyzed. **New, required** so the synthesized non-curated `case.toml` can populate `commit_sha`. The orchestrator already has it (it names the generated branch `codegenie/cve-<id>-<shortsha>`). Plain `str`, **not** a newtype — see Notes (commit SHAs are boundary data, per `index_health.schema.json`'s explicit ruling).
- **`outcome_kind`** — the `RemediationOutcome.kind` (`validated`, `not_applicable`, `requires_human_review`, `failed`); routes the case (positive / negative / ambiguous disposition).
- **`cve_id` + `plugin_id` + `recipe_id`** — so the case knows which task class to register under. `recipe_id` is `None` when no recipe matched.
- **`workflow_id`** is carried on the enclosing `WorkflowSpanningEvent`, not duplicated in the payload — the synthesizer reads it (and `timestamp`) off the event.

S6-04 owns the emit site (the orchestrator's `run(...)` exits via a `finally` that calls `event_log.emit_spanning(WorkflowSpanningEvent(event_type="bench_replayable", ...))`). S6-01 owns the `WorkflowSpanningEvent` union including the `bench_replayable` literal. **This story does not re-implement those.** What this story owns is:

1. The exact `BenchReplayablePayload` Pydantic schema (frozen, `extra="forbid"`) the orchestrator's call site instantiates.
2. The Phase 6.5 backfill-hook integration test that consumes ≥ 10 `bench_replayable` events from the spanning stream and produces eval cases mechanically (without a human in the loop).
3. The 1-page operator runbook documenting how to run, where artifacts land, how to verify the BLAKE3 chain, and how to surface the evidence to operators.

The fence S9-02 ships is what locks the `bench_replayable` literal into the union; this story ensures the emit site is real and the payload is consumed.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals G9` — "Phase 6.5 backfill readiness. Every workflow emits `BenchReplayable` on the spanning event stream carrying input-snapshot fingerprint + `Transform.diff_bytes_sha256`. Phase 6.5's `codegenie eval backfill` lifts 10 cases mechanically."
  - `../phase-arch-design.md §Component design C9` — `WorkflowSpanningEvent.event_type` includes `bench_replayable`; the payload shape commitment ("each type has a typed payload schema").
  - `../phase-arch-design.md §Integration with Phase 04` + `§Path to production end state` — "`BenchReplayable` spanning events are the seed source for Phase 4's solved-example store" / "Phase 6.5 unblocked".
  - `../High-level-impl.md §Step 9` — verbatim Done criterion: "`pytest tests/integration/test_phase65_backfill_hook.py` produces ≥10 eval cases mechanically from the test event stream."
- **Phase ADRs:**
  - `../ADRs/0005-two-stream-event-log-per-adr-0034.md` §Consequences — "The spanning stream is the seed source for Phase 6.5's `BenchReplayable` events — `codegenie eval backfill` reads it directly." Also: BLAKE3 chain semantics + `fcntl.flock` cross-process safety.
  - `../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — the runbook framing: name what the chain detects (local tamper) and what it does not (host compromise — Phase 16's Sigstore anchors).
- **Existing code:**
  - `src/codegenie/plugins/events.py` (S6-01) — `WorkflowSpanningEvent` definition; the `bench_replayable` literal lives here.
  - `src/codegenie/transforms/orchestrator.py` (S6-04) — `RemediationOrchestrator.run(...)`'s `finally` is the emit site.
  - `src/codegenie/cli.py` + Phase 0's `audit verify` — the BLAKE3-chain verifier extended in S6-05.
  - Phase 6.5 final design: `docs/phases/06.5-per-task-class-eval-harness/final-design.md §Architecture` — `loader.py`, `bench/{tc}/cases/`, `BenchCase` shape; the **`case.toml` schema** (~line 274: `case_id, task_class, disposition, difficulty, source, commit_sha, added_at, last_validated_at`, + optional `cassette_*`) and the case-directory contract (`case.toml` + `input/` + `expected/`; the loader raises on a missing `input/`). This is the schema AC-5/AC-6 must conform to — read it before touching `_phase65_contract.py`. `bench/vuln-remediation/cases/` is the destination for the backfilled cases.
  - `docs/operations/` — runbook home (create if missing).

## Goal

Ship the `BenchReplayablePayload` Pydantic schema, an integration test that mechanically synthesizes ≥ 10 eval cases from the spanning stream (no human in the loop, no LLM), and a 1-page operator runbook covering how to run Phase 3, where artifacts land, how to verify the BLAKE3 chain, and how to surface evidence to operators.

## Acceptance criteria

- [ ] **AC-1** — `src/codegenie/plugins/bench_replayable.py` (NEW) exports `BenchReplayablePayload`, a Pydantic v2 model: `model_config = ConfigDict(frozen=True, extra="forbid")`; fields:
  - `input_snapshot_sha256: BlobDigest`
  - `transform_diff_bytes_sha256: BlobDigest | None = None` — `None` (not `""`) for every non-`validated` outcome; an empty string is not a valid `BlobDigest` (64-hex). (validator: hardened — was `BlobDigest` with an unresolved `""`-vs-`None` choice; `None` is the sum-type-honest shape and matches `recipe_id`.)
  - `commit_sha: str` — git HEAD SHA of the analyzed repo; required so the synthesized non-curated `case.toml` can populate Phase 6.5's required `commit_sha`. Plain `str`, **not** a newtype. (validator: added — Coverage/Consistency block finding: Phase 6.5 `case.toml` requires `commit_sha` and the payload had no source for it.)
  - `outcome_kind: Literal["validated", "not_applicable", "requires_human_review", "failed"]`
  - `cve_id: CveId`
  - `plugin_id: PluginId`
  - `recipe_id: RecipeId | None = None` — `None` when no recipe matched.
  - A `@model_validator(mode="after")` enforces the cross-field invariant: `transform_diff_bytes_sha256 is not None` **iff** `outcome_kind == "validated"`. (validator: added — makes the illegal "validated but no diff" / "not_applicable but has a diff" states unrepresentable; mirrors the `Validated` cross-field validator in `outcomes.py`.)
  All identifier types from `codegenie.types.identifiers` (S1-01).
- [ ] **AC-2** — `RemediationOrchestrator.run(...)`'s `finally` block instantiates a `BenchReplayablePayload` and calls `event_log.emit_spanning(WorkflowSpanningEvent(event_type="bench_replayable", payload=payload.model_dump(mode="json", exclude_none=True), ...))` before flushing. (validator: hardened — was bare `model_dump()`; `WorkflowSpanningEvent.payload` is typed `dict[str, str | int | bool | float | list[str]]` per arch §C9 and does **not** admit `None` — `exclude_none=True` drops the optional keys so no `None` value reaches the arch-typed dict; `recipe_id`/`transform_diff_bytes_sha256` carry `= None` defaults so the round-trip `model_validate` still reconstructs faithfully.)
- [ ] **AC-3** — `bench_replayable` is emitted **exactly once on every exit path of `RemediationOrchestrator.run(...)`** — `validated`, `not_applicable`, `requires_human_review`, `failed`, **and the exception path where `run(...)` raises before a `Transform` was assigned** (the `finally` defensively emits `outcome_kind="failed"`, `transform_diff_bytes_sha256=None`). Verified by `tests/unit/transforms/test_orchestrator.py` with a test parametrized over all five exit conditions; each parametrization injects a fake `EventLog`, runs the orchestrator, and asserts `sum(1 for e in fake.spanning if e.event_type == "bench_replayable") == 1` and that the emitted payload's `outcome_kind` matches the path. (validator: hardened — "every exit path" was unenumerated and "exactly once" was unpinned; a happy-path-only assertion would not catch a `failed` branch that never emits or a double-emit.)
- [ ] **AC-4** — `bench_replayable` events appear **only on the spanning stream**: `tests/unit/transforms/test_orchestrator.py` asserts the workflow-internal stream (`.codegenie/events/workflow-internal/<workflow_id>.jsonl.zst`) contains zero `bench_replayable` events. (validator: added — ADR-0005 two-stream invariant; a lazy impl emitting to both streams would still pass the spanning-stream read.)
- [ ] **AC-5** — `tests/integration/test_phase65_backfill_hook.py` (NEW) does the following in one test:
  1. Runs `codegenie remediate ...` against the 10 distinct fixture repos of the Step 8 portfolio (`express-cve-2024-21501/`, `monorepo-workspaces/`, `transitive-only-cve/`, `peer-dep-conflict/`, `major-bump-required/`, `breaking-test-suite/`, `stale-scip/`, `malformed-package-json/`, `malicious-npmrc/`, `postinstall-canary/`) via the `run_remediate_against_fixture` fixture **reused as-is from S8-02** — S9-04 does not re-decide the jail strategy or re-create fixtures (see Depends-on; both S8-01 and S8-02 are hard preconditions).
  2. Reads `.codegenie/events/spanning/append.jsonl.zst`; parses each line into a typed `WorkflowSpanningEvent`; filters to `event_type == "bench_replayable"`.
  3. **Exact count, no double-emit.** All 10 fixtures enter `RemediationOrchestrator.run(...)` (none fail at the loader phase — verified: `malformed-package-json/`, `malicious-npmrc/`, `postinstall-canary/` are *target-repo* adversarial fixtures, the plugin loads fine and the orchestrator runs). Asserts `len(bench_events) == 10` **and** `len({e.workflow_id for e in bench_events}) == 10` (one event per workflow — a double-emit bug producing 11+ fails here; `>= 10` would not). If a future fixture is known to exit before the orchestrator's `finally` (E10-class loader failure, exit-8 concurrent lock), the expected count is adjusted with an inline comment naming which fixtures do/do not emit — never a bare `>=` floor.
  4. **Payload field assertions.** Every payload `model_validate`s cleanly; every payload has truthy `input_snapshot_sha256` and truthy `commit_sha`; `transform_diff_bytes_sha256` is a 64-hex digest for `outcome_kind == "validated"` and `None` for the other three kinds. Asserts the portfolio exercises the branch: at least one payload has `outcome_kind == "not_applicable"` (`peer-dep-conflict/`, `major-bump-required/`), at least one `"validated"`, and at least one each of `"failed"` and `"requires_human_review"` if the portfolio produces them — name the fixture next to each expected kind.
  5. **Mechanical synthesis.** For each `bench_replayable` event, calls `_synthesize_bench_case(event, cases_root) -> Path` (the shell — see signature note below and Notes-for-implementer) which writes a complete case directory under `cases_root` (`tmp_path / "bench" / "vuln-remediation" / "cases"`): `case.toml`, `input/input-pointer.toml`, and `expected/`. `{case-id}` is `sha256(input_snapshot_sha256 + transform_diff_bytes_sha256-or-"" + workflow_id)[:16]` — fully deterministic, no human input, no wall-clock.
  6. **Contract conformance — the load-bearing assertion.** For every written case directory: (a) `case.toml` parses with `tomllib` and `model_validate`s cleanly against the vendored `_phase65_contract.BenchCase` (`extra="forbid"`); (b) the directory contains `input/` and `expected/` subdirs (Phase 6.5's loader raises on a missing `input/`); (c) the loaded `BenchCase` carries `task_class == "vuln-remediation"`, `source == "outcome-ledger-derived"`, a `disposition` consistent with the payload's `outcome_kind` per the pinned mapping, a non-empty `commit_sha`, and `added_at == last_validated_at ==` the event's `timestamp`; (d) `input/input-pointer.toml` carries the payload's `input_snapshot_sha256`. A `_synthesize_bench_case` that writes an empty or partial `case.toml` must fail this AC. (validator: this entire sub-item was *absent* — the old test asserted only `len(case_dirs) >= 10`, so a synthesizer writing garbage passed; this is the cardinal G9-promise check.)
  7. **Determinism / idempotence.** Synthesizing the same 10-event set twice into two separate roots produces byte-identical `case.toml` files (assert per-file SHA-256 equality). (validator: added — the outline requires `_synthesize_bench_case` be "deterministic"; `datetime.now()` for timestamps would silently break this and Phase 6.5's `run_id` reproducibility.)
  8. **Mechanical-not-LLM, scoped.** Snapshot `before = set(sys.modules) & _FORBIDDEN_LLM` immediately before the synthesis loop and `after` immediately after; assert `after == before`. (validator: hardened — the old `assert "anthropic" not in sys.modules` is process-global and session-order-dependent: it fails spuriously if any earlier test imported an SDK and proves nothing about the synthesis step specifically. The before/after delta is order-independent and scoped to the code under test. Mirror the pre-clean/restore discipline of `tests/fence/test_no_llm_in_transforms.py` — cite it.)
- [ ] **AC-6** — `tests/integration/_phase65_contract.py` (NEW) vendors Phase 6.5's `BenchCase` shape as a contract snapshot (`extra="forbid"`) carrying **exactly** the fields documented in `docs/phases/06.5-per-task-class-eval-harness/final-design.md` §"`case.toml` schema": `case_id, task_class, disposition (Literal positive/negative/ambiguous), difficulty, source (Literal curated/outcome-ledger-derived/regression-converted), commit_sha, added_at, last_validated_at`, plus optional `cassette_path`/`cassette_blake3`. A module-level comment cites the `final-design.md` section + line so a reviewer can diff the two. (validator: added — a contract snapshot that silently diverges from the real schema is worse than none; this AC pins the snapshot to the documented source of truth.)
- [ ] **AC-7** — `_synthesize_bench_case`'s `outcome_kind → disposition` mapping is exhaustive and pinned: `validated → positive`, `failed → negative`, `not_applicable → ambiguous`, `requires_human_review → ambiguous`. A unit test (`tests/integration/test_phase65_backfill_hook.py` or a sibling) exercises all four kinds and asserts the resulting `disposition`. (validator: added — without this, `not_applicable`/`requires_human_review` had no defined disposition and an implementer would guess.)
- [ ] **AC-8** — `docs/operations/phase03-runbook.md` (NEW, 1 page / ≤ 60 lines of content excluding code blocks) covers exactly:
  - **How to run.** `codegenie vuln-index refresh` → `codegenie gather <repo>` (Phase 2) → `codegenie remediate <repo> --cve <id>`; exit codes 0 (validated), 3 (not-applicable), 4 (failed), 7 (requires-human-review), 8 (concurrent), 1 (internal). The four operator-facing flags (`--cve`, `--max-cost-usd` (Phase 4), `--dry-run` (Phase 4), `--verbose`). Phase 3 carries only `--cve`; the others are forward-stable surface. The exit codes and the artifact paths in the next bullet are cross-checked against `src/codegenie/cli.py` at write time (not invented) — a wrong exit code in an operator runbook is a worse failure than a missing one (ADR-0011 honest-framing applies to docs).
  - **Where artifacts land.** `.codegenie/context/repo-context.yaml` (Phase 2 input), `.codegenie/events/workflow-internal/<workflow_id>.jsonl.zst`, `.codegenie/events/spanning/append.jsonl.zst`, `.codegenie/cache/bundles/`, `.codegenie/handoff/<workflow_id>.md` (HITL), `remediation-report.yaml` (workflow-local), the generated branch (`codegenie/cve-<id>-<shortsha>`).
  - **How to verify the BLAKE3 chain.** `codegenie audit verify --spanning-stream .codegenie/events/spanning/append.jsonl.zst`; exit 0 = unbroken; nonzero = break-point line emitted to stderr. What the chain *does* detect (local tamper, partial-write corruption); what it does *not* detect (host compromise — that gap is closed by Sigstore anchoring of the event stream, deferred to the production roadmap / Phase 16; note separately that ADR-0011 assigns `PLUGINS.lock` Sigstore signing to Phase 11 — do not conflate the two artifacts).
  - **How to surface to operators.** `remediation-report.yaml` is the canonical operator artifact; `outcome.kind`, `outcome.failing` (for `Validated(passed=False)`), and the handoff markdown (HITL) are the three fields operators read. The runbook gives one screenshot-equivalent (formatted code block) of each.
- [ ] **AC-9** — `tests/fence/test_event_taxonomy_complete.py` (S9-02) passes — `bench_replayable` has both a declared variant in `WorkflowSpanningEvent` and an emit site in the orchestrator.
- [ ] **AC-10** — `mypy --strict` clean; `ruff check`, `ruff format --check` clean on touched files.
- [ ] **AC-11** — TDD plan's red test exists, committed, green.

## Implementation outline

1. **`BenchReplayablePayload` schema.** New file `src/codegenie/plugins/bench_replayable.py` (~45 LoC). Pydantic v2, frozen, `extra="forbid"`. Imports newtypes from `codegenie.types.identifiers`. Carries the seven fields of AC-1 (including `commit_sha: str`) and the `@model_validator(mode="after")` cross-field invariant. The emit site calls `model_dump(mode="json", exclude_none=True)` so the dict stored on `WorkflowSpanningEvent.payload` never carries a `None` value (arch §C9 types that dict without `None`).
2. **Orchestrator emit site (extension of S6-04).** In `RemediationOrchestrator.run(...)`'s `finally`, build a `BenchReplayablePayload` from the closing state — `input_snapshot_sha256` from `repo_snapshot.sha256`; `commit_sha` from the repo HEAD the orchestrator already resolved for the branch name; `transform_diff_bytes_sha256` from `transform.diff_bytes_sha256` **or `None`** when there is no transform (including the crash-before-`transform`-assigned path — the `finally` must defensively handle an unbound `transform`); `outcome_kind` from the `RemediationOutcome.kind` (`"failed"` on the exception path); identifiers from the resolution + recipe match. Emit via `event_log.emit_spanning(...)` exactly once. Flush after.
3. **Backfill integration test.** New file `tests/integration/test_phase65_backfill_hook.py`. Sequential loop over the 10 fixtures sharing one `tmp_path` workspace so all 10 workflows append to the same spanning stream. Asserts every AC-5 sub-item. The load-bearing helper is split (functional core / imperative shell — see Notes): a pure `_bench_case_from_event(event) -> BenchCaseContract` mapping (table-testable, no I/O) and a thin `_synthesize_bench_case(event, cases_root) -> Path` shell that writes `case.toml` + `input/` + `expected/`. Both deterministic, single-pass, no I/O beyond `tmp_path` writes, no wall-clock.
4. **Phase 6.5 contract snapshot.** Since Phase 6.5 has not shipped yet (per CLAUDE.md "Phases 3, 5, 6.5 — Designed but not implemented"), the test vendors Phase 6.5's `BenchCase` shape as a contract snapshot under `tests/integration/_phase65_contract.py` carrying exactly the documented `case.toml` fields (AC-6). When Phase 6.5 lands, its maintainer replaces the snapshot with a real `from codegenie.eval.models import BenchCase` and deletes the vendored shape. This is the same `test_phase5_contract_snapshot.py` pattern from S6-06.
5. **Operator runbook.** `docs/operations/phase03-runbook.md`. Use the four headings above; ≤ 60 lines of content. Include verbatim CLI invocations for copy-paste. Cross-reference the ADRs (ADR-0005 for the BLAKE3 chain framing, ADR-0011 for what the chain does / does not detect). Add a `## See also` block linking `phase-arch-design.md` and `final-design.md`.
6. **mkdocs nav.** If `mkdocs.yml` has an `operations:` section, add the runbook there; if not, surface the file under the existing phases nav with a one-line note (do not invent a new top-level nav for a single page).

## TDD plan — red / green / refactor

There are **two** red tests: the integration backfill test, and the orchestrator emit-path unit test. Both must exist, committed, and fail for the right reason before any production code is written.

### Red 1 — orchestrator emits on every exit path (unit)
Test file path: `tests/unit/transforms/test_orchestrator.py` (extension)

```python
import pytest

EXIT_PATHS = ["validated", "not_applicable", "requires_human_review", "failed",
              "exception_before_transform"]


@pytest.mark.parametrize("exit_path", EXIT_PATHS)
def test_run_emits_exactly_one_bench_replayable(exit_path, fake_event_log, orchestrator_for) -> None:
    """Why it matters: AC-2/AC-3 — Phase 6.5 backfill needs one bench_replayable
    per workflow on every termination, including the crash-before-Transform path.
    A happy-path-only emit silently drops the negative cases the adversarial bench
    needs; a double-emit corrupts the case count."""
    orch = orchestrator_for(exit_path, event_log=fake_event_log)
    try:
        orch.run()
    except Exception:
        pass  # exception_before_transform path: run() raises; finally must still emit
    bench = [e for e in fake_event_log.spanning if e.event_type == "bench_replayable"]
    assert len(bench) == 1, f"{exit_path}: expected 1 bench_replayable, got {len(bench)}"
    expected_kind = "failed" if exit_path == "exception_before_transform" else exit_path
    assert bench[0].payload["outcome_kind"] == expected_kind
    # ADR-0005: bench_replayable is spanning-only — never on the internal stream.
    internal = [e for e in fake_event_log.internal if e.event_type == "bench_replayable"]
    assert internal == []
```

### Red 2 — ten workflows backfill mechanically into Phase-6.5-valid cases (integration)
Test file path: `tests/integration/test_phase65_backfill_hook.py`

```python
import sys
import json
import tomllib
from pathlib import Path

import zstandard

from codegenie.plugins.bench_replayable import BenchReplayablePayload
from codegenie.plugins.events import WorkflowSpanningEvent
from tests.integration._phase65_contract import BenchCase  # vendored Phase 6.5 shape (AC-6)

FIXTURES = [
    "express-cve-2024-21501", "monorepo-workspaces", "transitive-only-cve",
    "peer-dep-conflict", "major-bump-required", "breaking-test-suite",
    "stale-scip", "malformed-package-json", "malicious-npmrc",
    "postinstall-canary",
]
_FORBIDDEN_LLM = {"anthropic", "langgraph", "openai", "langchain", "transformers"}


def _read_spanning(events_path: Path) -> list[WorkflowSpanningEvent]:
    raw = zstandard.ZstdDecompressor().decompress(events_path.read_bytes())
    return [WorkflowSpanningEvent.model_validate_json(line)
            for line in raw.splitlines() if line]


def test_ten_workflows_emit_bench_replayable_and_backfill_mechanically(
    tmp_path: Path, run_remediate_against_fixture
) -> None:
    """Why it matters: Phase 6.5's promise — `codegenie eval backfill` lifts
    ≥10 cases mechanically — is unmeetable if the producer payload is missing
    fields or the consumer needs human glue. The mechanical-not-LLM contract
    is the cardinal G9 commitment (phase-arch-design.md §Goals)."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    for fx in FIXTURES:
        run_remediate_against_fixture(fx, workspace=workspace)

    spanning = workspace / ".codegenie" / "events" / "spanning" / "append.jsonl.zst"
    assert spanning.exists(), "spanning stream not produced"
    events = _read_spanning(spanning)
    bench_events = [e for e in events if e.event_type == "bench_replayable"]

    # Exact count, no double-emit (AC-5.3): all 10 fixtures reach the orchestrator.
    assert len(bench_events) == 10
    assert len({e.workflow_id for e in bench_events}) == 10

    payloads = [BenchReplayablePayload.model_validate(e.payload) for e in bench_events]
    # Payload field assertions (AC-5.4).
    for p in payloads:
        assert p.input_snapshot_sha256 and p.commit_sha
        if p.outcome_kind == "validated":
            assert p.transform_diff_bytes_sha256 is not None
        else:
            assert p.transform_diff_bytes_sha256 is None
    assert any(p.outcome_kind == "not_applicable" for p in payloads)  # peer-dep / major-bump
    assert any(p.outcome_kind == "validated" for p in payloads)       # express-cve

    cases_root = tmp_path / "bench" / "vuln-remediation" / "cases"
    before = set(sys.modules) & _FORBIDDEN_LLM
    for ev in bench_events:
        _synthesize_bench_case(ev, cases_root)  # shell over a pure event->BenchCase mapping
    after = set(sys.modules) & _FORBIDDEN_LLM
    assert after == before, f"synthesis imported LLM SDK(s): {after - before}"

    # Contract conformance — the load-bearing assertion (AC-5.6).
    case_dirs = sorted(cases_root.iterdir())
    assert len(case_dirs) == 10
    for d in case_dirs:
        assert (d / "input").is_dir() and (d / "expected").is_dir()
        case = BenchCase.model_validate(tomllib.loads((d / "case.toml").read_text()))
        assert case.task_class == "vuln-remediation"
        assert case.source == "outcome-ledger-derived"
        assert case.commit_sha
        assert case.added_at == case.last_validated_at
        pointer = tomllib.loads((d / "input" / "input-pointer.toml").read_text())
        assert pointer["input_snapshot_sha256"]

    # Determinism / idempotence (AC-5.7).
    second = tmp_path / "bench2"
    for ev in bench_events:
        _synthesize_bench_case(ev, second)
    for d in case_dirs:
        twin = second / d.name / "case.toml"
        assert twin.read_bytes() == (d / "case.toml").read_bytes()
```

State why each fails: Red 1 fails because `RemediationOrchestrator` does not yet emit `bench_replayable` (and the `fake_event_log` / `orchestrator_for` fixtures must be added). Red 2 fails first at import — `codegenie.plugins.bench_replayable` and `tests/integration/_phase65_contract.py` do not exist — and would then fail because `_synthesize_bench_case` does not exist. **Prerequisite:** the 10 fixture repos (S8-01) and the `run_remediate_against_fixture` fixture (S8-02) must already be on disk; if they are not, Red 2 fails for an unrelated reason — confirm the Depends-on chain is satisfied before starting.

### Green — minimal pass
- Ship `BenchReplayablePayload` per AC-1 (seven fields, the `@model_validator` cross-field invariant, `= None` defaults on the two optional fields).
- Extend `RemediationOrchestrator.run(...)`'s `finally` to emit exactly one `bench_replayable` per AC-2/AC-3, using `model_dump(mode="json", exclude_none=True)`; defensively handle the unbound-`transform` exception path.
- Add the `fake_event_log` / `orchestrator_for` unit fixtures.
- Vendor `tests/integration/_phase65_contract.py` carrying the documented Phase 6.5 `BenchCase` schema (AC-6).
- Implement the synthesis as a **pure mapping + thin shell**: `_bench_case_from_event(event) -> BenchCaseContract` (pure: `outcome_kind → disposition` via a `Final` dict, `case_id` from the three hashes, `source="outcome-ledger-derived"`, `task_class="vuln-remediation"`, `difficulty="backfill-unrated"`, timestamps from `event.timestamp`, `commit_sha` from the payload) and `_synthesize_bench_case(event, root) -> Path` (shell: writes `case.toml` + `input/input-pointer.toml` + an `expected/` artifact keyed off `transform_diff_bytes_sha256`).
- Write the runbook to satisfy the four-heading shape (AC-8).

### Refactor
- Extract the spanning-stream reader (`_read_spanning`) into a `tests/_helpers.py` shared with `tests/fence/test_no_llm_spend.py`'s YAML walker (both consume `.codegenie/` artifacts). Keep the typed return (`list[WorkflowSpanningEvent]`), not `list[dict]`.
- The `run_remediate_against_fixture` pytest fixture is **reused as-is from S8-02** (`tests/integration/test_end_to_end_express_cve.py`) — including S8-02's jail-vs-stub strategy. S9-04 does not re-invent or re-decide invocation plumbing. If S8-02 has not yet shipped the fixture as importable, that is a blocking dependency, not work for this story.
- Document at the top of `bench_replayable.py` exactly which Phase 6.5 `case.toml` field each payload field maps to (a small ASCII table is fine) so future readers see the cross-phase contract — keep it in sync with the Context table.
- Edge cases from §Edge cases that touch this code: E4 (`peer-dep-conflict/`) and E6 (`major-bump-required/`) produce `NotApplicable` outcomes — the payload's `transform_diff_bytes_sha256` is `None` for these. **E10** (per arch §Edge cases: a concrete plugin *fails to load* → `PluginRejected(import_error)`, **exit 4 at the loader phase, before resolution**) produces **no** `bench_replayable` event, because the workflow exits before `RemediationOrchestrator.run(...)` — and therefore its `finally` — is ever entered. The 10-fixture portfolio for AC-5 is chosen so none of them hit E10; if a future fixture does, AC-5.3's exact count is adjusted with an inline comment. (validator: corrected — the prior text mislabelled E10 as "universal fallback substitution refused"; the conclusion was right but the label inverted the arch's framing.)

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/plugins/bench_replayable.py` | NEW — `BenchReplayablePayload` Pydantic schema (7 fields + cross-field `model_validator`). |
| `src/codegenie/transforms/orchestrator.py` | Extend `RemediationOrchestrator.run(...)`'s `finally` to emit exactly one `bench_replayable` on all five exit paths, using `model_dump(mode="json", exclude_none=True)`. |
| `tests/integration/test_phase65_backfill_hook.py` | NEW — 10 cases synthesized mechanically and validated against the Phase 6.5 `BenchCase` contract; no LLM SDK imported by the synthesis step. |
| `tests/integration/_phase65_contract.py` | NEW — vendored Phase 6.5 `BenchCase` shape pinned to `final-design.md`'s documented `case.toml` schema (contract snapshot until Phase 6.5 ships). |
| `tests/unit/transforms/test_orchestrator.py` | Extend — parametrized test over all five exit paths: each emits `bench_replayable` exactly once, on the spanning stream only. |
| `docs/operations/phase03-runbook.md` | NEW — 1-page runbook (run / artifacts / verify chain / surface to operators). |
| `mkdocs.yml` | Add the runbook to nav (or document why the existing nav already covers it). |

## Out of scope

- **Phase 6.5's `codegenie eval backfill` CLI** — owned by Phase 6.5 (not Phase 3). This story ships the **payload** and the **mechanical-synthesis pattern**; the CLI that lifts production cases ships with Phase 6.5.
- **Phase 4's solved-example store** (`.codegenie/solved/<task_class>/<example_id>.json`) — Phase 4 builds on top of `bench_replayable` additively. This story does not pre-empt the Phase 4 schema.
- **Sigstore anchoring of `bench_replayable` events** — Phase 16's hardening. The BLAKE3 chain detects local tamper; Sigstore would detect host compromise. Out of scope per ADR-0011 honest framing.
- **A `codegenie events query` CLI** — operators can `zstdcat | jq` in Phase 3 (`jq` is in `ALLOWED_BINARIES` per ADR-0012 specifically for this). A typed query CLI is Phase 13 operator-portal territory.
- **Bench files measuring the `bench_replayable` emit cost** — `bench_event_appender_throughput` (S9-03) already measures the spanning-stream write path. Single-event emit cost is dominated by the BLAKE3 + `fcntl.flock` round-trip already benchmarked.

## Notes for the implementer

- **Mechanical, not LLM-driven.** The before/after `sys.modules` delta (AC-5.8) is load-bearing. If the synthesis temptation is "just ask Claude to extract the case fields from the payload," that is exactly the failure mode this story exists to prevent. The synthesis must be a pure dict→file mapping; if a field cannot be mapped without inference, the payload schema is missing a field — surface that to ADR-0005. (This is precisely why hardening *added* `commit_sha` to the payload — it was un-derivable.)
- **`transform_diff_bytes_sha256` is `BlobDigest | None`, never `""`.** A `BlobDigest` is a 64-hex digest; the empty string is not a valid value of that type, and `None` is the honest "there is no transform" shape. The `@model_validator` ties `transform_diff_bytes_sha256 is not None` to `outcome_kind == "validated"` so the illegal combinations cannot be constructed. `recipe_id` follows the same `… | None` shape — do not average the two into one `""`-sentinel and one `None` (Rule 7).
- **Functional core / imperative shell.** Split the synthesis into a pure `_bench_case_from_event(event) -> BenchCaseContract` (no I/O — payload + event metadata → typed case) and a thin `_synthesize_bench_case(event, root) -> Path` write shell. The pure function is the load-bearing "mechanical, no LLM" contract and must be directly table-testable with events-and-dataclasses, with no `tmp_path` round-trip — mirrors the codebase's `_strip_comments(bytes) -> bytes` vs `load(path)` split.
- **`outcome_kind → disposition` is a catalog, not control flow.** Express it as a module-level `_DISPOSITION: Final[Mapping[str, str]]` dict and look it up — matches the codebase's "Module-level `Final` dicts for marker catalogs" convention; a reviewer sees all four rows at once. If `outcome_kind` is a `Literal`, a `mypy`-checkable exhaustiveness `assert` over the dict keys is cheap insurance.
- **Read spanning events as typed `WorkflowSpanningEvent`, not raw `dict`.** The model exists (S6-01); `model_validate_json` per line gives `e.event_type` / `e.payload` as `mypy`-checked accesses and catches producer/consumer drift — the exact class of bug this story is about.
- **`commit_sha` is a plain `str`, not a newtype.** Do **not** add a `CommitSha` row to `identifiers.py`. The codebase has a documented convention (`src/codegenie/schema/probes/index_health.schema.json`: commit SHAs are carried as raw strings — "not a newtype — commit SHAs are not kernel identifiers"). `IndexHealthProbe`, `scip_index.py`, and `coordinator/snapshot.py` all follow this. Forking it here would violate Rule 11.
- **`difficulty` has no mechanical source.** Phase 3 runs carry no difficulty signal. The synthesizer sets a documented constant default (`"backfill-unrated"`); a human curator or Phase 6.5's `eval backfill` may refine it. This is honest mechanical behaviour — do not infer a difficulty from the outcome (that would be a judgment, violating "Facts, not judgments").
- **`_synthesize_bench_case` is intentionally test-local.** It is a *pattern demonstration*; Phase 6.5's real `codegenie eval backfill` CLI re-implements the production version against its own (then-real) `BenchCase` import. Do not "DRY" it into `src/codegenie/` — the durable contract this story ships under `src/` is the `BenchReplayablePayload` schema; the synthesis helper is a disposable leaf (Rule 2 — one consumer is not a kernel).
- **`BlobDigest` is a `NewType` (S1-01).** Pass it through; do not stringify and re-construct. The smart-constructor `parse_blob_digest` belongs at the *boundary* (when reading a payload back off disk), not at the emit site (which constructs from already-typed values).
- **The runbook is 1 page on purpose.** If the implementer hits 80+ lines, something belongs in `phase-arch-design.md` instead. Operators read this in a hurry; bullet density matters.
- **`codegenie audit verify` already exists** (Phase 0). S6-05 extends it to verify the BLAKE3 chain on the spanning stream. The runbook documents the operator-facing invocation; the implementation is S6-05's.
- **`mkdocs.yml` nav additions can break the docs CI.** Run `make docs` locally before committing.
- **Phase 6.5 vendoring is a documented contract snapshot.** When Phase 6.5 ships, the maintainer of that phase replaces `tests/integration/_phase65_contract.py` with a real import + deletes the vendored shape. Until then, the vendored shape must match `final-design.md`'s documented `case.toml` schema exactly (AC-6) — a snapshot that has silently drifted is worse than none. Surface drift via the same `test_phase5_contract_snapshot.py` pattern S6-06 uses.
- **The orchestrator's `finally` runs even on exception** — that's the point of `finally`. If the workflow crashed before assigning a `transform`, the emit code must defensively handle the partial state (`outcome_kind="failed"`, `transform_diff_bytes_sha256=None`). AC-3's `exception_before_transform` parametrization is the regression test for this.
- **This is a slow integration test.** Ten `codegenie remediate` runs is multi-minute; it inherits S8-02's jail/skip discipline. Confirm it does not destabilise the `--cov-fail-under=85` gate when run as a narrow subset (use `--no-cov` for ad-hoc subset runs, per CLAUDE.md).
- **Match `S9-02`'s docstring discipline.** Every test docstring opens with the *why* (G9 commitment, mechanical contract) before the *how* — future readers should understand the load-bearing rationale at a glance.
