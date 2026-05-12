# Phase 05 — Sandbox + Trust-Aware gates: Performance-first design

**Lens:** Performance — throughput, latency, token economy, footprint.
**Designed by:** Performance-first design subagent
**Date:** 2026-05-12

## Lens summary

I designed Phase 5 as if the sandbox is the gravity well of the entire system. Phase 5 is where wall-clock goes to die: every transform pays a cold microVM, a `npm ci`, a test suite, an SBOM diff, and a runtime trace before a single token of the next workflow can be spent. At portfolio scale (10s–1000s of repos × ~3 gate evaluations per workflow under the three-retry default of ADR-0014) the gate evaluator is the single biggest CPU sink in the production system and the single biggest source of tail latency. Everything I chose is in service of one thing: **make the sandboxed gate look as close to a cache hit as possible**, and when it is not a hit, share warm state aggressively across consecutive runs in the same workflow.

The two big plays are (1) a **pre-warmed per-fixture rootfs cache** (Firecracker on Linux/CI, Docker-in-Docker on macOS, both behind one `SandboxClient` RPC) so the second-onward gate evaluation in a workflow boots in ~150 ms instead of ~6 s, and (2) a **content-addressed `GateVerdict` cache** keyed on `(patch_blake3, lockfile_blake3, base_image_digest, gate_id, gate_inputs_digest)` so retry-2 and retry-3 hit the cache for any gate whose inputs are byte-identical to retry-1 (which is exactly what happens for *passing* gates after a fix to one node — only the failed gate re-runs). The three-retry default in ADR-0014 is preserved as a config knob, but the cache lets a "retry" be a millisecond decision when only one signal changed.

What I explicitly deprioritized: defense-in-depth beyond ADR-0012's microVM boundary (no nested sandboxes inside the microVM, no per-gate uid jail on top of the kernel boundary, no egress proxy with TLS pinning), operator-experience polish (single CLI flag surface; no interactive gate replay UI in Phase 5), and ironclad "no shared state ever" purism (I deliberately share a *read-only* node_modules layer and a *read-only* base-image cache across gate runs in the same workflow — security can fight me on this in the synth).

## Goals (concrete, measurable)

Targets are aggressive on purpose — the synth will trim. All are p50/p95 against the Phase 3+4 fixture portfolio (small Node service, ~120 unit tests, ~40 MB `node_modules`).

| # | Goal | Target |
|---|---|---|
| 1 | **Workflows/hour per worker** (1 worker = 1 Temporal pod / 1 local process) | ≥ 24 (cold-corpus) / ≥ 90 (warm-corpus with verdict-cache hits on 2 of 3 gates) |
| 2 | **Time-to-PR p95, Phase-5 gate stack only** (the wall-clock added on top of Phase 3/4) | ≤ 65 s warm / ≤ 180 s cold |
| 3 | **Cold microVM boot p95** | ≤ 6.5 s (Firecracker) / ≤ 12 s (DinD on macOS) |
| 4 | **Warm microVM boot p95** (snapshot resume + pre-baked rootfs) | ≤ 200 ms (Firecracker `snapshot-load`) |
| 5 | **Gate-verdict cache hit rate** across a three-retry loop (gates whose inputs are unchanged across retries) | ≥ 60% (target tracked by `gate_verdict_cache_hit_total`) |
| 6 | **Re-run of an identical patch on an identical fixture** (replay) | 100% cache hit; **0 microVM boots**; wall-clock ≤ 1.5 s |
| 7 | **`$/PR` added by Phase 5** | $0 — all-deterministic; no LLM at the gate (ADR-0008 invariant) |
| 8 | **Per-worker steady-state memory ceiling** | ≤ 3.0 GB (orchestrator + 2 concurrent in-flight gates + chromadb mmap from Phase 4 + Firecracker overhead) |
| 9 | **Per-worker concurrent gate slots** | 4 (1 build + 1 install + 1 test + 1 runtime-trace can interleave; cgroup-bounded to 70% of host CPU) |
| 10 | **Tail latency: p99 of any single gate evaluation** | ≤ 240 s (the test-runtime gate dominates; bounded by per-gate timeout) |
| 11 | **`gate_pass_total / gate_invocation_total` over the fixture suite** (efficiency — not a quality metric, a "are we paying for gates that always pass" sanity check) | ≥ 0.85 on the green-path fixtures |
| 12 | **Three-retry loop wall-clock budget** (ADR-0014 cap = 3; failed gate must re-run; passing gates must hit cache, not re-run) | retry-2 ≤ 110% of retry-1 wall-clock; retry-3 ≤ 115% |

