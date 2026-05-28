# Validation report — S4-02 `codegenie eval run` subcommand

**Validated:** 2026-05-28
**Validator:** phase-story-validator
**Verdict:** HARDENED
**Findings:** 19 total — 8 block, 9 harden, 2 nit

The story's *goal* (drive the harness end-to-end on the stub bench, emit JSONL, persist a
chained `BenchRunReport`, partition exit codes) is sound and traces directly to
`phase-arch-design.md §Exit criteria #6`. **But the Implementation Outline, six ACs, and
every line of TDD test code contradict the hardened sibling contracts** (S4-01, S3-01,
S3-02, S3-06, S2-01, S2-02, S2-03, S2-04, S4-04, S4-05 are all `HARDENED`/`Ready-HARDENED`).
An executor following the story verbatim would write code against an API surface that does
not exist and tests that import a symbol S4-01 deliberately renamed. Every issue is
patchable in place → HARDENED, not RESCUE.

Conflict-resolution priority applied: **Consistency > Coverage > Test-Quality > Design-Patterns**.
The dominant lens here is Consistency — the story drifted from contracts that were hardened
*after* it was written.

---

## Critic: Consistency (lens: does the story contradict the hardened arch / ADRs / sibling stories?)

### F-CON-1 (BLOCK) — wrong Click symbol name
Every TDD snippet imports `from codegenie.eval.cli import eval as eval_group`. S4-01
(HARDENED 2026-05-28, AC-1 + its Validation note F-CON-3/F-DP-3) **renamed the exported
group to `eval_group`** (`@click.group(name="eval")`) specifically to avoid shadowing the
`eval()` builtin. There is no `eval` symbol and no alias. All imports → `from codegenie.eval.cli import eval_group`.

### F-CON-2 (BLOCK) — the `Runner(...)` constructor + `run_eval()` signature do not exist
Outline steps 6–7 prescribe
`Runner(task_class=tc, cases=cases, concurrency=…, max_cost_usd=…, no_cache=…)` then
`asyncio.run(runner.run_eval())`. The hardened runner is **stateless** (`Runner()` takes no
args) and exposes two methods:

- `Runner().plan(task_class_name, *, sut_digest_fn, bench_root, out_dir, run_started_iso, cassette_root, harness_version, registry=None) -> RunPlan` (S3-01 AC-… / line 60).
- `Runner().run_eval(plan, *, system_under_test, rubric_runner, cache_dir, timeout_per_case_seconds, concurrency=None, on_score=None, max_cost_usd=5.0, out_dir) -> BenchRunReport` (S3-06 AC-2 — the audit-writing composition root).

`run_eval` takes a **`plan`**, not zero args; `max_cost_usd`/`concurrency` are `run_eval`
kwargs, not constructor args; there is no `no_cache` parameter anywhere (see F-CON-8).

### F-CON-3 (BLOCK) — `verify(...)` returns, it does not raise; and `plan()` already verifies
Outline step 5 says `vr = verify(out_dir=out)` and tags it "`ChainTamperDetected` (→ 5)".
Two errors: (a) S2-04 AC-4 pins `verify(out_dir, since=None) -> VerifyResult` — it **returns**
`VerifyResult(ok=False, …, reason=…)`; it never raises `ChainTamperDetected`. (b) `Runner.plan()`
(S3-01 AC-4) **already calls `audit.verify()` internally** and raises `ChainTamperDetected`
(positional args) on `ok is False`, and `BenchCaseDigestMismatch` on a poisoned case, *before
any SUT call*. So the CLI must **not** call `verify` separately for the run path — the exit-5
(tamper) and exit-6 (digest) paths come from `plan()` raising, caught by S4-01's `main()`
mapper. Remove the redundant `verify` call from the `run` body.

### F-CON-4 (BLOCK) — `chain_head` is filled by `run_eval`, not the CLI
Notes-for-implementer says "the CLI must use `report.model_copy(update={"chain_head": head})`".
S3-06 AC-2 makes `run_eval`'s body do exactly that and **return the report with `chain_head`
already populated**. The CLI receives a finalized report and emits it verbatim. There is no
`head` value in the CLI's scope (`run_eval` discards the `write_run_record` return path
internally). The stdout-JSONL and on-disk-JSON share `chain_head` because S2-04 AC-3a pins the
on-disk record's `chain_head` to equal the returned head — not because the CLI re-stamps it.

