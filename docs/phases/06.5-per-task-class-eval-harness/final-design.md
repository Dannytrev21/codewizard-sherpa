# Phase 6.5 — Per-task-class eval harness + first benches: Final design

**Status:** Design of record (synthesized from three competing designs + critique).
**Synthesized by:** Graph-of-Thought synthesizer subagent
**Date:** 2026-05-12
**Sources:** [`design-performance.md`](design-performance.md) · [`design-security.md`](design-security.md) · [`design-best-practices.md`](design-best-practices.md) · [`critique.md`](critique.md)

## Lens summary

The synthesis is **best-practices-shaped on the public surface, security-shaped on the load-bearing trust boundaries, and performance-shaped only where it can be added later without breaking the audit chain.** The single non-reversible decision — rubric isolation — goes to the security lens: the rubric runs in a per-case subprocess (not the harness's Python process), with stdin/stdout JSON I/O and a hard wall-clock cap. We do **not** ship Firecracker/gVisor in Phase 6.5 (the critic correctly flagged the macOS/CI runner-substrate problem); we ship a `subprocess.run` rubric runner with `env={}`, `cwd=tmpfs-scratch`, and a documented `RubricRunner` Protocol so a future ADR can swap subprocess for microVM without touching `BenchScore` shape or the audit chain. Cache, parallelism, Sigstore anchors, and per-case microVMs are all deferred — the critic's strongest argument is that the *evidence shape* must be right now (because retrofitting changes the score), and everything else is layerable.

The runner is **serial in Phase 6.5** (best-practices + security), with a single registered seam (`RubricRunner` Protocol; concurrency parameter on `run_eval` defaulting to `1`) so the performance lens can land an `asyncio.Semaphore` pool in Phase 7+ without re-shaping anything. Audit records are **chain-linked Phase-0-shaped JSON files** (best-practices' Phase-0 reuse + security's `prev_hash` chain), but **Sigstore anchors and operator-fingerprint signing are deferred** — the critic correctly identified them as paying every-night costs to detect a threat (A3) that already requires shell on the operator. Promotion stays **read-only verdict + hand-edited PR against `bench/{tc}/registration.py#current_tier`** (security's TB-6 shape, slightly amended — tier state lives next to the bench, not in a separate `docs/trust-tiers.yaml`, because the latter creates a cross-bench central edit Phase 7 cannot make under its no-edits-to-existing-code invariant).

## Goals (concrete, measurable)

| # | Goal | Source |
|---|---|---|
| G1 | `src/codegenie/eval/` package exports ≤ 8 public names; mypy `--strict` clean; ruff `C901` complexity ≤ 8/function. | `[B]` |
| G2 | `BenchScore` is `frozen=True, extra="forbid"`; `score ∈ [0, 1]` validated; static-introspection test rejects field names matching `confidence | llm | self_reported | model_says`. | `[B+S]` (mirrors Phase 5 ADR-0014) |
| G3 | Rubric runs in an isolated subprocess (`subprocess.run`, `env={}`, `cwd=<tmpfs scratch>`, hard wall-clock cap, JSON stdin/stdout). The rubric is **never** imported into the harness Python process. | `[S]` (modulated — subprocess, not microVM, in Phase 6.5) |
| G4 | Promotion is read-only: `PromotionGate.evaluate(...) → PromotionVerdict` is a pure function; no code path mutates a tier. Tier change is a hand-edited PR against `bench/{tc}/registration.py#current_tier` reviewed by CODEOWNERS. | `[B+S]` |
| G5 | Audit records are JSON files at `.codegenie/eval/runs/<utc-iso>-<short>.json` (mode 0600, atomic write via `os.replace`); each record carries `prev_hash` linking to the previous run for the same task class; `codegenie eval verify` re-walks the chain. | `[S]` (chain) + `[B]` (Phase-0 RunRecord shape) |
| G6 | Fence-CI gate: a task class registered via `@register_task_class("foo")` without `bench/foo/{cases,rubric.py,registration.py,README.md}` and `≥ min_cases_for_promotion[bronze]` cases fails CI with a specific diagnostic naming the missing path. AST-walk **plus** a literal-decorator-name lint rule (rejects aliased imports of `register_task_class` inside `bench/*/registration.py`). | `[B+S]` (closes critic's alias-dodge) |
| G7 | `codegenie eval run --task-class=vuln-remediation` exits 0 against the backfilled bench; emits per-case JSONL to stdout + a single aggregate; writes the audit record. CI runs cassettes only (Phase 4 discipline); no live LLM calls in CI. | `[P+B+S]` (all three agree) |
| G8 | `BenchScore.cost_usd` is mandatory and aggregated into `BenchRunReport.total_cost_usd`. Operator live runs accept `--max-cost-usd` (default $5.00) and abort on exceed. Concurrent live runs use a `flock`-based per-task-class lock so the cost cap holds across processes. | `[P]` + critic's concurrent-cost-leak fix |
| G9 | Net-new runtime dependencies in `[project].dependencies`: 0. Pydantic v2, click, structlog, pyyaml already pinned; `blake3` is added to `[project.optional-dependencies].eval` only (BLAKE3 chain hashing matches Phase 0; eval is opt-in install). | `[B]` modulated — hashing matches Phase 0 (critic flagged the SHA-256 vs BLAKE3 divergence) |
| G10 | Total LOC for `src/codegenie/eval/` excluding docstrings + tests: ≤ 700 LOC (modest bump over `[B]`'s 600 to absorb the subprocess rubric runner + chain hashing). | `[B]` modulated |
| G11 | Cache layer: **deferred to Phase 7+ (or Phase 13)** with a documented seam in `RubricRunner` and `run_eval` so it can land without changing `BenchScore` or audit shape. Phase 6.5 ships no cache. | `[synth]` (resolves the critic's hardest attack on `[P]`) |
| G12 | Parallelism: **deferred to Phase 7+** with a `concurrency: int = 1` parameter on `run_eval` and a `RubricRunner` that is process-isolation-safe. Phase 6.5 runs serial. | `[synth]` (resolves critic's "serial is asserted, not argued" by accepting `[B+S]` for now and naming the upgrade path) |
| G13 | Sigstore anchors + operator-fingerprint signing: **deferred** to Phase 16 production hardening (tracked as a new ADR slot). Phase 6.5's chain detects local tamper; Phase 16's anchors detect host-compromise. | `[synth]` (resolves critic's L6 cost/benefit attack on `[S]`) |

## Architecture

```
src/codegenie/eval/
├── __init__.py            # public surface (≤ 8 re-exports)
├── models.py              # Pydantic v2: BenchCase, BenchScore, BenchRunReport,
│                          # PromotionVerdict, EvalRunRecord (the chained audit entry)
├── registry.py            # @register_task_class + TaskClassRegistry + default_registry
│                          # (mirrors @register_probe shape exactly — [B])
├── rubric.py              # Rubric Protocol (runtime_checkable) + RubricRunner Protocol
│                          # (the seam for subprocess-now / microVM-later)
├── rubric_runner.py       # SubprocessRubricRunner: spawns python -c "<rubric>"
│                          # with env={}, cwd=tmpfs-scratch, JSON stdin/stdout,
│                          # hard wall-clock cap. Strategy-pattern with a stub
│                          # InProcessRubricRunner for tests only (gated by env var,
│                          # never used in CI or by `codegenie eval run`).
├── loader.py              # bench/{tc}/cases/ → tuple[BenchCase, ...];
│                          # imports bench/{tc}/registration.py via real package path
│                          # (sys.path prepend on bench/, not synthesized name —
│                          # closes critic's importlib hand-wave)
├── runner.py              # run_eval(...) → BenchRunReport; SERIAL by default;
│                          # concurrency parameter is the seam for Phase 7+;
│                          # SUT invocation is async-aware (asyncio.run wrapping
│                          # documented and tested — closes critic's SIGALRM problem
│                          # by using asyncio.wait_for, not signal.SIGALRM)
├── promotion.py           # PromotionGate.evaluate(...) → PromotionVerdict; PURE
│                          # function. Reads `current_tier` from the registration
│                          # (TaskClass.current_tier), not from a central YAML.
├── audit.py               # write_run_record(report, out_dir) → Path;
│                          # chain-walks prior records for prev_hash;
│                          # codegenie eval verify command re-walks the chain.
├── errors.py              # EvalError hierarchy under CodegenieError
└── cli.py                 # `codegenie eval run` + `codegenie eval verify`
                           # + `codegenie eval promote-verdict` subcommands.

bench/                     # contract territory (CODEOWNERS-gated)
├── README.md              # the bench/ contract itself
├── vuln-remediation/
│   ├── registration.py    # @register_task_class("vuln-remediation",
│   │                      #   current_tier="bronze",
│   │                      #   min_cases_for_promotion={"silver": 10, "gold": 30, ...})
│   ├── rubric.py          # one class implementing Rubric (run via SubprocessRubricRunner)
│   ├── README.md          # what this bench measures + how to add cases
│   └── cases/
│       └── {case-id}/
│           ├── case.toml          # provenance, disposition, difficulty
│           ├── input/             # frozen repo snapshot OR input-pointer.toml
│           └── expected/          # ground-truth diff + expected CVE delta
├── migration-chainguard-distroless/
│   ├── registration.py
│   ├── rubric.py
│   ├── README.md
│   └── cases/...                  # ≥3 seed cases; Phase 7 expands to ≥10

.codegenie/eval/runs/<utc-iso>-<short>.json    # chained audit records
```

**Why this shape.**
- The package layout is `[B]`'s — every name a Phase 0/Phase 5 contributor recognizes.
- The `RubricRunner` strategy is the load-bearing departure: it bakes the security boundary into the type system today and lets the implementation evolve from `subprocess` to `microVM` later via ADR + a one-class swap.
- Tier state lives **on the registration** (not in `docs/trust-tiers.yaml`) so adding a new task class in Phase 7 is genuinely "extension by addition" — the critic's roadmap-level point #1.

## Components

### `src/codegenie/eval/registry.py` — `@register_task_class` + `TaskClassRegistry`
- **Provenance:** `[B]` with one `[S]` element (CODEOWNERS protection on `bench/**/registration.py`).
- **Purpose:** Open registry; same shape as `@register_probe` and `@register_signal_kind`.
- **Interface:**
  ```python
  @register_task_class(
      "vuln-remediation",
      current_tier="bronze",
      min_cases_for_promotion={"silver": 10, "gold": 30, "platinum": 100},
  )
  class VulnRemediationRubric(Rubric): ...
  ```
  `default_registry: TaskClassRegistry` (module-level singleton); `TaskClassRegistry()` is constructable for tests; `TaskClassAlreadyRegistered` raised on collision (mirrors `SignalKindAlreadyRegistered`).
- **Internal design:** `_task_classes: dict[str, TaskClass]`. The decorator returns the class unchanged.
- **Why this choice over the alternatives:** `[P]`'s `importlib.metadata` entry-point lookup is rejected — it requires installing each `bench/{tc}/` as a distribution, which (a) makes Phase 7 require a `pyproject.toml` edit (violates extension-by-addition); (b) makes test isolation hard (entry points are global). `[S]`'s `tools/digests.yaml` rubric pin is rejected for the same reason — central manifest edit on every rubric change blocks Phase 7's no-edits invariant. `[B]`'s direct decorator import wins.
- **Tradeoffs accepted:** Module-level singleton requires test discipline (use a fresh `TaskClassRegistry()` in unit tests). Same trade Phase 0 made.

### `src/codegenie/eval/models.py` — Pydantic v2 models
- **Provenance:** `[B]` shape, `[S]` field-name discipline, `[P]` cost field.
- **Purpose:** All wire types for the eval domain.
- **Interface:** `BenchCase`, `BenchScore`, `BenchRunReport`, `PromotionVerdict`, `EvalRunRecord` (chained audit entry), `TaskClass` (frozen `dataclass` with `rubric_class: type[Rubric]`).
  ```python
  class BenchScore(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      passed: bool
      score: float = Field(ge=0.0, le=1.0)
      breakdown: dict[str, float]              # flat — no nested dicts/lists in values
      failure_modes: tuple[str, ...]           # tuple for immutability
      cost_usd: float = Field(ge=0.0)
      duration_seconds: float = Field(ge=0.0)
      # No `confidence`, `llm_*`, `self_reported_*`, `model_says_*` fields.
      # Enforced by tests/unit/test_bench_score_static.py (mirrors Phase 5
      # ADR-0014's test_objective_signals_static.py).

  class EvalRunRecord(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      schema_version: Literal[1]
      task_class: str
      run_id: str                              # SHA-256 of (task_class || sorted_case_ids || score_jsons)
      report: BenchRunReport
      case_digest_set: dict[str, str]          # case_id → BLAKE3 of case directory
      rubric_digest: str                       # BLAKE3 of rubric.py
      cassette_digest_set: dict[str, str | None]  # case_id → BLAKE3 of cassette file
      harness_version: str
      started_at: datetime
      finished_at: datetime
      prev_hash: str                           # SHA-256 of previous record's bytes; "0"*64 at genesis
  ```
- **Internal design:** `extra="forbid", frozen=True` everywhere. `BenchScore.breakdown` is `dict[str, float]` (no nested values) — same anti-smuggle pattern as Phase 5 ADR-0014's `ObjectiveSignals.extra`. `failure_modes` is `tuple` not `list` so the type system rejects mutation.
- **Why this choice over the alternatives:** `[P]`'s `BenchScore` collapsed `provenance` and `case_id` *into* `BenchScore`; we keep them on `BenchCase`/`EvalRunRecord` to keep `BenchScore` purely "the rubric's facts about one case" (CLAUDE.md "Facts not judgments"). `[S]`'s `BenchRunRecord` becomes our `EvalRunRecord` with the same `prev_hash` chain but **without** Sigstore `operator_fingerprint` and `microvm_image_digest` (deferred per G13).
- **Tradeoffs accepted:** Banned-substring static check is necessary but not sufficient (critic correctly flagged `evidence_strength` could smuggle confidence). The structural defense is `extra="forbid"` + the per-rubric review; the substring check is an early warning, not the whole defense. Documented in the test's docstring.

### `src/codegenie/eval/rubric.py` + `rubric_runner.py` — Rubric Protocol + RubricRunner strategy
- **Provenance:** `[B]` Protocol shape; `[S]` isolation discipline; `[synth]` subprocess-now-microVM-later split.
- **Purpose:** The contract every task class implements + the harness-side execution boundary.
- **Interface:**
  ```python
  @runtime_checkable
  class Rubric(Protocol):
      """Stateless. One method. Implementations live in bench/{tc}/rubric.py."""
      def score(self, case: BenchCase, harness_output: Mapping[str, Any]) -> BenchScore: ...

  class RubricRunner(Protocol):
      """The execution boundary. Strategy pattern: SubprocessRubricRunner now,
      future MicroVMRubricRunner under ADR amendment."""
      async def run(
          self,
          rubric_path: Path,
          case: BenchCase,
          harness_output: Mapping[str, Any],
          *,
          wall_clock_cap_seconds: float,
      ) -> BenchScore: ...

  class SubprocessRubricRunner:
      """Default. Spawns `python -I -B <rubric_runner_entrypoint> < inputs.json > output.json`
      with env={}, cwd=<tmpfs scratch dir>, no inherited file descriptors, hard wall-clock
      cap via asyncio.wait_for(asyncio.create_subprocess_exec(...).wait(), timeout=...).
      JSON stdin/stdout — the rubric never shares memory with the harness. The runner
      copies bench/{tc}/rubric.py bytes into the scratch dir before spawn (no import).
      """
  ```
- **Internal design:** `SubprocessRubricRunner` uses `asyncio.create_subprocess_exec` with `env={}`, `cwd=<scratch>`, `stdin=PIPE`, `stdout=PIPE`, `stderr=PIPE`. Inputs serialized as JSON (`{case: <BenchCase.model_dump>, harness_output: ...}`) into stdin. Output read from stdout, parsed via `BenchScore.model_validate_json` (catches `extra="forbid"` violations + range errors). On timeout: `proc.kill()`, return `BenchScore(passed=False, failure_modes=("rubric_timeout",), score=0.0, ...)`. On non-zero exit or malformed output: `BenchScore(passed=False, failure_modes=("rubric_malformed",), ...)`. The rubric `.py` file is **copied** into scratch (not imported); the subprocess runs `python /scratch/rubric_entrypoint.py` where the entrypoint loads `/scratch/rubric.py` and dispatches.
- **Why this choice over the alternatives:** `[P]` and `[B]` import the rubric in-process — critic correctly identifies this as RCE-on-operator-host. `[S]` mandates Firecracker microVM — critic correctly identifies that GitHub-hosted CI runners can't run nested-virt without explicit config, and that gVisor-on-Lima is a second sandbox stack on top of Phase 5's DinD. **Subprocess with `env={}` and `cwd=<tmpfs>` is the load-bearing 80% of microVM isolation at 5% of the cost.** It blocks env-var read, restricts FS to scratch, breaks shared memory, and runs anywhere Python runs. It does **not** block network egress or `/etc/passwd` read — those are addressed by a future ADR-amend that swaps `SubprocessRubricRunner` for `MicroVMRubricRunner` in Phase 16. Crucially, the **`BenchScore` shape is identical either way**, so swapping runners does **not** invalidate prior audit records (the critic's strongest argument for getting rubric isolation right *now*).
- **Tradeoffs accepted:** Subprocess does not block network egress in Phase 6.5. A malicious rubric merged through CODEOWNERS can `urllib.request.urlopen("http://attacker.example")`. We accept this on the grounds that (a) CODEOWNERS + two-reviewer rule (G3 + the new invariant on `bench/**/rubric.py`) is the L1 defense; (b) the production sandbox in Phase 5 already establishes the network-egress-blocking pattern that Phase 16 will inherit; (c) shipping subprocess **now** preserves the audit-chain comparability that microVM-from-day-one would have required Firecracker on an unsupported substrate. We document a `tests/adversarial/test_rubric_isolation.py` that asserts `os.environ.get("ANTHROPIC_API_KEY")` returns `None` and that `Path("/scratch/").iterdir()` shows only the expected files; the network-egress test is `xfail` with a pointer to the future ADR.

### `src/codegenie/eval/loader.py` — bench-directory loader
- **Provenance:** `[B]` core, `[synth]` import-path fix.
- **Purpose:** Load `bench/{tc}/cases/*/case.toml` into `tuple[BenchCase, ...]`; trigger `bench/{tc}/registration.py` import for decorator side-effect.
- **Interface:** `load_task_class(name, bench_root=Path("bench")) -> TaskClass`; `load_cases(task_class) -> tuple[BenchCase, ...]`.
- **Internal design:** Prepends `bench_root.resolve()` to `sys.path` exactly once (under a `_bench_path_added` module guard), then `importlib.import_module(f"{name.replace('-', '_')}.registration")` — same shape as Phase 0's `codegenie.probes.{name}` import but with the bench root explicitly on `sys.path`. The `_codegenie_bench` synthesized prefix from `[B]` is rejected (critic correctly identified it as not actually working). `case.toml` parsed with stdlib `tomllib`. Sorted by `case_id` for determinism.
- **Why this choice over the alternatives:** `[P]`'s `importlib.metadata.entry_points` requires distribution install; `[B]`'s synthesized prefix doesn't resolve. `sys.path` prepend is the simplest approach that actually works and matches Phase 0's mental model.
- **Tradeoffs accepted:** Mutating `sys.path` is global state. We do it once, idempotently, and document it. Tests that need isolation use a fresh `TaskClassRegistry()` and pass `bench_root` explicitly.

### `src/codegenie/eval/runner.py` — `run_eval`
- **Provenance:** `[B]` shape, `[synth]` async correctness, `[P]` concurrency seam (deferred wire-up).
- **Purpose:** End-to-end execution for one task class.
- **Interface:**
  ```python
  async def run_eval(
      task_class_name: str,
      *,
      case_filter: Callable[[BenchCase], bool] | None = None,
      system_under_test: Callable[[BenchCase], Awaitable[Mapping[str, Any]]],
      rubric_runner: RubricRunner | None = None,        # default: SubprocessRubricRunner
      timeout_per_case_seconds: float = 600.0,
      concurrency: int = 1,                              # ≥1; Phase 6.5 ships 1
      max_cost_usd: float = 5.0,
      out_dir: Path = Path(".codegenie/eval/runs"),
      bench_root: Path = Path("bench"),
  ) -> BenchRunReport: ...
  ```
- **Internal design:** `async def`; the harness is async-shaped from Phase 6.5 because Phase 6's SUT is `async` (LangGraph `ainvoke`). Per-case timeout via `asyncio.wait_for(system_under_test(case), timeout=timeout_per_case_seconds)` — **not** `signal.SIGALRM` (critic correctly flagged the SIGALRM-vs-asyncio incompatibility in `[B]`). Per-case `try/except Exception` isolates failures: `BenchScore(passed=False, failure_modes=(f"harness_error: {type(e).__name__}",), score=0.0, cost_usd=0.0, ...)`. Concurrency: `asyncio.Semaphore(concurrency)`; with `concurrency=1` the semaphore is a no-op (serial). Cost cap: rolling sum of `BenchScore.cost_usd`; on exceed, cancel outstanding tasks (`task.cancel()`), set `BenchRunReport.aborted=True`, exit non-zero. Concurrent-process cost-cap protection: acquire a `flock` on `<bench_root>/.<task_class>.runlock` for live runs (`max_cost_usd > 0` and not in cassette mode); CI runs (cassettes only) skip the lock.
- **Why this choice over the alternatives:** `[B]`'s synchronous loop with `signal.SIGALRM` does not compose with Phase 6's async SUT. `[P]`'s aggressive parallelism + content-addressed cache extracts wall-clock at the cost of a `sut_digest` strategy the critic correctly demolished. `[S]`'s strict-serial is the right Phase 6.5 default but its "concurrency is an integrity-correlation risk" is rhetorical, not argued. We ship **serial in Phase 6.5 with a documented concurrency parameter**, accepting `[B+S]`'s wall-clock cost in exchange for shipping the right concurrency boundary that future phases extend without re-shaping.
- **Tradeoffs accepted:** No cache in Phase 6.5 (G11). Nightly serial run cost is the cost of correctness-before-speed at this surface size. The `RubricRunner` Protocol + `concurrency` parameter are the seams for Phase 7+ to layer on cache + parallelism without breaking the audit chain.

### `src/codegenie/eval/promotion.py` — `PromotionGate`
- **Provenance:** `[B]` pure-function shape, `[S]` apply-blocking discipline, `[synth]` tier-on-registration location.
- **Purpose:** Compute a `PromotionVerdict` from a `BenchRunReport` + the registration's tier config.
- **Interface:**
  ```python
  class PromotionGate:
      def evaluate(
          self,
          task_class: TaskClass,
          report: BenchRunReport,
          target_tier: Literal["silver", "gold", "platinum"],
          tier_thresholds: Mapping[str, float],   # passed in; loaded from registration
      ) -> PromotionVerdict: ...

      def apply(self, *args, **kwargs) -> NoReturn:
          raise PromotionMustBeHumanAuthorized(
              "Tier promotion is a hand-edited PR against "
              "bench/{task_class}/registration.py#current_tier."
          )
  ```
  Verdict carries `current_tier` (read from `task_class.current_tier`), `target_tier`, `evidence_sufficient: bool`, `reasons: tuple[str, ...]` (every failed condition listed individually, not just the first).
- **Internal design:** Pure function; no I/O writes outside an optional `.codegenie/eval/recommendations/<utc-iso>.json` audit-trail file (informational only). `evidence_sufficient = True` iff `report.mean_score ≥ tier_thresholds[target_tier]` AND `report.passed_count ≥ task_class.min_cases_for_promotion[target_tier]` AND `report.block_severity_failure_modes == ()`.
- **Why this choice over the alternatives:** `[B]`'s `docs/trust-tiers.yaml` central tier file would force Phase 7 to edit `docs/trust-tiers.yaml` — violating Phase 7's "no edits to existing code" exit criterion. `[S]`'s tier-on-registration is correct; we adopt it. `[S]`'s `apply()` raising unconditionally is a strong "fail-loud" signal — we keep it.
- **Tradeoffs accepted:** Tier state coupling: `current_tier` lives in code (`registration.py`). A tier promotion is a one-line code change reviewed via the standard PR flow. This is the same mechanism CODEOWNERS already governs; adding a separate YAML store would be ceremony without payoff.

### `src/codegenie/eval/audit.py` — chained audit-record writer
- **Provenance:** `[B]` Phase-0 RunRecord shape, `[S]` chain hashing (without Sigstore anchors).
- **Purpose:** Atomically write `EvalRunRecord` to `.codegenie/eval/runs/<utc-iso>-<short>.json`; chain-walk on read.
- **Interface:**
  - `write_run_record(record: EvalRunRecord, out_dir: Path) -> Path` — computes `prev_hash` from the most recent record for the same task class; writes mode 0600 atomically via `os.replace`.
  - `verify(task_class: str, since: datetime | None = None) -> VerifyResult` — re-walks chain entries; reports gaps and tampered records.
  - **No `publish_anchor`** — Sigstore + GPG are deferred per G13.
- **Internal design:** `prev_hash = sha256(read_bytes(prior_record_path))` for the most recent prior record by `started_at` for the same `task_class`. Genesis: `"0" * 64`. BLAKE3 (via `blake3` PyPI dep in `[project.optional-dependencies].eval`) for content hashing of cases/rubric/cassettes — **matches Phase 0's `codegenie/hashing.py`** (G9; closes the critic's SHA-256-vs-BLAKE3 divergence in `[B]`). The audit-chain identity hash is SHA-256 over the record bytes (matches Phase 0's identity-tuple convention; the chain head is verifiable without BLAKE3 if `eval` extras aren't installed).
- **Why this choice over the alternatives:** `[P]`'s JSONL stream + `runs.jsonl` index has no chain — once tampered, undetectable. `[S]`'s full Sigstore pipeline pays an every-night cost for a defense layer (L6) whose threat model assumes shell on the operator. We ship the chain (cheap, valuable) and defer Sigstore + GPG anchors to a future phase ADR. The chain alone catches every mid-stream tamper; Sigstore catches *post-pull-divergence*, which is a Phase 16 concern.
- **Tradeoffs accepted:** Without Sigstore anchors, an attacker with shell on the operator can rewrite `.codegenie/eval/runs/` end-to-end (recompute every `prev_hash`) and the local chain re-verifies. We accept this because (a) the threat already requires shell-on-operator, (b) the published audit anchor in git history can be added as a trivial follow-on PR (`audit/anchors/eval/<date>.json` with the chain head, no Sigstore), and (c) doing it now would either require Sigstore (paying the operational debt the critic correctly flagged) or operator GPG keys (unrealistic). Documented as a known gap.

### `src/codegenie/eval/cli.py` — `codegenie eval` subcommands
- **Provenance:** `[B]` click structure; `[P]` JSONL-to-stdout discipline; `[S]` `verify` subcommand.
- **Purpose:** Operator + CI surface.
- **Interface:**
  - `codegenie eval run --task-class=<name> [--cases=<glob>] [--concurrency=<int>] [--max-cost-usd=<float>] [--out=<path>] [--bench-root=<path>]`
  - `codegenie eval verify --task-class=<name> [--since=<iso>]`
  - `codegenie eval promote-verdict --task-class=<name> --target-tier=<tier>`
- **Internal design:** Heavy imports deferred per Phase 0 import-linter contract. Stdout is JSONL by default (one `BenchScore` per line, then one aggregate line, then the promotion verdict if `promote-verdict`); structlog logs to stderr. Exit codes: 0 on success; 1 on harness error; 2 on cost-cap exceeded; 3 on `TaskClassNotFound`; 4 on `bench/{name}/cases/` empty.
- **Tradeoffs accepted:** No `--watch`, no progress bar. `tqdm`-free; this is a CI-first tool.

### `bench/{task-class-slug}/` directory contract
- **Provenance:** `[B]` layout, `[S]` provenance metadata + CODEOWNERS, `[synth]` no `cases/digests.yaml` central pin.
- **Structure (enforced by fence-CI):**
  ```
  bench/{slug}/
  ├── registration.py   # exactly one @register_task_class("{slug}") call;
  │                     # current_tier="bronze" at first register
  ├── rubric.py         # one class implementing Rubric Protocol
  ├── README.md         # what this bench measures + how to add cases
  └── cases/
      └── {case-id}/
          ├── case.toml
          ├── input/             # frozen snapshot OR input-pointer.toml
          ├── expected/
          └── cassette.yaml      # optional; Phase 4 cassette path
  ```
  `case.toml` schema: `case_id`, `task_class`, `disposition` (positive/negative/ambiguous), `difficulty`, `source` (curated/outcome-ledger-derived/regression-converted), `commit_sha` (required iff `source != "curated"`), `added_at`, `last_validated_at`, optional `cassette_path`, optional `cassette_blake3` (the per-case integrity pin from `[S]`'s TB-8 — Phase 6.5 makes it advisory; Phase 7+ may make it strict).
- **Why this choice over the alternatives:** `[S]`'s `cases/digests.yaml` central digest pin is rejected — it forces a central edit on every case add, plus the critic correctly identified that "one mismatch → abort" turns one bad case into nuking the whole night's run. We move integrity pins to per-case (`cassette_blake3` in `case.toml`) and keep them advisory in 6.5 (warn-not-abort) so a single curation typo doesn't block all promotion evidence. CODEOWNERS protection on `bench/**` handles the "soften the corpus" threat at the L1 layer.
- **Tradeoffs accepted:** Bench cases live in this repo (all three lenses agreed; ADR-0016 §Open Q4 defers the split). When migration cases start including customer Dockerfiles, a sibling `codewizard-sherpa-benches` repo becomes the right move — flagged as an open question for Phase 7's exit review.

### Fence-CI test extension
- **Provenance:** `[B]` AST walk, `[S]` literal-decorator lint, `[synth]` alias-dodge fix.
- **Purpose:** A task class registered via `@register_task_class("foo")` without `bench/foo/{cases,rubric.py,registration.py,README.md}` and ≥10 cases fails CI with a specific diagnostic.
- **Internal design:** Two-stage. Stage 1: AST-walk every `bench/*/registration.py`, find calls to `register_task_class` (name-or-attribute matching, accepting `register_task_class(...)`, `eval_registry.register_task_class(...)`, etc.) with a string-literal first argument. **Reject** non-literal first args with a specific error (closes critic's literal-name hole). Stage 2: For each registered name, assert directory contract + ≥ `min_cases_for_promotion["bronze"]` cases (default 10). The matcher does **not** trigger on aliased imports (`from codegenie.eval import register_task_class as rtc`) because we require the literal symbol name `register_task_class` in the decorator position — closes critic's alias-dodge with a one-line lint rule documented in `bench/README.md`.
- **Wall-clock budget:** ≤ 2s for the whole fence test (`[P]`'s budget; the AST-only check makes it cheap).

## Data flow

End-to-end `codegenie eval run --task-class=vuln-remediation`:

1. **CLI parse + lazy import.** `click` parses; `runner.run_eval` and `loader.load_task_class` imported on demand. Phase 6's `build_vuln_loop` is **not** imported here — only inside the `system_under_test` callable wired by the CLI.
2. **Loader.** `load_task_class("vuln-remediation")` prepends `bench/.resolve()` to `sys.path` once, then `importlib.import_module("vuln_remediation.registration")`. Decorator fires → `default_registry.register(TaskClass(...))` → `TaskClassAlreadyRegistered` on collision (loud crash). `load_cases(task_class)` walks `cases/*/case.toml`, parses with `tomllib`, validates via `BenchCase` Pydantic model. Sorted by `case_id`.
3. **Runner.** `run_eval(...)` async; instantiates `SubprocessRubricRunner`. **For each case, in serial (concurrency=1):**
   - `harness_output = await asyncio.wait_for(system_under_test(case), timeout=600.0)` — Phase 6's `build_vuln_loop().ainvoke(...)` with cassette replay; on `TimeoutError` or `Exception` → `BenchScore(passed=False, failure_modes=("timeout",) or ("harness_error: ...",))`.
   - `score = await rubric_runner.run(rubric_path, case, harness_output, wall_clock_cap_seconds=60.0)` — subprocess spawn with `env={}, cwd=<tmpfs scratch>`; JSON I/O; Pydantic validates output (`extra="forbid"` + `score ∈ [0,1]`).
   - `cost_total += score.cost_usd`; if `cost_total > max_cost_usd`, cancel outstanding tasks, mark `BenchRunReport.aborted = True`, exit code 2.
   - Score logged as one JSONL line to stdout via structlog.
4. **Aggregate.** `mean_score`, `passed_count`, `total_cost_usd`, `block_severity_failure_modes` (union across cases). Compute `run_id = sha256(task_class || sorted_case_ids || score_jsons)` (deterministic — two engineers running the same SUT + cassettes get the same `run_id`).
5. **Audit.** `audit.write_run_record(EvalRunRecord(report, prev_hash=..., case_digest_set=..., rubric_digest=..., cassette_digest_set=..., harness_version=..., started_at, finished_at), out_dir=.codegenie/eval/runs/)`. Atomic write via `os.replace(tmp, final)`. Mode 0600. `prev_hash` derived from the most recent prior record for this task class.
6. **Promotion verdict (optional, via separate subcommand).** `promote-verdict --target-tier=silver` reads the latest `EvalRunRecord` for the task class, verifies the chain via `audit.verify`, calls `PromotionGate.evaluate(...)`, prints the verdict as JSON. **Does not modify any tier.**
7. **Exit.** Code 0 if every case passed AND no `block`-severity failure mode AND not aborted; otherwise non-zero.

**Trust boundary crossings (per security lens):**
- TB-1 (curator → `bench/`): CODEOWNERS-protected branch. `[Phase 6.5]`
- TB-2 (rubric.py source → rubric *executor*): `SubprocessRubricRunner` boundary; JSON I/O over pipe; `env={}`; `cwd=<scratch>`. `[Phase 6.5]`
- TB-3 (rubric subprocess → harness): Pydantic schema validation on JSON output; range checks; wall-clock + RSS caps enforced by harness. `[Phase 6.5]`
- TB-4 (harness → audit): chained `EvalRunRecord` writes; `codegenie eval verify` re-walks. `[Phase 6.5]`
- TB-5 (audit → promotion gate): gate refuses to read on chain-tamper detection. `[Phase 6.5]`
- TB-6 (promotion gate → tier change): `apply()` always raises; tier change is a hand-edited PR. `[Phase 6.5]`
- TB-7 (outcome ledger → `regression-converted` cases): contract for Phase 13; Phase 6.5 defines `BenchCase.source = "regression-converted"` shape but doesn't ship the conversion path. `[Phase 13]`
- TB-8 (cassette → bench runner): `cassette_blake3` per case; advisory in 6.5; strict in 7+. `[Phase 7+]`
- TB-9 (chain → published anchor): Sigstore/GPG anchors deferred to Phase 16. `[Phase 16]`

## Failure modes & recovery

| Failure | Detected by | Containment | Recovery | Source |
|---|---|---|---|---|
| Duplicate `@register_task_class("foo")` | `TaskClassRegistry.register` at import time | `TaskClassAlreadyRegistered` raised loudly with both qualnames | Rename one; PR cannot land | `[B]` |
| `case.toml` malformed | `BenchCase` Pydantic validation in `loader.load_cases` | `BenchCaseLoadError` with case directory + failing field; **the failing case is excluded; other cases continue**; aggregate marked `had_load_errors=True`; exit code 1 | Fix `case.toml`; re-run | `[B]` modulated — exclude-and-continue is the intentional containment so one bad case doesn't nuke the night (closes critic's `[S]` "one mismatch → abort" attack); the run still exits non-zero (CLAUDE.md "Fail loud") |
| SUT raises during one case | Per-case `try/except Exception` in `run_eval` | `BenchScore(passed=False, failure_modes=("harness_error: <Type>: <msg>",), score=0.0, cost_usd=0.0)`; other cases continue | Investigate the SUT failure; the case becomes a regression test | `[B+P]` |
| SUT exceeds `timeout_per_case_seconds` | `asyncio.wait_for` `TimeoutError` | `BenchScore(passed=False, failure_modes=("timeout",), ...)`; other cases continue | Widen the timeout if legitimate; otherwise treat as a real failure | `[synth]` (asyncio.wait_for, not SIGALRM — closes critic's `[B]` SIGALRM problem) |
| Rubric subprocess returns non-JSON or malformed `BenchScore` | Subprocess stdout parse + Pydantic validation | `BenchScore(passed=False, failure_modes=("rubric_malformed: <detail>",), ...)`; other cases continue | Investigate the rubric; CI runs rubric unit tests as a separate gate | `[S]` modulated |
| Rubric subprocess exceeds wall-clock cap | `asyncio.wait_for` on the subprocess | `proc.kill()`; `BenchScore(passed=False, failure_modes=("rubric_timeout",), ...)`; other cases continue | Investigate rubric performance; raise cap if legitimate | `[S]` |
| Rubric attempts env-var read | Subprocess `env={}` | `os.environ.get("ANTHROPIC_API_KEY")` returns `None`; rubric continues but produces a wrong score | Adversarial test (`tests/adversarial/test_rubric_env_read.py`) catches at PR time | `[S]` modulated (subprocess, not microVM) |
| Rubric attempts network egress | **Not blocked in Phase 6.5**; documented gap | An attacker with merged-rubric access can exfiltrate (CODEOWNERS is the L1 defense) | Phase 16 ADR introduces `MicroVMRubricRunner`; `BenchScore` shape unchanged so audit chain remains comparable | `[synth]` (deferred per G13) |
| Cost cap exceeded mid-run | Aggregator after each `BenchScore` | Cancel outstanding tasks; `BenchRunReport.aborted=True`; exit code 2 | Cached scores stand for completed cases | `[P]` |
| Concurrent live runs racing on cost cap | `flock` on `<bench_root>/.<task_class>.runlock` for live runs | Second invocation blocks until first releases | Operator runs serially; CI cassette runs skip the lock | `[synth]` (closes critic's `[P]` concurrent-cost-leak attack) |
| Audit chain tampered | `audit.verify` re-walks chain on `promote-verdict` | `ChainTamperDetected` raised; promotion gate refuses to read | Investigate (likely operator host compromise); restore from a prior commit's audit dir | `[S]` modulated |
| `bench/{name}/registration.py` missing `@register_task_class` literal | Fence-CI AST walk (Stage 1) | CI fail with named diagnostic; PR blocked | Add the decorator with a literal name | `[B+S]` |
| New task class registered without `bench/{name}/cases/` ≥ 10 cases | Fence-CI dir-walk (Stage 2) | CI fail naming the missing path | Land cases (or land the registration in the same PR with cases) | `[B]` |
| `BenchScore` smuggles a banned field name | Static-introspection test + `extra="forbid"` runtime | CI fail before merge | Rename the field; the substring check is an early warning, not the whole defense | `[B+S]` |
| `promotion.apply()` called from code | `PromotionMustBeHumanAuthorized` raised unconditionally | Loud failure with stack trace | Tier change must be a hand-edited PR | `[S]` |

## Resource & cost profile

- **Wall-clock for nightly `bench/vuln-remediation/` (10 cases, serial, cassette replay):** dominated by SUT — typically 10 × 5–30 s = 50–300 s. Subprocess rubric overhead: ~50–200 ms per case (subprocess fork + Python startup + JSON parse). **Total nightly: ~1–6 minutes.** Acceptable for nightly cadence per ADR-0016 §Decision §5.
- **Wall-clock for fence-CI gate:** ≤ 2 s.
- **CLI cold start:** ≤ 600 ms (Phase 0 import-linter contract preserved; `pydantic`/`click`/`structlog` deferred to subcommand body).
- **Memory:** O(cases) Pydantic instances; ≤ 50 MB for a 100-case run. Subprocess rubric: ~30–80 MB resident per spawn (one at a time in serial mode).
- **Disk:** Each run writes ~10–30 KB JSON. 365 nightly × 2 task classes × ~20 KB = ~15 MB/yr durable. No retention/rotation in Phase 6.5; Phase 16 adds it.
- **LLM cost:** $0 in CI (cassettes only). Live operator runs surfaced via `BenchScore.cost_usd` → `BenchRunReport.total_cost_usd`; `--max-cost-usd` (default $5.00) enforces per-run cap; `flock` enforces cross-process cap.
- **Where security/best-practices cost performance:** subprocess rubric adds ~50–200 ms/case vs in-process import. At 10 cases × 200 ms = 2 s of nightly overhead — far below the SUT-dominated wall-clock. **Worth it** to ship the right rubric trust boundary on day one.
- **Where the synthesis explicitly defers performance:** no cache (G11), no parallelism (G12). The performance lens's headline 8-min cold-cache target becomes ~6-min-and-acceptable. Phase 7+ can layer cache + concurrency on the documented seams (`RubricRunner` Protocol + `concurrency` parameter) without invalidating audit-chain comparability. The critic correctly identified that anything reversible can wait.

## Test plan

### Unit tests (≥ 90% line, ≥ 80% branch on `src/codegenie/eval/`; `[B]`'s budget kept)

- `test_eval_registry.py` — decorator registers; duplicate raises `TaskClassAlreadyRegistered` with both qualnames; `default_registry` singleton; fresh `TaskClassRegistry()` for tests.
- `test_eval_models.py` — `frozen=True` rejects mutation; `extra="forbid"` rejects unknown fields; `BenchScore.score` rejects 1.5/-0.1; `BenchCase.disposition` rejects unknown literal; `commit_sha` required iff `source != "curated"`.
- `test_bench_score_static.py` — **load-bearing.** Recursive field walk; rejects `confidence | llm | self_reported | model_says` substrings. (Direct port of Phase 5's `test_objective_signals_static.py`. Documented as early warning, not whole defense — critic flagged the `evidence_strength` smuggle path.)
- `test_rubric_protocol.py` — `isinstance(rubric, Rubric)` for every registered task class.
- `test_loader.py` — sorted by `case_id`; malformed `case.toml` raises `BenchCaseLoadError` naming the case dir; missing `input/` raises with the missing path; sys.path prepend is idempotent.
- `test_runner.py` — single-case run produces `BenchRunReport`; SUT exception → `harness_error` `BenchScore`; SUT timeout → `timeout` `BenchScore`; rubric malformed output → `rubric_malformed` `BenchScore`; rubric timeout → `rubric_timeout`; aggregate `mean_score` correct; cost-cap exceed cancels outstanding tasks.
- `test_promotion.py` — `evidence_sufficient=True` only when all three conditions met; `reasons` enumerates every failed condition; `apply()` raises `PromotionMustBeHumanAuthorized`; `evaluate` does not write any file outside the (optional) recommendations dir.
- `test_audit.py` — atomic write at mode 0600; filename `{utc-iso}-{8-hex}.json`; `prev_hash` correctly chains the most-recent prior record for the same task class; `verify` detects a single-record edit and reports the offending record.
- `test_cli.py` — `--task-class=unknown` exits 3; missing `--task-class` exits 2; `--cases='001-*'` filters; `eval verify` walks the chain and reports tampered records.
- `test_eval_fence.py` — **load-bearing.** Synthetic `bench/foo/` with registration but no `cases/` fails; with 9 cases fails; fully-populated passes; non-literal first arg fails with named diagnostic; aliased import (`register_task_class as rtc`) fails (closes critic's alias-dodge).
- `test_eval_package_imports_no_llm_sdk.py` — AST walk; reject `import anthropic | openai | langchain | langgraph | transformers` from `src/codegenie/eval/`.

### Property tests

- `test_benchscore_invariants.py` (Hypothesis) — `0 ≤ score ≤ 1`; `failure_modes` is a tuple; `passed_count(report) ≤ len(report.per_case)`. Roadmap §Phase 6.5 testing requirement.
- `test_runner_aggregate_correctness.py` — runner-computed `mean_score == statistics.fmean(s.score for s in scores)`.

### Integration tests

- `test_eval_end_to_end_vuln.py` — `codegenie eval run --task-class=vuln-remediation` against backfilled bench (10 cases) exits 0; emits 10 JSONL + 1 aggregate; writes one audit JSON; aggregate `mean_score` matches snapshot (regenerated via `scripts/regen_eval_snapshot.py` per ADR-0007 contract pattern).
- `test_eval_promotion_verdict.py` — synthetic `BenchRunReport` + synthetic registration → `PromotionVerdict` with right shape; no tier mutation.
- `test_phase4_cassette_replay.py` — one vuln case via Phase 4 cassette replay; two consecutive runs produce identical `run_id`. ADR-0016 §Tooling assertion as executable test.
- `test_audit_chain_walks.py` — write 5 records, `verify` returns clean; mutate one byte in record 3, `verify` returns mismatch at record 3.
- `test_concurrent_cost_cap.py` — two concurrent live-mode `eval run` invocations on the same task class; second blocks on `flock`; total cost ≤ cap (closes critic's `[P]` concurrent-cost-leak attack).

### Adversarial tests

- `test_rubric_env_read.py` — rubric subprocess attempts `os.environ.get("ANTHROPIC_API_KEY")`; assert returned `None` because subprocess `env={}`.
- `test_rubric_fs_isolation.py` — rubric attempts `Path("/etc/passwd").read_bytes()`; assert it succeeds (subprocess does not block FS — known gap, documented), but a `Path("../../../").iterdir()` from `cwd=<scratch>` must show only the scratch contents.
- `test_rubric_network_egress.py` — `xfail` with explicit pointer to the future `MicroVMRubricRunner` ADR; rubric attempts `urllib.request.urlopen("http://attacker.example")`; passes today, fails (correctly) under microVM.
- `test_rubric_cannot_smuggle_llm_assessment.py` — rubric tries to return a dict with extra `llm_confidence` field; assert `extra="forbid"` raises and the case becomes `rubric_malformed`.
- `test_promotion_apply_blocked.py` — direct call to `promotion.apply(...)` raises `PromotionMustBeHumanAuthorized`.
- `test_chain_tamper_detected.py` — rewrite a record byte; `audit.verify` returns mismatch; `promote-verdict` exits non-zero.

### E2E

- `test_eval_run_against_real_bench.py` — `subprocess.run(["codegenie", "eval", "run", "--task-class=vuln-remediation"])`; exit 0; one new audit file; stdout contains 10 JSONL + aggregate.

### Golden files

- `tests/snapshots/eval_run_report.v1.json` — frozen `BenchRunReport` shape; regen via `scripts/regen_eval_snapshot.py` (ADR-0007 pattern).

## Risks (top 5)

1. **Subprocess rubric isolation is weaker than microVM and the gap is real.** A merged-through-CODEOWNERS rubric can read host FS outside scratch (`/etc/passwd`), egress to network, and consume unbounded RSS until OS kill. **Mitigation:** CODEOWNERS + two-reviewer rule on `bench/**/rubric.py` is the L1 defense; the `BenchScore` shape is identical between subprocess and microVM so a future ADR-amend swaps the runner without invalidating prior audit records (the load-bearing critic argument). The roadmap explicitly tracks this in a Phase 16 ADR slot.
2. **Bench-case curation cost dominates Phase 6.5's actual schedule.** ADR-0016 §Tradeoffs flags this; no design can fix it. **Mitigation:** ship `bench/vuln-remediation/` from Phases 3–4's solved-example corpus (zero net curation, just re-shaping); ship `bench/migration-chainguard-distroless/` with 3 seed cases from publicly-documented Chainguard examples; Phase 7 owns the expansion to ≥10. Critic correctly noted no design allocates engineering for case extraction — flagged for the implementation plan.
3. **Rubric correctness is itself untested.** A bug in `rubric.score(...)` makes every bench score wrong. **Mitigation:** every rubric ships with its own unit tests under `bench/{tc}/tests/`; CI runs them. Mutation-testing the rubric is ADR-0016 §Open Q5 — Phase 16 territory.
4. **`current_tier` lives in `registration.py` (a Python file edited by humans).** A typo in a tier promotion PR ("silver" → "siver") could pass review and silently fail the gate's `Literal[...]` check at runtime. **Mitigation:** `BenchCase.disposition` and `PromotionVerdict.current_tier` and `TaskClass.current_tier` all use `Literal["bronze","silver","gold","platinum"]` so Pydantic catches typos at registration import — fence-CI runs registration imports for every task class.
5. **The audit chain catches local tamper but not host-compromise-with-full-rewrite.** An attacker with shell on the operator can rewrite every `.json` record and recompute every `prev_hash` — local re-verify passes. **Mitigation:** Phase 16 ADR introduces published anchors (a daily commit of the chain head into git history); deferring per G13 because Sigstore vs. GPG is the wrong question to ship in Phase 6.5. Documented as a known gap.

## Synthesis ledger

### Vertex count
- Performance design `[P]`: ~38 atomic decisions extracted (cache, sut_digest, cassette_digest, asyncio pool, JSONL stream, `repo.tar.zst`, cost cap, `runs.jsonl` index, etc.)
- Security design `[S]`: ~42 (microVM rubric, BLAKE3 chain, Sigstore anchors, two-signature curation, `cases/digests.yaml`, TB-1..TB-8 boundaries, `apply()` raises, etc.)
- Best-practices design `[B]`: ~34 (Protocol vs ABC, `default_registry` singleton, `signal.SIGALRM`, `_codegenie_bench` import prefix, `docs/trust-tiers.yaml`, `tomllib`, etc.)
- **Total: ~114 vertices.**

### Edges
- AGREE: 22 (Pydantic `frozen=True, extra="forbid"`; `@register_task_class` decorator; `TaskClassAlreadyRegistered` collision shape; `BenchScore.score ∈ [0,1]`; static-introspection test on banned substrings; cassettes-only in CI; promotion is human; `bench/{tc}/{cases,rubric.py,registration.py}` directory contract; per-case `try/except`; CODEOWNERS on `bench/**`; etc.)
- CONFLICT: 13 (concurrency model; rubric isolation; cache layer; audit shape — JSONL vs chain vs Phase-0 RunRecord; bench provenance — descriptive vs two-signature vs CODEOWNERS-only; archive format — `.tar.zst` vs unspecified vs `input/expected/` dirs; cost cap; promotion authority shape; fence-CI implementation; hash algorithm; tier-state location — registration vs YAML; timeout mechanism; sandbox stack)
- COMPLEMENT: 8 (`[B]`'s typed errors + `[S]`'s adversarial tests + `[P]`'s property tests; `[B]`'s loader pattern + `[S]`'s digest verification; `[P]`'s cost cap + `[B]`'s ledger surfacing + `[S]`'s cost-discussion-deferral)
- SUBSUME: 5 (`[B]`'s and `[P]`'s rubric isolation are weaker variants of the same thing; `[S]`'s `BenchRunRecord` subsumes `[B]`'s `EvalRunRecord` shape)

### Conflict-resolution table

| Dimension | `[P]` picks | `[S]` picks | `[B]` picks | Winner | Exit-fit | Roadmap-fit | Commitments-fit | Critic-fit | Sum |
|---|---|---|---|---|---|---|---|---|---|
| Rubric isolation | In-process import | Per-case microVM (Firecracker/gVisor) | In-process import + Pydantic + static check | **Subprocess (`env={}`, JSON I/O) — synth** | 3 | 3 | 3 | 3 | 12 |
| Concurrency | asyncio pool sized to sandbox cap | Strict serial (asserted) | Serial + SIGALRM | **Serial in 6.5 with `concurrency` seam — `[B+S]`+synth** | 3 | 3 | 3 | 2 | 11 |
| Cache layer | Content-addressed `BenchScore` cache | None (deferred) | None | **None in 6.5; documented seam — `[S+B]`+synth** | 3 | 3 | 3 | 3 | 12 |
| Audit shape | JSONL stream + `runs.jsonl` index | BLAKE3-chained records + Sigstore anchors | Phase-0 RunRecord JSON | **Chained JSON records (no Sigstore) — `[B+S]` minus L6** | 3 | 3 | 3 | 3 | 12 |
| Bench provenance | Descriptive metadata | Two-signature CODEOWNERS + Sigstore + `cases/digests.yaml` | CODEOWNERS + 90-day staleness warn | **CODEOWNERS + per-case `cassette_blake3` advisory + staleness warn — `[B]`+synth** | 3 | 3 | 2 | 3 | 11 |
| Bench archive format | `.tar.zst` level 3 | Tar-serialization (unspecified) | `input/`+`expected/` dirs | **`input/`+`expected/` dirs (no archive) — `[B]`** | 3 | 2 | 3 | 3 | 11 |
| Cost cap | `--max-cost-usd` mid-run abort | Deferred to Phase 13 | Sum into report only | **`--max-cost-usd` + `flock` cross-process — `[P]`+synth** | 3 | 3 | 3 | 3 | 12 |
| Promotion authority | Read-only verdict as last JSONL line | `apply()` raises; tier in `registration.py#current_tier` | Read-only verdict; tier in `docs/trust-tiers.yaml` | **`apply()` raises + tier in registration.py — `[S]`** | 3 | 3 | 3 | 3 | 12 |
| Fence-CI implementation | Regex on first/second line | Three gates incl. workflow-digest meta-gate | AST walk for literal name | **AST walk + literal-symbol-name lint (no aliases) — `[B+S]`+synth** | 3 | 3 | 3 | 3 | 12 |
| Hash algorithm | `blake3` PyPI dep | BLAKE3 via `codegenie/hashing.py` | SHA-256 implied | **BLAKE3 (matches Phase 0) in `[project.optional-dependencies].eval` — `[S]`+synth** | 3 | 3 | 3 | 3 | 12 |
| Tier-state location | On registration (implicit) | On registration | `docs/trust-tiers.yaml` | **On registration — `[P+S]`** | 3 | 3 | 3 | 3 | 12 |
| Timeout mechanism | `asyncio.wait_for` (implicit) | Subprocess wall-clock | `signal.SIGALRM` | **`asyncio.wait_for` — `[P]`+synth** | 3 | 3 | 3 | 3 | 12 |
| Sandbox stack | None (in-process) | Firecracker on Linux/CI; gVisor-on-Lima on macOS | None | **Subprocess only — synth** (defers Phase 5's sandbox stack question) | 3 | 3 | 2 | 3 | 11 |

(Score legend per Step-3: 0=cannot win, 1=poor fit, 2=acceptable, 3=strong fit. Veto-strength on column 3.)

### Shared blind spots considered

| Blind spot (critic) | Carried forward / departed | Why |
|---|---|---|
| All three keep `bench/` in same repo (ADR-0016 §Open Q4 deferred) | **Carried forward for Phase 6.5; flagged for Phase 7 review** | Splitting introduces the org-shared-bench question (CODEOWNERS spans repos, etc.) the critic correctly identifies as Phase 7+ territory. Same-repo is the conservative default; flagged in §Risks. |
| All three hand-wave the live-LLM cadence | **Carried forward (no live-cadence commitment); G8 caps cost, defers cadence to Phase 13** | The critic is right that nobody knows when live evals run. We ship cost protection (`--max-cost-usd` + `flock`) so nobody can be surprised by a bill, and defer cadence per ADR-0016 §Open Q3. |
| All three treat `bench/vuln-remediation/` curation as easy | **Departed — flagged in §Risks #2** | Critic correctly notes none of the three allocates engineering for case extraction. Synthesizer flags this for the implementation plan; the harness is necessary but not sufficient — somebody has to extract 10 cases from the Phases 3–4 corpus. |

### Departures from all three inputs

1. **Subprocess `RubricRunner` instead of in-process (`[P]`/`[B]`) or microVM (`[S]`).** None of the three proposed it. The synth chooses subprocess because it captures ~80% of microVM's isolation at ~5% of the cost, runs everywhere Python runs (closes critic's CI-substrate attack), and — critically — preserves `BenchScore` shape so a future microVM swap doesn't invalidate audit records. Rationale: rubric isolation is the one non-reversible decision (per critic's §"Which disagreement matters most for *this* phase?"); shipping the boundary today is the load-bearing move; shipping the *strongest possible* boundary is not (microVM costs more than its threat reduction at this phase, given CODEOWNERS L1).
2. **`flock`-based cross-process cost cap.** None of the three handled the critic's "two concurrent live runs blow the cap" attack. Synth adds it in `run_eval`; CI cassette runs (cost = 0) skip the lock so they don't serialize unnecessarily.
3. **Tier state on `registration.py#current_tier`, not `docs/trust-tiers.yaml` (`[B]`).** `[S]` has this; `[B]` and `[P]` don't. Synth picks `[S]`'s shape because the YAML-central-edit pattern would force Phase 7 to edit a file outside `bench/migration-chainguard-distroless/`, violating the no-edits-to-existing-code invariant.
4. **No central `cases/digests.yaml` (departure from `[S]`).** `[S]`'s "one mismatch → abort" containment is the wrong shape (critic correctly flagged). Per-case `cassette_blake3` in `case.toml`, advisory in 6.5; strict in 7+. Closes `[S]`'s blast-radius problem.
5. **No Sigstore anchors / operator-fingerprint signing in 6.5 (departure from `[S]`).** Critic correctly identified the cost/threat asymmetry. Deferred to Phase 16 ADR slot. Local chain in 6.5 still catches every mid-stream tamper; published anchors solve a different (host-compromise) problem.
6. **`asyncio.wait_for` timeout, not `signal.SIGALRM` (`[B]`).** Critic correctly identified SIGALRM-vs-asyncio incompatibility. Phase 6's SUT is async; the harness must be too.

## Exit-criteria checklist

Per [roadmap.md §Phase 6.5](../../roadmap.md#phase-65--per-task-class-eval-harness--first-benches-preamble-to-phase-7) exit criteria:

| # | Criterion | Satisfied by |
|---|---|---|
| 1 | `src/codegenie/eval/` package exists; `@register_task_class`, `BenchScore`, harness runner, trust-tier promotion gate are unit-tested. | All Components above; `tests/unit/test_eval_*` |
| 2 | `bench/vuln-remediation/cases/` ≥ 10 curated cases with provenance metadata; `rubric.py` scores the full set; aggregate `bench_score.mean` recorded as bronze→silver candidate (numeric value deferred to ADR-0015). | `bench/vuln-remediation/` directory contract + integration test `test_eval_end_to_end_vuln.py` |
| 3 | `bench/migration-chainguard-distroless/cases/` ≥ 3 seed cases + working `rubric.py`; Phase 7 inherits and expands. | `bench/migration-chainguard-distroless/` skeleton |
| 4 | Fence-CI: PR adding `@register_task_class("foo")` without `bench/foo/{cases,rubric.py,registration.py}` fails with specific diagnostic. | `tests/unit/test_eval_fence.py` two-stage AST + dir-walk |
| 5 | Trust-tier promotion gate wired but does not auto-promote. | `PromotionGate.evaluate` (read-only) + `apply()` raises unconditionally |
| 6 | `codegenie eval run --task-class=vuln-remediation` exits 0 on backfilled bench, emits aggregate + per-case `BenchScore` to stdout (JSON) + `.codegenie/eval/runs/<utc-iso>-<short>.json`. | `cli.py` + `audit.py` + integration test |
| 7 | Phase 7 can reference "`bench/migration-chainguard-distroless/cases/` ≥ 10 cases with `bench_score.mean ≥ tier_threshold[bronze]`" as hard precondition. | Threshold on `TaskClass.min_cases_for_promotion` + `PromotionGate` reads it |

## Load-bearing commitments check

Per [production/design.md §2](../../production/design.md):

| Commitment | How design honors it |
|---|---|
| **No LLM in the gather pipeline** | Harness imports zero LLM SDKs; `test_eval_package_imports_no_llm_sdk.py` enforces structurally. SUT (Phase 6) calls LLMs via Phase 4 cassettes; harness never does. |
| **Facts, not judgments** | `BenchScore` is per-case facts; `BenchRunReport` carries no `aggregate_passed` boolean — that's a judgment computed by `PromotionGate.evaluate` from facts + tier thresholds. |
| **Honest confidence** | Static-introspection rejects `confidence/llm/self_reported/model_says` field names; `extra="forbid"` rejects unknown fields; `failure_modes` surfaces every mode (not just the first); `block`-severity failure modes block promotion regardless of `mean_score`. |
| **Determinism over probabilism for structural changes** | Harness is deterministic given fixed cassettes + cases + rubric; `run_id = sha256(...)` is content-addressed; two engineers get byte-identical aggregates. |
| **Extension by addition** | New task class = new `bench/{slug}/` directory + one decorator call. Zero edits to `src/codegenie/eval/`. Tier state on `registration.py` (no central YAML); no central digest manifest. Phase 7's no-edits invariant is preserved. |
| **Organizational uniqueness as data, not prompts** | Rubrics are Python (data shape: `Rubric` Protocol); per-task-class `min_cases_for_promotion` is data on the registration; tier thresholds are loaded from registration, not prompted. |
| **Progressive disclosure for context** | `BenchCase` carries paths, not inlined fixtures; runner loads case bytes lazily; audit record indexes per-case results by `case_id`. |
| **Humans always merge** (extended to "humans always promote") | `PromotionGate.apply()` raises unconditionally; tier change is a hand-edited PR against `registration.py#current_tier` reviewed by CODEOWNERS. ADR-0009 not amended. |

## Roadmap coherence check

**What prior phases established that this design depends on:**
- Phase 0: project scaffolding (`pyproject.toml` extras), CLI `click` integration, `codegenie/audit.py` shape (Phase-0 RunRecord), import-linter contract, `codegenie/hashing.py` (BLAKE3).
- Phase 4: cassette discipline (replay in CI; no live LLM); per-cassette identity stable enough to hash per case (the critic correctly flagged that Phase 4 must commit to per-case-addressable cassette identity — flagged as a Phase 6.5 → Phase 4 coordination requirement in §Open questions).
- Phase 5: ADR-0014 (`extra="forbid"` introspection pattern); ADR-0003 (`@register_signal_kind` shape mirrored); ADR-0006 (Protocol-when-structural / ABC-when-default-behavior split); ADR-0016 (this design implements it); ADR-0008 (LLM-Judge deferral — this design's `bench/judgment-arbitration/` slot is reserved for the un-deferral ADR).
- Phase 6: LangGraph SUT (`build_vuln_loop().ainvoke(...)`) is the system-under-test for vuln-remediation; per-workflow SQLite checkpointer pattern reused in `.codegenie/eval/scratch/<case_id>.sqlite3`.

**What this design establishes that later phases will need:**
- Phase 7 inherits the registry, the `RubricRunner` Protocol, the `bench/` directory contract, the audit chain, and uses `bench/migration-chainguard-distroless/` as the second worked example. Phase 7's no-edits-to-existing-code invariant is preserved.
- Phase 13 reads `BenchRunReport.total_cost_usd` from `.codegenie/eval/runs/` audit records (cost ledger ingestion). Phase 13's outcome-ledger reconciliation routes through `bench/{tc}/cases-pending/` (TB-7 contract reserved here, not implemented).
- Phase 15 (agentic recipe authoring) registers `bench/agentic-recipe-authoring/` via the same decorator; rubric scores generated recipes against held-out repos.
- Phase 16 swaps `SubprocessRubricRunner` → `MicroVMRubricRunner` via ADR; adds Sigstore/GPG audit anchors; adds `last_validated_at` staleness probe; adds chain-publication PR job.

**New ADRs implied by this design (to be written under `docs/phases/06.5-per-task-class-eval-harness/ADRs/`):**
1. `0001-eval-registry-mirrors-probe-registry.md` — the `@register_task_class` decision and why we use it instead of entry points.
2. `0002-benchscore-frozen-extra-forbid.md` — the Pydantic discipline mirroring Phase 5 ADR-0014.
3. `0003-rubric-as-protocol.md` — Protocol-not-ABC; `RubricRunner` strategy seam.
4. `0004-promotion-gate-read-only-verdict.md` — `apply()` raises; tier on `registration.py`.
5. `0005-subprocess-rubric-runner-as-isolation-boundary.md` — **NEW (synth)** — the load-bearing rubric-isolation decision; documents the subprocess-now / microVM-later split and the audit-chain comparability argument.
6. `0006-eval-audit-chain-without-anchors.md` — **NEW (synth)** — chained `EvalRunRecord` ships without Sigstore/GPG anchors; future phase ADR adds them.
7. `0007-no-cache-no-parallelism-in-6.5.md` — **NEW (synth)** — defers `[P]`'s cache + parallelism to Phase 7+ via documented seams.

## Open questions deferred to implementation

1. **Phase 4 cassette per-case identity contract.** All three designs assume Phase 4 commits to a per-case-addressable cassette identity the harness can hash without importing Phase 4 internals. Phase 4's `final-design.md` does not commit to this. **Action:** Phase 6.5 implementation must coordinate with Phase 4's owner to add a public `cassette_path_for(task_class, case_id) -> Path` helper; failing that, the harness reads `case.toml#cassette_path` and trusts the curator. Documented in `bench/README.md`.
2. **Bench-case extraction tooling.** None of the three designs specify how to extract ≥10 vuln-remediation bench cases from the Phases 3–4 solved-example corpus. The implementation plan must allocate engineering for this (estimated 1–2 weeks).
3. **Live-LLM cadence.** When does the live (non-cassette) eval run? Once per cassette re-record? Once per recipe-set release? Per ADR-0016 §Open Q3, this is deferred to Phase 13 cost ledger; `--max-cost-usd=$5.00` default is conservative until Phase 13 lands.
4. **`bench/` repo split.** ADR-0016 §Open Q4 defers same-repo-vs-split. Phase 6.5 keeps same-repo; Phase 7's exit review reconsiders if migration cases include customer Dockerfiles.
5. **Rubric mutation testing.** ADR-0016 §Open Q5; Phase 16 territory. Phase 6.5 ships per-rubric unit tests under `bench/{tc}/tests/` as the immediate mitigation.
6. **`MicroVMRubricRunner` substrate choice.** When the future ADR un-defers microVM rubric isolation, it must pick between Firecracker, gVisor, Lima, Docker-in-Docker, or wasmtime. Coordinate with Phase 5's sandbox-stack ADR-0019 — the same substrate decision should apply.
7. **Audit anchor PR shape.** Chain-head publication into git history (without Sigstore) is a one-line follow-on PR — defer to whichever phase first finds host-compromise-detection load-bearing (likely Phase 16). The chain-only approach in 6.5 is sufficient for the threats in scope.