These are *my* targets under this lens — they're aggressive against ADR-0019's "Default: Docker-with-seccomp" because I'm committing to Firecracker-on-Linux as the production target inside Phase 5 (synth may roll back to DinD-everywhere; I'll surface the cost of doing so in §Tradeoffs).

## Architecture

```
                      Phase 3/4 RemediationOrchestrator
                                 │
                                 ▼  RecipeApplication (patch on worktree)
                  ┌────────────────────────────────────────────────────┐
                  │  src/codegenie/gates/coordinator.py                 │
                  │  GateCoordinator.run_with_retries(application, 3)   │
                  │   - reads/writes Pydantic GateLedger (in-memory)    │
                  │   - drives the three-retry policy (ADR-0014)        │
                  └──────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
         ┌───────────────────────────────────────────────────────────┐
         │  GateVerdictCache (content-addressed, Phase-1 cache reuse)│
         │   key = blake3(patch || lockfile || base_image_digest ||  │
         │                gate_id || gate_inputs_digest)             │
         │   value = GateVerdict { passed, signals, evidence_paths } │
         │   cold hit → skip the entire gate; emit cache.replay event│
         └──────────────┬────────────────────────────────────────────┘
                        │ miss
                        ▼
         ┌───────────────────────────────────────────────────────────┐
         │  GateExecutor — runs one gate inside one microVM           │
         │   - Build gate                                              │
         │   - Install gate (npm ci --ignore-scripts)                  │
         │   - Test gate (npm test, network=none + escalation signal) │
         │   - Policy gate (LockfilePolicyScanner + Prove-It asserts) │
         │   - RuntimeTrace gate (C4 from Phase 2 — lands here)        │
         │   - CVE delta gate (post-patch grype vs pre-patch baseline)│
         └──────────────┬────────────────────────────────────────────┘
                        │
                        ▼
         ┌───────────────────────────────────────────────────────────┐
         │  SandboxClient — single RPC surface (ADR-0012 §39)         │
         │    .exec(rootfs_id, argv, env, copyin, copyout, timeout)   │
         │    .snapshot(vm_id) / .resume(snapshot_id)                 │
         │   Selects backend by env:                                  │
         │    - FirecrackerBackend (Linux/CI; KVM detected)           │
         │    - DockerInDockerBackend (macOS; no KVM)                 │
         └──────────────┬────────────────────────────────────────────┘
                        │
                        ▼
         ┌───────────────────────────────────────────────────────────┐
         │  RootfsCache + WarmPool                                    │
         │   - Pre-baked OCI rootfs per (base_image_digest,           │
         │     node_major, fixture_class) — built once per CI day     │
         │   - WarmPool keeps N=4 snapshots resumed-and-paused        │
         │   - Snapshot reuse across gates in the *same workflow*     │
         │     (same patch → same node_modules layer can be shared    │
         │     read-only between Install and Test gates)              │
         └──────────────┬────────────────────────────────────────────┘
                        │
                        ▼
         ┌───────────────────────────────────────────────────────────┐
         │  SignalAggregator                                          │
         │   - reads sandbox copyout artifacts (build.log, junit.xml, │
         │     grype.json, trace.jsonl)                               │
         │   - emits TrustSignals (objective-only, ADR-0008)          │
         │   - feeds back into GateLedger                             │
         └───────────────────────────────────────────────────────────┘

  On-disk layout under .codegenie/ (extends Phase 3/4 layout):
   .codegenie/
     gates/
       verdict-cache/<gate-id>/<key-prefix>/<sha256>.json    ← Tier-0 cache
       rootfs/<base_image_digest>/<node_major>.ext4          ← pre-baked rootfs
       snapshots/<rootfs_digest>/<seed>.snap                 ← Firecracker mem-snap
       ledger/<run-id>.jsonl                                 ← per-run ledger
       evidence/<run-id>/<gate-id>/                          ← copy-out artifacts
     audit/<run-id>.jsonl                                    ← BLAKE3-chained (Phase 2/3)

  Package additions on top of Phase 3/4:
  src/codegenie/
    gates/                  ← NEW
      __init__.py
      models.py             ← GateInputs, GateVerdict, TrustSignals, GateLedger
      coordinator.py        ← GateCoordinator (three-retry loop, ADR-0014)
      executor.py           ← GateExecutor (one gate × one microVM)
      cache.py              ← GateVerdictCache (content-addressed)
      signals.py            ← SignalAggregator (objective only)
      registry.py           ← registered gate types; @register_gate decorator
      types/
        build.py
        install.py
        test.py
        policy.py
        runtime_trace.py   ← finishes C4 deferred from Phase 2
        cve_delta.py
    sandbox/               ← NEW (the ADR-0012 chokepoint package)
      __init__.py
      contract.py          ← SandboxClient ABC + RPC dataclasses
      firecracker.py       ← FirecrackerBackend (Linux/CI)
      dind.py              ← DockerInDockerBackend (macOS)
      rootfs.py            ← RootfsBuilder + RootfsCache
      warmpool.py          ← snapshot warm pool
      copyio.py            ← copy-in/copy-out helpers (no shared mounts)
```