### F-CON-5 (BLOCK) — audit filename derivation is owned by `write_run_record`, and is wrong here
AC (line 46) claims `<utc-iso>` = `report.run_started_iso` and `<short>` = `report.run_id[:8]`.
S2-04 AC-1 + impl line 144 pin the filename to `f"{utc_iso}-{secrets.token_hex(4)}.json"` —
`<short>` is a **random 8-hex token**, not `run_id[:8]`, and `<utc_iso>` is derived inside the
writer (UTC ISO, `:`→`-`), not from `run_started_iso`. The CLI does not construct or even see
the path (`run_eval` calls `write_run_record` internally and returns only the report). The CLI
learns the file exists by globbing `out`. All filename-derivation assertions must be replaced
with "exactly one new `*.json` appeared under `out` and it round-trips to a `BenchRunReport`
whose `chain_head` equals the emitted aggregate's `chain_head`".

### F-CON-6 (BLOCK) — `PromotionGate` API: missing `target_tier`, missing `TierConfig` construction, incomplete-report raise
AC (line 43) + outline step 9 say `gate = PromotionGate(…); verdict = gate.evaluate(report)`.
S4-04 pins `PromotionGate(tier_config: TierConfig, registry=None)` (constructed from
`load_tier_config(Path("docs/trust-tiers.yaml"))`) and `evaluate(report, target_tier, *, evidence_window=()) -> PromotionVerdict`. So:
- `--with-verdict` needs a **target tier** — there is no `--target-tier` flag on `run`. The
  honest options: (a) add `--target-tier` to `run` (mirrors `promote-verdict`), or (b) derive
  the next tier from `TierConfig.current_tiers[task_class]`. This must be specified. (Recommended:
  add `--target-tier`, optional, defaulting to the task class's current tier — keeps the verdict
  meaningful and the seam explicit.)
- `evaluate` **raises `IncompleteReportForPromotion` when `report.complete is False`** (S4-04
  Goal). A cost-capped run with `--with-verdict` would raise. Since the run exits 2 on
  `complete is False` regardless, the CLI must **gate the verdict on `report.complete is True`**
  (skip verdict + recommendation, exit 2) — do not call `evaluate` on a partial report.

### F-CON-7 (BLOCK) — `write_recommendation` signature
Outline step 9 invokes `write_recommendation(verdict, …)` against a full path. S4-05 pins
`write_recommendation(verdict: PromotionVerdict, out_dir: Path = Path(".codegenie/eval/recommendations")) -> Path`
— it takes the **directory**; the `<utc-iso>.json` filename is derived inside the writer.
Call it `write_recommendation(verdict, recommendations_dir)`.

### F-CON-8 (BLOCK) — `--no-cache` has no wiring point in the hardened runner
S3-02 F-DP-8 **explicitly deferred** the `CachePort`/cache-disable injection as YAGNI
("Today: module-level imports"). `Runner.execute`/`run_eval` carry `cache_dir` but no
`no_cache` flag, and `cache.get`/`cache.put` are module-level imports with no per-run bypass.
The story's promised semantics ("reads bypassed, **writes still land in the canonical cache** so
a re-run hits") are not buildable without reviving the deferred seam. Resolution that needs
**zero runner change**: `--no-cache` routes the run's `cache_dir` to a fresh ephemeral directory
(e.g. `tempfile.mkdtemp()` or `out/.nocache-<token>/`). Every `get` misses (cold dir); writes
land in the throwaway dir and are discarded; the canonical cache is never touched, so a
subsequent run *without* `--no-cache` is still cold. AC + Notes rewritten to this; the original
"writes still persist to the canonical cache" claim is removed as contradicting S3-02 F-DP-8.

