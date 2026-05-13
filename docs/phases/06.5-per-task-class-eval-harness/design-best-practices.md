# Phase 6.5 — Per-task-class eval harness + first benches: Best-practices design

**Lens:** Best practices — idiomatic, maintainable, conventional, well-tested.
**Designed by:** Best-practices design subagent
**Date:** 2026-05-12

## Lens summary

I optimized for a single thing: **the next engineer who opens `src/codegenie/eval/` should recognize every pattern they see.** Same decorator shape as `@register_probe` (Phase 0 S2-05) and `@register_signal_kind` (Phase 5 ADR-0003); same `frozen=True, extra="forbid"` Pydantic discipline as `ObjectiveSignals` (Phase 5 ADR-0014); same Protocol-when-structural / ABC-when-default-behavior split as Phase 5 ADR-0006; same audit-record layout as Phase 0's `RunRecord` (ADR-0004). No new abstractions where an existing one already fits. The only net-new package is `src/codegenie/eval/`; the only net-new top-level directory is `bench/`. I explicitly **deprioritized**: parallel/sharded eval throughput (correctness > speed at this surface size; nightly cadence absorbs a serial runner), adversarial bench-case curation, sandboxing the rubric itself (Phase 16 territory per ADR-0016 §Open Q5), and any LLM-driven helpers (would violate "no LLM in gather pipeline" — and the *harness* is gather-shaped: deterministic, cacheable, auditable).

## Conventions honored