## Components

### `SandboxClient` (`src/codegenie/sandbox/contract.py`)
- **Purpose:** The single chokepoint between gate logic and any sandbox stack. Same contract regardless of Firecracker / DinD / future gVisor. Phase 2's `run_in_sandbox` (bwrap/sandbox-exec) is preserved for *probe* execution; this is a new, *additional* chokepoint specifically for *gate* execution, because gate workloads run untrusted patched code and need a strictly stronger boundary (ADR-0012 §39).
- **Interface:**
  - `exec(rootfs_id: RootfsId, argv: list[str], env: Mapping[str,str], copyin: Mapping[Path, bytes], copyout_globs: list[str], timeout_s: int, network: Literal["none","scoped"]) -> SandboxRunResult`
  - `snapshot(vm_id: VmId, name: str) -> SnapshotId`
  - `resume(snapshot_id: SnapshotId) -> VmId`
  - `dispose(vm_id: VmId) -> None`
  - Errors: `SandboxBootFailed`, `SandboxTimeout`, `SandboxBackendUnavailable`, `CopyOutMissing`.
- **Internal design:** Backend selection at process start by KVM/`/dev/kvm` capability probe + env override (`CODEGENIE_SANDBOX_BACKEND=firecracker|dind`). Firecracker backend uses `jailer` + a pre-baked kernel image (`tools/firecracker/<digest>/vmlinux.bin`) + the rootfs from `RootfsCache`. DinD backend wraps `docker run --rm --network=none --cap-drop=all --security-opt=no-new-privileges` against a slim image baked the same way. **No host volume mounts ever** — copy-in/copy-out only, even on DinD (we accept the throughput hit for backend parity). The RPC is sync — gates are coarse-grained; async overhead isn't worth the complexity at this layer.
- **Tradeoffs accepted:** Two backends to maintain (CI parity vs dev-on-macOS). DinD path is slower (no microVM snapshot reuse). I'm betting Phase 5 ships on Linux/CI as the hot path and macOS is the dev-loop only — Firecracker is what the production target hits, and the perf numbers in §Resource & cost profile assume Firecracker. ADR-0019 is *not* resolved by this design; I commit to Firecracker as the *Linux backend* and DinD as the *macOS backend* without claiming the synthesis must keep them.

### `RootfsCache` + `WarmPool` (`src/codegenie/sandbox/rootfs.py`, `warmpool.py`)
- **Purpose:** Eliminate the cold-boot cost on the second-onward gate evaluation. ADR-0012 §32 notes Firecracker cold start is ~100 ms in theory but the *useful* cold start (kernel + rootfs + npm + node) is several seconds. We make that one-time per `(base_image_digest, node_major, fixture_class)`.
- **Interface:**
  - `RootfsBuilder.bake(base_image_digest, node_major, fixtures: list[FixtureSpec]) -> RootfsId` — produces an `.ext4` image with Node, npm, pinned-version `ncu`, and a pre-populated `~/.npm` cache for the registry mirror.
  - `RootfsCache.get_or_bake(...)` — content-addressed lookup under `.codegenie/gates/rootfs/`.
  - `WarmPool.acquire(rootfs_id) -> VmId` — pops a pre-resumed paused VM; refills the pool in the background; on miss, falls back to cold boot.
- **Internal design:** Pre-bake runs once per CI day as a Phase-0-style preflight (`codegenie gates prepare`). The bake pulls the base image, installs Node, runs `ncu --version` to warm caches, and snapshots an `.ext4`. The warm pool is sized N=4 — enough to cover the three-retry × interleaved-gates case on a single worker. Pool refills off the critical path. **The `node_modules` layer for one workflow's `npm ci` result is *also* snapshotted after the Install gate succeeds**, and the Test gate resumes from that snapshot — so Install + Test share state, saving ~10–25 s of redundant `npm ci`.
- **Tradeoffs accepted:** Disk usage. A rootfs is ~200 MB; with 6 base images × 3 node majors = ~3.6 GB of `.ext4` files per worker. Snapshots add ~50–150 MB each. Storage growth rate documented in §Resource & cost profile. Security: sharing a `node_modules` snapshot across Install→Test gates within one workflow is *intentional*. Different workflows never share — the snapshot is keyed on `(patch_blake3, lockfile_blake3)`. Security-first will object; my answer is that the patch is already known and the snapshot is read-only inside the Test VM.