### F-CON-9 (HARDEN) — test paths must mirror the eval convention
"Files to touch" puts tests at `tests/unit/test_cli_run_flags.py` and
`tests/integration/test_cli_run.py` (flat). S4-01 (F-CON-1) established that **eval unit tests
live under `tests/unit/eval/`**, and the repo already groups CLI integration tests under
`tests/integration/cli/`. Move to `tests/unit/eval/test_cli_run_flags.py` and
`tests/integration/eval/test_cli_run.py`. (No existing-file collision either way, but the
convention is load-bearing for discoverability.)

### F-CON-10 (HARDEN) — `load_task_class` / `load_cases` are not called directly on the run path
Outline steps 2–4 call `load_task_class(task_class, bench_root)` then `load_cases(tc)` then
construct `Runner(...)`. `plan()` (S3-01) **resolves the task class and loads cases
internally**. The CLI passes the task-class *name* to `plan()`. The `--cases` glob therefore
filters `plan.cases` *after* plan returns — see F-COV-3.

---

## Critic: Coverage (lens: do the ACs collectively guarantee the goal? edge cases?)

### F-COV-1 (BLOCK) — SUT / rubric_runner / sut_digest_fn sourcing is undesigned
The single biggest implementability gap. `plan()` needs `sut_digest_fn`; `run_eval()` needs
`system_under_test` **and** `rubric_runner`. The CLI is handed only a task-class *name* string.
`TaskClass` (S1-03 AC-2, frozen 6-field dataclass) carries `rubric_class` but **no SUT** — so
the rubric_runner is derivable (build from `task_class.rubric_class` via S3-03's subprocess
RubricRunner) but the SUT is not. The arch (§Scenario 1) hard-binds `VulnRemediationSut` to
`vuln-remediation` yet `§cli.py` never says how the name→SUT mapping happens. Without resolving
this, `codegenie eval run --task-class=stub-task-class` cannot run and the integration test
cannot be written.