- **No LLM in the gather pipeline** (`CLAUDE.md`, production design.md §2.1, ADR-0005) → The harness itself is fully deterministic. The *system under test* invokes LLMs (via Phase 4 cassettes in CI per ADR-0016 §Tooling), but the rubric, runner, registry, promotion-gate evaluator, and audit writer never call an LLM. A `test_eval_package_imports_no_llm_sdk.py` AST test (mirror of Phase 0's `test_pyproject_fence.py` and `test_import_linter_blocks_heavy_from_cli.py`) enforces this structurally.
- **Facts, not judgments** (design.md §2.2) → `BenchScore` reports per-case *facts*: `passed`, `score`, `breakdown`, `failure_modes`, `cost_usd`. The *judgment* "is this task class ready to promote bronze → silver?" remains a deliberate, ADR-anchored human decision (ADR-0016 §Decision §4 — "promotion remains a deliberate, ADR-anchored decision"). The `PromotionVerdict` data model encodes "what the evidence says"; the act of promotion is a separate PR with CODEOWNERS sign-off.
- **Honest confidence** (design.md §2.3, Phase 5 ADR-0014 lineage) → `BenchScore` carries `failure_modes: tuple[str, ...]` and `breakdown: dict[str, float]`. A 0.9 aggregate with one `block`-severity failure mode is *not* a pass — the promotion gate reports both. Provenance lives on `BenchCase` (`source: Literal["curated", "outcome-ledger-derived", "regression-converted"]`, `commit_sha`, `added_at`, `last_validated_at`) per ADR-0016 §Decision §6.
- **Extension by addition** (design.md §2.5, ADR-0016 §Decision §3) → New task classes register via one decorator + one bench directory. Zero edits to `src/codegenie/eval/` are needed to add `migration-chainguard-distroless` (Phase 7), `agentic-recipe-authoring` (Phase 15), or any future class. The fence-CI test makes this enforceable: a `@register_task_class("foo")` without `bench/foo/` fails CI with a named diagnostic.
- **Humans always merge** (design.md §2.8, ADR-0009, ADR-0016 §Decision §4) → `PromotionGate.evaluate(task_class, current_tier) -> PromotionVerdict` is a *read-only verdict source*. Nothing in `src/codegenie/eval/` writes a tier change. Tier state lives in a hand-edited YAML (`docs/trust-tiers.yaml`, see Components) reviewed via PR — the same shape as `CODEOWNERS`.
- **Determinism over probabilism for structural changes** (design.md §2.4, `CLAUDE.md`) → The harness is deterministic given a fixed cassette set + fixed bench cases + fixed rubric. Two engineers running `codegenie eval run --task-class=vuln-remediation` on the same commit produce byte-identical `BenchScore` aggregates. The audit record's `run_id` is content-addressed (SHA-256 of inputs + outputs) so duplicate runs are detectable.
- **Progressive disclosure** (design.md §2.7) → `BenchCase` carries paths, not inlined fixtures. The runner loads case bytes lazily. The audit record indexes per-case results by `case_id`; full per-case output is written to `.codegenie/eval/runs/<run-id>/cases/<case-id>.json`, not into the aggregate JSON. Same pattern as Phase 0's `RepoContext` indexing raw artifacts under `.codegenie/context/raw/`.
- **Cost is observable** (design.md §2.9, ADR-0024) → `BenchScore.cost_usd: float` is mandatory per ADR-0016 §Open Q3. The runner sums per-case costs into the aggregate `BenchRunReport.total_cost_usd` and emits it as a structured-log field that Phase 13's cost ledger can ingest without code change.

## Goals (concrete, measurable)

- **Public API surface:** ≤ 8 exported names from `codegenie.eval` — `register_task_class`, `TaskClassRegistry`, `default_registry`, `TaskClass`, `BenchCase`, `BenchScore`, `Rubric`, `run_eval`. (Plus a `cli` submodule import; CLI commands are not part of the Python API.)
- **Test coverage target:** ≥ 90% line, ≥ 80% branch on `src/codegenie/eval/` — matches Phase 0's ratcheting (`--cov-fail-under=85` floor, with eval-specific bump in `pyproject.toml`).
- **Cyclomatic complexity ceiling per function:** 8 (enforced by ruff `C901` configured at 8). The runner's per-case dispatch is the only place near the ceiling.
- **Net-new top-level packages:** 1 (`src/codegenie/eval/`).
- **Net-new directories at repo root:** 1 (`bench/`).
- **Net-new ADRs in `06.5/ADRs/`:** 4 — `0001-eval-registry-mirrors-probe-registry.md`, `0002-benchscore-frozen-extra-forbid.md`, `0003-rubric-as-protocol.md`, `0004-promotion-gate-read-only-verdict.md`. Each cites Phase 5 ADR-0016 as the parent contract.
- **Net-new runtime dependencies in `[project].dependencies`:** 0. Pydantic v2, click, pyyaml, structlog are already pinned (Phase 0 S1-01). Bench cases use stdlib `pathlib` + `tomllib` (3.11+) for `case.toml`.
- **Net-new optional dependencies in `[project.optional-dependencies].eval`:** 0 at landing. Slot is reserved per roadmap §Phase 6.5 Tooling for future harness-only deps; left empty until needed.
- **Plain-Python-to-framework-coupled ratio:** ~85/15. Most of the package is dataclasses-shaped Pydantic models, dict lookups, file reads, and a `for` loop over cases. The Click subcommand and Pydantic `BaseModel` subclasses are the only framework coupling.
- **mypy `--strict` clean** on all of `src/codegenie/eval/` and `bench/**/rubric.py` and `bench/**/registration.py`.
- **Total LOC for `src/codegenie/eval/` excluding docstrings + tests:** target ≤ 600 LOC (Phase 0's `probes/` + `audit.py` is ~450 LOC for comparable surface — this is slightly larger due to the rubric Protocol and promotion gate; still under 1 KLOC).

## Architecture

```
src/codegenie/eval/
├── __init__.py            # public surface: re-exports register_task_class,
│                          # TaskClassRegistry, default_registry, TaskClass,
│                          # BenchCase, BenchScore, Rubric, run_eval
├── models.py              # Pydantic v2 models: BenchCase, BenchScore,
│                          # BenchRunReport, PromotionVerdict, TaskClass
│                          # (frozen=True, extra="forbid" everywhere)
├── registry.py            # @register_task_class decorator + TaskClassRegistry
│                          # mirrors src/codegenie/probes/registry.py exactly
├── rubric.py              # Rubric Protocol (runtime_checkable);
│                          # one method: score(case, harness_output) -> BenchScore
├── loader.py              # bench/{task-class}/cases/ → list[BenchCase];
│                          # bench/{task-class}/registration.py side-effect import
├── runner.py              # run_eval(task_class, cases, system_under_test)
│                          # → BenchRunReport; serial execution; per-case
│                          # exception isolation; timeout per case
├── promotion.py           # PromotionGate.evaluate(task_class, current_tier)
│                          # → PromotionVerdict; reads bench/<class>/runs/ history
│                          # + docs/trust-tiers.yaml; pure function, no I/O writes
├── audit.py               # write_run_record(report, out_dir) → Path
│                          # mirrors src/codegenie/audit.py shape (RunRecord →
│                          # EvalRunRecord); writes .codegenie/eval/runs/<utc>-<short>.json
├── errors.py              # TaskClassAlreadyRegistered, BenchCaseLoadError,
│                          # RubricViolation, PromotionGateError
└── cli.py                 # `codegenie eval run --task-class=<name>` subcommand;
                           # defers heavy imports per Phase 0 import-linter contract

bench/                                      # contract territory (CODEOWNERS-gated)
├── vuln-remediation/
│   ├── registration.py                     # one-liner: @register_task_class("vuln-remediation")
│   ├── rubric.py                           # exports class VulnRemediationRubric(Rubric)
│   ├── cases/
│   │   ├── 001-cve-2024-21538-cross-spawn/
│   │   │   ├── case.toml                   # provenance, disposition, difficulty
│   │   │   ├── input/                      # frozen repo snapshot (or pointer)
│   │   │   ├── expected/                   # ground-truth diff, expected CVE delta
│   │   │   └── cassette.yaml               # Phase 4 cassette for replay
│   │   ├── 002-.../
│   │   └── ... (≥10 cases per ADR-0016 §Consequences)
│   └── README.md                           # what this bench measures, how cases are added
├── migration-chainguard-distroless/        # ≥3 seed cases at Phase 6.5 exit;
│   ├── registration.py                     # Phase 7 expands to ≥10
│   ├── rubric.py
│   └── cases/...
└── README.md                               # the bench/ directory contract itself

docs/trust-tiers.yaml                       # hand-edited; PR-reviewed; what tier each
                                            # task class is currently at + thresholds
```

The diagram mirrors Phase 0's mental model: registry collects, runner dispatches, audit writer records, CLI invokes. The novelty is `bench/` as a peer of `src/` and `tests/` — contract territory the same way `tests/snapshots/` is contract territory under ADR-0007.

## Components

### `src/codegenie/eval/__init__.py`

- **Purpose:** Single public-import surface for the package.
- **Public interface:**
  ```python
  from .registry import register_task_class, TaskClassRegistry, default_registry
  from .models import TaskClass, BenchCase, BenchScore, BenchRunReport, PromotionVerdict
  from .rubric import Rubric
  from .runner import run_eval

  __all__ = (
      "register_task_class", "TaskClassRegistry", "default_registry",
      "TaskClass", "BenchCase", "BenchScore", "BenchRunReport", "PromotionVerdict",
      "Rubric", "run_eval",
  )
  ```
- **Internal design:** Explicit imports, no `importlib.metadata` scan. Same pattern as `src/codegenie/probes/__init__.py` (Phase 0 S2-05). No top-level heavy imports — the Phase 0 `import-linter` contract is extended to forbid `pydantic`, `pyyaml`, `click` from `codegenie.eval.__init__` (these come in via submodules).
- **Dependencies:** stdlib only.
- **Where it lives:** `src/codegenie/eval/__init__.py`.
- **Tradeoffs accepted:** A handful of explicit re-exports vs. a single `from .registry import *`. The explicit list is the documented contract surface; `__all__` is the source of truth (idiomatic per [PEP 8](https://peps.python.org/pep-0008/#public-and-internal-interfaces)).

### `src/codegenie/eval/registry.py` — `@register_task_class` + `TaskClassRegistry`

- **Purpose:** Open registry mirroring `@register_probe` (Phase 0 S2-05) and `@register_signal_kind` (Phase 5 ADR-0003). Same collision shape, same import-time registration, same lookup interface.
- **Public interface:**
  ```python
  class TaskClassAlreadyRegistered(ProbeError):
      """Raised at decoration time when a task class name collides with an existing
      registration. Mirrors SignalKindAlreadyRegistered from Phase 5 ADR-0003."""

  class TaskClassRegistry:
      def register(self, task_class: TaskClass) -> TaskClass: ...
      def all_task_classes(self) -> tuple[TaskClass, ...]: ...
      def get(self, name: str) -> TaskClass: ...  # raises KeyError on miss

  default_registry: TaskClassRegistry = TaskClassRegistry()

  def register_task_class(name: str, *, bench_path: str | None = None,
                          min_cases_for_promotion: dict[str, int] | None = None
                          ) -> Callable[[type[Rubric]], type[Rubric]]:
      """Decorator factory. Applied to a Rubric subclass in bench/<name>/registration.py.
      `bench_path` defaults to `bench/{name}/`. `min_cases_for_promotion` defaults to
      {"silver": 10, "gold": 50, "platinum": 200} per ADR-0016 §Decision §3 floor."""
  ```
- **Internal design:** `TaskClassRegistry._task_classes: dict[str, TaskClass]` (instance-level so tests can construct independent registries — same trick as Phase 0 `Registry._probes: list[type[Probe]]`). `register(...)` checks `name in self._task_classes`; on collision raises `TaskClassAlreadyRegistered(f"task class {name!r} already registered by {existing.rubric_class.__qualname__}; new registration from {task_class.rubric_class.__qualname__}")`. The decorator returns the rubric class unchanged so `class VulnRemediationRubric(Rubric)` stays usable as a normal class.
- **Dependencies:** `codegenie.eval.errors`, `codegenie.eval.models`, `codegenie.eval.rubric`. No third-party.
- **Where it lives:** `src/codegenie/eval/registry.py`.
- **Tradeoffs accepted:** Module-level `default_registry` is a global singleton — same compromise Phase 0 made for `@register_probe`. The pattern is idiomatic and tested across Phase 0/1 (the `default_registry` singleton has not caused a single issue in the gather layer). The cost is global state in tests; mitigated by allowing fresh `TaskClassRegistry()` instances in unit tests, exactly as Phase 0's `test_registry.py` does.

### `src/codegenie/eval/models.py` — Pydantic v2 models

- **Purpose:** All shared data shapes for the eval domain. One file because each model is small and they share constants.
- **Public interface:**
  ```python
  class BenchScore(BaseModel):
      """Per-case rubric output. Frozen, no extra fields, no LLM-judgment fields.
      Mirrors Phase 5 ADR-0014's ObjectiveSignals discipline."""
      model_config = ConfigDict(frozen=True, extra="forbid")

      passed: bool
      score: float = Field(ge=0.0, le=1.0)
      breakdown: dict[str, float]            # rubric-internal sub-scores
      failure_modes: tuple[str, ...]         # ordered, deduplicated by rubric
      cost_usd: float = Field(ge=0.0)        # ADR-0016 §Open Q3

  class BenchCase(BaseModel):
      """Loaded from bench/{task-class}/cases/{case-id}/case.toml."""
      model_config = ConfigDict(frozen=True, extra="forbid")

      case_id: str                           # the directory name; primary key within bench
      task_class: str                        # parent task-class slug
      disposition: Literal["positive", "negative", "ambiguous"]
      difficulty: Literal["easy", "medium", "hard"]
      source: Literal["curated", "outcome-ledger-derived", "regression-converted"]
      commit_sha: str | None                 # provenance pointer if source != "curated"
      added_at: datetime                     # UTC, tz-aware
      last_validated_at: datetime
      input_path: Path                       # absolute, resolved by loader
      expected_path: Path
      cassette_path: Path | None             # None for cases that run live (operator-only)

  class BenchRunReport(BaseModel):
      """Aggregate result for one eval run; serialized to .codegenie/eval/runs/."""
      model_config = ConfigDict(frozen=True, extra="forbid")

      run_id: str                            # SHA-256 of (task_class, case_ids, scores)
      task_class: str
      started_at: datetime
      ended_at: datetime
      per_case: tuple[tuple[str, BenchScore], ...]    # (case_id, score) pairs
      mean_score: float = Field(ge=0.0, le=1.0)
      passed_count: int = Field(ge=0)
      total_cost_usd: float = Field(ge=0.0)
      block_severity_failure_modes: tuple[str, ...]   # union across cases
      # No 'aggregate_passed: bool' — that's a judgment; promotion.py computes it
      # from this report + tier thresholds. Facts, not judgments. (design.md §2.2)

  class PromotionVerdict(BaseModel):
      """Read-only result from PromotionGate.evaluate(...). Carries the evidence;
      the actual tier change is a hand-edited PR against docs/trust-tiers.yaml."""
      model_config = ConfigDict(frozen=True, extra="forbid")

      task_class: str
      current_tier: Literal["bronze", "silver", "gold", "platinum"]
      target_tier: Literal["bronze", "silver", "gold", "platinum"]
      evidence_sufficient: bool
      reasons: tuple[str, ...]               # why not, if not (or "all conditions met")

  @dataclass(frozen=True, slots=True)
  class TaskClass:
      """Registry record — what a `@register_task_class` decoration produces.
      Plain dataclass, not a Pydantic model: it's not serialized to JSON; it's
      a runtime registry record (the Pydantic models above are the wire types).
      Plain-data-over-clever-types per the best-practices lens."""
      name: str
      bench_path: Path
      min_cases_for_promotion: Mapping[str, int]
      rubric_class: type[Rubric]
  ```
- **Internal design:** Pydantic v2 throughout. `ConfigDict(frozen=True, extra="forbid")` on every wire model — directly mirrors Phase 5 ADR-0014. The static-introspection test from Phase 5 (`test_objective_signals_static.py`) is the precedent for `tests/unit/test_bench_score_static.py`: walk every field reachable from `BenchScore` and assert no name contains `confidence`, `llm`, `self_reported`, `model_says`. This is the load-bearing structural enforcement that `BenchScore` cannot smuggle in an LLM-self-assessment field.
- **Dependencies:** `pydantic>=2.0` (already pinned), stdlib `datetime`, `pathlib`, `typing`.
- **Where it lives:** `src/codegenie/eval/models.py`.
- **Tradeoffs accepted:** One file holds five models. The alternative is one-file-per-model, which is over-modular for ~150 LOC of total Pydantic. Per the best-practices brief: "3 abstractions for 3 cases is right." Five small models in one file beats five files with three lines of imports each. `TaskClass` is a `@dataclass(frozen=True)`, not a Pydantic model, because it carries a `type` object (`rubric_class`) that doesn't serialize cleanly to JSON and doesn't need validation — Pydantic-where-it-pays-off is more idiomatic than Pydantic-everywhere.

### `src/codegenie/eval/rubric.py` — `Rubric` Protocol

- **Purpose:** The contract every task class implements. One method.
- **Public interface:**
  ```python
  @runtime_checkable
  class Rubric(Protocol):
      """Per-task-class scoring contract. One method. Stateless.

      Implementations live in bench/{task-class}/rubric.py and register via
      @register_task_class. The rubric receives the system-under-test output for
      one case and the expected ground-truth bundle; it returns a frozen BenchScore.

      Why Protocol (not ABC): per Phase 5 ADR-0006, Protocol when the contract is
      purely structural (no shared default behavior). Rubrics share no defaults —
      vuln-remediation scoring and migration scoring have nothing in common
      beyond returning BenchScore. ABC would impose ceremony with no payoff.
      """
      def score(self, case: BenchCase, harness_output: Mapping[str, Any]) -> BenchScore: ...
  ```
- **Internal design:** `typing.Protocol` with `@runtime_checkable` so `isinstance(rubric, Rubric)` works in the runner's defensive type-check. Per Phase 5 ADR-0006: Protocol when structural (this case), ABC when shared default behavior (the `Gate` ABC in Phase 5). The rule is documented in `docs/conventions.md` (Phase 5 contribution); this design extends it by example.
- **Dependencies:** stdlib `typing` only.
- **Where it lives:** `src/codegenie/eval/rubric.py`.
- **Tradeoffs accepted:** Protocol can't enforce a constructor signature. Mitigation: the registry takes a `type[Rubric]` and instantiates it with no args; rubrics that need configuration read from `bench/{task-class}/rubric_config.toml` (a convention, not a code requirement). A `tests/unit/test_rubric_protocol.py` asserts every registered task class's `rubric_class` satisfies the Protocol via `isinstance`.

### `src/codegenie/eval/loader.py` — bench-directory loader

- **Purpose:** Walk `bench/{task-class}/cases/` and produce `tuple[BenchCase, ...]`. Side-effect-import `bench/{task-class}/registration.py` to trigger decorator registration.
- **Public interface:**
  ```python
  def load_task_class(name: str, bench_root: Path = Path("bench")) -> TaskClass:
      """Import bench/{name}/registration.py (triggers @register_task_class
      side-effect) and return the registered TaskClass. Raises
      TaskClassNotFound if registration didn't land the name."""

  def load_cases(task_class: TaskClass) -> tuple[BenchCase, ...]:
      """Walk task_class.bench_path/cases/, parse case.toml in each subdir,
      construct BenchCase models. Sorted by case_id for determinism."""
  ```
- **Internal design:** Uses `importlib.import_module` with a synthesized module name like `_codegenie_bench.{task_class_name}.registration`. The `_codegenie_bench` prefix avoids polluting the `codegenie` namespace. `case.toml` parsed with stdlib `tomllib` (Python 3.11+). All paths resolved relative to `bench_root` then `Path.resolve()`'d so the Pydantic models carry absolute paths.
- **Dependencies:** stdlib `importlib`, `tomllib`, `pathlib`.
- **Where it lives:** `src/codegenie/eval/loader.py`.
- **Tradeoffs accepted:** Side-effect imports are not pure. Pydantic-strict folks would prefer a declarative manifest. But the side-effect-import pattern is exactly what Phase 0/1 do for probes (`from . import language_detection  # registered via @register_probe`), and consistency with the existing pattern beats theoretical purity. Same precedent, same trade.

### `src/codegenie/eval/runner.py` — `run_eval`

- **Purpose:** End-to-end harness execution for one task class. Loads cases, invokes the system under test for each case, calls the rubric, aggregates into a `BenchRunReport`. Writes audit record.
- **Public interface:**
  ```python
  def run_eval(
      task_class_name: str,
      *,
      case_filter: Callable[[BenchCase], bool] | None = None,
      system_under_test: Callable[[BenchCase], Mapping[str, Any]],
      timeout_per_case_seconds: float = 600.0,
      out_dir: Path = Path(".codegenie/eval/runs"),
      bench_root: Path = Path("bench"),
  ) -> BenchRunReport:
      """Run the eval harness for one task class.

      Args:
          task_class_name: registered slug, e.g. "vuln-remediation".
          case_filter: optional predicate to subset cases (CLI's --cases glob
              expands to this).
          system_under_test: callable that takes a BenchCase and returns a
              dict the rubric can score. For vuln-remediation this is a thin
              wrapper around Phase 6's LangGraph workflow with cassette replay.
          timeout_per_case_seconds: per-case wall-clock cap; exceeded cases
              record passed=False with failure_mode="timeout".
          out_dir: where to write the JSON audit record.
          bench_root: override for tests.

      Returns:
          BenchRunReport (frozen) with per-case scores and aggregate.

      Raises:
          TaskClassNotFound: registration.py didn't register the name.
          BenchCaseLoadError: a case.toml failed to parse or required path missing.
      """
  ```
- **Internal design:** Plain `for case in cases:` loop. Per-case `try` block isolates a single case failure (`Exception` → `BenchScore(passed=False, score=0.0, failure_modes=("harness_error: ...",), ...)`). Timeout via `signal.SIGALRM` on POSIX (stdlib; same approach as Phase 0's probe coordinator timeout). Serial, not parallel — the performance-first design will propose `asyncio.gather`; I'm explicitly choosing serial because (a) bench sets are 10–50 cases, (b) the nightly cadence absorbs serial runtime, (c) parallel adds resource contention against the Phase 4 cassette layer with no observable benefit at this volume, and (d) serial output ordering makes debugging eval failures trivial. After the loop, compute aggregates and build the `BenchRunReport`. Call `audit.write_run_record(report, out_dir)`. Return `report`.
- **Dependencies:** `codegenie.eval.models`, `codegenie.eval.loader`, `codegenie.eval.audit`, `codegenie.eval.errors`. Stdlib `signal`, `time`, `datetime`.
- **Where it lives:** `src/codegenie/eval/runner.py`.
- **Tradeoffs accepted:** Serial is slower than parallel for large bench sets. At >100 cases per task class, this design would need revisiting — flagged as an open question, not designed-around prematurely. Per Rule 2 (Simplicity First): minimum code that solves the problem.

### `src/codegenie/eval/promotion.py` — `PromotionGate`

- **Purpose:** Compute a `PromotionVerdict` from the most recent bench run + the configured tier thresholds. Pure function.
- **Public interface:**
  ```python
  class PromotionGate:
      """Read-only verdict source for trust-tier promotion.

      Does NOT mutate trust tiers. The act of promotion is a hand-edited PR
      against docs/trust-tiers.yaml reviewed by CODEOWNERS, per ADR-0016
      §Decision §4 ("promotion remains a deliberate, ADR-anchored decision").
      """
      def __init__(self, tier_config: TierConfig) -> None: ...

      def evaluate(
          self,
          task_class: str,
          current_tier: Literal["bronze", "silver", "gold", "platinum"],
          report: BenchRunReport,
      ) -> PromotionVerdict:
          """Return a verdict. evidence_sufficient is True iff:
            - report.mean_score >= tier_config.threshold[target_tier]
            - report.passed_count >= task_class.min_cases_for_promotion[target_tier]
            - report.block_severity_failure_modes == ()
          Reasons enumerate every failed condition individually so the verdict
          is auditable when evidence_sufficient is False.
          """

  @dataclass(frozen=True)
  class TierConfig:
      """Loaded from docs/trust-tiers.yaml."""
      thresholds: Mapping[str, float]  # e.g., {"silver": 0.8, "gold": 0.9}
  ```
- **Internal design:** Pure function with explicit inputs — no global state, no I/O writes. The `evaluate` method takes the report as a parameter (not loaded from disk inside) so it's trivially unit-testable. The `TierConfig` is loaded once by the CLI from `docs/trust-tiers.yaml` and passed in.
- **Dependencies:** `codegenie.eval.models`. Stdlib only.
- **Where it lives:** `src/codegenie/eval/promotion.py`.
- **Tradeoffs accepted:** No automatic promotion. The performance lens might want a `promote_if_ready()` mutator. I'm choosing pure-verdict because ADR-0016 §Decision §4 is explicit: promotion is human. A code path that mutates tier state would create exactly the failure mode ADR-0016 exists to prevent (silent promotion based on bench score alone).

### `src/codegenie/eval/audit.py` — audit-record writer

- **Purpose:** Serialize `BenchRunReport` to `.codegenie/eval/runs/<utc-iso>-<short>.json`. Mirrors Phase 0's `AuditWriter` (S3-06) byte-for-byte in shape.
- **Public interface:**
  ```python
  def write_run_record(report: BenchRunReport, out_dir: Path) -> Path:
      """Write report to out_dir/<utc-iso>-<short-hash>.json at mode 0600.
      Returns the absolute path of the written file.

      The filename pattern matches Phase 0 audit records exactly so a single
      `audit verify` tool can later (Phase 13) scan both probe runs and eval
      runs without forking.
      """
  ```
- **Internal design:** `report.model_dump_json(indent=2)`. Filename `f"{report.started_at.isoformat()}-{report.run_id[:8]}.json"`. `os.umask(0o077)` before open; close immediately. Single-write, atomic via `os.replace(tmp, final)` (idiomatic POSIX atomic-write).
- **Dependencies:** stdlib `json` (via Pydantic's `model_dump_json`), `os`, `pathlib`.
- **Where it lives:** `src/codegenie/eval/audit.py`.
- **Tradeoffs accepted:** No retention/rotation logic. `.codegenie/eval/runs/` will grow unboundedly. Phase 16 (production hardening) can add rotation. Phase 6.5 stays minimal.

### `src/codegenie/eval/errors.py` — typed errors

- **Purpose:** Explicit, typed errors instead of bare `RuntimeError`. Rule 12 (Fail loud): callers can `except TaskClassNotFound:` without parsing strings.
- **Public interface:**
  ```python
  class EvalError(CodegenieError):
      """Base class for all eval-package errors. Subclasses CodegenieError
      from src/codegenie/errors.py (Phase 0 S2-01)."""

  class TaskClassAlreadyRegistered(EvalError):
      """Duplicate name passed to @register_task_class. Raised at import time."""

  class TaskClassNotFound(EvalError):
      """No registration.py registered the requested task class name."""

  class BenchCaseLoadError(EvalError):
      """case.toml malformed, missing required path, or schema violation."""

  class RubricViolation(EvalError):
      """Rubric returned an object that isn't a BenchScore or returned a
      BenchScore with score outside [0, 1]. (Pydantic validation catches the
      latter; this is the runner-side belt-and-suspenders check.)"""
  ```
- **Internal design:** Plain exception subclasses. Inherit from `CodegenieError` (Phase 0 S2-01) so a top-level `except CodegenieError:` in the CLI catches everything.
- **Dependencies:** `codegenie.errors`.
- **Where it lives:** `src/codegenie/eval/errors.py`.
- **Tradeoffs accepted:** None — typed errors are the idiomatic Python answer.

### `src/codegenie/eval/cli.py` — `codegenie eval run` subcommand

- **Purpose:** CLI entrypoint. Mirrors Phase 0's `codegenie gather` (S4-02) in shape.
- **Public interface:**
  ```python
  @click.group("eval")
  def eval_group() -> None:
      """Run the per-task-class eval harness."""

  @eval_group.command("run")
  @click.option("--task-class", required=True, help="Registered task-class slug.")
  @click.option("--cases", default=None, help="Optional glob filter on case_id.")
  @click.option("--out", default=".codegenie/eval/runs",
                type=click.Path(path_type=Path),
                help="Where to write the audit JSON.")
  @click.option("--bench-root", default="bench",
                type=click.Path(exists=True, path_type=Path),
                help="Override bench/ root for tests.")
  def run(task_class: str, cases: str | None, out: Path, bench_root: Path) -> None:
      """Run the eval harness for one task class against its bench cases.

      Emits per-case + aggregate BenchScore as JSON to stdout (one event per
      line, JSONL) and writes the full BenchRunReport to <out>/<utc>-<short>.json.
      Exit code: 0 if every case passed and no block-severity failure modes
      surfaced; 1 otherwise. (Promotion-tier verdict is a separate `eval
      promote-verdict` subcommand to keep concerns split.)
      """
  ```
- **Internal design:** Click subcommand registered with the existing `codegenie` Click group (Phase 0 S4-02). All heavy imports (`pydantic`, `pyyaml`, `bench/*/rubric.py` chain) deferred inside the command body — same import-linter contract as Phase 0's `cli.py`. The CLI's `system_under_test` for vuln-remediation is wired via `from codegenie.workflows.vuln import run_against_case` (Phase 6 entrypoint); for migration it's the Phase 7 entrypoint (not yet wired — the CLI emits a clear "Phase 7 not yet implemented" message when invoked with `--task-class=migration-chainguard-distroless` until Phase 7 lands).
- **Dependencies:** `click` (deferred-imported), `codegenie.eval.runner`, `codegenie.eval.loader`.
- **Where it lives:** `src/codegenie/eval/cli.py`.
- **Tradeoffs accepted:** No interactive prompts, no progress bar (would conflate stdout JSONL with TTY noise). Operators see structured logs via `structlog` (already pinned, Phase 0) on stderr; bench results on stdout. Same stdout/stderr separation as Phase 0's `codegenie gather`.

### `bench/{task-class-slug}/` directory contract

- **Purpose:** The data-shape contract. Treated like `tests/snapshots/`: contract territory; mutations require ADR amendment for `cases/` removals.
- **Structure (enforced by fence-CI):**
  ```
  bench/{task-class-slug}/
  ├── registration.py    # Required. Exactly one @register_task_class("{slug}") call.
  ├── rubric.py          # Required. Defines a class that satisfies Rubric Protocol.
  ├── README.md          # Required. What this bench measures; how to add cases.
  └── cases/             # Required. ≥ min_cases_for_promotion[bronze] cases (default 10).
      └── {case-id}/
          ├── case.toml          # Required. Parsed into BenchCase.
          ├── input/             # Required (or input-pointer.toml — see below).
          ├── expected/          # Required.
          └── cassette.yaml      # Optional. Phase 4 cassette for CI replay.
  ```
- **Internal design:** `case.toml` schema:
  ```toml
  case_id = "001-cve-2024-21538-cross-spawn"
  task_class = "vuln-remediation"
  disposition = "positive"   # positive | negative | ambiguous
  difficulty = "medium"      # easy | medium | hard
  source = "curated"         # curated | outcome-ledger-derived | regression-converted
  commit_sha = "abc123..."   # required iff source != "curated"
  added_at = 2026-05-12T00:00:00Z
  last_validated_at = 2026-05-12T00:00:00Z
  cassette_path = "cassette.yaml"  # relative to this case directory
  ```
  Validated by `BenchCase` Pydantic model at load time.
- **Where it lives:** `bench/` at repo root.
- **Tradeoffs accepted:** Bench cases live in the same repo as code. ADR-0016 §Open Q4 defers the org-sharing question; landing them here is the conservative default. If the bench grows beyond ~500 cases or accumulates proprietary repo snapshots, Phase 13/16 can migrate to a sibling repo without changing the loader shape.

### `tests/unit/test_eval_fence.py` — directory-contract fence test

- **Purpose:** Mirror of Phase 0's `tests/unit/test_pyproject_fence.py` for the bench-directory contract. Asserts: every `@register_task_class("name")` call has a corresponding `bench/{name}/` directory with `registration.py`, `rubric.py`, `README.md`, `cases/`, and `cases/` contains ≥10 subdirectories each with `case.toml`. A task class registered without a bench directory fails CI with a specific diagnostic.
- **Implementation sketch:**
  ```python
  import importlib
  import ast
  from pathlib import Path
  import pytest

  REPO_ROOT = Path(__file__).resolve().parents[2]
  BENCH_ROOT = REPO_ROOT / "bench"

  def _registered_task_class_names() -> set[str]:
      """Scan bench/*/registration.py via AST (no execution) and extract the
      string literal passed to @register_task_class. AST-only because we want
      this test to run BEFORE the rubric modules import — catching a missing
      bench/ directory should not require the registration to succeed."""
      names = set()
      for reg_py in BENCH_ROOT.glob("*/registration.py"):
          tree = ast.parse(reg_py.read_text())
          for node in ast.walk(tree):
              if (isinstance(node, ast.Call)
                  and isinstance(node.func, ast.Name)
                  and node.func.id == "register_task_class"
                  and node.args
                  and isinstance(node.args[0], ast.Constant)):
                  names.add(node.args[0].value)
      return names

  def test_every_registered_task_class_has_full_bench_dir() -> None:
      for name in _registered_task_class_names():
          d = BENCH_ROOT / name
          for required in ("registration.py", "rubric.py", "README.md", "cases"):
              assert (d / required).exists(), (
                  f"task class {name!r} registered in {d}/registration.py but "
                  f"required file/dir bench/{name}/{required} is missing. "
                  f"See ADR-0016 §Consequences."
              )
          case_dirs = [p for p in (d / "cases").iterdir() if p.is_dir()]
          assert len(case_dirs) >= 10, (
              f"task class {name!r} has {len(case_dirs)} cases in bench/{name}/cases/; "
              f"ADR-0016 §Decision §3 requires min_cases_for_promotion[bronze] ≥ 10."
          )
          for case_dir in case_dirs:
              assert (case_dir / "case.toml").exists(), (
                  f"case {case_dir} missing case.toml"
              )
  ```
- **Where it lives:** `tests/unit/test_eval_fence.py`.
- **Tradeoffs accepted:** AST-only scan misses dynamic `register_task_class(name)` calls where `name` isn't a string literal. That's fine — the convention is literal strings (mirrors `@register_probe` precedent), and a non-literal would already fail review.

## Data flow

End-to-end `codegenie eval run --task-class=vuln-remediation`:

```
1. Click parses args → cli.py:run(...)
2. cli.py imports codegenie.eval.runner (heavy import deferred per Phase 0
   import-linter contract)
3. runner.run_eval("vuln-remediation", ...) calls loader.load_task_class(...)
4. loader imports _codegenie_bench.vuln_remediation.registration
       └─ this executes bench/vuln-remediation/registration.py
       └─ which calls @register_task_class("vuln-remediation")
       └─ which calls default_registry.register(TaskClass(...))
       └─ duplicate-name check; if collision, TaskClassAlreadyRegistered raised
          at import time with both classes' qualnames (mirrors Phase 0 register_probe
          duplicate-name behavior exactly)
5. loader.load_cases(task_class) walks bench/vuln-remediation/cases/*/case.toml,
   parses with stdlib tomllib, constructs BenchCase Pydantic instances. Pydantic
   validates schema (extra="forbid" catches typos). Sorted by case_id.
6. runner instantiates the rubric: rubric = task_class.rubric_class()
   Defensive isinstance(rubric, Rubric) check; raises RubricViolation if not.
7. For each case in cases:
       a. result_dict = system_under_test(case)  # invokes Phase 6 workflow
          with cassette replay; runner catches Exception and records
          BenchScore(passed=False, failure_modes=("harness_error: <type>",), ...)
       b. score = rubric.score(case, result_dict)
       c. Pydantic re-validates score (defense-in-depth)
       d. score logged as one JSONL line to stdout via structlog
8. After loop: aggregate. mean = sum(scores) / len(scores). Compute run_id =
   sha256(task_class || sorted_case_ids || score_jsons).
9. report = BenchRunReport(...)
10. audit.write_run_record(report, out=.codegenie/eval/runs/) atomically writes
    <utc-iso>-<short>.json at mode 0600. Same shape as Phase 0's RunRecord.
11. CLI exits 0 if all cases passed AND no block-severity failure modes; 1 otherwise.
12. Operator runs `codegenie eval promote-verdict --task-class=vuln-remediation
    --target-tier=silver` separately to produce a PromotionVerdict; verdict is
    advisory, not a state change.
```

Convention shine points:
- Decorator at step 4 is identical to `@register_probe` decoration shape from Phase 0.
- Pydantic validation at steps 5 + 7c is identical to `_ProbeOutputValidator` (Phase 0 S3-02).
- Audit write at step 10 is identical to `AuditWriter.record(...)` shape (Phase 0 S3-06).
- The verdict separation at step 12 honors design.md §2.2 (facts not judgments) and ADR-0009 (humans always merge — by extension, humans always promote).

## Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| `bench/{name}/registration.py` missing or doesn't call `@register_task_class("name")` | `loader.load_task_class` → `TaskClassNotFound` | CLI prints the expected path and exits 1; fence-CI test catches this before merge. |
| Duplicate `@register_task_class("foo")` across two bench dirs | `TaskClassRegistry.register` at import time → `TaskClassAlreadyRegistered` | Import-time crash with both rubric class qualnames in the message; PR cannot land. |
| `case.toml` malformed | `BenchCase` Pydantic validation in `loader.load_cases` → `ValidationError` wrapped in `BenchCaseLoadError` | Error names the case directory and the failing field; case is excluded from the run with a logged warning; aggregate computed on remaining cases; exit code 1. |
| System-under-test raises during one case | `runner` per-case `try/except Exception` | Recorded as `BenchScore(passed=False, score=0.0, failure_modes=("harness_error: <ExceptionType>: <message>",), cost_usd=0.0)`. Other cases continue. The harness never falls over because one case is broken. |
| System-under-test exceeds `timeout_per_case_seconds` | `signal.SIGALRM` in runner | Same as above with `failure_modes=("timeout",)`. |
| Rubric returns a non-`BenchScore` object | `runner`'s defensive type-check + Pydantic re-validation → `RubricViolation` | Run aborts (rubric is global to the task class, not per-case); error names the rubric class and the offending return value. |
| Rubric returns `BenchScore` with `score=1.5` | Pydantic `Field(ge=0.0, le=1.0)` validation | Same as above. (Belt-and-suspenders: the rubric author can't smuggle out-of-range scores.) |
| `.codegenie/eval/runs/` not writable | `audit.write_run_record` → `PermissionError` | CLI logs the path and exits 1; the in-memory report is also dumped to stderr as JSON so the run isn't fully lost. |
| Static introspection finds a banned-substring field on `BenchScore` | `tests/unit/test_bench_score_static.py` (mirrors Phase 5's `test_objective_signals_static.py`) | CI failure; PR cannot land. Field must be renamed (e.g., `evidence_strength` instead of `confidence_score`). |
| Trust tier YAML missing or malformed | `PromotionGate.__init__` → `PromotionGateError` | The `eval run` path doesn't need this; only `eval promote-verdict` does. Verdict subcommand exits 1 with a clear message; main eval run is unaffected. |

All errors subclass `CodegenieError` so the top-level CLI handler catches them uniformly.

## Resource & cost profile

- **Cold-start time for `codegenie eval run`:** ≤ 600 ms target (matches Phase 0's `codegenie gather` cold-start ≤ 500 ms, plus ~100 ms for Pydantic model imports). The eval CLI inherits Phase 0's import-linter contract — no top-level heavy imports.
- **Per-case eval runtime:** dominated by the system-under-test, not the harness. For vuln-remediation with cassettes: ~5–30 seconds per case. Harness overhead: ≤ 50 ms per case (Pydantic validate, log, write).
- **Memory:** O(cases) Pydantic instances held in memory; ≤ 50 MB for a 100-case run.
- **Disk:** Each run writes one ~10 KB JSON file. 365 nightly runs = ~3.5 MB/yr. Per-case raw outputs (Phase 4 cassette replays) live under `.codegenie/eval/runs/<run-id>/cases/` and are ~1–10 KB each.
- **LLM cost:** $0 in CI (cassettes only). Live operator runs: per-case cost surfaced in `BenchScore.cost_usd`, aggregated to `BenchRunReport.total_cost_usd` — Phase 13's cost ledger consumes this without code change.
- **Where convention costs performance:** The serial runner is slower than `asyncio.gather` would be by ~5x. At 10–50 cases per task class, the difference is ~30–150 seconds of nightly wall-clock — well under the cadence budget. Not designed-around.
- **Where convention saves future maintenance:** Single audit-record format (Phase 0's `RunRecord` shape, extended to `EvalRunRecord`) means Phase 13's cost ledger and Phase 11's PR provenance both ingest eval audit records without forking the parser.

## Test plan

### Unit tests (≥ 90% line, ≥ 80% branch on `src/codegenie/eval/`)

- `tests/unit/test_eval_registry.py` — decorator registers a task class; duplicate-name registration raises `TaskClassAlreadyRegistered` at import time with both qualnames in the message; `get(name)` raises `KeyError` on miss; `all_task_classes()` returns a tuple (not a list — immutable accessor); `default_registry` is a module-level singleton. Mirrors Phase 0's `test_registry.py` line for line.
- `tests/unit/test_eval_models.py` — `BenchScore`, `BenchCase`, `BenchRunReport`, `PromotionVerdict` all `frozen=True` (mutation raises); `extra="forbid"` rejects unknown fields; `BenchScore.score` rejects `1.5` and `-0.1` via `Field(ge, le)`; `BenchCase.disposition` rejects `"unknown"` via `Literal`; `commit_sha` required iff `source != "curated"` (model validator).
- `tests/unit/test_bench_score_static.py` — **load-bearing.** Walks every field reachable from `BenchScore` via `pydantic.fields.FieldInfo` (recursive through `dict` value types) and asserts no field name contains `confidence`, `llm`, `self_reported`, `model_says`. Direct port of Phase 5's `test_objective_signals_static.py`. Catches the failure mode where a contributor adds `llm_confidence: float` "just for logging."
- `tests/unit/test_rubric_protocol.py` — every registered task class's `rubric_class` satisfies the `Rubric` Protocol via `isinstance(rubric, Rubric)`; a class missing `score()` does not satisfy.
- `tests/unit/test_loader.py` — `load_cases` returns sorted-by-`case_id`; malformed `case.toml` raises `BenchCaseLoadError` naming the case directory; missing `input/` directory raises with the missing-path; cassette-less cases load cleanly.
- `tests/unit/test_runner.py` — single-case run produces a `BenchRunReport`; system-under-test exception is captured as `BenchScore(passed=False, failure_modes=("harness_error: ...",))` and other cases proceed; timeout produces `failure_modes=("timeout",)`; rubric returning a non-`BenchScore` raises `RubricViolation`; aggregate `mean_score` is correct against a hand-computed fixture.
- `tests/unit/test_promotion.py` — `evaluate` returns `evidence_sufficient=True` only when mean ≥ threshold AND passed_count ≥ min AND no block-severity failure modes; `reasons` enumerates every failed condition individually (not just the first); `PromotionGate` does not mutate any state (verified by snapshotting the tier YAML before/after).
- `tests/unit/test_audit.py` — `write_run_record` produces a file at mode `0600`; filename matches `{utc-iso}-{8-hex}.json`; written content round-trips through Pydantic without loss; atomic-write semantics (the partial file isn't visible during write).
- `tests/unit/test_cli.py` — `--task-class=unknown` exits 1 with `TaskClassNotFound` in stderr; `--cases='001-*'` filters; missing `--task-class` exits 2 (Click usage error).
- `tests/unit/test_eval_fence.py` — **load-bearing.** A synthetic `bench/foo/` with `registration.py` calling `@register_task_class("foo")` but missing `cases/` fails the test; a synthetic bench dir with only 9 cases fails the test; a fully-populated synthetic bench dir passes. Same shape as Phase 0's `test_pyproject_fence.py`.
- `tests/unit/test_eval_package_imports_no_llm_sdk.py` — AST walk of `src/codegenie/eval/**/*.py` asserts no `import anthropic | openai | langchain | langgraph | transformers`. Direct extension of the Phase 0 fence (which scopes to runtime deps); this is the source-tree-side check for the eval-package gather discipline.

### Integration tests (the seams)

- `tests/integration/test_eval_end_to_end_vuln.py` — wire `bench/vuln-remediation/` to a small Phase 6 LangGraph workflow stub (Phase 6 ships the real one; the integration test uses a deterministic fixture wrapper). Assert: `codegenie eval run --task-class=vuln-remediation` exits 0 against the backfilled 10 cases, writes one audit JSON, and the aggregate `mean_score` matches a snapshot. The snapshot is regenerated by a `scripts/regen_eval_snapshot.py` script (same pattern as Phase 0 S2-02's snapshot regen — the audit record is contract territory).
- `tests/integration/test_eval_promotion_verdict.py` — given a synthetic `BenchRunReport` and a synthetic `docs/trust-tiers.yaml`, `eval promote-verdict --target-tier=silver` exits 0 with the right `PromotionVerdict` shape on stdout. No tier state changes.
- `tests/integration/test_phase4_cassette_replay.py` — one vuln-remediation case runs via Phase 4 cassette replay (not live LLM); assert determinism: two consecutive runs produce identical `run_id`. This is the ADR-0016 §Tooling assertion ("bench runs in CI use Phase 4's cassette discipline") rendered as an executable test.

### E2E (minimal — what we're proving)

- `tests/e2e/test_eval_run_against_real_bench.py` — `subprocess.run(["codegenie", "eval", "run", "--task-class=vuln-remediation"])` on the actual `bench/vuln-remediation/` directory. Assert: exit 0; one new file in `.codegenie/eval/runs/`; stdout contains 10 JSONL lines plus an aggregate line. This is the "the binary actually works against real data" smoke test.

### Property tests

- `tests/property/test_benchscore_invariants.py` (Hypothesis) — for any `BenchScore` generated by `Hypothesis`'s strategy: `0 <= score <= 1`; `failure_modes` is a tuple (not a list — immutability invariant); `passed_count(report) <= len(report.per_case)`.
- `tests/property/test_runner_aggregate_correctness.py` — for any list of `BenchScore`s, the runner-computed `mean_score` equals `statistics.fmean(s.score for s in scores)`. Catches drift if someone "optimizes" the mean computation.

### Adversarial tests (rubric isolation)

- `tests/adv/test_rubric_cannot_mutate_bench_case.py` — a rubric attempting `case.case_id = "new"` raises `ValidationError` (frozen). Confirms `frozen=True` is load-bearing for rubric isolation.
- `tests/adv/test_rubric_cannot_smuggle_llm_assessment.py` — a synthetic rubric tries to return a `BenchScore`-look-alike with an extra `llm_confidence` field; Pydantic `extra="forbid"` rejects it; the test asserts the rejection message names the offending field.

### Golden files

- `tests/snapshots/eval_run_report.v1.json` — frozen `BenchRunReport` shape; regenerated via `scripts/regen_eval_snapshot.py`; contract-territory snapshot following ADR-0007's pattern. Drift fails the integration test with a pointer to `templates/adr-amendment.md`.

## Risks (top 5)

1. **Bench-case curation cost dominates Phase 6.5's actual schedule.** ADR-0016 §Tradeoffs flags this; the design can't fix it. Mitigation: ship `bench/vuln-remediation/` with 10 cases drawn from Phases 3–4's solved-example corpus (zero net curation, just re-shaping existing CVE-fix scenarios as bench cases). `bench/migration-chainguard-distroless/` gets 3 seed cases from publicly-documented Chainguard migration examples. Phase 7 expands.
2. **Rubric correctness is itself untested.** A bug in `rubric.score(...)` makes every bench score wrong without anyone noticing. Mitigation in Phase 6.5: every rubric ships with its own unit tests under `bench/{task-class}/tests/` (one per scoring axis); CI runs them. Deeper mitigation (mutation testing) is ADR-0016 §Open Q5 — Phase 16 territory, acknowledged as a known gap.
3. **The `default_registry` global is shared across tests.** A test that registers `"foo"` and doesn't clean up will collide with the next test that registers `"foo"`. Mitigation: every unit test that touches registration uses a fresh `TaskClassRegistry()` instance, not `default_registry`. Phase 0's `test_registry.py` has this discipline; we copy it. A `pytest` fixture `clean_default_registry` is provided for the rare integration test that must use the singleton.
4. **AST-only fence-CI misses non-literal task-class names.** If a contributor writes `register_task_class(get_name())` with a non-literal, the fence test won't see the registration and won't enforce the bench-dir contract for it. Mitigation: a separate lint rule (a one-line `ast.walk` over `bench/*/registration.py` asserting every `@register_task_class(...)` call's first arg is `ast.Constant`) — added to `tests/unit/test_eval_fence.py` as a second assertion.
5. **Stale `last_validated_at` is invisible without a staleness probe.** ADR-0016 §Open Q assigns this to Phase 16. Mitigation in Phase 6.5: emit a warning when `now - case.last_validated_at > timedelta(days=90)` from `loader.load_cases`. The warning is a `structlog.warn(...)`, not an error, so it doesn't block the run but is visible in CI logs. Phase 16 escalates to an error.

## Acknowledged blind spots

What this lens deprioritized — these are real costs of the best-practices design that the synthesizer should weigh against the other two lenses:

- **Eval throughput.** Serial runner means 50-case bench sets take 50× the longest case. For the nightly cadence and the 10–50-case bench sizes targeted at Phase 6.5 / Phase 7 exit, this is fine. At Phase 13+ scale (post-merge ledger reconciliation generating many regression-converted cases), it will need to be revisited. The performance-first design will likely propose `asyncio.gather` and a `--parallel=N` flag; I'm not opposing that for a future phase, only deferring it.
- **Bench-case integrity / tampering.** Bench cases are checked into git. A malicious contributor could add a case that's "easy" to ensure their feature passes. Mitigation in Phase 6.5: CODEOWNERS gating on `bench/`. Stronger mitigation (signed cases, content-addressing) is the security-first design's job.
- **Cassette poisoning / replay attacks.** Cassettes carry recorded LLM responses; a malicious cassette could cause the rubric to falsely pass. Mitigation in Phase 6.5: cassettes are content-hashed; the case.toml carries `cassette_sha256`. Stronger mitigation is the security-first lens's concern.
- **Rubric DSL or declarative scoring.** I chose Python-coded rubrics over YAML-declarative scoring because Python lets the rubric express the actual logic of "did the CVE drop out of the dependency tree" without inventing a mini-language. The cost: rubrics can have bugs. The alternative (declarative scoring) would also have bugs in the DSL interpreter. Wash.
- **Adversarial-synthetic bench cases.** ADR-0016 §Open Q1 defers this. Synthetic LLM-generated bench cases could surface failure modes faster than hand-curation but risk drifting from the real-world distribution. Best-practices lens passes on this — Phase 13/15 territory once the curated baseline exists.
- **Pluggable rubric implementations across languages.** A future Java task class might want a Java-coded rubric. Phase 6.5 ties rubrics to Python. Acknowledged; the abstraction cost of polyglot rubrics isn't worth it for a single language at the current scope.

## Open questions for the synthesizer

1. **Should `bench/` live in this repo or a sibling `codewizard-sherpa-benches` repo?** ADR-0016 §Open Q4 defers; the best-practices design assumes same-repo for now. Synthesizer should weigh against the security-first lens's view on proprietary repo snapshots.
2. **Should `PromotionGate.evaluate` be exposed as a Python API or only as a CLI subcommand?** This design exposes both. The CLI is the operator path; the Python API is needed for Phase 13's cost-ledger reconciliation. If Phase 13 doesn't materialize the Python use case, the API is over-built. Defer to synthesizer.
3. **Is `signal.SIGALRM` the right timeout mechanism on Linux + macOS dev machines?** Phase 0's probe coordinator uses `asyncio.wait_for`; the eval runner is synchronous. Synthesizer should confirm consistency with whatever the performance-first design proposes for parallelism — if parallelism lands, timeouts become per-task `asyncio.wait_for` and `signal.SIGALRM` goes away.
4. **Should the rubric have access to the audit record from prior runs?** Useful for "did this case regress?" scoring. Phase 6.5 says no (rubrics are stateless per-case); Phase 13 may revisit.
5. **Tier names — `bronze/silver/gold/platinum` per ADR-0016, but the four-tier choice is data, not contract.** Should the design pin them as `Literal[...]` or load from `docs/trust-tiers.yaml`? This design pins them in `BenchCase.disposition` and `PromotionVerdict.current_tier` as `Literal[...]`. Adding a fifth tier becomes an ADR amendment (consistent with "extension by addition" + the `extra="forbid"` discipline). The performance-first or security-first lens may prefer string-typed for flexibility; the best-practices lens chooses Literal for type-safety. Synthesizer's call.
