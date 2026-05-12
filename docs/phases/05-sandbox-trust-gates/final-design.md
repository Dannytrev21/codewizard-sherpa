# Phase 05 — Sandbox + Trust-Aware gates: Final design

**Status:** Design of record (synthesized from three competing designs + critique).
**Synthesized by:** Graph-of-Thought synthesizer subagent
**Date:** 2026-05-12
**Sources:** `design-performance.md` · `design-security.md` · `design-best-practices.md` · `critique.md`

---

## Lens summary

The synthesis takes **best-practices' package shape** (one `sandbox/` package + one `gates/` package, gate logic as YAML data, plain `for`-loop retry, ledger-as-data) as the skeleton; pulls **security-first's data-layer invariants** (`ObjectiveSignals` Pydantic with `extra="forbid"` + CI introspection test, signed pre-patch test inventory, in-VM init holds HMAC, no-credentials-in-sandbox enforced at the type level, host-side eBPF where available); and rejects **performance-first's verdict cache and Install→Test snapshot sharing in Phase 5** (the critic's attacks on cache-key omissions and read-only-`node_modules` correctness landed). On the central conflict — **DiD-on-macOS vs Lima-microVM-on-macOS** — the synthesis departs from all three: ship **DinD as the macOS default (honoring the roadmap)** with an explicit `gate_isolation_class` field that propagates downstream, *and* ship Firecracker-on-Linux/CI as a real second backend (not a stub, but the contract test + a single smoke test is enough Phase 5 evidence — Phase 16's ADR-0019 resolution gets the real benchmark from Phase 13). Phase 5 does **not** ship a verdict cache (Phase 9's territory once Temporal's idempotency model is in place); it does ship a **YAML gate catalog** so Phase 7 distroless lands as data + new signal files, not edits. Phase 5 **extends Phase 3's `TrustScorer`** rather than replacing it — the new objective signals (`trace`, `policy`) are injected into the existing strict-AND, and the signal kind enum is widened additively via an explicit ADR-P5 amendment, with a test that exercises the widening shape so Phase 7 has a worked example.

---

## Goals (concrete, measurable)

Targets are deliberately less aggressive than performance's but more honest. p50/p95 against the Phase 3/4 fixture portfolio (small Node service, ~120 unit tests, ~40 MB `node_modules`).

| # | Goal | Target | Source |
|---|---|---|---|
| 1 | **Public surface introduced** | 1 `SandboxClient` Protocol + 1 `Gate` ABC + 1 `RetryLedger` Pydantic family. No second strict-AND scorer; Phase 3's `TrustScorer` is *extended*, not replaced. | `[B]+[synth]` |
| 2 | **New top-level packages** | 2: `src/codegenie/sandbox/`, `src/codegenie/gates/`. | `[B]` |
| 3 | **Sandbox isolation, Linux/CI** | Firecracker with KVM where available; DinD as the documented fallback. Real (not stub) Firecracker boot proven by one CI smoke test on a KVM runner; the rest of Phase 5's tests run on DinD so the dev loop is not gated on KVM. | `[P]+[B]+[synth]` |
| 4 | **Sandbox isolation, macOS dev** | DinD (`docker run` against Docker Desktop's Linux VM). `gate_isolation_class: "shared_kernel"` annotated on every verdict. Phase 11's merge gate refuses to auto-promote `shared_kernel` verdicts (humans always merge per ADR-0009, but the annotation propagates). No Lima requirement. | `[synth — departs from S]` |
| 5 | **No credentials in the sandbox** | `SandboxSpec.env` is `Mapping[str,str]` filtered by a static allowlist (`PATH`, `NODE_ENV`, `NPM_CONFIG_*`, `HTTPS_PROXY`); orchestrator-side enforcement function with a CI test that asserts no env name containing `KEY`, `TOKEN`, `SECRET`, `PASSWORD` ever passes the filter. | `[S]+[B]+[synth]` |
| 6 | **`ObjectiveSignals` schema** | Pydantic `BaseModel` with `model_config = ConfigDict(extra="forbid", frozen=True)`. CI test introspects the model and asserts no field name contains `confidence`, `llm`, `self_reported`, `model_says`. ADR-0008 is enforced by code, not prose. | `[S]+[synth]` |
| 7 | **Signal kind extensibility** | `GateSignal.kind` is **not** a closed `Literal`; it is a registered string registered via `@register_signal_kind` decorator (Phase 1 probe registry pattern reused). Phase 7's `baseimage` and `shell_presence` register as new kinds without editing the model. | `[synth — departs from all three]` |
| 8 | **Retry default** | `max_attempts=3` (ADR-0014 verbatim). Per-gate override via YAML; CLI flag `--max-attempts-override <int>` requires `--operator-ack` + emits `gate.attempts_override` audit event. (Security's "no override flag" rejected — ADR-0014 explicitly says configurable.) | `[B]+[P]` |
| 9 | **Test-inventory tampering signal** | Pre-patch test inventory is hashed by the orchestrator and copy-in'd to the sandbox; the in-VM test runner discovers tests and emits `tests.delta_test_count` as a *signal*, not a hard fail. Strict-AND treats `delta < 0` (tests removed) as a fail; `delta > 0` (tests added) is logged but does **not** fail the gate. (Phase 11 PR review surfaces the delta.) Resolves S's "patch can't add tests" objection. | `[synth — departs from S's hard-fail]` |
| 10 | **SAST inside the gate** | **Not in Phase 5.** Phase 12 owns deeper validation. Phase 5 ships: build, install, test, policy (lockfile), runtime-trace, cve-delta. Six signals. | `[B]+[P]+[synth — rejects S's SAST]` |
| 11 | **Runtime-trace gate** | strace inside the sandbox (works on DiD + Firecracker). Trace diff against Phase 2 baseline. Coverage signal (`trace.coverage_ok`) is emitted but **not strict-AND**; coverage below threshold becomes a `confidence: low` annotation on the trace signal that the *aggregator* surfaces, not a hard fail. (Security's "host-side eBPF required" rejected — won't work on macOS dev.) | `[synth — departs from S's host-eBPF hard requirement]` |
| 12 | **Verdict cache** | **Not in Phase 5.** Performance's `GateVerdictCache` is appealing but the critic's three concrete attacks (registry-mirror state not in the key, kernel version not in rootfs key, gate-impl source hash) all land. Phase 9's Temporal idempotency primitive is the right home. Phase 5 ships the *cache key derivation function* as forward-compatible data (`SandboxSpec.sandbox_spec_hash`) so Phase 9 can plug a cache behind it. | `[synth — rejects P, ships the seam]` |
| 13 | **Snapshot reuse across gates** | **Not in Phase 5.** Performance's Install→Test shared `node_modules` snapshot crosses ADR-0012 §33 ("every gate starts clean") and the critic correctly notes test runners write under `node_modules/.cache/`. Each gate is its own ephemeral sandbox boot. Phase 9 with Temporal activity-pinning is the right place. | `[S]+[B]+[synth]` |
| 14 | **Build gate latency (cold)** | p50 ≤ 90 s, p95 ≤ 180 s. (Best-practices' targets — honest, no warm pool.) | `[B]` |
| 15 | **Test gate latency** | p50 ≤ 60 s, p95 ≤ 120 s. | `[B]` |
| 16 | **Runtime-trace gate latency** | p50 ≤ 15 s, p95 ≤ 45 s. | `[B]` |
| 17 | **Three-retry loop wall-clock** | retry-2 ≤ 1.6× retry-1 wall-clock (no cache; failed gate's downstream re-runs; passing gates re-run too — honest budget). | `[synth]` |
| 18 | **Test coverage** | ≥ 90% line / 80% branch across new packages; 95%/90% on `gates/runner.py` and `sandbox/contract.py`. | `[B]` |
| 19 | **Exit-criterion E2E** | Demonstrate retry-1 fail + retry-2 recover **with feedback-path semantics actually exercised** (Phase 4's `FallbackTier.run` is invoked with `prior_attempts` and produces a *different* `RecipeApplication`). Critic's attack on best-practices' marker-file fixture landed; the fixture is rebuilt around real Phase-4 re-planning. | `[synth]` |
| 20 | **Tokens per run** | 0 inside Phase 5's package boundary. Phase 4 token cost on retry is the responsibility of Phase 4's `LlmInvocationGuard` running-total hook (already shipped). Phase 5 emits `cost.sandbox.run` ledger entries; the Phase 4 cost ledger composes. | `[B]+[synth]` |
| 21 | **Operator CLI** | `codegenie sandbox health` / `inspect <gate-run-id>` / `gc`. Plus `SandboxHealthProbe` registered as a Probe (ADR-0007 honest-confidence input). Performance's "no CLI" rejected. | `[B]` |

---

## Architecture

```
                 codegenie remediate <repo> --cve <id>
                                  │
                                  ▼ (Phase 3/4 unchanged)
              ┌──────────────────────────────────────────┐
              │ Phase 3 RemediationOrchestrator           │
              │   Stages 1–5 unchanged                    │
              │   Stage 6: Validate → wrapped by Phase 5  │  [P5 EDIT, ADR-P5-001]
              └──────────────────┬───────────────────────┘
                                 │ RecipeApplication from Phase 4
                                 ▼
        ┌─────────────────────────────────────────────────────────────┐
        │ src/codegenie/gates/runner.py — GateRunner                   │  [B-core]
        │                                                              │
        │  def run(transition: TransitionId, ctx: GateContext)         │
        │      -> GateOutcome:                                         │
        │     for attempt in 1..max_attempts:                          │
        │         spec = SandboxSpecBuilder.for_gate(gate_yaml,        │
        │                  attempt, ctx)                               │
        │         run = SandboxClient.execute(spec)                    │
        │         signals = [collect_*(run, ...) for ... in gate]      │
        │         os = ObjectiveSignals.from_collected(signals)        │  [S — strict schema]
        │         outcome = Gate.evaluate(os, ctx)                     │
        │         RetryLedger.record(attempt, os, outcome)             │
        │         if outcome.passed: return outcome                    │
        │         if not outcome.retryable: break                      │
        │         ctx = ctx.with_prior_attempt(outcome)                │
        │     return GateOutcome.escalate(ledger)                      │
        └──────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────────────────────────────┐
        │ src/codegenie/sandbox/ — SandboxClient Protocol              │  [B-core]
        │                                                              │
        │   class SandboxClient(Protocol):                             │
        │       def execute(self, spec: SandboxSpec) -> SandboxRun: ...│
        │       def health(self) -> SandboxHealth: ...                 │
        │                                                              │
        │   Registered backends (built-in):                            │
        │     - DockerInDockerClient   (default; v0.5.0)               │
        │     - FirecrackerClient      (Linux/CI w/ KVM; real impl)    │
        │                                                              │
        │   Backend chosen by:                                         │
        │     1. --sandbox-backend CLI flag                            │
        │     2. ~/.config/codegenie/sandbox.yaml                      │
        │     3. Auto-detect KVM → Firecracker, else DiD               │
        │                                                              │
        │   Every SandboxRun carries gate_isolation_class:             │  [synth]
        │     "microvm"        (Firecracker)                           │
        │     "shared_kernel"  (DiD)                                   │
        └──────────────────┬──────────────────────────────────────────┘
                           │ SandboxRun: run_id, exit_code, logs_dir,
                           │   trace_dir, copy_out_root, duration_ms,
                           │   microvm_seconds, gate_isolation_class
                           ▼
        ┌─────────────────────────────────────────────────────────────┐
        │ Signal collectors (plain functions, register-by-decorator):  │
        │   sandbox/signals/build.py    → BuildSignal      (kind=build)│
        │   sandbox/signals/install.py  → InstallSignal    (kind=inst) │
        │   sandbox/signals/tests.py    → TestSignal       (kind=tests)│
        │   sandbox/signals/trace.py    → TraceSignal      (kind=trace)│
        │   sandbox/signals/policy.py   → PolicySignal     (kind=policy│
        │   sandbox/signals/cve_delta.py→ CveDeltaSignal   (kind=cve)  │
        │                                                              │
        │ Each signal returns an ObjectiveSignals fragment via         │
        │ ObjectiveSignalsBuilder; ConfigDict(extra="forbid") on the   │
        │ aggregated model. NO LLM IMPORT anywhere under sandbox/.     │
        └──────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────────────────────────────┐
        │ Gate catalog (YAML data):                                    │  [B]
        │   src/codegenie/gates/catalog/                               │
        │     stage6_validate.yaml      → required signals + retry     │
        │     stage6_validate_loose.yaml→ dev-only; build+test only    │
        │     _schema.json                                             │
        │                                                              │
        │ Gate.evaluate(os, ctx) is a pure function:                   │
        │   for each required signal in gate.required_signals:         │
        │     ts3_signal_input = TrustSignal(kind, passed, details)    │
        │   trust_outcome = Phase3TrustScorer.score(ts3_signals)       │  [synth — REUSE]
        │   return GateOutcome(passed=trust_outcome.passed, ...)       │
        └─────────────────────────────────────────────────────────────┘

        Cross-cutting:
        ┌─────────────────────────────────────────────────────────────┐
        │ RetryLedger (Pydantic; append-only BLAKE3-chained from       │
        │  Phase 2/3/4 chain head)                                     │
        │ .codegenie/remediation/<run-id>/gates/<gate_id>/             │
        │   attempts.jsonl                                             │
        │   manifest.yaml                                              │
        │   sandbox/<sandbox_run_id>/{stdout.log,stderr.log,trace.jsonl│
        │                             ,policy.json,sbom.json}          │
        └─────────────────────────────────────────────────────────────┘

  Package layout (additions on top of Phase 4):
  src/codegenie/
    sandbox/                  ← NEW
      __init__.py
      contract.py             ← SandboxClient Protocol + SandboxSpec/SandboxRun
      env_allowlist.py        ← static env filter; CI test enforces            [S+synth]
      registry.py             ← @register_sandbox_backend
      did/
        client.py             ← DockerInDockerClient (default)
        build.py              ← single docker buildx chokepoint (documented)
        run.py                ← docker run chokepoint
        copy_out.py
        network_policy.py     ← iptables / network=none enforcement
      firecracker/
        client.py             ← FirecrackerClient (real, KVM-gated)
        rootfs.md             ← documents the pinned vmlinux + rootfs digests
      signals/
        __init__.py
        registry.py           ← @register_signal_kind
        models.py             ← ObjectiveSignals (extra=forbid, frozen)        [S]
        build.py / install.py / tests.py / trace.py / policy.py / cve_delta.py
      health/
        probe.py              ← SandboxHealthProbe (Probe ABC, ADR-0007)
      errors.py
    gates/                    ← NEW
      __init__.py
      contract.py             ← Gate ABC, GateContext, GateOutcome, TransitionId
      runner.py               ← GateRunner: the three-retry loop
      retry_ledger.py         ← RetryLedger
      catalog_loader.py
      catalog/
        stage6_validate.yaml
        stage6_validate_loose.yaml
        _schema.json
      errors.py
    cli/
      sandbox.py              ← codegenie sandbox {health,inspect,gc}

  Phase 0 fence policy CI updates (importer allowlist additions):
    sandbox/                  may NOT import langgraph|anthropic|chromadb
    gates/                    may NOT import langgraph|anthropic|chromadb
    sandbox/                  may NOT import recipes|transforms|rag|llm|planner
    gates/                    may import sandbox|transforms/validation
    Phase 3 trust/             grows two signal-kind registrations (additive)

  Additive interface contract (Phase 3 amend; ADR-P5-002):
    transforms/validation/ApplyContext gains an optional
       `prior_attempts: list[AttemptSummary] = []` field; default empty so
       Phase 3 callsites are unchanged. Phase 4's FallbackTier.run reads
       it when present.
```

---

## Components

### 1. `SandboxClient` — the Protocol

- **Provenance:** `[B]`
- **Purpose:** One contract every microVM/container backend satisfies.
- **Interface:**
  ```python
  class SandboxClient(Protocol):
      def execute(self, spec: SandboxSpec) -> SandboxRun: ...
      def health(self) -> SandboxHealth: ...
  ```
- **Internal design:** `runtime_checkable` Protocol from best-practices' design. Registration via `@register_sandbox_backend` is the same shape as Phase 1's `@register_probe`. Per the critic's "convention drift" attack on best-practices (Protocol vs ABC), we accept the Protocol choice and **add an ABC-vs-Protocol consistency rule to `docs/conventions.md`** (ADR-P5-006): "structural duck-typed contract → Protocol; concrete inheritance with shared default behavior → ABC." Phase 7 follows the same rule for new backend additions.
- **Why this choice over the alternatives:** Best-practices' shape is right. Security's separate `codegenie-gated` daemon adds an OS-service dependency that Phase 6's LangGraph tests would need a fixture for — the critic's attack on the security design's daemon stands. Performance's `SandboxClient` interface is fine but its env=arbitrary-Mapping accepts credentials; we tighten via `env_allowlist.py`.
- **Tradeoffs accepted:** Two-method Protocol is minimal; new backends must implement both. No daemon means orchestrator process is the sole holder of microVM control creds — acceptable because there are no other portfolio-level creds in this phase (Phase 11 introduces git push tokens; by then Phase 9 Temporal worker isolation owns the boundary).

### 2. `SandboxSpec` / `SandboxRun` / `ObjectiveSignals`

- **Provenance:** `[B] (shape) + [S] (extra=forbid + CI introspection) + [synth] (open signal-kind registry)`
- **Purpose:** Carry every byte between the sandbox boundary and the gate evaluator. Pydantic, frozen, no business logic.
- **Interface (sketch):**
  ```python
  class SandboxSpec(BaseModel):
      model_config = ConfigDict(extra="forbid", frozen=True)
      base_image: str                       # digest-pinned
      copy_in: list[CopyInEntry]            # host->sandbox, ro|rw
      env: Mapping[str, str]                # validated by env_allowlist
      cmd: list[str]
      network: Literal["none","scoped"]
      egress_allowlist: list[str]
      enable_trace: bool
      time_budget_seconds: int
      memory_limit_mib: int
      pids_limit: int
      copy_out: list[str]
      label: str
      sandbox_spec_hash: str                # blake3 prefix; forward-compatible
                                            # cache key for Phase 9

  class SandboxRun(BaseModel):
      model_config = ConfigDict(extra="forbid", frozen=True)
      run_id: str                           # uuid7
      spec: SandboxSpec
      backend: Literal["docker_in_docker","firecracker"]
      gate_isolation_class: Literal["shared_kernel","microvm"]    # [synth]
      started_at: datetime
      ended_at: datetime
      exit_code: int
      duration_ms: int
      microvm_seconds: float                # for cost ledger
      image_pull_bytes: int
      build_cache_hit: bool
      logs_dir: Path
      trace_path: Path | None
      copy_out_root: Path
      timed_out: bool
      killed_by_oom: bool

  class ObjectiveSignals(BaseModel):
      model_config = ConfigDict(extra="forbid", frozen=True)
      # one optional sub-model per registered signal kind
      build: BuildSignal | None = None
      install: InstallSignal | None = None
      tests: TestSignal | None = None
      trace: TraceSignal | None = None
      policy: PolicySignal | None = None
      cve_delta: CveDeltaSignal | None = None
      # extension via ADR amendment: new optional field per new kind
  ```
- **Internal design:** All Pydantic `extra="forbid", frozen=True`. The signal sub-models each carry `passed: bool`, `details: dict[str, str | int | bool]`, `provenance: SignalProvenance`, `at: datetime`. The CI introspection test from security walks every field name reachable from `ObjectiveSignals` and asserts none contain `confidence`, `llm`, `self_reported`, `model_says`. Adding a new signal kind is an ADR-P5-amendable additive field — explicit, surfaced.
- **Why this choice over the alternatives:** Security's `extra="forbid"` model with CI introspection is the strongest ADR-0008 enforcement of the three. Best-practices' `details: dict[str, primitive]` allows `confidence` to slip in (critic flagged). Performance's `TrustSignals` model is replaced by Phase 3's existing `TrustScorer` consumption — no second scorer.
- **Tradeoffs accepted:** Adding a new signal kind requires an additive Pydantic field — captured by ADR amendment. The critic worried about the `Literal["build","tests","trace","policy"]` enum on best-practices' design; we **drop the closed Literal** entirely (synth departure: signal kinds are an open registry).

### 3. `DockerInDockerClient` — the Phase 5 default backend (macOS + Linux/CI)

- **Provenance:** `[B]+[synth]`
- **Purpose:** Execute `SandboxSpec` against a Docker daemon. Default on macOS dev; default on Linux CI when KVM is unavailable.
- **Interface:** `execute(spec) -> SandboxRun`; `health() -> SandboxHealth`. Same Protocol.
- **Internal design:**
  - Uses the `docker` Python SDK. Subprocess allowed only inside `did/build.py` for `docker buildx build --progress=plain` (the SDK's build progress streaming is awkward); the carve-out is documented and a fence-CI test asserts no other module under `sandbox/` imports `subprocess`.
  - `network=none` → `--network=none`; `network=scoped` → isolated bridge + iptables allowlist enforced by `did/network_policy.py` (the one file allowed to invoke `iptables`).
  - **No host volume mounts ever for the workload tree**; copy-in is `docker cp` after a one-off `docker create`, copy-out is `docker cp` from the container post-exec. (Bind mounts allowed only for the read-only base-image FS layers, which are already content-addressed.) This honors performance's "copy-in/copy-out only" stance and security's "no shared volumes."
  - **strace** is the trace capture mechanism on DiD (cross-platform; the critic's concern about `SYS_PTRACE` on Docker Desktop is real — addressed by the **CI fixture** that adds `--cap-add=SYS_PTRACE --security-opt seccomp=unconfined` to the test runner. A `SandboxHealthProbe` check at startup asserts strace works, with a clear remediation hint on failure.).
  - `env_allowlist` is applied here: only allowlisted keys propagate into the container's env. Hardcoded denylist on `*KEY*`, `*TOKEN*`, `*SECRET*`, `*PASSWORD*`. CI test on the allowlist.
  - `gate_isolation_class: "shared_kernel"` always.
- **Why this choice over the alternatives:** The critic identified the macOS dev loop as the central conflict. Security wanted Lima+gVisor on macOS, which makes Phase 6+ tests need Lima (the critic's attack landed). The roadmap explicitly says DinD is the portable macOS choice. We honor the roadmap *and* propagate `gate_isolation_class` so Phase 11's promotion machinery can refuse to auto-promote shared-kernel verdicts (which is moot because humans always merge — but the annotation is the same shape Phase 11 will read).
- **Tradeoffs accepted:** macOS dev verdicts are produced under a shared kernel. We **explicitly accept** that an attacker who can both (a) influence the Phase 4 LLM output and (b) defeat `--ignore-scripts` could escape DiD on a developer laptop. Production gates run on Linux/CI with Firecracker. Documented in §Risks risk-2.

### 4. `FirecrackerClient` — the Linux/CI second backend (real, KVM-gated)

- **Provenance:** `[P] (real impl, not stub) + [synth]`
- **Purpose:** Execute the same `SandboxSpec` under hardware-virtualized isolation when KVM is present.
- **Interface:** Same Protocol. `health()` returns `reachable=False` with clear reason on hosts without KVM or a pinned firecracker binary digest.
- **Internal design:** Shells out to a pinned Firecracker binary (digest in `tools/digests.yaml`). Uses a pre-baked `vmlinux` + rootfs `.ext4` from `tools/firecracker/<digest>/` (built by a Phase-0-style preflight, `codegenie sandbox prepare`, documented in `firecracker/rootfs.md`). Boot is cold every time — **no warm pool in Phase 5** (the critic's attacks on performance's WarmPool and snapshot reuse landed). The rootfs cache-key includes `(base_image_digest, node_major, vmlinux_digest, rootfs_builder_version)`. `gate_isolation_class: "microvm"`.
- **Why this choice over the alternatives:** Best-practices proposed a stub that "generates no evidence" (critic flagged) — the whole point of building Firecracker in Phase 5 is to produce ADR-0019 evidence. Performance over-promised (warm pool, verdict cache) and under-budgeted DiD-on-macOS. We ship Firecracker as a real backend with **one CI smoke test on a self-hosted KVM runner** that boots, runs `npm ci && npm test` on the hello-node fixture, asserts a `SandboxRun` shaped identically to the DiD one. Phase 13's cost ledger collects per-backend numbers; Phase 16's ADR-0019 resolution reads them.
- **Tradeoffs accepted:** One additional CI runner (self-hosted KVM) plus the rootfs pre-bake script. The Firecracker rootfs is a maintenance burden (bumping `npm` versions = rebuild + new digest in `tools/digests.yaml`). Bit-rot risk: same mitigation as best-practices proposed — a weekly cron runs the smoke test even if no PR touches the sandbox code.

### 5. `Gate` (ABC) + YAML catalog + `StrictAndGate`

- **Provenance:** `[B]+[synth]`
- **Purpose:** Encode "given these `ObjectiveSignals`, do we advance?" as a pure function plus data.
- **Interface:**
  ```python
  class Gate(ABC):
      gate_id: str
      required_signals: tuple[SignalKind, ...]
      retry_policy: RetryPolicy

      @abstractmethod
      def evaluate(self, os: ObjectiveSignals, ctx: GateContext) -> GateOutcome: ...

  class StrictAndGate(Gate):
      """Translates ObjectiveSignals to Phase 3 TrustSignals + delegates."""
  ```
- **Internal design:** `StrictAndGate.evaluate(os, ctx)` is a **thin adapter**: it materializes a list of `TrustSignal(kind, passed, details)` from the populated `ObjectiveSignals` sub-models and **calls Phase 3's existing `TrustScorer.score(...)`**. Phase 3's `TrustScorer` is the canonical scorer; Phase 5 does not ship a second one. The new signal kinds (`trace`, `policy`, `cve_delta`) are registered as additional `TrustSignal.kind` values via Phase 3's existing extension point — ADR-P5-003 captures this additive widening with a worked test (`tests/integration/test_trustscorer_widening.py` asserts the existing Phase 3 strict-AND still passes when only build/install/test are present, and adds the new kinds without changing scorer logic).
- **Why this choice over the alternatives:** All three Phase-5 designs effectively replaced Phase 3's `TrustScorer` — the critic flagged this as a violation of commitment §2.5 (extension by addition). The synthesis instead **extends** the existing scorer by injecting new signal kinds, with the StrictAndGate adapter as the seam. Phase 7 distroless adds two more kinds (`baseimage`, `shell_presence`) by registering them — no edits to `TrustScorer`, no edits to `StrictAndGate`, just new signal files and an ADR-P7 amendment.
- **Tradeoffs accepted:** `StrictAndGate` is a small adapter (~40 LOC) that translates one Pydantic model into another. The alternative — Phase 5's `ObjectiveSignals` *being* the Phase 3 signal model — would have required editing Phase 3 to widen its model in place. Worse trade.

### 6. `GateRunner` — the three-retry loop

- **Provenance:** `[B]+[synth]`
- **Purpose:** Implement ADR-0014 once. Loop as data, not control flow.
- **Interface:**
  ```python
  class GateRunner:
      def __init__(self, *, client: SandboxClient, gate: Gate,
                   ledger: RetryLedger, max_attempts: int = 3) -> None: ...
      def run(self, ctx: GateContext) -> GateOutcome: ...
  ```
- **Internal design:** Plain `for attempt in range(1, max_attempts + 1)` loop, same shape as best-practices. Each iteration: build `SandboxSpec` (depends on `attempt` via the YAML's per-attempt overrides), execute, collect signals into `ObjectiveSignals`, evaluate gate, record to ledger, decide. Three branches: `passed → return`, `failed && retryable && attempt < max → ctx = ctx.with_prior_attempt(outcome); continue`, `else → return escalate(ledger)`.
  - **Retry feedback semantics (CRITICAL):** `ctx.with_prior_attempt(outcome)` produces a new `GateContext` whose `prior_attempts: list[AttemptSummary]` field is appended. **Phase 4's `FallbackTier.run` and Phase 3's `ApplyContext` are amended additively (ADR-P5-002) to accept `prior_attempts: list[AttemptSummary] = []`** as a kwarg. When the orchestrator re-enters Phase 4 for a retry, it passes `prior_attempts` through; `FallbackTier` includes them in the planner prompt (fence-wrapped with Phase 4's existing untrusted-text fence, truncated to 8 KB, pattern-checked for canary collisions — security's defense ported into Phase 4 by extension).
  - **`AttemptSummary`** is a Pydantic frozen model: `attempt_id`, `sandbox_run_id`, `failing_signals: list[Literal["build","install","tests","trace","policy","cve_delta"]]`, `prior_failure_summary: str` (≤ 4 KB, sanitized by `FenceWrapper`), `evidence_paths: dict[str, Path]`. **No raw log bytes** — the summary is a structured digest of what failed.
  - On attempt 2+, if the same `failing_signals` set repeats, the ledger flags `flake_score=0` (best-practices' "same signature twice" non-retryable shortcut). At 3 identical signatures, the outcome is `failed_unrecoverable`, not `escalate` — distinct exit semantics.
- **Why this choice over the alternatives:** Performance's `GateCoordinator` is sync-with-bounded-async — premature concurrency for Phase 5 (the critic's roadmap-level §1 attack noted Phase 6 LangGraph will re-implement the retry loop anyway). Security's `codegenie-gated` daemon over AF_UNIX is over-engineered for Phase 5's threat model. Best-practices' shape is right; we tighten the feedback path semantics so Phase 4's interface extension is explicit and ADR-recorded.
- **Tradeoffs accepted:** No concurrent gate evaluation. Phase 5 ships sync. Phase 9 with Temporal owns concurrency. The critic's roadmap §1 says Phase 6 will re-implement the retry inside LangGraph anyway — we accept that. The `GateRunner.run` function body becomes a LangGraph subgraph; the `for` loop maps to recursive node calls; **the `RetryLedger` shape is what Phase 6 lifts unchanged**, which is the contract that survives.

### 7. `RetryLedger` — audit-grade attempt log

- **Provenance:** `[B]+[S — chain extension]`
- **Purpose:** Append-only record of every attempt + every signal payload. The artifact that proves the exit criterion.
- **Interface:**
  ```python
  class RetryLedger:
      def __init__(self, *, run_dir: Path, gate_id: str,
                   prev_chain_head: bytes | None) -> None: ...
      def record(self, attempt: Attempt) -> None: ...
      def head(self) -> bytes: ...
      def attempts(self) -> list[Attempt]: ...
  ```
- **Internal design:** Each `record` writes one BLAKE3-chained JSON line to `attempts.jsonl` under `.codegenie/remediation/<run-id>/gates/<gate_id>/`. The first line's `prev_hash` is the Phase 4 chain head (read at `GateRunner.__init__`). The chain verification test at startup: `prev_chain_head` must match the persisted Phase 4 head — if not, raise `AuditChainCorrupted` and refuse to run any gate. Same shape as Phase 2/3/4.
  - **Chain compatibility test (ADR-P5-005):** A new integration test asserts that Phase 4's `solved_example.duplicate_skipped` chain event and the `engine_used` stamping produce chain entries whose field shape Phase 5 can read. Critic's roadmap §6 attack ("none has verified that Phase 4's chain events produce entries Phase 5 will consume") is closed by an explicit golden-fixture test.
- **Why this choice over the alternatives:** Performance's audit ledger is identical in shape; we keep best-practices' file layout because it composes with Phase 3's already-extant `remediation-report.yaml` index.
- **Tradeoffs accepted:** JSONL append-only on a single host; no replication in Phase 5. Phase 16 production hardening replicates.

### 8. `SandboxHealthProbe` — Phase 5's B2 analog

- **Provenance:** `[B]`
- **Purpose:** Detect silent unavailability of the sandbox backend. ADR-0007 "honest confidence" input.
- **Interface:** Standard `Probe`. `name="sandbox_health"`. `declared_inputs=["~/.config/codegenie/sandbox.yaml", "tools/digests.yaml"]`. Emits `SandboxHealth` into `RepoContext.health.sandbox`.
- **Internal design:** Reads sandbox config, instantiates the configured backend, calls `client.health()`. Failure modes detected: docker daemon down, daemon up but rootless misconfigured, buildx missing, base image registry unreachable, KVM missing (Firecracker), pinned digest unpullable, strace unavailable (macOS DiD without `SYS_PTRACE`).
- **Why this choice over the alternatives:** Performance shipped no health probe; security shipped a daemon-based health check that requires the daemon to be up; best-practices got this right. We keep best-practices' shape.

### 9. Signal collectors — six functions (+ open registry for Phase 7)

- **Provenance:** `[B] (shape) + [synth] (open registry)`
- **Purpose:** Translate a `SandboxRun` into a typed signal sub-model that fits into `ObjectiveSignals`.
- **Interface:**
  ```python
  @register_signal_kind("build")
  def collect_build_signal(run: SandboxRun) -> BuildSignal: ...

  @register_signal_kind("install")
  def collect_install_signal(run: SandboxRun) -> InstallSignal: ...

  @register_signal_kind("tests")
  def collect_test_signal(run: SandboxRun) -> TestSignal: ...

  @register_signal_kind("trace")
  def collect_trace_signal(run: SandboxRun,
                            baseline: TraceBaseline | None) -> TraceSignal: ...

  @register_signal_kind("policy")
  def collect_policy_signal(run: SandboxRun,
                             policy_yaml: Path) -> PolicySignal: ...

  @register_signal_kind("cve_delta")
  def collect_cve_delta_signal(run: SandboxRun,
                                 pre_patch_sbom: Path) -> CveDeltaSignal: ...
  ```
- **Internal design:** Plain functions. Each ≤ 60 LOC. The **policy collector's `policy_yaml` source is `tools/policy/sandbox-policy.yaml`** — a digest-pinned, codegenie-owned file under version control, **NOT** read from the target repo's working tree. This closes critic's attack on best-practices §6 ("the LLM-produced patch can modify in-repo policy"). The path is constant; the bytes are checked at startup against `tools/digests.yaml`.
- **Why this choice over the alternatives:** Functions over an ABC with N subclasses (composition over inheritance). Open signal-kind registry instead of best-practices' closed `Literal` — Phase 7 distroless adds `baseimage` and `shell_presence` as new files with `@register_signal_kind`, zero edits.
- **Tradeoffs accepted:** Adding a fifth signal is a fifth file *plus* a new optional field on `ObjectiveSignals` (ADR-P5-amendment). The Pydantic model widening is the only "edit" — and it's explicitly an ADR-gated additive change.

### 10. CLI surface — `codegenie sandbox`

- **Provenance:** `[B]`
- **Purpose:** Operator surface.
- **Public interface:**
  - `codegenie sandbox health` — prints SandboxHealth.
  - `codegenie sandbox inspect <gate-run-id>` — pretty-prints `attempts.jsonl` with signals and durations.
  - `codegenie sandbox gc [--older-than 7d]` — removes old `.codegenie/sandbox/runs/<id>/` dirs.
  - `codegenie sandbox prepare [--backend firecracker]` — pre-bake the Firecracker rootfs (preflight).
- **Internal design:** `click`. New `--sandbox-backend {did,firecracker,auto}` flag on `codegenie remediate`. New `--max-attempts-override <int>` requires `--operator-ack` (best-practices). Audit-emits `gate.attempts_override`.

---

## Data flow

End-to-end run, **the exit criterion case**: vuln remediation; recipe fails; Phase 4 falls back to LLM; LLM produces an initial patch that breaks a test; retry-1 re-invokes Phase 4 with `prior_attempts`; Phase 4 produces a different patch that passes.

1. **Phase 3 Stages 1–4 run unchanged.** Recipe selected, transform applied, lockfile canonicalized. Recipe-application fails (`reason=catalog_miss`). Phase 4's `FallbackTier.run(advisory, repo_ctx, recipe_selection, prior_attempts=[])` runs. LLM returns a structured plan; patch lands at `.codegenie/remediation/<run-id>/patch-attempt-1.diff`. **Trust boundary:** the patch bytes are now LLM output influenced by adversary-influenced repo content. [Phase 4 unchanged; the new `prior_attempts` kwarg has empty default, so Phase 4 callsites are not edited]
2. **Phase 5 Stage 6 begins.** `GateRunner.run(transition=stage6_validate, ctx=GateContext(worktree, advisory, recipe, transform_output, prior_attempts=[]))`.
3. **Attempt 1: `SandboxSpecBuilder.for_gate(stage6_validate.yaml, attempt=1, ctx)` produces a `SandboxSpec`:**
   - `base_image: cgr.dev/chainguard/node@sha256:<pinned>`
   - `copy_in: [(worktree, /work, ro), (test-inventory.json, /work/.codegenie/inventory.json, ro)]`
   - `env: {PATH: ..., NODE_ENV: test}` (env_allowlist filtered; no creds)
   - Two-phase `cmd`: phase A `npm ci --ignore-scripts` with `network=scoped` to `registry.npmjs.org`; phase B `npm test` with `network=none` and `strace -f -e trace=execve,connect`
   - `enable_trace: true`
   - `time_budget_seconds: 600`
   - `gate_isolation_class` set by backend (DiD → `shared_kernel`; Firecracker → `microvm`)
4. **`SandboxClient.execute(spec)`** runs the two phases, captures stdout/stderr/strace into `.codegenie/sandbox/runs/<run-id>/`. Exit code 1 (jest reported 1 failure). `SandboxRun` returned.
5. **Signal collectors run in sequence:**
   - `collect_build_signal` → `BuildSignal(passed=True, details={"image_built":True})`
   - `collect_install_signal` → `InstallSignal(passed=True, details={"deps":127})`
   - `collect_test_signal` → `TestSignal(passed=False, details={"failing_tests":1, "first_failure":"auth/jwt.test.ts: should reject expired tokens", "delta_test_count":0})`
   - `collect_trace_signal` → `TraceSignal(passed=True, details={"new_shell":0, "new_endpoints":0, "coverage_ok":True})`
   - `collect_policy_signal` (against digest-pinned `tools/policy/sandbox-policy.yaml`) → `PolicySignal(passed=True, details={"hits":0})`
   - `collect_cve_delta_signal` → `CveDeltaSignal(passed=True, details={"direction":"-1", "pre_count":3, "post_count":2})`
6. **`ObjectiveSignals` assembled.** CI introspection test already asserted no `confidence` field is reachable; Pydantic `extra="forbid"` rejects unknown fields at construction time.
7. **`StrictAndGate.evaluate(os, ctx)`:** materializes `TrustSignal(kind="build", passed=True, details=...)` × 6, calls Phase 3's `TrustScorer.score([...])`. Returns `TrustOutcome(passed=False, failing=["tests"])`. `GateOutcome(passed=False, retryable=True, attempt=1, failing_signals=["tests"], summary="1 test failed: auth/jwt.test.ts")` returned.
8. **`RetryLedger.record(Attempt(attempt_id=1, sandbox_run_id=..., signals=os, outcome=..., prior_failure_summary="1 test failed; first: auth/jwt.test.ts: should reject expired tokens"))`.** BLAKE3 chain extends.
9. **Loop iterates.** `ctx = ctx.with_prior_attempt(outcome)` → `prior_attempts=[AttemptSummary(failing_signals=["tests"], prior_failure_summary=..., evidence_paths=...)]`.
10. **Orchestrator re-enters Phase 4 for the retry.** `FallbackTier.run(advisory, repo_ctx, recipe_selection, prior_attempts=[...])`. Phase 4's prompt builder includes the fence-wrapped, truncated, canary-checked `prior_failure_summary` from the AttemptSummary as planner context. **Phase 4 produces a different `RecipeApplication`** (different `patch_blake3`).
11. **Attempt 2.** `SandboxSpecBuilder.for_gate(stage6_validate.yaml, attempt=2, ctx)` — YAML may set a slightly more verbose `cmd` for attempt 2 (e.g., `npm test -- --verbose --maxWorkers=1`). New `SandboxClient.execute(spec)`. Tests pass.
12. **Signal collectors → ObjectiveSignals → StrictAndGate.evaluate → Phase 3 TrustScorer → `GateOutcome(passed=True, attempt=2)`.**
13. **`RetryLedger.record(Attempt(2, ...))`.** Two entries in `attempts.jsonl`.
14. **`GateRunner.run` returns `GateOutcome.passed`.** Orchestrator continues Phase 3 Stage 7 (handoff to local branch — Phase 11 is when real PRs open).
15. **Audit-chain & cost emissions:** Each attempt emits `cost.sandbox.run` ledger entries (microvm-seconds, image-pull bytes, build-cache hit/miss) for Phase 13 to roll up. Phase 4's `LlmInvocationGuard` running-total hook is consumed across both attempts (the critic's blind-spot #3 — "every Phase 5 workflow that exercises retry-1-fail spends Phase 4 tokens × 2" — is honest in the cost ledger).

---

## Failure modes & recovery

| Failure | Detected by | Containment | Recovery | Source |
|---|---|---|---|---|
| Docker daemon unreachable at startup | `SandboxHealthProbe` | `SandboxBackendUnavailable` raised before any gate runs | Operator starts docker; or `--sandbox-backend firecracker` if KVM available | `[B]` |
| Docker daemon dies mid-build | `DockerInDockerClient.execute` catches `docker.errors.APIError` | `SandboxRunFailed`; counts toward `max_attempts` | Retry; if 3× `APIError`, escalate exit 11 | `[B]` |
| Base-image digest unpullable | image pull on attempt 1 | `SandboxImageUnavailable` | `codegenie sandbox health` for pointer; ADR-amend to bump digest | `[B]` |
| Sandbox timed out (`time_budget_seconds`) | dind SIGKILL; `SandboxRun.timed_out=True` | `TestSignal(passed=False, details={"timed_out":true})`; **non-retryable** by default | Escalate exit 11 unless YAML opts into `timeout_retryable=true` | `[B]` |
| OOM kill inside sandbox | `SandboxRun.killed_by_oom=True` | Non-retryable | Operator inspects, bumps `memory_limit_mib`, re-runs | `[B]` |
| `npm` postinstall calls egress | `network=scoped` allowlist drops; or `--ignore-scripts` blocks | Verdict.fail via `trace.new_endpoints`; audit `sandbox.egress.blocked` | Retry feedback shows the LLM what was attempted; at 3, human review | `[S]+[P]` |
| LLM-produced patch deliberately removes a test | Test inventory diff: `tests.delta_test_count < 0` | Strict-AND fails (negative delta is a fail signal); positive delta logged but not failed | Retry; if persists, escalate; reviewer sees the delta in evidence bundle | `[synth]` |
| Trace gate sees new shell invocation | strace diff vs Phase 2 baseline | `TraceSignal(passed=False)`; **non-retryable** | Always escalates — new shell invocations require human review | `[B]+[S]` |
| Trace gate coverage low | strace observed too few syscalls (e.g., binary statically linked + skipped strace) | `TraceSignal.details={"coverage_ok":false}`; **logged but not strict-AND fail** | Surfaced as `confidence: low` annotation; reviewer judges | `[synth — departs from S's hard-fail]` |
| Policy gate fails (lockfile policy from Phase 3 + digest-pinned sandbox policy) | `collect_policy_signal` against `tools/policy/sandbox-policy.yaml` (NOT the repo) | Retryable iff `policy.retry_allowed=true` in gate YAML | Phase 4's `FallbackTier` re-invokes with `prior_attempts` | `[B]+[S+synth]` |
| CVE delta direction positive (patched code adds a vuln) | grype diff post vs pre | `CveDeltaSignal(passed=False)` | Phase 4 replans; if persists, escalate | `[P]` |
| YAML gate catalog invalid | `catalog_loader` schema check at startup | `GateCatalogInvalid` | CLI exit before any gate runs | `[B]` |
| `attempts.jsonl` chain hash mismatch | `RetryLedger.record` precheck | `AuditChainCorrupted` | Refuse run; operator inspects (intentional brittleness) | `[B]+[S]` |
| Phase 4 chain-head mismatch on Phase 5 startup | `RetryLedger.__init__` reads Phase 4 chain head | `AuditChainCorrupted` | Refuse run (closes critic roadmap §6) | `[synth]` |
| `--max-attempts-override` set without `--operator-ack` | click validator | Click exit 2 | Operator adds the ack flag | `[B]` |
| Firecracker on non-KVM host | `FirecrackerClient.health()` | `FirecrackerKvmMissing` | Operator gets KVM-capable runner or switches to `did` | `[B]` |
| strace `SYS_PTRACE` missing on macOS DiD | `SandboxHealthProbe` startup check | `StraceUnavailable` warning with `SandboxHealth.warnings` | Operator runs `codegenie sandbox health` for remediation hint; documented runtime config | `[synth — addresses critic's strace blind spot]` |
| `microvm_seconds` cost ledger emission fails | `CostEmitter` wraps write errors | Logged WARNING; gate continues | Cost ledger shows `emission_error=true`; Phase 13 replays | `[B]` |
| Same failing-signal signature 3× | Ledger flake-score detection | `failed_unrecoverable` (not `escalate`) | Distinct exit semantics — reviewer knows the LLM is stuck | `[B]+[synth]` |

Every failure path writes one audit event into the BLAKE3 chain. Phase 13 pivot tables key off the event names.

---

## Resource & cost profile

Order-of-magnitude figures. Single-machine M-series Mac developer or 4-vCPU Linux CI runner.

- **Docker image footprint:** Chainguard Node base ~50 MB compressed, ~150 MB on disk. Pulled once per digest pin.
- **Per-gate cold (DiD, image not cached, deps not cached):** ~120 s wall, ~95 s microvm-seconds.
- **Per-gate warm (image cached, deps cached):** ~25 s wall, ~22 s microvm-seconds.
- **Per-gate trace overhead:** strace adds ~10–15% wall time on Node test suites. Acceptable in Phase 5; Phase 12+ may reduce with eBPF on Linux.
- **Disk per run:** `.codegenie/sandbox/runs/<id>/` ~5–20 MB. `codegenie sandbox gc --older-than 7d` is the housekeeping path.
- **Firecracker cold boot (Linux/CI):** ~6 s rootfs + kernel boot + npm cache warmup. **No warm pool in Phase 5**; this is the actual cost every time. Phase 9 with Temporal may introduce activity-pinning for warm-pool reuse — that's the right home, not Phase 5.
- **Three-retry cost (worst case):** 3 × (~120 s gate + Phase 4 LLM cost). Phase 4 LLM cost on each retry is real and is tracked by Phase 4's `LlmInvocationGuard` running-total. The critic's blind-spot was right — we surface this honestly.
- **Memory per worker:** ~2.0 GB (orchestrator 200 MB + chromadb mmap 400 MB + 1 active sandbox VM × 1 GB + buffers 400 MB). 2 concurrent workers fits in 4 GB; this is the developer-laptop budget.
- **Audit-chain growth:** ~5 entries per gate × ~6 gates per workflow × ~1 KB per entry = ~30 KB per workflow. Linear; manageable.
- **Token cost:** 0 inside Phase 5's package boundary. Phase 4 tokens on retry are tracked by Phase 4's `LlmInvocationGuard`.

**Tradeoff against security / best-practices:** No verdict cache means retry-3 pays full freight every gate, not just the failing one. The critic correctly noted ADR-0025's per-workflow cap (Phase 13) will be materially worse than necessary in the worst case. This is **explicitly accepted** for Phase 5; Phase 9's Temporal idempotency primitive is the right place to add the cache, with proper input-key audit (the kind the critic showed performance got wrong).

---

## Test plan

### Unit tests (~70%; fast; no docker)

- `tests/sandbox/test_contract.py` — `SandboxSpec`/`SandboxRun`/`ObjectiveSignals` schema invariants, `extra="forbid"` rejection, frozen-model immutability, `sandbox_spec_hash` byte-stability across two constructions.
- `tests/sandbox/test_objective_signals_static.py` — **the critical CI test.** Walks every field reachable from `ObjectiveSignals` and asserts no field name contains `confidence`, `llm`, `self_reported`, `model_says`. Locks ADR-0008 by code.
- `tests/sandbox/test_env_allowlist.py` — given a deny pattern list (`*KEY*`, `*TOKEN*`, `*SECRET*`, `*PASSWORD*`), asserts an arbitrary env dict is filtered correctly. Hypothesis-based: any env mapping containing a denied substring is rejected.
- `tests/sandbox/test_did_network_policy.py` — given an allowlist YAML, generated iptables rules are byte-identical to a golden file.
- `tests/sandbox/test_did_copy_out.py` — given a fake `SandboxRun`, `docker cp` argument list is byte-identical to a golden command list; SDK mocked.
- `tests/sandbox/signals/test_*.py` — one file per collector. Each feeds a fixture log and asserts the resulting signal sub-model matches a golden Pydantic dump.
- `tests/sandbox/health/test_probe.py` — `SandboxHealthProbe` against mocked backends.
- `tests/gates/test_runner.py` — **the workhorse.** All retry-loop branches asserted with a fake `SandboxClient` (in-memory; scripted `SandboxRun` sequence). Cases: pass on 1; pass on 2; pass on 3; fail after 3 (escalate); fail after 3 with identical signature (failed_unrecoverable); non-retryable on 1 → immediate escalate; `timed_out` non-retryable; `oom_killed` non-retryable; `--max-attempts-override` raises floor; ledger chain extends; `with_prior_attempt` produces correct `AttemptSummary`.
- `tests/gates/test_retry_ledger.py` — append-only invariants; BLAKE3 chain links; reject out-of-order writes; reject chain-tamper; **reject startup with Phase 4 chain-head mismatch** (golden Phase 4 head).
- `tests/gates/test_catalog_loader.py` — every YAML in `gates/catalog/` parses and validates; invalid YAML rejected.

### Property tests (hypothesis)

- `StrictAndGate.evaluate(os, ctx)` materializes signals correctly: for every combination of `[passed/failed] × 6 signals`, the gate's verdict matches `all(passed)` — and matches what Phase 3's `TrustScorer.score(...)` returns on the same inputs (the property test asserts *equivalence with Phase 3's scorer*, not a reimplementation).
- `RetryLedger.record(N).head()` deterministically depends on `(records, prev_chain_head)`.
- `SandboxSpec.sandbox_spec_hash` invariant under reordering of `env` dict keys (sorted before hashing).
- Signal collectors are pure: same fixture → same signal sub-model.

### Integration tests (~25%; medium; uses `pytest-docker`)

- `tests/integration/sandbox/test_did_end_to_end.py` — rootless dind via `pytest-docker`, real `SandboxSpec` against `tests/fixtures/repos/hello-node/`, real `SandboxRun` returned; `npm ci` actually ran inside the sandbox.
- `tests/integration/gates/test_stage6_validate.py` — full Stage 6 gate against `known-good-node/`. Single attempt, passes.
- `tests/integration/gates/test_stage6_retry_recovers.py` — **THE exit-criterion test, REWRITTEN.** The fixture is `tests/fixtures/repos/breaking-change-cve/`. Phase 4's `FallbackTier` is invoked on the *real* CVE input; the LLM's first response (via VCR cassette `cassette-attempt-1.yaml`) produces a patch that breaks a test; retry-1 invokes `FallbackTier.run(... prior_attempts=[AttemptSummary(...)])`; the second cassette `cassette-attempt-2.yaml` produces a different patch that passes. Assertions: `attempts.jsonl` has 2 entries with **distinct `attempt_id`s, distinct `prior_failure_summary`s, distinct `sandbox_run_id`s, distinct patch bytes**, and the Phase 4 prompt sent on attempt 2 contained the fence-wrapped `prior_failure_summary`. **This closes critic best-practices §4 (marker-file fixture).**
- `tests/integration/gates/test_stage6_three_attempts_escalates.py` — fixture that fails identically every time; ledger captures 3 attempts; runner returns `failed_unrecoverable`; CLI exit 11.
- `tests/integration/sandbox/test_network_policy_enforcement.py` — sandbox tries to curl github.com with `network=none` (fails), `network=scoped` non-matching (fails), `network=scoped` matching (succeeds).
- `tests/integration/sandbox/test_trace_baseline_diff.py` — deterministic shell-spawn introduced in the patch; trace collector reports it; gate fails non-retryable.
- `tests/integration/sandbox/test_test_inventory_delta.py` — patch removes one test; `tests.delta_test_count = -1`; strict-AND fails. Patch adds one test; `delta = +1`; strict-AND passes; reviewer evidence bundle shows the delta.
- `tests/integration/gates/test_firecracker_smoke.py` — **Linux/CI KVM-only**, marked `@pytest.mark.skip_if_no_kvm`. Boots Firecracker against the pinned vmlinux + rootfs, runs hello-node `npm ci && npm test`, asserts `SandboxRun` shape matches DiD's. **Single weekly cron in addition to PR-trigger** so the path doesn't bit-rot.
- `tests/integration/chain/test_phase4_chain_compat.py` — golden Phase 4 chain head fixture; Phase 5 `RetryLedger` reads it and verifies. Closes critic roadmap §6.

### Adversarial / negative

- `tests/adversarial/test_patch_disables_test.py` — patch removes a test file and edits `package.json#scripts.test` to `exit 0`. Pre-patch inventory diff catches it (`delta < 0`); verdict.fail.
- `tests/adversarial/test_postinstall_exfil.py` — patch contains a `postinstall` that POSTs to `evil.com`. `--ignore-scripts` blocks; even if scripts were enabled, `network=scoped` allowlist drops; audit `sandbox.egress.blocked` recorded.
- `tests/adversarial/test_prompt_injection_in_error_log.py` — test fails with stderr containing `Ignore all previous instructions...`. Phase 4's fence + canary pattern matcher fires before reaching the LLM; log replaced with `<redacted>`; retry proceeds. (Reuses Phase 4's `FenceWrapper`.)
- `tests/adversarial/test_in_repo_policy_ignored.py` — patch includes a `.codegenie/policy.yaml` modification. Verifies the digest-pinned `tools/policy/sandbox-policy.yaml` is used, **not** the repo's file. Closes critic best-practices §6.
- `tests/adversarial/test_audit_chain_tamper.py` — manually edit `attempts.jsonl` to drop an entry. Restart `GateRunner`. Chain verification fails; refuses to serve.

### Supply chain & schema enforcement

- `tests/schema/test_digests_yaml.py` — `tools/digests.yaml` includes `sandbox.firecracker`, `sandbox.vmlinux`, `sandbox.rootfs`, `sandbox.policy_yaml`. CI gate.
- `tests/schema/test_no_llm_imports_in_sandbox.py` — `fence` CI extended: `sandbox/**/*.py` and `gates/**/*.py` may not import `anthropic`, `langgraph`, `chromadb`, `sentence_transformers`.
- `tests/schema/test_no_subprocess_outside_build_chokepoint.py` — only `sandbox/did/build.py` may import `subprocess` under `sandbox/`.

### E2E

- `tests/e2e/test_remediate_with_sandbox.py` — runs `codegenie remediate ./tests/fixtures/repos/cve-fixture/ --cve CVE-2024-FAKE-NPM --sandbox-backend did` (reuses Phase 3's CVE fixture). Asserts exit 0, remediation branch exists, report references `gates/stage6_validate/`, `attempts.jsonl` has exactly 1 attempt.

---

## Risks (top 5)

1. **DiD on macOS is shared-kernel for LLM-produced code.** Phase 5's macOS dev verdicts are produced under Docker Desktop's shared Linux VM. An attacker who (a) influences Phase 4's LLM output and (b) defeats `--ignore-scripts` could escape DiD on a developer laptop. **Mitigation:** `gate_isolation_class: "shared_kernel"` annotated on every verdict; Phase 11's merge gate refuses to auto-promote shared-kernel verdicts (and humans always merge per ADR-0009). Production gates on Linux/CI run Firecracker. The trade is dev-loop ergonomics > microVM-on-macOS purism — security's Lima requirement stalls Phase 6/7's dev loop (critic's central attack landed). Documented as the explicit roadmap-honoring choice in ADR-P5-004.
2. **No verdict cache means retry-3 pays full freight.** Three retries × six gates × ~120 s = ~36 min worst-case cold workflow. The cost dashboard will surface this; the per-workflow cap (Phase 13) accounts for it. Phase 9's Temporal idempotency model is where the cache lands — with proper input-key audit (the kind the critic showed performance got wrong by omitting registry-mirror state + kernel digest).
3. **The Firecracker rootfs may bit-rot.** Without continuous CI exercise it slowly diverges from the DiD path. **Mitigation:** weekly self-hosted KVM cron in addition to PR-trigger smoke test; rootfs build provenance test asserts digest match.
4. **strace coverage on macOS DiD is fragile.** Docker Desktop's nested Linux VM requires `--cap-add=SYS_PTRACE --security-opt seccomp=unconfined` for strace to see child processes. **Mitigation:** `SandboxHealthProbe` startup check fails loudly with a clear remediation message; the trace gate's `coverage_ok` signal is annotated as `confidence: low` when strace coverage is suspicious, not an automatic fail (departs from security's hard-fail because that breaks every macOS dev gate).
5. **Phase 4's `FallbackTier.run` interface gains a kwarg.** ADR-P5-002 documents the additive `prior_attempts: list[AttemptSummary] = []` extension. **Mitigation:** the default-empty kwarg means Phase 4's existing callsites are unchanged; only the orchestrator's retry path passes the kwarg. An integration test asserts Phase 4's prompt builder includes the fence-wrapped summary when `prior_attempts` is non-empty (closes critic cross-design observation #3 — "none of the three checked Phase 4's `FallbackTier.run` accepts a `prior_attempts` kwarg shape"). Phase 4's contract-snapshot test regenerates with the additive field.

---

## Synthesis ledger

### Vertex count
- Performance design: ~32 vertices
- Security design: ~38 vertices
- Best-practices design: ~30 vertices
- **Total: ~100 vertices**

### Edges
- AGREE: 14 (e.g., 0 LLM tokens at the gate; ADR-0014 three-retry default; strict-AND ADR-0008; audit-chain extension; `--ignore-scripts`; gate is a transition; no shared volumes for the working tree; runtime trace as a signal; `network=none` for tests; CLI/operator surface mostly aligned at top level)
- CONFLICT: 18 (sandbox stack on macOS; verdict cache; snapshot reuse Install→Test; Phase 3 `TrustScorer` replace vs extend; signal kind closed Literal vs open registry; gate-control daemon vs in-process; eBPF host-side vs strace in-VM; test-inventory hard-fail vs delta-signal; SAST in Phase 5; override flag for max-attempts; policy YAML source (repo vs codegenie-owned); env arbitrary vs allowlist; sandbox health probe yes/no; Firecracker stub vs real; warm pool yes/no; one-time callback URL vs filesystem handoff; retry-context as raw log vs structured AttemptSummary; cold-boot budget claim defensibility)
- COMPLEMENT: 12 (security's `extra="forbid"` model + best-practices' YAML catalog; performance's `sandbox_spec_hash` forward-compat + best-practices' Protocol; security's HMAC ObjectiveSignals envelope + best-practices' RetryLedger BLAKE3 chain; etc.)
- SUBSUME: 6 (best-practices' single chokepoint subsumes performance's no-host-mounts purist position; Phase 3's existing `TrustScorer` subsumes all three designs' new scorers; etc.)

### Conflict-resolution table

| Dimension | [P] picks | [S] picks | [B] picks | Winner | Exit-fit | Roadmap-fit | Commitments-fit | Critic-fit | Sum |
|---|---|---|---|---|---|---|---|---|---|
| Sandbox stack default macOS | DinD | Lima+gVisor (refuses DinD) | DinD | **DinD on macOS, Firecracker on Linux/CI; `gate_isolation_class` annotation** `[synth — honors roadmap]` | 3 | 3 | 2 | 3 | **11** |
| Verdict cache | `GateVerdictCache` (content-addressed) | None | None | **None in Phase 5; ship `sandbox_spec_hash` seam for Phase 9** `[synth — defers]` | 3 | 3 | 3 | 3 | **12** |
| Install→Test node_modules snapshot reuse | Yes | No | No | **No** `[S]+[B]` (critic landed on read-only-mount correctness) | 3 | 3 | 3 | 3 | **12** |
| Phase 3 `TrustScorer` relationship | Replace with `SignalAggregator` | Replace with `ObjectiveSignals` model | Extend (widen signal set) | **Extend Phase 3's TrustScorer; StrictAndGate is a thin adapter** `[B+synth]` | 3 | 3 | 3 | 3 | **12** |
| Signal kind enum shape | Six gate types as Python files | `extra="forbid"` Pydantic (closed) | Closed `Literal["build","tests","trace","policy"]` | **Open registry via `@register_signal_kind`** `[synth — departs from all three]` | 2 | 3 | 3 | 3 | **11** |
| Gate-control process topology | Single orchestrator process | Separate `codegenie-gated` daemon | Single orchestrator process | **Single orchestrator process** `[P+B]` (critic's daemon attack landed) | 3 | 3 | 2 | 3 | **11** |
| Runtime-trace source | strace in-VM + (Linux) eBPF | Host-side eBPF *required* | strace in-VM | **strace in-VM, coverage_ok as soft signal not hard fail** `[B+synth]` | 3 | 3 | 3 | 2 | **11** |
| Test-inventory delta | Not addressed | Hard-fail on any delta ≠ 0 | Not addressed | **`delta < 0` fails strict-AND; `delta > 0` logs but doesn't fail** `[synth — middle path]` | 3 | 3 | 3 | 3 | **12** |
| SAST in Phase 5 | No | Yes (semgrep in rootfs) | No | **No (Phase 12 owns)** `[P+B]` (critic's scope-creep attack on S landed) | 3 | 3 | 2 | 3 | **11** |
| eBPF requirement | Optional | **Required** (macOS = no eBPF = no Phase 5) | None (strace only) | **strace in-VM; eBPF optional Phase 12+** `[B+synth]` | 3 | 3 | 3 | 3 | **12** |
| `--max-attempts-override` flag | Configurable knob | **No override flag** | `--max-attempts-override <int>` + `--operator-ack` | **`--max-attempts-override` + `--operator-ack` + audit event** `[B+P]` (ADR-0014 says configurable) | 3 | 3 | 2 | 3 | **11** |
| Sandbox health probe | None | Daemon-up implicit check | `SandboxHealthProbe` (ADR-0007) | **`SandboxHealthProbe`** `[B]` (critic flagged P for shipping no health probe) | 3 | 2 | 3 | 3 | **11** |
| Firecracker on Linux/CI shape | Hard-pin Firecracker as production target | Required for production isolation | Stub only | **Real impl + one CI smoke test + weekly cron; generates ADR-0019 evidence** `[synth]` | 2 | 3 | 3 | 3 | **11** |
| Env into sandbox | `env: Mapping[str,str]` arbitrary | No env inheritance | `env: dict[str,str]` allowlist in comment only | **Static allowlist enforced in `env_allowlist.py` + CI test on denied substrings** `[S+B+synth]` | 3 | 2 | 3 | 3 | **11** |
| Policy source | Not specified | Digest-pinned in rootfs | In-repo `.codegenie/policy.yaml` (unspecified) | **Digest-pinned `tools/policy/sandbox-policy.yaml` (codegenie-owned, NOT repo)** `[S+synth]` | 3 | 2 | 3 | 3 | **11** |
| Retry feedback transport | `signals` payload as kwarg into Phase 4 | Fence-wrapped truncated error log | `prior_attempts: list[AttemptOutcome]` (Phase 4 not yet verified) | **`prior_attempts: list[AttemptSummary]` (structured, fence-wrapped summary, ADR-P5-002 amends Phase 4 additively)** `[synth]` | 3 | 3 | 3 | 3 | **12** |
| Retry counter authority | Sync coordinator (in-process) | Daemon retry counter (in `codegenie-gated`) | Inside `GateRunner` | **Inside `GateRunner`; ledger is the durable record** `[B]` | 3 | 3 | 2 | 3 | **11** |
| LLM judge persona | No | Deferred to "Phase 5+N" | Deferred to Phase 6/8 | **Deferred; flag as production-design.md gap (no phase actually ships it)** `[synth — surfaces it]` | 2 | 3 | 3 | 3 | **11** |

Tiebreakers: where sums tied, we used critic's recommendation. The verdict-cache row (winner = none) and snapshot-reuse row (winner = no) match the critic's explicit positions. The macOS sandbox row (winner = DiD) honors the roadmap, which the critic flagged as the central conflict.

### Shared blind spots considered

The critic surfaced three quiet agreements. Disposition:

1. **All three accept the patch is copied into the sandbox in full.** None contemplates malicious `.git/hooks/post-checkout`, `package.json#scripts.preinstall`, or `npm run`'s arbitrary script invocation. **Carried forward**: the synthesis accepts this as an acknowledged Phase 5 limit. `--ignore-scripts` blocks install scripts but `npm test` runs scripts by design. The microVM (Firecracker on Linux/CI) is the boundary that absorbs the post-`npm-test`-escape risk. On DiD/macOS, the boundary is weaker and `gate_isolation_class: "shared_kernel"` annotates that fact for Phase 11's review. **Surfaced in §Risks risk-1.**
2. **All three treat `runtime_trace` as a strict gate signal but none calibrates the baseline.** **Departed from**: the synthesis drops `runtime_trace.coverage_ok` from strict-AND and makes it a `confidence: low` annotation. Trace-baseline drift will produce false positives (best-practices' risk-4 noted reviewer fatigue). The Phase 2 baseline refresh path remains an open question for Phase 11.
3. **All three assume Phase 4 accepts the failed-gate error log as a clean retry input.** **Departed from**: the synthesis makes the interface contract explicit via ADR-P5-002. `AttemptSummary` is a Pydantic model with a structured `prior_failure_summary` field, fence-wrapped and canary-checked. The integration test `test_stage6_retry_recovers.py` asserts the Phase 4 prompt actually contains the fence-wrapped summary. Phase 4's contract-snapshot test regenerates (loud).

### Departures from all three inputs

1. **Open signal-kind registry (instead of any closed enum or Literal).** Performance had Python files per gate type but used a `SignalAggregator` with a known signal set; security used `extra="forbid"` Pydantic; best-practices used `Literal["build","tests","trace","policy"]`. The critic flagged all three for violating extension-by-addition (Phase 7 distroless can't add a new signal kind without editing). The synthesis ships an open registry via `@register_signal_kind` decorator — Phase 1's `@register_probe` pattern reused. The `ObjectiveSignals` Pydantic model gets a new optional field per ADR amendment; the decorator registry is the catalog.
2. **`gate_isolation_class` annotation propagated downstream.** None of the three designs ship this. The synthesis introduces it explicitly so Phase 11's merge gate can refuse to auto-promote shared-kernel verdicts and Phase 13's ROI dashboard can segment cost by isolation class.
3. **Test-inventory delta as a *signal*, not a hard fail.** Security made `tests.delta_test_count != 0` a hard fail (forbids legitimate test additions); best-practices and performance didn't address it. The synthesis: `delta < 0` (removed tests) fails strict-AND; `delta > 0` (added tests) is logged but doesn't fail. Phase 11's reviewer sees the delta in evidence.
4. **Firecracker as a real backend with one CI smoke test + weekly cron.** Performance pre-committed Firecracker production targets (premature per ADR-0019); security committed Firecracker + gVisor (two-stack production routing, also pre-empts ADR-0019); best-practices shipped a stub (generates no evidence). The synthesis ships Firecracker as a real backend whose evidence is ADR-0019-grade (cold-start latency, kernel feature requirements, cost per evaluation — Phase 13 collects, Phase 16 resolves).
5. **DiD on macOS is the explicit default; security's Lima requirement is rejected.** The roadmap names DiD as the portable macOS choice; the critic flagged this as the central conflict. The synthesis honors the roadmap and propagates `gate_isolation_class: "shared_kernel"` so downstream phases can read the annotation.
6. **Policy YAML source is digest-pinned `tools/policy/sandbox-policy.yaml`** (codegenie-owned, NOT repo-resident). Security pinned ruleset to digest in the rootfs (closer); best-practices left source unspecified (critic-flagged). The synthesis: explicit constant path, digest-pinned in `tools/digests.yaml`, CI-asserted at startup.

The synthesis also identifies a **production-design.md gap the critic surfaced**: the LLM Judge persona in §3.1's Stage 5 row ("Trust-Aware gate on disagreement") is deferred by all three Phase-5 designs to "Phase 5+N" — but no roadmap phase actually owns it. The synthesis surfaces this as an open question (§ below) for the architect to amend the roadmap, not for Phase 5 to ship.

---

## Exit-criteria checklist

Per roadmap.md Phase 5 entry:

- [x] **"No transform leaves the sandbox unverified."** → `GateRunner.run` is the only entry path from Phase 3 Stage 6; the gate registry's `stage6_validate.yaml` requires build + install + tests + trace + policy + cve_delta signals; the strict-AND adapter calls Phase 3's existing `TrustScorer`. There is no callsite where a transform reaches Stage 7 without `GateOutcome.passed=True`.
- [x] **"Three-retry loop demonstrated end-to-end with at least one case that fails on retry-1 and recovers on retry-2."** → `tests/integration/gates/test_stage6_retry_recovers.py` runs the breaking-change-cve fixture through Phase 4's `FallbackTier.run(... prior_attempts=[...])` and asserts `attempts.jsonl` has 2 entries with distinct `attempt_id`s, distinct `prior_failure_summary`s, distinct `sandbox_run_id`s, and distinct patch bytes. The Phase 4 prompt on attempt 2 demonstrably contains the fence-wrapped prior failure summary.
- [x] **"microVM isolation, build/test/runtime gates."** → Firecracker `FirecrackerClient` (real, KVM-gated) on Linux/CI; DiD `DockerInDockerClient` everywhere else. Six gates registered (build, install, tests, trace, policy, cve_delta). Trace gate uses strace in-VM with diff against Phase 2 baseline.

---

## Load-bearing commitments check

Per `production/design.md` §2:

- **§2.1 No LLM in the gather pipeline.** Phase 5 packages `sandbox/` and `gates/` are added to Phase 0 fence-CI deny-list for `anthropic`, `langgraph`, `chromadb`. CI test enforces. The retry-feedback path passes through Phase 4's `FallbackTier` (which has the LLM) but **only via the structured `AttemptSummary` model** — no raw bytes from the sandbox cross into Phase 4's prompt without Phase 4's existing fence + canary defenses.
- **§2.2 Facts, not judgments.** `ObjectiveSignals` is six structured signals over objective measurements (exit codes, syscall diffs, SBOM diffs, lockfile policy hits). CI introspection test asserts no `confidence`/`llm`/`self_reported`/`model_says` field is reachable. Phase 3's `TrustScorer` consumes the same structured facts.
- **§2.3 Honest confidence.** `SandboxHealthProbe` (Phase 5's B2 analog) surfaces backend unavailability before any gate runs. The `trace.coverage_ok` signal becomes a `confidence: low` annotation rather than a silent pass when strace coverage is suspicious — the gate is honest about what it didn't see.
- **§2.4 Determinism over probabilism for structural changes.** The gate machinery is deterministic. `GateRunner.run` is a `for` loop. `Gate.evaluate` is a pure function over `ObjectiveSignals`. The retry decision tree is three branches. No LLM in any control-flow decision.
- **§2.5 Extension by addition.** **The most-attacked commitment.** The synthesis: Phase 3's `TrustScorer` is **extended**, not replaced, via the `StrictAndGate` adapter; `GateSignal.kind` is an open registry, not a closed Literal; Phase 4's `FallbackTier.run` interface is amended additively with a default-empty `prior_attempts` kwarg; signal kinds register via decorator. Phase 7 distroless will add `BaseImageSignal` + `ShellPresenceSignal` as **new files with `@register_signal_kind` + new optional fields on `ObjectiveSignals`** — no edits to `GateRunner`, no edits to `TrustScorer`, no edits to existing signal collectors. The single ADR-gated additive edit to Phase 3 (`TrustSignal.kind` widening to accept new registered kinds) is captured by ADR-P5-003 with a worked test.
- **§2.6 Organizational uniqueness as data.** Gate definitions are YAML under `gates/catalog/`. Network policy is YAML under `did/network_policy.yaml`. Sandbox policy is digest-pinned YAML under `tools/policy/sandbox-policy.yaml`. Adding a gate variant is a YAML PR + snapshot test.
- **§2.7 Progressive disclosure.** Sandbox runs write `manifest.yaml` + per-step logs under `.codegenie/sandbox/runs/<id>/`. The `remediation-report.yaml` from Phase 3 indexes them by `sandbox_run_id`; logs are not inlined. Three nested directories deep is the ceiling.
- **§2.8 Humans always merge.** Phase 5 still has no `git push`, no GitHub API. The `escalate-to-human` exit (code 11) is the contract Phase 6's `interrupt()` lifts unchanged. `gate_isolation_class` annotation propagates so Phase 11's merge-gate can refuse to auto-promote shared-kernel verdicts.
- **§2.9 Cost is observable end-to-end and bounded.** Every sandbox invocation emits a `cost.sandbox.run` ledger entry. Phase 4's `LlmInvocationGuard` running-total composes across retries. Phase 13 reads both ledgers.

---

## Roadmap coherence check

### What prior phases established that this design depends on

- **Phase 0:** `pyproject.toml`, fence-CI, Click CLI patterns, audit-chain primitive. All preserved.
- **Phase 1:** `Probe` ABC, `@register_probe` decorator, content-addressed cache, schema validation. `SandboxHealthProbe` follows the same shape. The decorator pattern is reused for `@register_signal_kind` and `@register_sandbox_backend`.
- **Phase 2:** `run_in_sandbox` chokepoint, trace baseline, depgraph, security probes. **Phase 5's `SandboxClient` is a new chokepoint specifically for *gate* execution; Phase 2's `run_in_sandbox` continues to serve probe execution.** ADR-P5-001 documents the two-chokepoint shape. The trace baseline persisted by Phase 2's Layer-B trace probe is the input to `collect_trace_signal`.
- **Phase 3:** `TrustScorer` (strict-AND), `RecipeEngine` ABC, `Recipe.engine` Literal, `ApplyContext`, `Transform` ABC, `RemediationOrchestrator`, lockfile policy scanner, audit-chain BLAKE3. **The synthesis extends `TrustScorer` rather than replacing it.** `ApplyContext` gains `prior_attempts: list[AttemptSummary] = []` additively (ADR-P5-002).
- **Phase 4:** `FallbackTier.run`, `RagLlmEngine`, `LeafLlmAgent`, `LlmInvocationGuard`, `FenceWrapper`, `SolvedExampleStore`, `engine_used` discriminator. **`FallbackTier.run` gains `prior_attempts: list[AttemptSummary] = []` additively (ADR-P5-002).** The fence-wrapping pattern Phase 4 already uses for untrusted text is the seam for `prior_failure_summary` in retry context. Phase 4's chain head is the predecessor of Phase 5's first chain entry.

### What this design establishes that later phases will need

- **Phase 6 (LangGraph state machine):** `GateRunner.run` becomes the body of a LangGraph subgraph; the `for` loop maps to recursive node calls; `RetryLedger` lifts unchanged into the Pydantic state ledger; `GateOutcome.escalate` is the signal that triggers `interrupt()`. The `with_prior_attempt`-shaped state mutation is exactly what a LangGraph reducer wants. The critic's roadmap §1 warning (Phase 6 will re-implement the retry loop) is accepted — the *data shapes* survive, the *control flow* gets re-wrapped.
- **Phase 7 (distroless):** New signal collectors (`BaseImageSignal`, `ShellPresenceSignal`) register via decorator; new optional fields on `ObjectiveSignals`; new gate YAML (`distroless_validate.yaml`). The diff for Phase 7 touches only new files plus an ADR amendment widening `ObjectiveSignals` additively. **The critic's roadmap §2 attack on extension-by-addition is addressed by the open registry + open optional-field shape.**
- **Phase 9 (Temporal):** Each `GateRunner.run` invocation becomes a Temporal Activity. `SandboxSpec.sandbox_spec_hash` is the input key for an activity-level idempotency cache (the verdict cache best-practices and security deferred, performance attempted prematurely). The cache's input-key audit follows the lessons the critic surfaced — registry-mirror state, kernel digest, gate-impl source hash must all be in the key.
- **Phase 11 (handoff):** `gate_isolation_class` annotation feeds the merge-gate's auto-promote refusal. Evidence bundles reference `attempts.jsonl` paths. The escalation envelope (exit 11) is what Phase 6's `interrupt()` produces and Phase 11's reviewer UI surfaces.
- **Phase 13 (cost ledger):** `cost.sandbox.run` ledger entries roll up by `(workflow_id, stage, gate_id, gate_isolation_class)`. The per-workflow cap (ADR-0025) reads cumulative `microvm_seconds` + Phase 4's `LlmInvocationGuard` running-total.
- **Phase 16 (production hardening):** ADR-0019 resolves with real evidence from Phase 13. Multi-tenant noisy-neighbor protection lands on top of the existing `cgroups`-only stance. SAST (deferred from Phase 5) lands as a new signal collector via the open registry.

### New ADRs implied by this design

- **ADR-P5-001** — Two-chokepoint sandbox seam: `run_in_sandbox` (Phase 2 chokepoint for probes) and `SandboxClient` (Phase 5 chokepoint for gates) coexist. Stage 6 callsite swap from `validation/*` direct call to `GateRunner.run` is the single orchestrator edit.
- **ADR-P5-002** — Additive extension of `ApplyContext` and `FallbackTier.run` to accept `prior_attempts: list[AttemptSummary] = []`. Phase 3 contract-snapshot test regenerates with the new optional field; Phase 4's prompt builder consumes the fence-wrapped summary on attempt 2+.
- **ADR-P5-003** — Phase 3 `TrustScorer` widening via signal-kind registry. New registered kinds (`trace`, `policy`, `cve_delta`) plus the seam for Phase 7's future kinds. Worked test `tests/integration/test_trustscorer_widening.py`.
- **ADR-P5-004** — macOS dev-loop posture: DiD is the macOS default; `gate_isolation_class` propagates; Lima requirement explicitly rejected. Documents the roadmap-honoring choice.
- **ADR-P5-005** — Phase 4 chain-head compatibility: golden Phase 4 chain head fixture; Phase 5 `RetryLedger` startup test verifies it. Closes critic roadmap §6.
- **ADR-P5-006** — Protocol-vs-ABC convention: structural duck-typed contracts → `Protocol`; concrete inheritance with shared default behavior → `ABC`. Resolves critic's convention-drift attack on best-practices.

### Roadmap gap surfaced (architect should pick up separately)

The **LLM Judge persona** in `production/design.md §3.1` (Stage 5 Validation "on disagreement when objective signals conflict") is **not assigned to any roadmap phase**. All three Phase-5 designs defer it; the synthesis defers it; but no later phase entry mentions it. The architect should either (a) add it to Phase 16 explicitly, (b) amend the roadmap to drop the persona from `design.md`, or (c) introduce a new mid-roadmap phase. This is the critic's roadmap-level §5 attack carried forward as a roadmap-amendment ask.

---

## Open questions deferred to implementation

1. **Firecracker rootfs build cadence.** Daily? Weekly? Per-ADR-bump? The synthesis ships `codegenie sandbox prepare` as a Phase-0-style preflight; the production cadence is a Phase 14 (continuous gather + MCP operationalized) decision.
2. **Trace baseline refresh path.** Phase 11's Stage 7 Learning could absorb merged-PR-induced baseline updates, but the policy (auto-update vs human-curated) is open. Phase 5 ships the diff machinery; the refresh process is Phase 11.
3. **`--allow-test-network` interaction.** Phase 3 introduced `--allow-test-network` as an escalation flag. In Phase 5, does it widen `egress_allowlist` and silence the `trace.new_endpoints` signal, or just widen and leave the signal as informational? Synthesis default: widen + signal stays informational; reviewer sees the addition in evidence.
4. **One YAML catalog or two?** `stage6_validate.yaml` (strict, six signals) and `stage6_validate_loose.yaml` (build+test only, for fast local dev). Best-practices proposed two; the synthesis ships both. The dev-only loose gate's verdicts are annotated `gate_catalog: loose` so Phase 11 can refuse to auto-promote them. (Even though humans always merge, the annotation matters for the evidence bundle's clarity.)
5. **Phase 13 cost-cap interaction with retries.** Three retries × six gates × Phase 4 LLM cost-per-retry can blow ADR-0025's per-workflow cap. Phase 5 emits the ledger; Phase 13 owns the cap. Open question: should `GateRunner` short-circuit on cumulative spend? Synthesis default: no, Phase 13's middleware reads the running total and short-circuits.
6. **Weekly Firecracker cron infrastructure.** A self-hosted KVM runner is required. The synthesis assumes the org has one; the actual provisioning is a Phase 0 operational task that needs an owner.
7. **`AttemptSummary.evidence_paths` retention.** Performance proposed 14-day GC; the synthesis adopts that, but Phase 11's reviewer needs paths to resolve from the eventual PR evidence bundle, which may be reviewed > 14 days post-creation. The synthesis defers the retention policy to Phase 11.