**Resolution (consistent with the repo's Open/Closed registries — see Design-Patterns):** a
small SUT-resolver registry `codegenie.eval.sut_registry` with `@register_sut(task_class_name)`
+ `resolve_sut(name) -> SystemUnderTest` (and a matching `sut_digest_fn`), mirroring
`default_registry` (S1-03), `plugins/registry.py`, and `transforms/signal_kinds.py`. The stub
bench registers a stub SUT through this seam; S5 registers `VulnRemediationSut` by *addition*
(zero CLI edits). The rubric_runner is built from `task_class.rubric_class`. New ACs (AC-3, AC-12)
make the seam + its observable extension constraint testable. **This is a real new seam; the
executor should confirm via a one-paragraph ADR (phase-architect) if the cost looks high — but
the design is forced by the goal, so it is in scope, not gold-plating.**

### F-COV-2 (HARDEN) — missing AC: `plan()`-raised exits are exercised end-to-end via the CLI
S4-01 tested the mapper at the helper boundary. S4-02 is the first story that proves the *full*
CLI path: a poisoned-case fixture → exit 6, a tampered chain → exit 5, an unknown task class →
exit 3, a missing `bench/` → exit 4 — all surfaced by `plan()` raising and `main()` mapping.
Added AC-9 with concrete fixtures (reuse S2-02's digest-mismatch + S2-04's chain-tamper fixture
builders).

### F-COV-3 (HARDEN) — `--cases` glob semantics vs `plan()` ownership
`plan()` builds `cases` + the `cache_keys` mapping with the invariant
`set(cache_keys.keys()) == {c.case_id for c in cases}` (S3-01 AC-1a). The glob filter must
preserve that invariant: `filtered = tuple(c for c in plan.cases if fnmatch(c.case_id, glob))`;
empty → exit 1 naming the glob + available ids; else
`plan = dataclasses.replace(plan, cases=filtered, cache_keys={c.case_id: plan.cache_keys[c.case_id] for c in filtered})`
(re-runs `__post_init__`, invariant holds). AC-2 + AC-4 rewritten to pin this.

### F-COV-4 (HARDEN) — empty-bench / zero-matching-cases distinction
`--cases` non-match → exit 1 (operator error). But a task class with *zero cases on disk* is a
legitimate state (S2-02 AC-11 / S3-01 AC-12 — `plan()` succeeds with `cases=()`). The two must
not collapse. Added AC covering: zero-case bench with no `--cases` → exit 0, aggregate with
`passed_count=0`, no per-case lines; `--cases` glob matching nothing → exit 1.

### F-COV-5 (NIT) — `--concurrency` lower bound
`--concurrency=0` / negative must be a click-validation error (exit ≠ 0 via click's usage path,
not a runtime crash). Pinned with `click.IntRange(min=1)`.

---

## Critic: Test-Quality (lens: would the TDD plan catch a wrong implementation?)

### F-TQ-1 (BLOCK) — the integration tests assume a non-existent fixture + injection path
`stub_bench_root` / `stub_bench_root_expensive` fixtures invoke `runner.invoke(eval_group, [...])`
expecting an end-to-end run, but there is no shown mechanism for the CLI to obtain the stub SUT
(F-COV-1). The tests must register the stub SUT into the `sut_registry` (via the resolver seam)
so the CLI's `resolve_sut("stub-task-class")` returns it. Rewrote the integration fixtures to
build on S3-01's `tests/helpers/bench.py:stub_task_class_fixture` + S3-02's stub SUT and to
register the SUT through the seam.

### F-TQ-2 (HARDEN) — JSONL shape test must pin types, not just key presence
The aggregate-line test only checks `k in agg`. A mutant emitting `lower_bound_95` as a string,
or `complete` as `1`, would pass. Pin `isinstance(agg["lower_bound_95"], float)`,
`agg["complete"] is True`, `isinstance(agg["isolation_class"], str) and agg["isolation_class"] == "subprocess"`,
and that the per-case `kind=="case"` lines number exactly `len(cases)` and carry `score` as a
float in `[0,1]`.

### F-TQ-3 (HARDEN) — chain_head single-source must be tested by equality, not by existence
The original test only asserts `agg["chain_head"]` is truthy and that the on-disk record's head
equals it. Strengthen: assert the **on-disk `chain_head` equals the stdout aggregate
`chain_head`** AND that `audit.verify(out).ok is True` after the run (proves the appended record
is chain-valid, catching a mutant that emits a head the writer never persisted). Mirrors S3-06
AC-15(iii).

### F-TQ-4 (HARDEN) — cost-cap test must assert the partial contract precisely
Pin `on_disk["complete"] is False` AND `on_disk["run_id"].startswith("partial:")` AND
`len(on_disk["per_case"]) == len(cases)` (S3-06 AC-7 guarantees `_Aborted` placeholders fill the
tuple) AND that **no `CancelledError` escaped** (catch_exceptions=False + exit 2, not a crash).

### F-TQ-5 (HARDEN) — `--format=human` test is too weak
Asserting the substrings `mean`/`stddev`/`lower_bound_95` appear lets a mutant that dumps the
JSON repr (which also contains those keys) pass. Strengthen: assert **no line parses as a JSON
object** (`json.loads` raises on every line) AND the three statistic *values* appear formatted
to a fixed precision AND there is one table row per case (count rows = `len(cases)`).

### F-TQ-6 (NIT) — deferred-import test must run after this story lands
Re-assert S4-01's cold-start guard (`tests/unit/eval/test_cli_scaffold.py`) stays green: after
`import codegenie.eval.cli`, no `pydantic`/`yaml`/`bench.`/`runner` modules are loaded. The
`run` body's imports (runner, audit, promotion, pydantic, the sut_registry) must all be
function-scoped. Pinned as an explicit AC rather than prose.

---

## Critic: Design-Patterns (lens: easy to extend by addition? misses registry/strategy/DIP?)

### F-DP-1 (HARDEN→AC) — the SUT resolver is the third sibling registry; make the seam observable
The repo already runs three decorator-registries (`default_registry`, `plugins/registry`,
`transforms/signal_kinds`) plus the probe registry — the rule-of-three is *well* past. The SUT
resolver (F-COV-1) should follow the identical kernel discipline (origin-tracking collision
error, `Final` default singleton, `registry=` DI kwarg for test isolation). Because it crosses
the rule-of-three threshold and the goal demands extensibility (S5/S6 add SUTs by addition),
the extension constraint is elevated to an **observable AC**: "registering a new task class's SUT
requires zero edits to `cli.py`" (AC-12), phrased as a constraint, not a pattern-name mandate.

### F-DP-2 (HARDEN) — `_emit_jsonl` / `_emit_human` are a Strategy keyed on `ctx.obj["format"]`
Keep them as two small private helpers dispatched by a module-level
`_EMITTERS: Final[Mapping[str, Callable[[BenchRunReport, TextIO], None]]]` mapping (mirrors the
codebase's `_DISPATCH`/marker-tuple idiom and S4-01's `_EXIT_CODE_TABLE`). Adding a future
`--format=csv` is then a one-row data edit, not an `if/elif` branch. NOT over-abstraction —
there are already two formats today (`human`, `jsonl`), so the map is the rule-of-two boundary
and matches the established Open/Closed seam. Surfaced in Notes; the dispatch-map is not forced
as an AC (Rule 2 — two helpers behind a dict is the ceiling; no Protocol/registry).

### F-DP-3 (NIT) — `Stream` type is `TextIO`; emitters take the stream as a param (testability)
Pass the output stream into the emitters (default the CLI's stdout) so tests capture without
monkeypatching `click.echo`. Already implied; pinned in Notes.

---

## Research

No findings tagged `NEEDS RESEARCH`. Every pattern (decorator-registry kernel, Strategy-via-dict,
`dataclasses.replace` to preserve a frozen invariant, glob-filter via stdlib `fnmatch`) is
precedented in this repo. Stage 3 skipped.

---

## Edits applied to the story

- **Status** `Ready` → `HARDENED (phase-story-validator, 2026-05-28)`.
- **Depends-on** expanded: added S3-01 (`plan`), S2-01 (`load_task_class`), S2-03 (cache_dir
  semantics), S4-04 (`PromotionGate`), S4-05 (`write_recommendation`); annotated the ones whose
  contracts the story had drifted from.
- **Context ¶2** rewrote the chain_head / single-source claim to match S3-06+S2-04 ownership.
- **Acceptance criteria** rewritten end-to-end (F-CON-1..8, F-COV-1..5, F-DP-1): correct Runner
  API, `plan()`-owns-verify, SUT-resolver seam + observable extension AC, glob-filter via
  `dataclasses.replace`, ephemeral-cache `--no-cache`, `--target-tier` for `--with-verdict`,
  complete-gated verdict, filename-by-glob-not-derivation, typed JSONL assertions, human-format
  no-JSON assertion, deferred-import re-assertion.
- **Implementation outline** rewritten to the real two-call flow (`plan()` → glob-filter →
  `run_eval()`), SUT/rubric/sut_digest_fn sourcing, format dispatch map.
- **TDD plan** all code rewritten: `eval_group` import, `tests/unit/eval/` + `tests/integration/eval/`
  paths, SUT-seam registration in fixtures, typed assertions, exit-3/4/5/6 end-to-end cases,
  cost-cap partial contract, human-format negative-JSON check.
- **Files to touch** corrected paths + added `src/codegenie/eval/sut_registry.py` (new seam) and
  the SUT-seam test helper.
- **Out of scope** added: real SUTs (S5/S6), `CachePort` revival, cross-host run lock,
  `promote-verdict` subcommand (S4-03+).
- **Notes for implementer** rewritten to the corrected contracts.

## Surfaced, not auto-fixed

- The **SUT-resolver registry** is a genuinely new seam the phase arch never named. It is forced
  by the goal and consistent with the repo's three existing registries, so it is left in scope —
  but the executor should drop a one-paragraph ADR (`phase-architect`) recording the
  `name → SystemUnderTest` resolution decision, since downstream stories (S5-05, S6-03, Phase 9
  Temporal SUT bridge) will all consume it. Flagged here; no ADR auto-written (Rule 3).
- Arch §cli.py + the C2 class diagram (`run_eval(task_class_name, *, system_under_test, …)`,
  line 175) drifted from the hardened `run_eval(plan, …)` (S3-06). Story follows the hardened
  story (correct). Flagged for a follow-on doc-sweep PR; not auto-edited.