### `GateVerdictCache` (`src/codegenie/gates/cache.py`)
- **Purpose:** Make retries cheap when only one gate changed. Three-retry loop (ADR-0014) is a *requirement*; what I'm optimizing is the cost of the *passing* gates inside that loop, which should be ~0.
- **Interface:**
  - `get(key: GateCacheKey) -> GateVerdict | None`
  - `put(key: GateCacheKey, verdict: GateVerdict, evidence_dir: Path) -> None`
  - `key_for(application: RecipeApplication, gate_id: str, inputs_digest: bytes) -> GateCacheKey`
- **Internal design:** Cache key is `blake3(patch_blake3 || lockfile_blake3 || base_image_digest || gate_id || sorted_serialized(gate_inputs))`. Cache value persists evidence path so the Trust-Aware decision is auditable on cache hit. Cache invalidation: never automatic — if any input changes, the key changes, the cache misses. Cache hits emit an `audit.cache_replay` event referencing the original BLAKE3-chained audit entry (Phase 2/3 chain extends).
- **Tradeoffs accepted:** Stale-cache risk if a gate's *internal* logic changes without its `gate_id` being bumped. I close this by including the gate implementation's source-hash (`src/codegenie/gates/types/<gate>.py` blake3) in the cache key. CI test asserts the cache key changes if the file changes by one byte.

