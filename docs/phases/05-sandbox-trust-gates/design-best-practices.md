# Phase 05 — Sandbox + Trust-Aware gates: Best-practices design

**Lens:** Best practices — idiomatic, maintainable, conventional, well-tested.
**Designed by:** Best-practices design subagent
**Date:** 2026-05-12

---

## Lens summary

Phase 5 is the first time the system makes an isolation claim. Before it, the gather pipeline and the recipe/LLM engines all ran in-process; Phase 1 had a hand-rolled `run_in_sandbox` chokepoint that Phase 3 reused for `npm ci` / `npm test` with `--network=none` and an overlay flag. That chokepoint is the seam. Phase 5 must (a) replace its body with a real microVM client (ADR-0012) without changing its call sites in Phases 1–4, (b) lift the validator-output stream into a typed *gate* layer that wraps a *node transition* (the same wrapper Phase 6's LangGraph `conditional_edge` will reach for), and (c) ship a three-retry loop (ADR-0014) that holds a single retry policy in one Pydantic model.

I optimize for: **one new package (`sandbox/`) + one new package (`gates/`), a single `SandboxClient` Protocol behind which DiD and Firecracker backends sit, retries as state-machine data not control flow, and a test pyramid that lets us iterate on gate weights without spinning a microVM.** The Docker-in-Docker backend ships in v0.5.0; Firecracker ships as a registered-but-skipped second backend with a one-shot smoke test (mirroring Phase 3's two-engine convention). ADR-0019 stays deferred; the seam makes the choice reversible.

I deprioritize: speed-to-first-build (no warm-pool VMs, no parallel-gate execution — both arrive in Phase 9 when Temporal lets us reason about concurrency without re-inventing it); the LLM Judge persona from `design.md §3.1` for ambiguous-signal adjudication (deferred to Phase 6/8 — Phase 5 ships binary objective signals only per ADR-0008); SAST/DAST inside the sandbox (Phase 5 runs `build` + `test` + `runtime trace` gates; SAST/DAST is a different deliverable Phase 12 owns); microVM image registry beyond a single ADR-pinned base. Aggressively boring; Phase 6 will need every one of those decisions later, and the seams are what matter.

---

## Conventions honored

- **No LLM in the gather pipeline → extended to gates.** `sandbox/` and `gates/` are added to the Phase 0 `fence` CI policy's deny-list for `anthropic`, `langgraph`, `chromadb`, `sentence-transformers`. The gate machinery never asks an LLM what it thinks; it asks the sandbox what happened.
- **Facts, not judgments (ADR-0008).** Every `GateSignal` is an objective measurement from the sandbox: build exit code, test exit code, runtime trace diff, policy hits. There is no `confidence_pct` field. The gate's verdict is a strict-AND over the signal set; ADR-0015 calibration is deferred but the *signal collection* lands here so Phase 13 has data to calibrate on.
- **Honest confidence.** Every signal carries `provenance` (which subprocess, which exit code, which log path on disk) and `at` (UTC, set inside the sandbox). The gate never reports "passed" without naming the sandbox run-id and the artifact paths.
- **Extension by addition (ADR-0007).** Phase 5 adds two new packages. The existing `run_in_sandbox(...)` symbol from Phase 1 gets a new implementation (additive substitution behind a Protocol) but its three callers in `validation/install.py`, `validation/test.py`, `validation/build.py` are unchanged. The `Transform` ABC, `RecipeEngine` ABC, `Validator` function signatures, `RepoContext` schema, `Probe` ABC are all unchanged. The single additive edit is the orchestrator: Phase 3's Stage 6 (Validate) is now invoked *through* `GateRunner.run(transition, …)` rather than calling validator functions directly. ADR-P5-001 captures the edit.
- **Determinism over probabilism for structural changes.** The retry loop is deterministic. It does not "ask the LLM to try again"; it re-invokes the prior node (Phase 4's `RagLlmEngine` or Phase 3's `NcuRecipeEngine`) with the failed gate's `GateSignals` appended to context. Phase 4's `FallbackTier` already accepts a `prior_attempts: list[AttemptOutcome]` kwarg shape; Phase 5 fills it.
- **Organizational uniqueness as data, not prompts.** Gate definitions are YAML under `src/codegenie/gates/catalog/`. Each entry names its sandbox profile, the signals it expects, the strict-AND predicate, and the retry policy. Bumping a gate is a YAML PR + a snapshot test.
- **Progressive disclosure (`production/design.md §2.7`).** Sandbox runs write a `manifest.yaml` + per-step logs under `.codegenie/sandbox/runs/<sandbox-run-id>/`. The `remediation-report.yaml` (Phase 3) indexes these via `sandbox_run_id`; it does not inline logs. Three nested directories deep is the ceiling.
- **Humans always merge (ADR-0009).** The three-retry loop terminates with one of: `passed`, `failed_unrecoverable`, or `awaiting_human` (the `interrupt()` analog). Phase 5 is still single-process so there is no Temporal signal; we exit with a documented code (`exit 11 = gate_escalate_human`) and an audit event. Phase 6 swaps in `interrupt()`; the Phase 5 escalation envelope is the contract Phase 6 lifts unchanged.
- **Probe contract preserved (ADR-0007).** A new `SandboxHealthProbe` (analog of Phase 1's `IndexHealthProbe`) reports whether the configured backend is callable from the operator's machine. Same ABC, same registration decorator, same provenance shape.
- **Cost observability (ADR-0024).** Every sandbox invocation emits a `cost.sandbox.run` ledger entry (microVM-seconds, image-pull bytes, build-cache hit/miss) keyed by `(workflow_id, stage, gate_id)` per `design.md §3.3`. Same JSONL stream Phase 4 writes its `cost.llm.invoked` entries to.

---

## Goals (concrete, measurable)

| # | Goal | Target |
|---|---|---|
| 1 | **Public surface introduced** | 2 ABCs: `SandboxClient` (Protocol), `Gate` (ABC). 1 new dataclass family: `SandboxSpec`, `SandboxRun`, `GateSignal`, `GateOutcome`, `Attempt`, `RetryLedger`. Phase 3/4 ABCs unchanged. |
| 2 | **New top-level packages** | 2 — `src/codegenie/sandbox/`, `src/codegenie/gates/`. Both sibling to `transforms/`, `recipes/`, `rag/`, `llm/`. |
| 3 | **Net new Python files in `src/`** | ~24 modules, ~2800 LOC target, 4000 hard ceiling. |
| 4 | **Test code ratio** | ≥ 1.6× source LOC (~4500–6500 LOC). The microVM half ships heavy. |
| 5 | **Test coverage target** | 90% line / 80% branch across new packages; 95%/90% on `gates/runner.py` and `sandbox/contract.py`. |
| 6 | **Cyclomatic complexity ceiling** | McCabe ≤ 10 per function, ruff `C901` enforced. `GateRunner.run` is the function most at risk; split into `_evaluate`, `_decide_next`, `_record_attempt`. |
| 7 | **Plain Python vs framework-coupled ratio** | ≥ 92% plain Python under `sandbox/` and `gates/`. `docker` Python SDK import line count: ≤ 2 (DiD client only). No `langgraph`, no `temporalio`. |
| 8 | **New dependencies** | 3 prod (`docker` SDK pinned minor, `pytest-docker` dev, `python-on-whales` *optional* for buildx — ADR-P5-005 picks one). 0 deps for Firecracker stub (it's an out-of-process binary check). |
| 9 | **Build gate latency (cold)** | p50 ≤ 90s, p95 ≤ 180s for a Node fixture. (DiD; Firecracker target deferred to ADR-0019 evidence.) |
| 10 | **Build gate latency (warm — image cached, deps cached)** | p50 ≤ 25s, p95 ≤ 60s. |
| 11 | **Test gate latency** | p50 ≤ 60s, p95 ≤ 120s (dominated by the repo's own suite). |
| 12 | **Runtime-trace gate latency** | p50 ≤ 15s, p95 ≤ 45s — captures syscalls + network endpoints during a 10-second smoke run. |
| 13 | **Retry default** | `max_attempts=3` (ADR-0014 verbatim). Per-gate override via YAML; CLI flag `--max-attempts-override <int>` requires `--operator-ack`. |
| 14 | **Exit-criterion coverage** | E2E test demonstrates retry-1 fail + retry-2 recover **with the exact attempt log on disk**: `attempts.jsonl` has 2 entries with distinct `attempt_id`s, distinct `prior_failure_summary`s, and `outcome ∈ ["failed","passed"]`. |
| 15 | **Tokens per run** | 0. Phase 5 ships no LLM call. Fence CI extended. |
| 16 | **VCR cassette discipline** | N/A for Phase 5 — no HTTP. `pytest-docker` provides ephemeral docker daemons; CI uses dind-rootless. |

---

## Architecture

ASCII. Phase 5 slots in as a thin **wrapper around Phase 3's Stage 6** and reuses the validator functions verbatim — they become *gate signal collectors*, not standalone callers.

```
                  codegenie remediate <repo> --cve <id>     (unchanged)
                                       │
                                       ▼
                  ┌──────────────────────────────────────────┐
                  │ Phase 3 RemediationOrchestrator           │
                  │   Stages 1–5 unchanged                    │
                  │   Stage 6: Validate → wrapped by Phase 5  │   [P5 EDIT, ADR-P5-001]
                  └──────────────────┬───────────────────────┘
                                     │ TransformOutput from Stage 5
                                     ▼
        ┌──────────────────────────────────────────────────────────────┐
        │  src/codegenie/gates/runner.py — GateRunner                  │
        │                                                              │
        │  def run(transition: TransitionId,                           │
        │          ctx: GateContext) -> GateOutcome:                   │
        │     for attempt in 1..max_attempts:                          │
        │         spec = SandboxSpecBuilder.for_gate(gate_yaml,        │
        │                  attempt, ctx)                               │
        │         run = SandboxClient.execute(spec)                    │
        │         signals = SignalCollector.collect(run)               │
        │         outcome = Gate.evaluate(signals)                     │
        │         RetryLedger.record(attempt, signals, outcome)        │
        │         if outcome.passed: return outcome                    │
        │         if not outcome.retryable: break                      │
        │         ctx = ctx.with_prior_attempt(outcome)                │
        │     return GateOutcome.escalate(ledger)                      │
        └──────────────────┬───────────────────────────────────────────┘
                           │
                           ▼
        ┌──────────────────────────────────────────────────────────────┐
        │  src/codegenie/sandbox/ — SandboxClient Protocol              │
        │                                                              │
        │   class SandboxClient(Protocol):                             │
        │       def execute(self, spec: SandboxSpec) -> SandboxRun: ...│
        │       def health(self) -> SandboxHealth: ...                 │
        │                                                              │
        │   Registered backends (built-in):                            │
        │     - DockerInDockerClient    [P5 default; v0.5.0 default]   │
        │     - FirecrackerClient       [P5 stub; ADR-0019 deferral]   │
        │                                                              │
        │   Backend chosen by ~/.config/codegenie/sandbox.yaml          │
        │   (backend: did | firecracker); operator override via         │
        │   --sandbox-backend.                                          │
        └──────────────────┬───────────────────────────────────────────┘
                           │ SandboxRun returned (run_id, exit_code,
                           │    logs_dir, trace_dir, copy_out_root,
                           │    duration_ms, microvm_seconds)
                           ▼
        ┌──────────────────────────────────────────────────────────────┐
        │  Signal collectors (plain functions, no class hierarchy):    │
        │    sandbox/signals/build.py    → BuildSignal                 │
        │    sandbox/signals/tests.py    → TestSignal                  │
        │    sandbox/signals/trace.py    → TraceSignal                 │
        │    sandbox/signals/policy.py   → PolicySignal                │
        │  Each reads SandboxRun on disk and returns a typed Pydantic  │
        │  GateSignal; no signal collector talks to anything else.     │
        └──────────────────┬───────────────────────────────────────────┘
                           │
                           ▼
        ┌──────────────────────────────────────────────────────────────┐
        │  Gate catalog (YAML data):                                   │
        │    src/codegenie/gates/catalog/                              │
        │      stage6_validate.yaml      → Build∧Test∧Trace∧Policy     │
        │      stage6_validate_loose.yaml→ opt-in; build∧test only     │
        │  Gate.evaluate is a pure function over GateSignals.          │
        └──────────────────────────────────────────────────────────────┘

        Cross-cutting:
        ┌──────────────────────────────────────────────────────────────┐
        │  RetryLedger (Pydantic; written to                            │
        │    .codegenie/remediation/<run-id>/gates/<gate-id>/           │
        │      attempts.jsonl — append-only BLAKE3-chained)             │
        │  Carries: attempt_id, started_at, sandbox_run_id, signals[],  │
        │   outcome, prior_failure_summary (the next attempt's context) │
        └──────────────────────────────────────────────────────────────┘

  Package layout (additions on top of Phase 4):
  src/codegenie/
    sandbox/                  ← NEW
      __init__.py
      contract.py             ← SandboxClient Protocol + SandboxSpec/SandboxRun
      registry.py             ← @register_sandbox_backend decorator
      did/
        client.py             ← DockerInDockerClient (default)
        compose.py            ← docker-compose templating
        build.py              ← `docker build` invocation (one chokepoint)
        run.py                ← `docker run --rm` invocation (one chokepoint)
        copy_out.py           ← `docker cp` orchestration
        network_policy.py     ← egress allowlist enforcement
      firecracker/
        client.py             ← FirecrackerClient (stub, ADR-0019)
        README.md             ← why this is a stub in v0.5.0
      signals/
        __init__.py
        build.py              ← parse docker build log → BuildSignal
        tests.py              ← parse test output → TestSignal
        trace.py              ← parse strace/seccomp log → TraceSignal
        policy.py             ← read policy.yaml hits → PolicySignal
      health/
        probe.py              ← SandboxHealthProbe (Probe ABC)
      models.py               ← SandboxSpec, SandboxRun, GateSignal, *_signal_kind
    gates/                    ← NEW
      __init__.py
      contract.py             ← Gate ABC, GateContext, GateOutcome, TransitionId
      runner.py               ← GateRunner: the three-retry loop
      retry_ledger.py         ← RetryLedger (Pydantic; BLAKE3-chained)
      catalog_loader.py       ← YAML loader (schema-validated)
      catalog/
        stage6_validate.yaml
        stage6_validate_loose.yaml
        _schema.json
    cli/
      sandbox.py              ← `codegenie sandbox {health,inspect,gc}`

  Phase 0 fence policy CI updates (importer allowlists):
    `transforms/`  may NOT import  `sandbox/`, `gates/`
       (transforms still call the validation helpers; the orchestrator
        wraps them in a gate, not the transform itself)
    `recipes/`     may NOT import  `sandbox/`, `gates/`
    `probes/`      may import      `sandbox/health/` only
    `rag/`,`llm/`  may NOT import  `sandbox/`, `gates/`
    `sandbox/`     may NOT import  `recipes/`, `transforms/`, `rag/`, `llm/`,
                                   `langgraph`, `anthropic`, `chromadb`
    `gates/`       may import      `sandbox/`, `transforms/validation/` (signal helpers)
```

---

## Components

### 1. `SandboxClient` — the Protocol

- **Purpose:** One contract every microVM backend satisfies. `execute(spec) -> run`; `health() -> health`. Two methods. No more.
- **Public interface:**
  ```python
  from typing import Protocol
  from .models import SandboxSpec, SandboxRun, SandboxHealth

  class SandboxClient(Protocol):
      def execute(self, spec: SandboxSpec) -> SandboxRun: ...
      def health(self) -> SandboxHealth: ...
  ```
- **Internal design:** **`Protocol`, not `ABC`.** Backends are duck-typed via `runtime_checkable`. Idiomatic Python 3.11+. Lets us treat the `FirecrackerClient` stub as "registered but not callable" without inheriting an `NotImplementedError`-littered base class — the registry's `health()` check is what decides callability. No multiple-inheritance trap (cf. `abc.ABC + Pydantic.BaseModel` combinatorics).
- **Why Protocol over ABC:** Composition over inheritance (best-practices rule 4). The backend already owns its lifecycle; we only need a structural type. The fence CI prevents accidental cross-cutting; Protocol is the shape that matches.
- **Dependencies:** `pydantic` only (for `SandboxSpec`/`SandboxRun` models). The `docker` SDK lives entirely in `did/client.py`.
- **Where it lives:** `src/codegenie/sandbox/contract.py`.
- **Tradeoffs accepted:** Protocol doesn't enforce signature at registration time. We get *one* runtime check inside `register_sandbox_backend`: `isinstance(instance, SandboxClient)` (the `runtime_checkable` form). Mistakes show up at startup with a typed error, not buried in a "AttributeError: 'NoneType' has no attribute 'execute'".

### 2. `SandboxSpec` + `SandboxRun` + `GateSignal` — the data model

- **Purpose:** Carry every byte of information a gate needs between the sandbox boundary and the gate evaluator. Pydantic, frozen, no business logic.
- **Public interface (sketch):**
  ```python
  class SandboxSpec(BaseModel):
      model_config = ConfigDict(extra="forbid", frozen=True)
      base_image: str                       # cgr.dev/chainguard/node:lts (default; ADR-pinned digest)
      copy_in: list[CopyInEntry]            # host_path -> sandbox_path, ro|rw
      env: dict[str, str]                   # validated allowlist (PATH, NPM_CONFIG_*, NODE_ENV...)
      cmd: list[str]                        # argv
      network: Literal["none","scoped"]     # scoped uses allowlist; none = no network
      egress_allowlist: list[str]           # only meaningful if network=scoped
      enable_trace: bool                    # strace/syscall capture for trace gates
      time_budget_seconds: int              # hard SIGKILL ceiling
      memory_limit_mib: int
      pids_limit: int
      copy_out: list[str]                   # paths inside sandbox to bring back
      label: str                            # human-readable; for log filenames
      sandbox_spec_hash: str                # blake3 over the prior fields (deterministic)

  class SandboxRun(BaseModel):
      model_config = ConfigDict(extra="forbid", frozen=True)
      run_id: str                           # uuid7
      spec: SandboxSpec
      backend: Literal["docker_in_docker","firecracker"]
      started_at: datetime
      ended_at: datetime
      exit_code: int
      duration_ms: int
      microvm_seconds: float                # for cost ledger
      image_pull_bytes: int
      build_cache_hit: bool
      logs_dir: Path                        # absolute, ephemeral inside .codegenie/sandbox/
      trace_path: Path | None
      copy_out_root: Path
      timed_out: bool
      killed_by_oom: bool

  class GateSignal(BaseModel):
      model_config = ConfigDict(extra="forbid", frozen=True)
      kind: Literal["build","tests","trace","policy"]
      passed: bool                          # binary; ADR-0008
      details: dict[str, str | int | bool]  # short, structured, ≤ 8 keys
      provenance: SignalProvenance          # which subprocess/log/exit-code
      at: datetime
  ```
- **Internal design:** All Pydantic with `extra="forbid"`. Frozen. `details` is intentionally `dict[str, primitive]`, not `Any` — keeps the audit chain reproducible across versions. The hash field on `SandboxSpec` is the cache key (Phase 5 doesn't ship sandbox-output caching, but Phase 9's Temporal will, and the field lands here so the contract is forward-compatible).
- **Why this choice:** Plain data, no methods. Composition over inheritance (no `BaseGateSignal` hierarchy). The validator helpers in Phase 3 (`validation/install.py` etc.) already return `ValidatorOutput`; signal collectors translate `SandboxRun` + `ValidatorOutput` into `GateSignal`. That's the boundary.
- **Where it lives:** `src/codegenie/sandbox/models.py`.
- **Tradeoffs accepted:** A small data-shuffling layer (signal collectors) but each one is ≤ 60 LOC and reads top-to-bottom. The alternative (a `SignalCollector` ABC with one impl per signal) is over-engineering for four functions.

### 3. `DockerInDockerClient` — the Phase 5 default backend

- **Purpose:** Execute `SandboxSpec` against a Docker daemon (rootless dind in CI; host docker on developer macOS). Implements the Protocol.
- **Public interface:** `execute(spec) -> SandboxRun`; `health() -> SandboxHealth`.
- **Internal design:**
  - Uses the official `docker` Python SDK (`docker.from_env()`); no shelling out to `docker` CLI from this file. Subprocess is allowed only inside `did/build.py` for `docker buildx build --progress=plain --output=type=docker` because the Python SDK's build progress streaming is awkward; this is documented loudly and the `build.py` module has a single function.
  - **Network policy** (`did/network_policy.py`): `network=none` → `--network=none`; `network=scoped` → an isolated bridge network with iptables rules per the allowlist (default allow: `registry.npmjs.org`, `cgr.dev`, `index.docker.io`, the org's internal registry). The policy module is the one file allowed to invoke `iptables`; nobody else touches network primitives.
  - **Copy in/out** (`did/copy_out.py`): bind-mounts for copy-in (read-only by default; rw only when the YAML gate explicitly asks); `docker cp` for copy-out. **Both are typed Path operations** — no `os.path.join` over user strings.
  - **Trace capture** (when `enable_trace=true`): the sandbox launches `strace -f -e trace=execve,network,connect -o /trace/trace.log <cmd>`. Phase 5 does not ship eBPF; strace is the boring choice that works on macOS DiD and Linux CI.
  - **Resource limits** translated 1:1 to docker `--memory`, `--pids-limit`, `--ulimit`, `--stop-timeout`.
  - **Health check** (`health()`): `docker version`, `docker info`, `docker buildx ls`, plus a one-off `hello-world` run with `--network=none`. Returns `SandboxHealth(backend="did", reachable=True, version="…", warnings=[…])`. The `SandboxHealthProbe` in `probes/` calls this.
- **Why DiD over rootless podman / nerdctl:** widest-supported in CI (GHA, GitLab, CircleCI all ship DiD images); developer machines already have Docker Desktop; `pytest-docker` is the boring well-supported fixture library. Podman has a real but smaller ecosystem; Phase 16 production hardening will revisit.
- **Dependencies:** `docker` SDK (one import line). `python-on-whales` is **deliberately not adopted** — one more layer of indirection over the same CLI; the SDK is enough.
- **Where it lives:** `src/codegenie/sandbox/did/client.py`.
- **Tradeoffs accepted:** Cold-start is seconds, not milliseconds (no warm pool — Phase 9's territory). DiD requires privileged mode in CI for the inner daemon; the CI configuration ships this in a single composite action.

### 4. `FirecrackerClient` — the stub second backend

- **Purpose:** Honor the "two-backend" convention Phase 3 cut (`Ncu` + `OpenRewriteStub`) and prove the Protocol extends.
- **Public interface:** Same Protocol; `execute()` raises `BackendNotAvailable("firecracker backend is a v0.5.0 stub; see ADR-P5-002")` unless `--firecracker-experimental` is set on the CLI **and** the host has KVM + the pinned firecracker binary digest. `health()` returns `reachable=False` with a documented reason on every machine that lacks KVM/digest.
- **Internal design:** Single file, ~150 LOC. Wraps `firecracker-go-sdk` *not at all* — it shells out to a pinned firecracker binary via subprocess. The one-shot smoke test (CI, KVM-capable runner only, marked `@pytest.mark.skip_if_no_kvm`) confirms the binary boots a VM, runs `echo hello`, exits 0, returns a `SandboxRun` shaped identically to the DiD one. **That is the entire Phase 5 Firecracker deliverable.** ADR-0019 stays deferred; Phase 5 just proves the seam.
- **Why this choice:** The roadmap line "Firecracker explored for Linux/CI" + the convention from Phase 3 (`OpenRewriteEngineStub` was the same shape) means we ship a *registered* second backend and a *single proof* that it satisfies the contract. Phase 16 promotes one to production based on evidence per ADR-0019.
- **Where it lives:** `src/codegenie/sandbox/firecracker/client.py`.
- **Tradeoffs accepted:** No Linux-host parallel benchmark in Phase 5. The cost is one open question for the synthesizer.

### 5. `Gate` — the ABC, and the YAML catalog

- **Purpose:** Encode "given these `GateSignals`, do we advance?" as a pure function plus data.
- **Public interface:**
  ```python
  class Gate(ABC):
      gate_id: str                          # "stage6_validate"
      required_signals: tuple[SignalKind,…] # ("build","tests","trace","policy")
      retry_policy: RetryPolicy

      @abstractmethod
      def evaluate(self, signals: list[GateSignal]) -> GateOutcome: ...

  # Default impl that 95% of gates use:
  class StrictAndGate(Gate):
      """Strict-AND across required_signals; ADR-0008. No optional signals."""
  ```
- **Internal design:** `StrictAndGate` is the one concrete class shipped in v0.5.0; it covers `stage6_validate` and `stage6_validate_loose`. Subclassing `Gate` is reserved for future "M-of-N" gates that Phase 6/12 may want. Gate **data** is YAML under `gates/catalog/`; **logic** is `StrictAndGate`. A gate definition refers to a `SandboxSpec` template by name (templates live alongside the YAML), the signals required, and the retry policy.
- **Why this choice over alternatives:** Phase 3's pattern is exactly this — `RecipeEngine` ABC + YAML recipes. Phase 5 reuses the convention. Operator-visible knobs live in YAML; new gate *shapes* require a new `Gate` subclass + an ADR.
- **Where it lives:** `src/codegenie/gates/contract.py` + `src/codegenie/gates/catalog/*.yaml` + `gates/catalog_loader.py`.
- **Tradeoffs accepted:** Two evaluators (StrictAndGate + future M-of-N) double on lines but read trivially. Worth it over a single "configurable evaluator" that takes a predicate AST in YAML — that's the path to a homegrown DSL.

### 6. `GateRunner` — the three-retry loop

- **Purpose:** Implement ADR-0014 once, in one file, with the loop as data not control flow.
- **Public interface:**
  ```python
  class GateRunner:
      def __init__(self, *,
                   client: SandboxClient,
                   gate: Gate,
                   ledger: RetryLedger,
                   max_attempts: int = 3) -> None: ...

      def run(self, ctx: GateContext) -> GateOutcome: ...
  ```
- **Internal design:** A single `for attempt in range(1, max_attempts + 1)` loop. Each iteration: build the `SandboxSpec` (which depends on `attempt` because the prior failure's `details` may rewrite `cmd` — e.g., retry-2 may run `npm test -- --verbose` to capture more signal), invoke `client.execute(spec)`, run signal collectors, evaluate the gate, record to ledger, decide. The decision tree is exactly three branches: `passed → return passed`, `failed && retryable && attempt < max → continue with prior_attempt context`, `else → return escalate(ledger)`.
- **Why this choice over alternatives:** The naive "decorator-based retry" (`@retry(times=3)`) hides the state machine. ADR-0014 is explicit that the *prior attempt's error log is appended to context for the next attempt* — that is a state-machine property, not a "try again" property. A plain `for` loop with the ledger as the shared state makes this readable in one screen. Phase 6's LangGraph `conditional_edge` will wrap `GateRunner.run` unchanged; the `for` becomes `recur_to_node`, but the data shape is identical.
- **Where it lives:** `src/codegenie/gates/runner.py`.
- **Tradeoffs accepted:** No concurrent gate evaluation in Phase 5. (Phase 9 introduces concurrency under Temporal; injecting `asyncio.gather` here would be premature.)

### 7. `RetryLedger` — the audit-grade attempt log

- **Purpose:** Append-only record of every attempt + every signal. The artifact that proves the exit criterion ("retry-1 failed, retry-2 recovered").
- **Public interface:**
  ```python
  class RetryLedger:
      def __init__(self, *, run_dir: Path, gate_id: str,
                   prev_chain_head: bytes | None) -> None: ...

      def record(self, attempt: Attempt) -> None: ...   # append to attempts.jsonl
      def head(self) -> bytes: ...                       # BLAKE3 chain head
      def attempts(self) -> list[Attempt]: ...           # read-side
  ```
- **Internal design:** Each `record` writes one line of `attempts.jsonl` under `.codegenie/remediation/<run-id>/gates/<gate_id>/attempts.jsonl`. Each line carries `prev_hash` (BLAKE3 of the prior line) → extends Phase 2's audit chain into the gate machinery. Refuses out-of-order writes via an in-process lock + a startup-time check that `prev_hash == prior_chain_head` (rejects edits-after-the-fact).
- **Why this choice over alternatives:** A SQLite table would be operationally fine but introduces a dependency Phase 5 doesn't need; the audit-chain pattern is already in Phase 2. Append-only JSONL is `tail -f`-able for debugging.
- **Where it lives:** `src/codegenie/gates/retry_ledger.py`.
- **Tradeoffs accepted:** JSONL parsing per read is O(n) in attempts; with `max_attempts=3` this is irrelevant. Phase 13's roll-up reads the same lines and writes to the ledger of ledgers.

### 8. `SandboxHealthProbe` — Phase 5's B2-analog

- **Purpose:** Detect silent unavailability of the sandbox backend (the "IndexHealth equivalent" for Phase 5 — `design.md §2.3` honest-confidence commitment).
- **Public interface:** Standard `Probe`. `name="sandbox_health"`. `declared_inputs = ["~/.config/codegenie/sandbox.yaml"]`. `applies_to_tasks=["*"]`. Emits a `SandboxHealth` Pydantic blob into `RepoContext.health.sandbox`.
- **Internal design:** Reads `~/.config/codegenie/sandbox.yaml`, instantiates the configured backend, calls `client.health()`, persists the result. Failure modes detected: docker daemon down, daemon up but rootless misconfigured, buildx missing, base image registry unreachable, KVM not present (for Firecracker), pinned base-image digest no longer pullable.
- **Why this choice over alternatives:** ADR-0007 demands new capabilities surface through the probe contract when they're "honest confidence" inputs. The alternative ("crash at gate time") would mean every operator's first sandbox gate failure is a Stack Overflow trip.
- **Where it lives:** `src/codegenie/sandbox/health/probe.py`.
- **Tradeoffs accepted:** One more probe to keep golden-fixtured. Phase 1's probe-test convention covers it.

### 9. Signal collectors — four functions

- **Purpose:** Translate a `SandboxRun` into a typed `GateSignal`.
- **Public interface:**
  ```python
  def collect_build_signal(run: SandboxRun) -> GateSignal: ...
  def collect_test_signal(run: SandboxRun) -> GateSignal: ...
  def collect_trace_signal(run: SandboxRun,
                            baseline: TraceBaseline | None) -> GateSignal: ...
  def collect_policy_signal(run: SandboxRun,
                             policy_yaml: Path) -> GateSignal: ...
  ```
- **Internal design:** Plain functions. Each reads `run.logs_dir`, parses a known log format (jest XML, mocha JSON, npm stderr, strace log), and returns the signal. No shared state. Each is ≤ 60 LOC. **The trace collector** is the only one with subtlety: it diffs the captured syscall+network set against `TraceBaseline` (which Phase 2's Layer-B trace probe already produces and persists at `.codegenie/context/traces/<entrypoint>.json`). Diff is by *kind of signal*, not free strings — "new shell invocation observed" vs the baseline's executed-binaries set; "new network endpoint" vs the baseline's egress allowlist. Trace collector returns `passed=False` if the diff is non-empty; details name the new entries.
- **Why this choice over alternatives:** Functions, not a `SignalCollector` ABC. The four collectors share no state; they each parse one log format. An ABC + four subclasses adds 40 LOC of inheritance noise for no benefit (composition over inheritance, rule 4).
- **Where it lives:** `src/codegenie/sandbox/signals/{build,tests,trace,policy}.py`.
- **Tradeoffs accepted:** Adding a fifth signal (e.g., SBOM-delta in Phase 7's distroless work) means a fifth file — additive, no edits. That is the point.

### 10. CLI surface — `codegenie sandbox`

- **Purpose:** Operator surface for the sandbox layer. Three subcommands.
- **Public interface:**
  - `codegenie sandbox health` — prints the SandboxHealth blob.
  - `codegenie sandbox inspect <gate-run-id>` — pretty-prints `attempts.jsonl` with signals and durations.
  - `codegenie sandbox gc [--older-than 7d]` — removes `.codegenie/sandbox/runs/<id>/` directories beyond the retention window.
- **Internal design:** `click`. Same conventions as Phase 0/3/4 CLIs. No new flags on `codegenie remediate` except `--sandbox-backend {did,firecracker}`, `--max-attempts-override <int>` (requires `--operator-ack`), and `--gate-catalog {strict,loose}`.
- **Where it lives:** `src/codegenie/cli/sandbox.py`.
- **Tradeoffs accepted:** Three subcommands is the floor for an operator-visible layer.

---

## Data flow

End-to-end run for `codegenie remediate ./services/auth --cve CVE-2024-FAKE-NPM`, with retry:

1. **Phase 3 Stages 1–5 run unchanged.** Recipe selected, transform applied, lockfile canonicalized, patch committed to a worktree branch.
2. **Stage 6 enters `GateRunner.run(transition=stage6_validate, ctx=...)`.** Ctx carries the worktree path, the `Advisory`, the `Recipe`, the `TransformOutput`, and an empty `prior_attempts` list.
3. **Attempt 1.** `SandboxSpecBuilder.for_gate(stage6_validate.yaml, attempt=1, ctx)` produces a `SandboxSpec`:
   - `base_image: cgr.dev/chainguard/node@sha256:<pinned-digest>`
   - `copy_in: [(worktree_path, /work, ro)]`
   - `cmd: ["sh","-c","cd /work && npm ci --ignore-scripts && npm test && /opt/codegenie/smoke.sh"]`
   - `network: none` for the test step; the spec carries two phases (install runs in `network=scoped` to `registry.npmjs.org`, test+smoke run in `network=none`) — the DiD client honors the two-phase shape via a chained `docker run`.
   - `enable_trace: true`
   - `time_budget_seconds: 600`
4. **`DockerInDockerClient.execute(spec)`** runs the two phases, captures stdout/stderr/strace into `.codegenie/sandbox/runs/<sandbox-run-id>/`, returns a `SandboxRun` with `exit_code=1` (say, jest reported one test failure).
5. **Signal collectors run.** `BuildSignal.passed=True` (install + the docker image both built). `TestSignal.passed=False` with `details={"failing_tests":3, "first_failure":"auth/jwt.test.ts: should reject expired tokens"}`. `TraceSignal.passed=True` (no new shell/network). `PolicySignal.passed=True`.
6. **`StrictAndGate.evaluate(...)` returns `GateOutcome(passed=False, retryable=True, summary="test failure: 3 tests failed")`.** `retryable=True` because no signal is in the non-retryable set (e.g., `policy.hard_block`).
7. **`RetryLedger.record(Attempt(attempt_id=1, sandbox_run_id=..., signals=[...], outcome=..., prior_failure_summary="3 tests failed; first: …"))`**. Audit chain extended.
8. **Loop continues.** `ctx.with_prior_attempt(outcome)` appends the outcome; the next `SandboxSpecBuilder` call sees `prior_attempts=[Attempt(1)]` and (per `stage6_validate.yaml`) chooses a more verbose `cmd` for attempt 2 (`npm test -- --verbose --maxWorkers=1`) so the operator-facing log has more context.
9. **Attempt 2.** Hypothetical: the prior failure was a flaky timer-based test; the more-deterministic invocation passes. `SandboxRun` returns `exit_code=0`. Signal collectors all return `passed=True`. `StrictAndGate` returns `GateOutcome(passed=True, attempt=2)`.
10. **`RetryLedger.record(Attempt(2, …, outcome=passed))`** writes the second line of `attempts.jsonl`. `GateRunner.run` returns `passed`.
11. **Orchestrator continues to Phase 3's existing `TrustScorer`** which now consumes the gate's final `GateOutcome` (its signals carried verbatim). Strict-AND green; branch finalized. Stage 7 of Phase 3 unchanged.
12. **Stage-7 artifact additions:** `gates/stage6_validate/attempts.jsonl` and `gates/stage6_validate/manifest.yaml` (summary). The `remediation-report.yaml` index lists them by relative path.

**Convention call-outs that the data flow exposes:**

- Phase 5 didn't edit Phase 3's `TrustScorer` — it injected the gate's signals into the same signal set Phase 3 already aggregates. The Phase 3 strict-AND list lengthens by exactly the new objective signals (`trace.passed`, `policy.passed`), which lands as ADR-P5-003.
- The exit-criterion E2E test enables a deterministic-flake fixture (`tests/fixtures/repos/flaky-timer-node/`) that produces `passed=False` exactly on attempt 1 and `passed=True` on attempt 2 — same fixture-driven property-test approach as Phase 3's CVE-feed fixtures.
- The `prior_failure_summary` field is the seed for Phase 6's `interrupt()` payload — Phase 6 reads it unchanged.

---

## Failure modes & recovery

Prefer explicit typed exceptions over generic `Exception`. Every exception type below lives in `src/codegenie/sandbox/errors.py` or `src/codegenie/gates/errors.py`.

| Failure | Detected by | Containment | Recovery |
|---|---|---|---|
| Docker daemon unreachable at startup | `SandboxHealthProbe` | `SandboxBackendUnavailable` raised before any gate runs | Operator starts docker; or `--sandbox-backend firecracker` if KVM is available |
| Docker daemon dies mid-build | `DockerInDockerClient.execute` catches `docker.errors.APIError` | Wrapped as `SandboxRunFailed`; attempt counts toward `max_attempts` | Retry consumes one of three attempts; if all three fail with `APIError`, escalate-to-human exit 11 |
| Base-image digest no longer in registry | image pull on attempt 1 | `SandboxImageUnavailable` | Operator runs `codegenie sandbox health` for a clear pointer; ADR-amendment to bump the pinned digest |
| Sandbox timed out (`time_budget_seconds`) | dind sends SIGKILL; `SandboxRun.timed_out=True` | `GateSignal(passed=False, details={"timed_out": true})`; **non-retryable** by default | Escalate-to-human exit 11 unless YAML gate opts into `timeout_retryable=true` |
| OOM kill inside sandbox | `SandboxRun.killed_by_oom=True` | Non-retryable | Operator inspects, increases `memory_limit_mib`, re-runs |
| Build gate fails with deterministic error | `collect_build_signal` | `BuildSignal.passed=False`; retryable; next attempt rebuilds | `RagLlmEngine.apply` (Phase 4) re-invoked on retry-2 with `prior_attempts` appended |
| Test gate fails (flaky) | `collect_test_signal` | `TestSignal.passed=False`; retryable | Attempt 2 uses `--maxWorkers=1` verbose mode; if still fails, escalate |
| Test gate fails (deterministic) | both attempts identical signature | Ledger captures both signatures; ledger writer flags `flake_score=0` (matching prior failure exactly) | Escalate-to-human exit 11 |
| Trace gate fails (new shell invocation) | `collect_trace_signal` against baseline | `TraceSignal.passed=False`; **non-retryable** (ADR-P5-004) | Always escalates — by design, new shell calls require human review |
| Trace gate fails (new network endpoint) | trace collector | `TraceSignal.passed=False`; **non-retryable** | Escalates; reviewer either adds to `network_policy.yaml` (with ADR amendment) or rejects |
| Policy gate fails (lockfile policy from Phase 3) | `collect_policy_signal` | Retryable iff `policy.retry_allowed=true` in gate YAML | Phase 4's `FallbackTier` re-invokes |
| YAML gate definition invalid | `catalog_loader` schema check at startup | `GateCatalogInvalid` | CLI exit before any gate runs |
| `attempts.jsonl` chain hash mismatch | `RetryLedger.record` precheck | `AuditChainCorrupted` | Refuse the run; operator inspects (likely manual edit; the chain is intentionally brittle to detect tampering) |
| Backend registered but `health().reachable=False` | startup probe + gate runner | `SandboxBackendNotReachable` | Pointer to remediation in error message; non-retryable |
| Firecracker invoked on a non-KVM host | `FirecrackerClient.health()` | `FirecrackerKvmMissing` | Operator either gets a KVM-capable runner or switches to `did` |
| `--max-attempts-override` set without `--operator-ack` | click validator | Click exit 2 | Operator adds the ack flag |
| `microvm_seconds` cost ledger emission fails | `CostEmitter` wraps write errors | Logged WARNING; gate continues | Cost-ledger entry shows `emission_error=true`; Phase 13 will replay |

Every failure path here writes one audit event into the BLAKE3 chain (`gate.attempt_started`, `gate.attempt_completed`, `gate.escalate`, `sandbox.spec_built`, `sandbox.run_started`, `sandbox.run_completed`, `sandbox.timed_out`, `sandbox.oom_killed`). Phase 13 pivot tables key off the same event names.

---

## Resource & cost profile

Order-of-magnitude figures, single-machine M-series Mac developer or 4-vCPU Linux CI runner. DiD backend.

- **Docker image footprint:** base Chainguard Node image ~50 MB compressed, ~150 MB on disk. Pulled once per ADR-amendment to the digest pin.
- **Per-gate cold (image not cached, deps not cached):** ~120s wall; ~95s of microvm-seconds (matches the build-gate-cold target).
- **Per-gate warm:** ~25s wall; ~22s microvm-seconds.
- **Per-gate trace overhead:** strace adds ~10–15% wall time on Node test suites in our fixtures. Acceptable for Phase 5; eBPF in Phase 16 will reduce.
- **Disk per run:** `.codegenie/sandbox/runs/<id>/` is ~5–20 MB depending on test verbosity; `codegenie sandbox gc --older-than 7d` is the housekeeping path.
- **Per-workflow cost ledger entry size:** ~600 bytes per attempt × 3 attempts × 1 gate = ~2 KB per workflow. Phase 13's collector trivially.
- **Token cost:** **0.** Phase 5 ships no LLM. Phase 4's per-invocation cap stays in effect on retries (each retry that fires Phase 4 fires its own `LlmInvocationGuard.precheck`).
- **Memory footprint of the orchestrator itself:** unchanged from Phase 4 (≤ 1.7 GB). The microVM payload doesn't share memory with the host process.

---

## Test plan

The pyramid:

### Unit tests (~70% of test code; fast; no docker)

- `tests/sandbox/test_contract.py` — `SandboxSpec`/`SandboxRun` Pydantic schema invariants, `extra="forbid"` rejection, `sandbox_spec_hash` byte-stability across two constructions, frozen-model immutability.
- `tests/sandbox/test_models.py` — `GateSignal` shape; `details` dict primitive-only enforcement; round-trip JSON serialization.
- `tests/sandbox/test_did_network_policy.py` — given an allowlist YAML, asserts the iptables rules generated are byte-identical to a golden file (`tests/golden/did/network_policy_default.iptables`).
- `tests/sandbox/test_did_copy_out.py` — given a fake `SandboxRun`, asserts `docker cp` arguments are byte-identical to a golden command list; no actual docker calls (the `docker` SDK is mocked via `unittest.mock`).
- `tests/sandbox/signals/test_*.py` — one file per collector. Each feeds a fixture log (`tests/fixtures/sandbox-runs/<scenario>/`) and asserts the resulting `GateSignal` matches a golden Pydantic dump (`tests/golden/signals/*.json`).
- `tests/sandbox/health/test_probe.py` — `SandboxHealthProbe` against mocked backends (one OK, one unreachable, one missing-buildx).
- `tests/gates/test_runner.py` — the workhorse. **All retry-loop branches asserted with a fake `SandboxClient`** (in-memory; returns a scripted sequence of `SandboxRun`s). Cases: pass on 1, pass on 2, pass on 3, fail after 3, non-retryable on 1 → immediate escalate, `timed_out` non-retryable, `oom_killed` non-retryable, `--max-attempts-override` raises floor, ledger chain extends correctly.
- `tests/gates/test_retry_ledger.py` — append-only invariants; BLAKE3 chain links; reject out-of-order writes; reject chain-tamper.
- `tests/gates/test_catalog_loader.py` — every YAML in `gates/catalog/` parses and validates; invalid YAML rejected with a specific exit code.
- **Property tests** (hypothesis) on `StrictAndGate.evaluate`: for every combination of `[passed/failed] × N signals`, the gate's verdict is `all(passed)`. Same for the few non-retryable kinds.

### Integration tests (~25% of test code; medium; uses `pytest-docker`)

- `tests/integration/sandbox/test_did_end_to_end.py` — spins up rootless dind via `pytest-docker`, runs a real `SandboxSpec` against a tiny Node fixture (`tests/fixtures/repos/hello-node/`), asserts a real `SandboxRun` comes back, asserts `npm ci` actually ran inside the sandbox (the host has no `node_modules`).
- `tests/integration/gates/test_stage6_validate.py` — full Stage 6 gate against `tests/fixtures/repos/known-good-node/`. Single attempt, passes.
- `tests/integration/gates/test_stage6_retry_recovers.py` — **THE exit-criterion test.** Uses `tests/fixtures/repos/flaky-timer-node/` whose test suite fails on the first run (a `pytest_dynamic_test_order` fixture rewrites a flag inside the sandbox between attempts via a sidecar marker file written by the gate YAML's attempt-2 `cmd`). Attempt 1 fails; attempt 2 passes; `attempts.jsonl` has 2 entries; final `GateOutcome.passed=True`. This is the deliverable named in the roadmap.
- `tests/integration/gates/test_stage6_three_attempts_escalates.py` — fixture that fails identically every time; ledger captures 3 attempts; runner returns `GateOutcome.escalate(...)`; CLI exit 11.
- `tests/integration/sandbox/test_network_policy_enforcement.py` — sandbox tries to `curl https://github.com`; with `network=none` it fails; with `network=scoped` allowlist-not-matching it fails; with the allowlist matching it succeeds. Three test cases, real dind.
- `tests/integration/sandbox/test_trace_baseline_diff.py` — fixture with a deterministic shell-spawn introduced in the patch; trace collector reports the new shell invocation; gate fails as non-retryable.

### E2E tests (~5% of test code; slow; one)

- `tests/e2e/test_remediate_with_sandbox.py` — runs `codegenie remediate ./tests/fixtures/repos/cve-fixture/ --cve CVE-2024-FAKE-NPM --sandbox-backend did` against a real CVE-fixture (Phase 3 already ships this). Asserts: exit 0, a remediation branch exists, the report references `gates/stage6_validate/`, the attempts ledger contains exactly 1 attempt (the fixture is clean).

### Golden files

- `tests/golden/signals/{build,tests,trace,policy}_*.json` — one per parsing scenario.
- `tests/golden/did/network_policy_*.iptables` — generated iptables rules.
- `tests/golden/gates/catalog/*.expanded.yaml` — the gate YAML after `catalog_loader` defaults are applied. Regenerating any of these requires the `goldens-reviewed` PR label (existing Phase 1 convention).

### Property tests (hypothesis)

- `StrictAndGate.evaluate` is `all([s.passed for s in signals])` for every signal-set permutation.
- `RetryLedger.record(N times).head()` deterministically depends on `(records, prev_chain_head)`.
- `SandboxSpec.sandbox_spec_hash` is invariant under reordering of `env` dict keys (because dict key order shouldn't change the hash — assert that we sort before hashing).
- The signal collectors are pure: same fixture → same `GateSignal` (no time/PID leak into `details`).

### Test fixtures introduced

- `tests/fixtures/repos/hello-node/` — minimal Node project; tests just `node -e "process.exit(0)"`.
- `tests/fixtures/repos/flaky-timer-node/` — the fixture for the exit-criterion retry test.
- `tests/fixtures/repos/cve-fixture/` — reused from Phase 3.
- `tests/fixtures/sandbox-runs/` — pre-recorded `SandboxRun` directories used by unit tests so signal collectors can run without a daemon.
- `tests/fixtures/iptables/` — golden iptables rules.

---

## Risks (top 5)

1. **The `dind-in-CI` configuration is brittle.** GitHub Actions' default `docker` daemon is not rootless; `pytest-docker`'s rootless fixture has known quirks on Mac. Mitigation: ship a `tests/conftest.py` that detects the environment and skips rootless tests with a clear marker; document the Linux-CI path explicitly. Trade-off: slightly different code paths between dev and CI (Mac uses host docker, Linux CI uses rootless dind); we live with it for Phase 5 and reopen in Phase 16.
2. **strace overhead inflates test gate latency on slow runners.** Mitigation: `enable_trace` is gate-YAML-controlled, so a fast-test gate variant can drop trace capture and pay only when the trace signal is required. Phase 12's deeper validation will revisit.
3. **The Firecracker stub may bit-rot.** Without a KVM-capable CI runner running its smoke test on every PR, the stub silently breaks. Mitigation: a separate weekly workflow (cron) runs the stub on a self-hosted KVM runner. If it red-lines, the operator gets a single email; the synthesizer should weigh whether to ship this in Phase 5 or defer to Phase 16. (Open question 3.)
4. **Trace baseline drift.** Phase 2's trace baseline is a snapshot. A perfectly innocent dependency upgrade may legitimately introduce a new syscall pattern; `TraceSignal.passed=False` always escalates by design (ADR-P5-004). Risk: reviewer fatigue. Mitigation: ship a `codegenie trace explain <sandbox-run-id>` subcommand in v0.5.0 that diffs against baseline in a human-readable way; the synthesizer may push back on adding a fourth subcommand here.
5. **Retry-context contamination.** Attempt 2 reads `prior_attempt.details`; if Phase 4's `RagLlmEngine` keys its planner cache on the prompt (and the prior_failure_summary changes the prompt), a retry can't cache-hit the planner. Outcome: retry is slower than expected. Mitigation: Phase 4's `query_key` already includes the failure context for exactly this reason; verify in an integration test that retry-2 hits a distinct query key.

---

## Acknowledged blind spots

This lens deprioritized:

- **Performance.** No warm-pool VMs; no parallel-attempt execution; no eager image pre-pull. Cold-start cost is real (~90s on first run of a portfolio scan); we eat it.
- **Security depth.** The sandbox's deny-all egress + allowlist is conservative but isn't seccomp-bpf hardened; we trust the DiD/Firecracker primitive. No seccomp profile authoring in Phase 5. Phase 16 hardens.
- **Multi-backend parallelism.** No "run on Firecracker and DiD in parallel, compare results" — the contract supports it but Phase 5 ships single-backend per run.
- **Microvm cost optimization.** Each gate pays the full microVM lifecycle. Phase 9 with Temporal will introduce activity-pinning for warm-pool reuse; Phase 5 does not.
- **Pre-warmed image registry.** A private mirror would cut cold-start by ~30s on first portfolio scans; Phase 14 territory.
- **Trace baseline auto-update.** A merged PR could update the baseline; Phase 11's Stage-7 Learning is the right home, not Phase 5.

---

## Open questions for the synthesizer

1. **Firecracker stub: ship in v0.5.0 or push to Phase 16?** The convention says ship it for contract extension (the Phase 3 OpenRewriteStub precedent). The CI cost is a weekly self-hosted KVM run. The performance/security designs may argue differently — perf may want the Firecracker fast-path now; security may want it now for hardware isolation. My default is "ship the stub + the contract test; defer real production routing to ADR-0019."
2. **Strict-AND vs M-of-N for the trace signal.** I shipped `TraceSignal` as strictly required and always non-retryable on a diff. The security lens may want strict-AND. The performance lens may want trace as an *advisory* signal that doesn't gate. The roadmap says "runtime trace stays stable" — I read that as required. Synthesizer should pick.
3. **`--allow-test-network` interaction with the trace gate.** Phase 3 introduced `--allow-test-network` as an explicit escalation flag. In Phase 5, this needs to be reconciled with `TraceSignal`'s new-network-endpoint detection. My default: `--allow-test-network` widens the trace gate's `egress_allowlist` to include `<test-pin>` but does not silence the trace signal — the signal becomes informational. Synthesizer may want a stronger or weaker stance.
4. **Cost-cap interaction with retries.** Phase 4 ships per-invocation cost-cap on LLM calls. Three retries means up to 3× LLM spend per workflow. ADR-0025's per-workflow cap is a Phase-13 deliverable; in the meantime, should Phase 5 ship a *gate-level* spend cap that aborts the retry loop at attempt 2 if the cumulative LLM spend already exceeds a configurable ceiling? My default: no, Phase 13 owns; Phase 5 only emits the ledger.
5. **One YAML catalog or two?** I shipped `stage6_validate.yaml` (strict) and `stage6_validate_loose.yaml` (no trace, no policy) so a developer running locally can opt into the looser gate. Performance lens may want this baked in. Security lens may want only strict. Synthesizer to decide.
6. **`pytest-docker` vs `testcontainers-python`.** Roadmap names `pytest-docker`. I honored it. The synthesizer may prefer testcontainers for its richer lifecycle API; my default is to follow the roadmap.