### `GateCoordinator` (`src/codegenie/gates/coordinator.py`)
- **Purpose:** Implement the ADR-0014 three-retry loop. Plus: dispatch passing-gates-from-cache before booting any VM.
- **Interface:**
  - `run(application: RecipeApplication, *, max_retries: int = 3) -> GateLedger`
  - Errors: `AllRetriesExhausted` (caller decides escalation — Phase 5 doesn't open PRs; Phase 11 does).
- **Internal design:** Single pass:
  1. For each gate in the registry, compute the cache key. If hit → record verdict in ledger; do not boot a VM.
  2. For each missed gate, dispatch to `GateExecutor.run(gate, application)` in a bounded asyncio pool (4 concurrent slots; cgroup-pinned). The gates are mostly independent (Build → Install → Test is a chain; Policy and CVE-delta are parallel to Build).
  3. Aggregate verdicts. If *any* gate failed, retry-loop logic kicks in:
     - retry_n ≤ max_retries: re-invoke upstream planner (Phase 4 `FallbackTier`) with the failure signals as context. Get a new `RecipeApplication`. **Recompute cache keys** — passing gates whose inputs didn't change hit cache; only the failed gate's downstream re-executes.
     - retry_n > max_retries: emit `gate.three_retry_exhausted` audit event; return ledger with `escalation_required=True`. Phase 6's `interrupt()` lands on this signal.
- **Tradeoffs accepted:** Coordinator stays sync-with-bounded-async-fan-out — no LangGraph here (that's Phase 6). I'm intentionally not pre-shaping this as a LangGraph node so Phase 5 can ship locally without `langgraph` in the gate path. Phase 6 will wrap `run()` as a single graph node and add `interrupt()`. This keeps Phase 5 boot-loop-fast in tests.

### `GateExecutor` (`src/codegenie/gates/executor.py`) and gate types (`src/codegenie/gates/types/*`)
- **Purpose:** One gate, one microVM, one verdict. Same interface for build / install / test / policy / runtime-trace / cve-delta.
- **Interface:**
  - `Gate` protocol with `id: str`, `applies(application) -> bool`, `inputs_digest(application) -> bytes`, `run(application, sandbox: SandboxClient) -> GateVerdict`.
  - Each gate's `run()` returns `GateVerdict(passed: bool, signals: dict[str, Signal], evidence_paths: dict[str, Path])`.
- **Internal design:** Each gate copies in only the *minimal* file set it needs (patch + lockfile + Dockerfile for Build; whole worktree for Install; built artifact for Test; SBOMs for CVE-delta), and copies out only its evidence artifacts. **Test gate** uses the `--network=none` + escalation-signal pattern Phase 3 set up — preserved verbatim. **RuntimeTrace gate** is C4 from Phase 2, deferred until Phase 5 because it needs the microVM stack. **CVE-delta gate** runs grype against the pre-patch SBOM (from Phase 2 cache) and the post-patch SBOM (rebuilt inside the gate VM), asserts non-positive direction (ADR-0008 signal).
- **Tradeoffs accepted:** Six gates is more than ADR-0012's "build + tests + policy + trace" list. CVE-delta is split out because it has a different cache-key shape (depends on the grype vuln-DB digest, not the patch). I'd rather have one more gate with a clean cache key than fewer gates with mixed-source caches.

### `SignalAggregator` (`src/codegenie/gates/signals.py`)
- **Purpose:** Convert raw gate artifacts → `TrustSignals` consumed by the Phase-3 `TrustScorer` (which already exists, strict-AND of objective signals only per ADR-0008).
- **Interface:** `aggregate(ledger: GateLedger) -> TrustSignals`. Strict-AND.
- **Internal design:** Pure function over the ledger. No I/O beyond reading evidence files. **LLM self-confidence never enters here** — ADR-0008 is enforced by *not having an interface to receive it*. The aggregator's input type literally cannot carry self-confidence.
- **Tradeoffs accepted:** Strict-AND is conservative — one failing signal fails the gate. I deliberately do not implement ADR-0015's weighted-trust-score (that's deferred until production data exists). The Phase-5 default is the same as Phase 3's binary-conservative.

## Data flow

One representative end-to-end run — vuln-remediation workflow, fixture repo with a known npm CVE, **second invocation of the same fixture (warm path)**, three-retry loop where retry-1 fails on Test gate but retry-2 passes:

1. **Entry.** Phase 4 `RemediationOrchestrator` reaches Stage 6 (`Validate`). Phase 5's `GateCoordinator.run(application, max_retries=3)` takes over.
2. **Cache lookups, parallel.** For each registered gate (Build, Install, Test, Policy, RuntimeTrace, CVE-delta), the coordinator computes the cache key from `(patch_blake3, lockfile_blake3, base_image_digest, gate_id, inputs_digest, gate_impl_hash)`. Five hits (this is a warm-corpus run of the same patch we've seen before), one miss (RuntimeTrace is new — first time we've enabled it for this fixture).
3. **Verdict-cache replay.** The five hits emit `audit.cache_replay` events referencing the original chained-audit entries. *No microVM is booted for these five gates.* Wall-clock for this step: ~30 ms total.
4. **RuntimeTrace gate dispatch.** `GateExecutor.run(runtime_trace_gate, application)`:
   1. `WarmPool.acquire(rootfs_id)` — pops a pre-resumed paused VM (200 ms). Pool refill happens in background.
   2. Copy-in: the patch worktree + the test entrypoint. (~5 MB; ~80 ms over the vsock.)
   3. `sandbox.exec(rootfs, ["node", "--inspect=0", "entrypoint.js"], network="none", timeout_s=30)` — `strace`/eBPF captures syscalls; output written to `/tmp/trace.jsonl`.
   4. Copy-out: `trace.jsonl` (~200 KB; ~10 ms).
   5. Aggregator reads trace; asserts no new shell invocations vs Phase 2 baseline; verdict = pass. Wall-clock for this gate: ~6.5 s (dominated by the entrypoint's own startup).
5. **First aggregation.** `SignalAggregator.aggregate(ledger)` — strict-AND across six gates. All pass. Return `GateLedger(passed=True, retry_count=0)`. **Done.** Total Phase-5 wall-clock for warm run: ~7 s.

Now imagine the **cold-path retry case** — same workflow, first time, retry-1 fails on Test:

1. Cold cache lookups — all six miss.
2. Build gate runs first (chain). Cold boot 6 s; build itself 18 s; verdict cached.
3. Install gate. Cold boot? No — we resume the snapshot from Build (same base image), 200 ms. `npm ci --ignore-scripts` 22 s. **Snapshot taken** of post-install state.
4. Test gate. Resume from Install snapshot (200 ms). `npm test` 35 s — **one test fails** (the patched dep broke a callsite). Verdict: fail. Test evidence cached *as a fail*.
5. Policy + RuntimeTrace + CVE-delta run in parallel to Build/Install/Test where dependencies allow — Policy passes against the lockfile; RuntimeTrace passes; CVE-delta passes.
6. `SignalAggregator` returns `passed=False`. Coordinator's retry-1 begins: re-invokes Phase 4 `FallbackTier` with `signals.test_failure` payload. FallbackTier returns a new `RecipeApplication` (different patch — different `patch_blake3`).
7. Cache re-lookup against the new key. **Policy and CVE-delta keys haven't changed** (lockfile, advisory, vuln-DB digest all unchanged) → cache hit. Build, Install, Test re-execute (their keys did change). Build 18 s, Install 22 s (snapshot reuse path *is broken* across patches — no node_modules sharing across patches; that's correct), Test 35 s — passes this time.
8. Aggregator returns `passed=True, retry_count=1`. **Done.** Total Phase-5 wall-clock for cold + retry-1-fail + retry-2-pass: ~152 s.

Parallelism is extracted at: (1) cache lookups for all gates (free), (2) gates with no upstream dep run concurrently in a 4-slot pool, (3) WarmPool refill is background, (4) copy-in/out is concurrent with VM bring-up where the API permits. Serialization is forced at: (1) Build → Install → Test chain (real data dependency), (2) the retry loop itself (ADR-0014 requires sequential retries — the new patch must see the prior failure signals).

## Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| Firecracker `vmlinux` mismatch (rootfs built against newer kernel) | `SandboxClient.exec` returns `SandboxBootFailed` | `RootfsCache` marks key invalid; rebuilds; one-time slow run; emits `gate.rootfs.rebake` audit event |
| WarmPool empty (refill not done in time) | `WarmPool.acquire` cold-boot fallback | Cold boot path; emits `gate.warmpool.miss` counter; pool size auto-bumps next workflow (capped at 8) |
| Snapshot resume corrupts (rare; Firecracker race) | Post-resume `uname -a` health check | Discard snapshot; cold-boot; mark snapshot file deleted; emits `gate.snapshot.corrupt` |
| Test gate timeout (test suite > p99 budget) | `SandboxClient` per-gate `timeout_s` | Treat as failure; aggregator marks `tests.exit_status != 0`; coordinator triggers retry-1 with `signal.test_timeout` context |
| `npm ci` egress (workflow tries to phone home through scoped allowlist) | `network="none"` for test gate; install gate uses `network="scoped"` to `registry.npmjs.org` only; egress to anything else fails inside the VM | Verdict = fail; `signals.disallowed_egress_bytes > 0`; aggregator strict-AND fails |
| Verdict cache poisoning (someone hand-edits a cached JSON) | Cache load verifies BLAKE3 over the value bytes against a chained-audit entry | Cache entry rejected; gate re-runs; emits `gate.cache.tamper_detected` |
| Three-retry exhaustion | Coordinator's retry counter | Returns `GateLedger(escalation_required=True)`; Phase 6 wraps with `interrupt()`; Phase 11 surfaces in PR review; no auto-merge |
| RuntimeTrace gate sees new shell invocation (regression) | Trace-diff against Phase 2 baseline | Gate fails; `signals.new_shell_invocations > 0`; the retry path is the same as test failure — Phase 4 replans |
| CVE-delta direction positive (patched code adds a new vuln) | grype diff post vs pre | Gate fails; Phase 4 replans; if retry exhaustion, escalates |
| Sandbox stack unavailable at startup (Docker daemon down on macOS) | `SandboxClient.__init__` capability probe | Fails loud; CLI exits non-zero with install hint; **never silently falls back to host exec** |

The orchestrator never catches `SandboxClient` errors and converts them to "passed" — there is no path through the code where a gate failure becomes a gate pass.

## Resource & cost profile

Concrete numbers — order-of-magnitude OK; the Phase-5 fixture portfolio drives them.

- **Tokens per run:** **0.** Phase 5 has no LLM. ADR-0008 forbids LLM self-confidence at the gate. The CVE-delta gate uses grype; the RuntimeTrace gate uses strace/eBPF. There is no place a token is spent at this layer. (LLM tokens are spent at Phase 4's `FallbackTier` *between* retries — Phase 4's token budget applies, not Phase 5's.)
- **Wall-clock per run:**
  - **p50 warm (verdict cache hits on 4 of 6 gates):** ~22 s — dominated by the two cold gates × ~10 s each.
  - **p50 cold, retry-0 pass:** ~85 s — Build 18 + Install 22 + Test 35 + parallel Policy/Trace/CVE-delta ~10 + boot/copy overhead ~ 5–8.
  - **p95 cold + one retry:** ~165 s.
  - **p99 (test-suite outlier on large fixture):** ~240 s.
- **Memory per worker:** ~3.0 GB ceiling. Breakdown: orchestrator 200 MB + chromadb mmap (Phase 4) 400 MB + 2 concurrent active VMs × 1 GB each (Firecracker memory size for Node-app gates) + RootfsCache mmap overhead 150 MB + buffers 200 MB.
- **Storage growth rate:** ~3.6 GB per worker for rootfs cache (6 base images × 3 node majors). Verdict cache grows ~50 KB per gate evaluation; with ~6 gates × 1000 workflows = ~300 MB per 1000 workflows. Evidence dirs ~5 MB per workflow → ~5 GB per 1000 workflows; documented retention is 14 days then GC.
- **Hot vs cold cost ratio:**
  - Cold microVM boot (Firecracker, including rootfs mount): ~6 s.
  - Warm microVM boot (snapshot resume): ~200 ms.
  - **Ratio: 30×.** This is what the WarmPool buys.
  - Cold verdict cache: 0 ms (cache miss is free; the cost is the gate that follows).
  - Warm verdict cache hit (cached gate): ~5 ms (read JSON + verify BLAKE3 + emit replay audit event). **Ratio versus running the gate: ~5000×.** This is what the verdict cache buys.
- **Throughput:** With 4 concurrent gate slots and ~85 s p50 cold runs, a single worker sustains ~24 cold workflows/hour, ~90 warm. At 10 workers, that's 240 → 900 workflows/hour — comfortably inside the portfolio-scale headroom.

## Test plan

What "this design passes its tests" means concretely, with the canary regression in §Performance regression tests at the bottom.

**Unit tests:**
- `SandboxClient.exec` against a stub backend that simulates boot/copy/exec/copyout, with golden timing assertions.
- `GateVerdictCache.key_for` — byte-stable across runs; cache key changes if any input byte changes (one parametrized test per input).
- `SignalAggregator.aggregate` — exhaustive truth-table tests over signal combinations; strict-AND assertion is the canonical test.
- Each gate type has a unit test against a synthetic `RecipeApplication` and a mocked `SandboxClient`.

**Integration tests (slow, opt-in `-m gates_integration`):**
- Real Firecracker on a Linux CI runner (KVM-capable): cold-boot one VM, exec a trivial command, copy out, assert wall-clock < 8 s.
- DinD on macOS: same flow, assert < 15 s.
- The exit criterion test: a fixture repo where retry-1 deliberately fails (the patch introduces a callsite break) and retry-2 (a different planner output) passes. This is the ADR-0014 demonstration.

**Property tests:**
- For every possible combination of objective signals (the input space is small — ~10 binary signals = 1024 combinations), the `SignalAggregator` output is asserted. This is hypothesis-driven.

**Snapshot tests:**
- `SandboxClient` RPC contract is frozen at v0.5.0 with a snapshot test (Phase 9 must not break this; Phase 16 may evolve it).
- `GateVerdict` schema is frozen.

**Performance regression tests (the canary):**
- A dedicated `tests/perf/` suite runs against a frozen fixture and asserts:
  - Cold cold microVM boot ≤ 8 s (Firecracker on CI runners).
  - Warm snapshot resume ≤ 250 ms.
  - End-to-end Phase-5 wall-clock for the canary fixture's three-gate pass: p95 ≤ 95 s, asserted with `pytest-benchmark`.
  - Verdict-cache hit rate over the fixture suite ≥ 60%.
- These are CI-gated. Performance regression breaks the build. The regression test is the contract Phase 8 (planner) and Phase 9 (Temporal) must not violate.

## Risks (top 5)

1. **Firecracker hard-pin on Linux/CI is a partial pre-emption of ADR-0019.** ADR-0019 is explicitly deferred. I am building one stack (Firecracker) on the assumption Phase 16 will keep it. If ADR-0019 picks gVisor or nested QEMU, the WarmPool/snapshot model changes (gVisor has no "snapshot" primitive of the same shape). The `SandboxClient` interface absorbs the change — but the *performance* characteristics shift. **Mitigation:** the contract is intentionally narrow (no snapshot in the public interface — `snapshot`/`resume` are backend-specific extensions); the WarmPool degrades to cold-boot mode if the backend lacks snapshot support. The targets in §Goals are then unachievable on non-Firecracker backends — surfaced as an explicit perf hit in the ledger.

2. **Snapshot reuse across Install→Test in the same workflow is a security position the synth will challenge.** Sharing the post-`npm ci` node_modules state read-only between gates is a real perf win (saves 15–25 s on the Test gate) but it does cross the "every gate starts clean" line from ADR-0012 §33. **Mitigation:** read-only mount; same workflow only; same patch_blake3 only; documented as a synth-level decision to escalate. If synth rejects, the cost is +20 s on the cold test-gate path — degrades p95 from ~85 s to ~105 s but does not threaten the workflows/hour target.

3. **Verdict cache poisoning if the gate implementation hash isn't included correctly.** If we forget to bump the cache key when a gate's logic changes, we serve stale verdicts. **Mitigation:** the cache key includes `blake3(open(gates/types/<gate>.py, "rb").read())`. A CI test asserts a one-byte change to any gate file changes the cache key. Plus: cache entries are BLAKE3-chained into the existing audit log; tamper-detection is invasive.

4. **`pytest-docker` (named in the roadmap) is slow on CI runners without KVM acceleration.** macOS CI runners on GitHub Actions are notoriously slow at DinD. **Mitigation:** macOS CI runs only the contract-level tests against a stub backend; the heavy integration tests are Linux-only with KVM. The Phase-0 `fence` job is extended to fail loudly if a Linux CI runner reports `/dev/kvm` missing (means we'd silently fall back to slow DinD-on-Linux).

5. **WarmPool starvation under burst load.** If 10 workflows fire simultaneously and the pool size is 4, the 5th–10th workflows pay cold boot. **Mitigation:** pool size is per-worker; horizontal scale is the answer. At 10 workers × 4 pool slots = 40 warm slots. The pool refill is async and amortized — burst of 10 within a worker takes pool-size cold boots upfront then warms again. Auto-resize raises pool size up to 8 if cold-boot rate exceeds 20% of acquisitions in a 5-minute window.

## Acknowledged blind spots

What this lens deprioritized — the synthesizer should weigh these against the security and best-practices designs:

- **No defense-in-depth inside the microVM.** I'm relying on ADR-0012's microVM boundary as *the* boundary. No bwrap inside the VM, no seccomp profile narrower than the default, no uid jail, no per-syscall allowlist. The security-first design will add layers here. My counter-argument is that the marginal isolation past Firecracker isn't free at gate-evaluation throughput and the microVM is already the strongest practical boundary; I will accept the synth adding a thin seccomp profile if it costs < 50 ms per gate.

- **No egress proxy with TLS pinning.** Install gate egress goes to `registry.npmjs.org` directly with deny-all-else firewall rules; CVE-delta hits the grype DB on cache miss. I am not running an HTTPS-MITM proxy for fine-grained allowlisting (security-first will). The cost of running an mitmproxy + cert injection adds ~150 ms to each network-using gate; I'd rather catch supply-chain attacks with SBOM diff + lockfile policy scan (already in Phase 3).

- **No interactive replay / debug UI.** Failed gates dump evidence to `.codegenie/gates/evidence/<run-id>/<gate-id>/` and that's it. The best-practices lens will probably want a `codegenie gates replay <run-id>` command and a Mermaid timeline view — I deferred those to a Phase 13 (AgentOps) follow-up because they don't move the perf numbers.

- **No fine-grained gate-level cost attribution.** I emit `cost.gate.*` events for the Phase-13 cost ledger but I do not segment microVM lifecycle cost vs in-VM build/test cost. Phase 13 will refine. I bet the dominant term is in-VM compute and that segmenting earlier is over-engineering.

- **Test gate's `--network=none` default + "needs network" escalation signal is preserved from Phase 3.** I did not enrich it. The security-first design may want a stricter "no escalation allowed" stance; the best-practices design may want an op-doc'd allowlist. I'm with Phase 3's synth: signal-escalate, never silently allow.

- **No multi-tenant noisy-neighbor protection beyond cgroups.** Two workflows on the same worker share the host kernel's I/O scheduler and the L3 cache. I have not added I/O throttling or per-workflow CPU pinning. Phase 16's production hardening picks this up.

- **No microVM image signing / supply chain verification.** The rootfs `.ext4` files are content-addressed but not signed. A determined attacker with write access to `.codegenie/gates/rootfs/` could swap one. The audit chain notices, but post-hoc. Security-first will demand `cosign`-signed rootfs images; I deferred.

## Open questions for the synthesizer

1. **Snapshot reuse Install→Test (same workflow, same patch, read-only):** keep, or reject for clean-room consistency with ADR-0012 §33? My ask: keep with explicit documentation; the perf delta is real and the isolation argument is weak (same patch, same VM kernel, read-only mount).

2. **Firecracker-on-Linux + DinD-on-macOS** vs **DinD-everywhere for Phase 5** (deferring Firecracker until Phase 14): my preference is the former because Phase 9's Temporal worker pods run on Linux and the production target should land on Firecracker before Phase 10 puts portfolio-scale load on the gate layer. ADR-0019's "no default committed" lets me pick. Synth call.

3. **Verdict cache scope:** local-disk only (my choice), or shared across workers via the same chromadb/Postgres that Phase 4 and Phase 9 introduce? Local is simpler and saves a network roundtrip; shared compounds savings at portfolio scale. I deferred to local for Phase 5, but the synth could pull a Redis-backed shared cache forward from Phase 8's hot-views work.

4. **Three-retry policy** (ADR-0014): my coordinator drives the retry loop synchronously. Should Phase 5 already shape this as a LangGraph node so Phase 6 is a no-op wrap? My answer was no — `langgraph` import is heavy and Phase 5's tests run faster without it. But the Phase-6 design may need this earlier. Critic will probably push back.

5. **Pre-bake authority:** who owns the `tools/firecracker/<digest>/vmlinux.bin` and the per-base-image rootfs builds? My design says a Phase-0-style preflight; in production this is a Phase 14 / Phase 16 concern (CI image pipelines). Phase 5 ships the build script but not the production scheduling. Synth should confirm.

6. **Cold-start budget vs ADR-0019 deferral:** I'm asserting Firecracker delivers ~6 s cold boot, ~200 ms snapshot resume for our payload shape. ADR-0019 explicitly says "evidence needed: cold-start latency tolerance." This design is *generating* that evidence (the perf regression tests are the gating data). Synth should affirm that running the experiment is acceptable Phase-5 work, not premature optimization.
