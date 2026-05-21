# Phase 7 — Add migration task class (Chainguard distroless): Final design

**Status:** Design of record (synthesized from three competing designs + critique).
**Synthesized by:** Graph-of-Thought synthesizer subagent
**Date:** 2026-05-19
**Sources:** `design-performance.md` · `design-security.md` · `design-best-practices.md` · `critique.md`

---

## Lens summary

The synthesis takes **best-practices' package shape, idiomatic registry seams, and "no-framework" assembly function** as the skeleton; pulls **security's microVM isolation for `ShellInvocationTraceProbe`, Dockerfile policy gate, and SBOM cross-verifier** for the trust boundary; and lifts **performance's content-addressed cache key topology and `dockerfile-parse` recipe engine choice** for the hot path — while explicitly rejecting performance's SQLite `vuln_provenance_cache` (per ADR-0038 deferral), performance/security's `MultiPluginCoordinator` (per ADR-0042 — Phase 8's job), and security's Chainguard STS/token apparatus (per critic — Chainguard distroless images are public). The synthesis **departs from all three** on six axes the critic landed:

1. **No `MultiPluginCoordinator` ships in Phase 7.** Phase 7 emits `Both` provenance + a typed `RequiresCoordination` event into the event log and stops. The actual sequencing, partial-application semantics, child-workflow fan-out, and PR-ordering policy belong to Phase 8's Planner per ADR-0042. This is the load-bearing critic finding and it overrides both performance and security.
2. **`ShellInvocationTraceProbe` is `runs_last=True, heaviness="heavy"` and executes the target-repo build inside the Phase 5 microVM stack** — adopting security's threat-model framing. It is *not* a reducer over Phase 2 output (performance was wrong: Phase 2 ships no runtime-trace artifact today), and it is *not* a `dive`+`strace` wrapper in a "Phase-2-shaped sandbox" (best-practices invented a sandbox tier that doesn't exist). The probe reuses Phase 5's existing `SandboxClient` with a new `role="probe"` parameter — added additively to Phase 5's spawn API under a Phase 7 ADR amendment, not a parallel `probe-control` process.
3. **`vuln.provenance` ships uncached in Phase 7** per ADR-0038 §Tradeoffs. No SQLite cache, no LRU, no `vuln_provenance.sqlite`. Phase 14 owns caching when portfolio-scale load justifies it. ADR-0038 is not amended.
4. **"Additive" is defined as `no byte-edit to existing plugin code or stable existing module bodies`** — wiring lines (one `import` in `src/codegenie/__init__.py`, one `$ref` insertion in the envelope schema, one `requires:` line in Phase 3's `tccm.yaml`, one row in `ALLOWED_BINARIES`) ARE byte-edits and are explicitly enumerated in a Phase 7 ADR-anchored allowlist on `tests/fence/test_kernel_frozen.py`. The fence test fails if a Phase 7 PR touches anything outside that allowlist.
5. **The new probes ship under the plugin (`plugins/distroless-migration--node--npm/probes/`), not under `src/codegenie/probes/`.** ADR-0031 is explicit: plugins contribute probes. Best-practices' placement in `src/codegenie/probes/layer_c/` and `layer_d/` is rejected — it would entrench a precedent that future task classes' probes live in the kernel tree. The `@register_probe` decorator + explicit-import collection at `src/codegenie/plugins/loader.py` still discovers them.
6. **`NpmVulnProvenanceAdapter` lives in the Phase 3 plugin (`plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py`) as a wholly-new file**, not re-exported from the Phase 7 plugin (rejects performance's inverted-dependency story) and not "promoting" anything (Phase 3 ships no `NpmVulnProvenanceAdapter` to promote — only a refuse-mode shape per ADR-0038 Consequences). The fence allows this *exact* new file path; nothing else under that plugin moves.

One non-obvious carry-forward: the `vuln.provenance` primitive lives at **`src/codegenie/primitives/vuln_provenance/`** (best-practices' placement), explicitly establishing `src/codegenie/primitives/` as the additive home ADR-0039 implies. Future bounded primitives land here without further architectural debate.

A second non-obvious choice: **`assemble_provenance(...)` is a free function** (best-practices' shape) but its ordering policy is **explicit data, not implicit `dict.items()` iteration** — a module-level `Final` tuple `_ADAPTER_DISPATCH_ORDER: Final[tuple[tuple[Layer, ...], ...]]` declares "app layer first, then base-image, then runtime." Registration order is no longer load-bearing; the critic's "registration order silently smuggled in as policy" attack is closed.

---

## Goals (concrete, measurable)

- **Zero edits to existing plugin code or stable module bodies** outside an ADR-anchored allowlist of byte-additions: (a) new `adapters/npm_provenance.py` file inside `plugins/vulnerability-remediation--node--npm/` (additive new file, not touch of existing files); (b) one `requires:` line in `plugins/vulnerability-remediation--node--npm/tccm.yaml`; (c) one `import` line in `src/codegenie/__init__.py` for the new primitive; (d) one `$ref` insertion in `src/codegenie/schema/repo_context.schema.json` per new probe; (e) two rows in `ALLOWED_BINARIES` (`dive`, `docker buildx`); (f) Phase 5 `SandboxClient.spawn(...)` gains a `role: SandboxRole` parameter (additive default = `gate`). `[B+synth — critic Issue 4 + roadmap-critique 4]`
- **Phase 3–6.5 regression suite green.** `make check` + `bench/vuln-remediation/` cassette replay runs as a hard pre-merge gate. Cost-ledger byte-equality (epsilon ≤ $0.01). `[B+P]`
- **`vuln.provenance` primitive lands at `src/codegenie/primitives/vuln_provenance/` with the seven-variant `Provenance` discriminated union per ADR-0038 verbatim** — Pydantic v2 `frozen=True, extra="forbid"`; smart constructor for external data; `mypy --strict` clean. **No cache in Phase 7** (ADR-0038 §Tradeoffs honored). `[B+synth]`
- **Two concrete `VulnProvenanceAdapter` implementations.** `NpmVulnProvenanceAdapter` in `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` (new file, additive); `AlpineVulnProvenanceAdapter` in `plugins/distroless-migration--node--npm/adapters/alpine_provenance.py` (new plugin). Both registered via `@register_provenance_adapter(layer=..., ecosystem=...)`. Neither plugin imports the other. `[B+synth — critic Issue Perf-5 + BP-2]`
- **Chain assembly is a free function with explicit dispatch order.** `assemble_provenance(cve, pkg, image, sbom, *, registry=None) -> Provenance` walks `_ADAPTER_DISPATCH_ORDER: Final[tuple[tuple[Layer, ...], ...]] = ((Layer.APP,), (Layer.BASE_IMAGE,), (Layer.RUNTIME,))`. No DSL, no class, no implicit-`dict`-order semantics. ≤ 80 LOC. Property-tested for idempotence. `[B+synth — critic BP-1]`
- **TCCM for `distroless-migration` ships as one YAML file** at `plugins/distroless-migration--node--npm/tccm.yaml`. `must_read` covers Dockerfile, base-image probe slice, SBOM. `should_read` covers `shell_invocation_trace`. `vuln.provenance(...)` is referenced as a **derived query under `derived_queries`**, not as a `must_read` entry — the critic correctly flagged that a function call is not "evidence to load." Phase 7 adds a `derived_queries:` band to the TCCM Pydantic schema (additive). `[B+synth — critic roadmap-6]`
- **Two new probes ship inside the plugin** (`plugins/distroless-migration--node--npm/probes/`): `BaseImageProbe` (static, layer C, `heaviness="light"`) and `ShellInvocationTraceProbe` (executes target build, layer D, `heaviness="heavy"`, `runs_last=True`). Each obeys the frozen Probe ABC (Phase 0 ADR-0007). Each has its own JSON sub-schema under `plugins/distroless-migration--node--npm/schema/` (wired into the envelope via one additive `$ref` per probe). Golden fixtures under `tests/golden/probes/{base_image,shell_invocation_trace}/`. `[S+B+synth — critic BP-5]`
- **`ShellInvocationTraceProbe` runs only inside the Phase 5 microVM stack.** A `tests/fence/test_shell_trace_probe_isolation.py` AST-walk asserts the probe's `run()` calls only `SandboxClient.spawn(...)`; no `subprocess.run`, `os.system`, `os.popen`. The probe gates execution behind `cache_strategy="content"` with `declared_inputs=["Dockerfile", "**/Dockerfile", "package.json", "image-digest:<resolved>"]`. `[S+synth]`
- **Phase 5 `SandboxClient.spawn(...)` gains a `role: SandboxRole` parameter** (sum type: `Role.GATE | Role.PROBE`), defaulting to `Role.GATE`. This is the ONE explicit Phase 5 amendment Phase 7 makes; ADR Phase-7-0003 records it. There is no separate `probe-control` process (security's design rejected — doubles the supervision tree). `[synth — critic Sec-5 + roadmap-3]`
- **Dockerfile recipes ship as deterministic `Transform` subclasses** extending Phase 3's `Transform` ABC. `DockerfileBaseImageSwapTransform` (cheap path, ≤ 80 ms) and `DockerfileMultiStageRefactorTransform` (expensive path, ≤ 350 ms). Pure-Python AST manipulation via `dockerfile-parse`. **No `docker build` invocation inside the recipe** — building is the Phase 5 gate's job. `[B+P]`
- **`DockerfilePolicyGate` ships as a Phase 5 gate-catalog contribution** — security's hard-fail invariant scanner (USER set, no new caps, no new privileged, exec-form ENTRYPOINT, no shell-form HEALTHCHECK, no new build-time secret mounts). Registered via Phase 5's existing `@register_signal_kind` mechanism — additive only. No `--allow-policy-violations` override flag in Phase 7. `[S]`
- **CVE-to-image lookup is a frozen YAML data file** at `plugins/distroless-migration--node--npm/data/chainguard_image_recommendation_table.yaml`. Refresh is an out-of-band PR under CODEOWNERS review. **No Sigstore bundle, no STS token client, no quarantine tier in Phase 7** — security's seven-component artifact is rejected per critic Sec-3 (architectural decree without ADR amendment of a one-line roadmap item). A separate ADR (Phase-7-0007) records the deferred signed-artifact upgrade as a future story; Phase 7 ships YAML-in-plugin. `[B+synth — critic Sec-3]`
- **No Chainguard credential class.** Chainguard `cgr.dev/chainguard/*` distroless images are public; pulls go through the existing Phase 2 registry-pull capability. No `ChainguardPullToken`, no STS client, no pull proxy. Phase 7 ADR-0006 records this rejection. `[synth — critic Sec-4]`
- **`Both` provenance variant produces evidence, not coordination.** When `assemble_provenance` returns `Both`, the migration orchestrator emits a typed `RequiresMultiPluginCoordination(workflow_id, app_record, base_record)` event into the event log and returns `Applicability.PendingCoordination` to the caller. Phase 8's Planner consumes this. No 24h watchdog, no `PartiallyApplied` event, no Phase 11 merge-gate dependency in Phase 7. `[synth — critic Perf-1 + Sec-1 + roadmap-1, 2]`
- **`vuln.provenance` is property-tested under adversarial SBOM inputs.** 100+ generated SBOMs with malformed/poisoned `locations[].layerID` are exercised; every case lands in `Unknown(reason="sbom_layer_attribution_absent")` or a typed-attested result — no `KeyError`, no silent `app_direct` default. `[S]`
- **End-to-end migration test** (`tests/e2e/test_distroless_migration_e2e.py`) migrates a Node.js fixture from a vulnerable Alpine base to `cgr.dev/chainguard/node`, gated by `@pytest.mark.phase07_e2e` (CI matrix-split for `--privileged` runners — opt-in per-PR via label, mandatory on `main`-merge). `[B+synth]`
- **Plugin contract validated against three plugins:** Phase 3's `vulnerability-remediation--node--npm`, Phase 7's `distroless-migration--node--npm`, and Phase 3's synthetic `tests/fixtures/plugins/example--noop--*/`. `[B]`
- **`$0.00` LLM spend per Phase 7 workflow.** Hard zero, asserted by `import_linter` contract: `src/codegenie/primitives/vuln_provenance/` and `plugins/distroless-migration--*/` may not import `anthropic|openai|langchain|langgraph|transformers`. `[B+S]`
- **Net-new runtime Python deps: 1 (`dockerfile-parse`).** Two new CLI binaries in `ALLOWED_BINARIES`: `dive`, `docker buildx`. Each requires an ADR amendment row (Phase 2 ADR-0001-style). `strace` is NOT added — `ShellInvocationTraceProbe` observes via Phase 5's existing eBPF host-side view (security's framing). `[B+S+synth — critic BP-2]`

---

## Architecture

```
              codegenie remediate <repo> --cve <id>
                  │   (no new --task-class flag — orchestrator infers from plugin resolution)
                  ▼
   ┌─────────────────────────────────────────────────────────────────────────┐
   │ src/codegenie/cli/remediate.py        [Phase 3 — UNCHANGED]              │
   └────────────────────────┬────────────────────────────────────────────────┘
                            │
                            ▼
   ┌─────────────────────────────────────────────────────────────────────────┐
   │ src/codegenie/plugins/resolver.py     [Phase 3 — UNCHANGED]              │
   │   Resolves on (task, language, build) tuple                              │
   │   PluginRegistry now contains both production plugins + universal HITL   │
   └────────────────────────┬────────────────────────────────────────────────┘
                            │
                            ▼
   ┌─────────────────────────────────────────────────────────────────────────┐
   │ src/codegenie/transforms/RemediationOrchestrator   [Phase 3 — UNCHANGED] │
   │   Drives the 5 in-code stages; accepts new Transform subclasses          │
   │   Calls vuln.provenance(...) when the dispatched plugin's TCCM           │
   │   declares it as a derived query                                         │
   └────────────────────────┬────────────────────────────────────────────────┘
                            │
                            ▼
   ┌─────────────────────────────────────────────────────────────────────────┐
   │ src/codegenie/primitives/vuln_provenance/   [NEW — Phase 7 bounded core] │
   │   __init__.py        public surface (Provenance, assemble_provenance,    │
   │                       VulnProvenanceAdapter, register_provenance_adapter,│
   │                       Layer, Ecosystem)                                  │
   │   types.py           seven-variant Provenance discriminated union        │
   │                       (verbatim from ADR-0038); nested Both              │
   │   protocols.py       VulnProvenanceAdapter Protocol (ADR-0032 shape)     │
   │   registry.py        @register_provenance_adapter; stores classes        │
   │                       (NOT instances — DI-friendly per critic BP-3)      │
   │   assembly.py        assemble_provenance(...) — free function;           │
   │                       explicit _ADAPTER_DISPATCH_ORDER tuple             │
   │   sbom_verifier.py   cross-checks syft locations[].layerID vs the        │
   │                       cached docker manifest digests (lifted from        │
   │                       security)                                          │
   │   syft_reader.py     SyftSbom Pydantic model (extra="allow" — Phase 2    │
   │                       deliberate decision; adapters defensive)           │
   │   errors.py          ProvenanceError(CodegenieError) hierarchy           │
   └────────────────────────┬────────────────────────────────────────────────┘
                            │
                            ▼
   ┌─────────────────────────────────────────────────────────────────────────┐
   │ plugins/distroless-migration--node--npm/   [NEW — second production      │
   │                                              plugin]                     │
   │   plugin.yaml          scope: (distroless-migration, node, npm);         │
   │                        precedence: 100; requirements.external_tools:     │
   │                        [docker, dive, docker-buildx]                     │
   │   tccm.yaml            must_read: dockerfile, base_image, sbom;          │
   │                        should_read: shell_invocation_trace,              │
   │                        node_build_system;                                │
   │                        derived_queries:                                  │
   │                          - name: provenance                              │
   │                            compute: vuln.provenance                      │
   │                            args: {cve_id: $workflow.cve,                 │
   │                                   package_id: $workflow.package,         │
   │                                   image_ref: $repo.base_image}           │
   │   adapters/                                                              │
   │     alpine_provenance.py    AlpineVulnProvenanceAdapter                  │
   │                              @register_provenance_adapter(               │
   │                                layer=Layer.BASE_IMAGE,                   │
   │                                ecosystem=Ecosystem.APK)                  │
   │   probes/                                                                │
   │     base_image_probe.py     BaseImageProbe (Layer C; light; static)      │
   │     shell_trace_probe.py    ShellInvocationTraceProbe (Layer D; heavy;   │
   │                              runs_last=True; calls SandboxClient.spawn(  │
   │                              role=Role.PROBE))                           │
   │   recipes/                                                               │
   │     dockerfile_base_image_swap.py   DockerfileBaseImageSwapTransform     │
   │     dockerfile_multi_stage.py       DockerfileMultiStageRefactor         │
   │   subgraph/api.py      5-stage pipeline (Discover / Match / Apply /      │
   │                        Validate / Report) — shape mirrors Phase 3        │
   │   data/                                                                  │
   │     chainguard_image_recommendation_table.yaml   frozen lookup           │
   │   schema/                                                                │
   │     base_image.schema.json                                               │
   │     shell_invocation_trace.schema.json                                   │
   │   skills/              YAML-frontmatter Skills (recipe selection hints)  │
   │   PLUGINS.lock entry   sha256(dir_tree)                                  │
   └────────────────────────┬────────────────────────────────────────────────┘
                            │
                            ▼
   ┌─────────────────────────────────────────────────────────────────────────┐
   │ plugins/vulnerability-remediation--node--npm/   [Phase 3 — ALLOWLISTED   │
   │                                                   ADDITIONS ONLY]        │
   │   adapters/                                                              │
   │     npm_provenance.py   NpmVulnProvenanceAdapter — NEW additive file     │
   │                          @register_provenance_adapter(                   │
   │                            layer=Layer.APP, ecosystem=Ecosystem.NPM)     │
   │                          (does NOT touch existing recipe path; reached   │
   │                          only when assemble_provenance is invoked)       │
   │   tccm.yaml             one new line in `requires:` block — additive    │
   │                          per ADR-0029                                    │
   │   [every other file under this directory: BYTE-LOCKED by fence test]    │
   └────────────────────────┬────────────────────────────────────────────────┘
                            │
                            ▼
   ┌─────────────────────────────────────────────────────────────────────────┐
   │ Phase 5 sandbox stack    [Phase 5 — ONE ADDITIVE AMENDMENT]              │
   │   SandboxClient.spawn(..., role: SandboxRole = Role.GATE)                │
   │   New value Role.PROBE recognized; same Firecracker/gVisor stack used   │
   │   New gates registered (additive via @register_signal_kind):            │
   │     DockerfilePolicyGate         (cheap, pre-build; security-lifted)     │
   │     DistrolessBuildGate          (docker buildx in microVM)              │
   │     ShellInvocationDeltaGate     (re-runs shell-trace probe on migrated │
   │                                    image; passes iff count == 0)        │
   └────────────────────────┬────────────────────────────────────────────────┘
                            │
                            ▼
   ┌─────────────────────────────────────────────────────────────────────────┐
   │ .codegenie/events/     [ADR-0034 — additive event variants]              │
   │   workflow-internal/<workflow_id>.jsonl.zst:                             │
   │     ProvenanceQueried(cve_id, provenance_kind, adapter_chain_used)       │
   │     BaseImageResolved(image_ref, digest, kind)                           │
   │     ShellInvocationObserved(count, locations)                            │
   │     DistrolessMigrationProposed(from_ref, to_ref, files_changed)         │
   │     DockerfilePolicyGatePassed | DockerfilePolicyGateFailed              │
   │     RequiresMultiPluginCoordination(workflow_id, app_record,             │
   │                                     base_record)   ← Phase 8 consumes    │
   └─────────────────────────────────────────────────────────────────────────┘
```

Three load-bearing architectural lines (provenance: best-practices structure + critic-mandated departures):

1. **`vuln.provenance` is a module, not a method, and not a class hierarchy.** It lives at `src/codegenie/primitives/vuln_provenance/`. `src/codegenie/primitives/` becomes the additive home for future ADR-0039 bounded primitives.
2. **Adapters are plugin-contributed and decorator-registered.** `@register_provenance_adapter(layer=..., ecosystem=...)` stores the **class** (not an instance — best-practices Issue BP-3 from critic). The chain-assembly function constructs instances lazily with their dependencies. Two-axis `(Layer, Ecosystem)` key.
3. **Chain assembly is a free function with explicit data-driven order.** `assemble_provenance(...)` walks `_ADAPTER_DISPATCH_ORDER: Final[tuple[tuple[Layer, ...], ...]]` — declared in code, not implicit in `dict` insertion. Operators predict behavior by reading one tuple.

---

## Components

### 1. `Provenance` discriminated union (`src/codegenie/primitives/vuln_provenance/types.py`)

- **Provenance:** Best-practices design verbatim, ADR-0038 shape.
- **Purpose:** Seven-variant typed return value of `vuln.provenance(...)`. ADR-0038 commits to the shape.
- **Interface:** Pydantic v2 discriminated union; `frozen=True, extra="forbid"`. Variants: `AppDirect`, `AppTransitive`, `AppVendored`, `BaseImage`, `RuntimeBundled`, `Both`, `Unknown`. `Both.app_record: AppKind` and `Both.base_record: BaseKind` are nested discriminated unions — `Both(both, both)` is unrepresentable at construction.
- **Internal design:** As best-practices design §1; exhaustiveness enforced via `match`/`assert_never` in every consumer.
- **Why over alternatives:** Adopting ADR-0038 verbatim is non-negotiable. Flat-records-with-optional-fields shape (security flirted with it) reintroduces half-valid states ADR-0033 forbids.
- **Tradeoffs:** Nested `Both` is slightly more complex than seven flat variants. Acceptable; the recursive footgun is closed at type-check time.

### 2. `VulnProvenanceAdapter` Protocol (`src/codegenie/primitives/vuln_provenance/protocols.py`)

- **Provenance:** Best-practices design + critic-mandated departure.
- **Purpose:** Structural contract every adapter satisfies. One adapter per `(Layer, Ecosystem)` slice. Mirrors ADR-0032's `DepGraphAdapter` shape.
- **Interface:** `@runtime_checkable Protocol`. `attribute(cve_id, package_id, image_ref, sbom: SyftSbom) -> Provenance`. `confidence() -> AdapterConfidence`. **No `cost_band`, no `applies_when` declaration** — performance's extension to the Protocol is rejected per critic Perf-5.
- **Internal design:** Duck-typed; no inheritance required.
- **Why over alternatives:** Performance proposed extending the Protocol with `cost_band + applies_when` — critic correctly flagged that as kernel-contract drift. Security's `AdapterConfidence` is kept (it composes with Phase 3 ADR-0010); the rest is rejected.
- **Tradeoffs:** Adapters must self-report `applies` via returning `Unknown(reason=...)` rather than refusing to be called — adds a single dispatched call per non-matching adapter (≤ 1 ms). The performance "save 2 calls" argument loses against open/closed adherence.

### 3. `@register_provenance_adapter` + registry (`src/codegenie/primitives/vuln_provenance/registry.py`)

- **Provenance:** Best-practices design + critic-mandated departure.
- **Purpose:** Decorator-registration of adapter **classes** (not instances). Mirrors `@register_probe` and `@register_dep_graph_strategy`.
- **Interface:**
  ```python
  class Layer(str, Enum):
      APP = "app"
      BASE_IMAGE = "base_image"
      RUNTIME = "runtime"

  class Ecosystem(str, Enum):
      NPM = "npm"
      YARN_BERRY = "yarn-berry"
      APK = "apk"
      DPKG = "dpkg"
      RPM = "rpm"
      # ... open to additive enum values

  _REGISTRY: Final[dict[tuple[Layer, Ecosystem], type[VulnProvenanceAdapter]]] = {}

  def register_provenance_adapter(*, layer: Layer, ecosystem: Ecosystem):
      def _wrap(cls: type[VulnProvenanceAdapter]) -> type[VulnProvenanceAdapter]:
          key = (layer, ecosystem)
          if key in _REGISTRY:
              raise RegistryError(f"duplicate adapter for {key!r}")
          _REGISTRY[key] = cls   # NOTE: class, not instance
          return cls
      return _wrap
  ```
- **Internal design:** Module-level `_REGISTRY: dict[tuple[Layer, Ecosystem], type[Adapter]]` — stores classes. Instances constructed lazily in `assemble_provenance` with DI-friendly constructor (`adapter_cls(sbom_reader=…, logger=…)` if the adapter declares such kwargs; otherwise `adapter_cls()`). Test isolation via `pytest` fixture that snapshots and restores `_REGISTRY` per test.
- **Why over alternatives:** Critic BP-3 caught that storing instances at decorator time forbids constructor DI and forces module-import work. Storing classes defers construction to dispatch.
- **Tradeoffs:** Adapter classes must accept no-arg construction OR declare a typed constructor signature the assembly function honors. We standardize on the latter — adapter `__init__` may take kwargs whose names match well-known dependencies the primitive injects (`sbom_reader`, `logger`, `image_manifest_cache`).

### 4. `assemble_provenance(...)` (`src/codegenie/primitives/vuln_provenance/assembly.py`)

- **Provenance:** Best-practices design + critic-mandated departure (BP-1, BP-4).
- **Purpose:** Compose adapter results into a single `Provenance`. Answers ADR-0038's deferred adapter-chain-assembly question.
- **Interface:**
  ```python
  _ADAPTER_DISPATCH_ORDER: Final[tuple[tuple[Layer, ...], ...]] = (
      (Layer.APP,),          # app-layer adapters first
      (Layer.BASE_IMAGE,),   # then base-image
      (Layer.RUNTIME,),      # then runtime-bundled
  )

  def assemble_provenance(
      cve_id: CveId,
      package_id: PackageId,
      image_ref: ImageRef | None,
      sbom: SyftSbom,
      *,
      registry: Mapping[tuple[Layer, Ecosystem], type[VulnProvenanceAdapter]] | None = None,
      adapter_factory: AdapterFactory | None = None,
  ) -> Provenance: ...
  ```
- **Internal design:** Builder-shaped accumulator (lifted from critic's "missed Builder" observation). Walks `_ADAPTER_DISPATCH_ORDER`; for each layer-set, iterates adapters in **sorted-by-Ecosystem-enum** order (deterministic, NOT `dict.items()`); calls each via `adapter_factory(cls)`; collects the first non-`Unknown` result per layer; composes `Both` when both `app_result` and `base_result` are non-`Unknown`. Uses `match`/`assert_never` on `(app_result, base_result)` per critic BP-4.

  ```python
  match (app_result, base_result):
      case (None, None):
          return Unknown(reason="no_adapter_resolved")
      case (app, None):
          return app
      case (None, base):
          return base
      case (app, base):
          return Both(app_record=app, base_record=base)
  ```
- **Why over alternatives:** Performance's `VulnProvenanceChainAssembler` class with `confidence × cost_band × applies_when` ordering was rejected (kernel-contract drift; admits non-open/closed). Security's `chain.py` class was rejected (over-engineered for two adapters). Best-practices' `for k, v in registry.items()` was rejected (smuggles `dict` insertion order as load-bearing policy).
- **Tradeoffs:** Adding a new `Layer` value (`Layer.SIDECAR`, future) requires touching `_ADAPTER_DISPATCH_ORDER`. Acceptable — adding a layer family is genuinely cross-cutting and warrants an explicit ADR. Adding a new `Ecosystem` to an existing layer is free (registry-only).

### 5. `BaseImageProbe` (`plugins/distroless-migration--node--npm/probes/base_image_probe.py`)

- **Provenance:** Best-practices design (shape) + performance (cache strategy) + critic-mandated placement (in plugin, not in `src/codegenie/probes/`).
- **Purpose:** Read every `FROM` line in every Dockerfile; resolve to immutable digest; classify as `{distroless | minimal | full | vendor_specific | unknown}` (best-practices marker catalog `_BASE_IMAGE_KIND_RULES`). Facts, not judgments.
- **Interface:** Probe ABC; `name = "BaseImage"`, `layer = "C"`, `tier = "task_specific"`, `applies_to_tasks = ["distroless-migration"]`, `applies_to_languages = ["*"]`, `declared_inputs = ["**/Dockerfile", "**/Dockerfile.*", "**/Containerfile", "image-digest:<resolved>"]`, `cache_strategy = "content"`, `heaviness = "light"`.
- **Internal design:** Static-only — reads parsed Dockerfile AST + emits per-stage records with `{path, stages: [{name, ref, digest, kind}], confidence}`. Uses Phase 2's already-shipped `image_digest_resolver` capability for digest resolution. No `dive`, no `docker pull`.
- **Why over alternatives:** Best-practices placed this in `src/codegenie/probes/layer_c/` — rejected per critic BP-5. ADR-0031 is explicit: plugins contribute probes. Living in the plugin keeps the precedent right for future task classes.
- **Tradeoffs:** p99 ≤ 60 ms cold per critic's challenge to performance's "negligible at Stage 0" — Phase 7 acknowledges this is *not* free at portfolio scale but Phase 7 itself doesn't run portfolio scans (Phase 10 does); cost shows up there with the right framing.

### 6. `ShellInvocationTraceProbe` (`plugins/distroless-migration--node--npm/probes/shell_trace_probe.py`)

- **Provenance:** **Security design wins on what this probe IS** (the load-bearing critic-flagged disagreement). Best-practices' placement (in plugin) and performance's caching strategy are kept.
- **Purpose:** Observe whether the target repo's build/start/healthcheck invokes a shell. **Executes target-repo build commands** — first probe in the gather pipeline to do so. Outputs `{shell_invocations: [{step, command, exec_form|shell_form}], count, confidence}`.
- **Interface:** Probe ABC; `name = "ShellInvocationTrace"`, `layer = "D"`, `tier = "task_specific"`, `applies_to_tasks = ["distroless-migration"]`, `cache_strategy = "content"`, `declared_inputs = ["Dockerfile", "**/Dockerfile", "package.json", "image-digest:<resolved>"]`, `heaviness = "heavy"`, `runs_last = True`.
- **Internal design:** `run()` calls `SandboxClient.spawn(role=Role.PROBE, ...)`. The microVM runs `docker buildx build` against the rendered builder stage + a short container boot. The trace is captured from **outside the VM** via Phase 5's existing eBPF host-side view (security's framing — no new isolation tech). The in-VM `strace` is informational only (and is NOT added to `ALLOWED_BINARIES`).
- **Why over alternatives:** Performance's "reducer over a pre-existing Phase 2 runtime trace" was rejected because Phase 2 does NOT produce a runtime-trace artifact today — performance invented a precondition. Best-practices' `dive`+`strace` "Phase-2-shaped sandbox" was rejected — there is no Phase-2-shaped sandbox tier, and `strace` in a shared-kernel environment is a CAP_SYS_PTRACE-requiring half-measure. Security's microVM execution surface is the only honest answer.
- **Tradeoffs:** Microvm boot is real cost — Firecracker ~150 ms cold + container boot (seconds). Cached aggressively by `(image-digest, Dockerfile-digest)`. Phase 7 does NOT solve macOS-via-Lima cost (security accepts seconds; we accept that). Phase 8's warm-pool reuse can lower this further; it is explicitly Phase 8's concern.
- **Phase 5 amendment:** `SandboxClient.spawn(role=Role.PROBE)` is the new caller — recorded in Phase 7 ADR-0003.

### 7. `NpmVulnProvenanceAdapter` (`plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py`)

- **Provenance:** Best-practices design + critic-mandated rejection of "promotion" framing.
- **Purpose:** Resolve `(cve_id, package_id)` against the npm dep tree. Returns `AppDirect | AppTransitive | Unknown(reason)`. **New file in the Phase 3 plugin directory** — additive only; the existing Phase 3 recipe path never reaches this file.
- **Interface:** Satisfies `VulnProvenanceAdapter`. `@register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)`.
- **Internal design:** Reads `package.json` + `package-lock.json` from gathered `RepoContext`. Walks resolved tree; chain length 1 → `AppDirect`; chain length > 1 → `AppTransitive`; absent → `Unknown(reason="sbom_layer_attribution_absent")`. Lifts the SBOM cross-verifier from security: confirms `locations[].layerID` against image manifest digests; mismatch → `AdapterConfidence.Degraded`.
- **Why over alternatives:** Performance's "ship in Phase 7 plugin and re-export from Phase 3" was rejected per critic Perf-5b — that inverts the dependency direction and is a layering violation. Best-practices' "promotion from Phase 3's refuse-mode shape" was rejected as a frame because there's no NpmVulnProvenanceAdapter in Phase 3 to promote (only an `Applicability.NotApplicable(reason=CVE_NOT_IN_APP_LAYER)` refusal). Adding this as a new file under Phase 3's plugin is the cleanest path; it lives where future npm-related provenance work would live.
- **Tradeoffs:** Adding a file inside an existing plugin directory IS a byte-edit per the "Additive semantics" decision below. It is allowlisted explicitly by file path in the Phase 7 fence amendment.

### 8. `AlpineVulnProvenanceAdapter` (`plugins/distroless-migration--node--npm/adapters/alpine_provenance.py`)

- **Provenance:** Best-practices design.
- **Purpose:** Resolve `(cve_id, package_id)` against an Alpine base-image's apk database. Returns `BaseImage | Unknown(reason)`.
- **Interface:** Satisfies `VulnProvenanceAdapter`. `@register_provenance_adapter(layer=Layer.BASE_IMAGE, ecosystem=Ecosystem.APK)`.
- **Internal design:** Reads `SyftSbom`'s `locations[].layerID`; matches against the `BaseImageProbe`'s layer-to-image-digest mapping. Cross-verifies via security's `sbom_verifier.py`. Returns `BaseImage(image_digest=..., layer_digest=..., distro_pkg=DistroPackage(name=..., version=...), stage=...)` on hit; `Unknown(reason="sbom_layer_attribution_absent")` on mismatch.
- **Tradeoffs:** Alpine-specific. Future Debian / RHEL adapters ship under their own plugins or a shared `base-image-tooling` plugin; each registers under its own `(Layer.BASE_IMAGE, Ecosystem.*)` key — no edits to this adapter.

### 9. `DockerfileBaseImageSwapTransform` (`plugins/distroless-migration--node--npm/recipes/dockerfile_base_image_swap.py`)

- **Provenance:** Best-practices design + performance's `dockerfile-parse` choice.
- **Purpose:** Cheap path. Swap `FROM node:18-alpine` → `FROM cgr.dev/chainguard/node:latest@sha256:<digest>` (plus multi-stage runner adjustments — `COPY --from=builder`, no shell, `USER nonroot`).
- **Interface:** Extends Phase 3's `Transform` ABC.
- **Internal design:** Pure-Python `dockerfile-parse` AST manipulation. **No `docker build` in the recipe** — building is the Phase 5 gate's job. Reads `data/chainguard_image_recommendation_table.yaml`.
- **Why over alternatives:** OpenRewrite Dockerfile support is immature; JVM cold-start ~2 s destroys the per-workflow budget. Convention drift (Phase 3 already shipped `OpenRewriteRecipeEngine` stub) is acknowledged but Phase 7 ADR-0005 records the rationale: Phase 7's recipes are pure-data Dockerfile edits, which `dockerfile-parse` solves directly; OpenRewrite stays the engine for Phase 8+ language-level transforms.
- **Tradeoffs:** Frozen recommendation table requires PR refresh; security's signed-Sigstore-bundle artifact is rejected per critic Sec-3 as a separate ADR amendment that didn't ship. A future story (Phase 7 ADR-0007, deferred) can upgrade the artifact if the threat model is ratified.

### 10. `DockerfileMultiStageRefactorTransform` (`plugins/distroless-migration--node--npm/recipes/dockerfile_multi_stage.py`)

- **Provenance:** Performance design.
- **Purpose:** Expensive path. Dockerfile has shell-using `RUN` lines that must move to a builder stage.
- **Internal design:** Per-stage AST manipulation. **No `asyncio.gather`** — the per-stage parallelism performance proposed buys ~250 ms on a 4-stage Dockerfile and adds complexity; Phase 7 ships the simpler synchronous shape. Performance's parallel fan-out is documented as an open question for Phase 13 if telemetry shows it's the bottleneck.
- **Tradeoffs:** ≤ 350 ms p99 vs performance's ~95 ms claim. Critic correctly flagged that `asyncio.gather` over CPU-bound AST work without `run_in_executor` is theatrical; we don't pretend.

### 11. `DockerfilePolicyGate` (Phase 5 gate-catalog contribution)

- **Provenance:** Security design.
- **Purpose:** Deterministic policy scan over rendered Dockerfile **before** any sandbox build. Six invariants: USER set non-root; no new `--cap-add`; no new `--privileged`; exec-form ENTRYPOINT; no shell-form HEALTHCHECK; no new build-time secret mounts.
- **Interface:** Phase 5 `Gate` ABC; registered via Phase 5's `@register_signal_kind` mechanism — additive only. No `--allow-policy-violations` override.
- **Internal design:** Pure function over rendered Dockerfile text + parsed AST. Lives in the plugin's `recipes/` directory (it gates the recipe output before sandbox boot).
- **Tradeoffs:** Invariant-list-driven, not semantic. Cannot detect behavioral regressions (Phase 12 owns that). Security's framing accepted.

### 12. `DistrolessBuildGate` & `ShellInvocationDeltaGate` (Phase 5 gate contributions)

- **Provenance:** Security design.
- **Purpose:** `DistrolessBuildGate` runs `docker buildx build` against the rendered Dockerfile inside the microVM. `ShellInvocationDeltaGate` re-runs `ShellInvocationTraceProbe` against the migrated image; passes iff `shell_invocations.count == 0`.
- **Interface:** Phase 5 `Gate` ABC; strict-AND with the existing scorer.
- **Internal design:** Both run inside the microVM via existing `SandboxClient.spawn(role=Role.GATE)`. The shell-delta gate is the canonical "distroless migration is provably correct" assertion — its passing is what makes the migration objectively safe.

### 13. `TCCM derived_queries` band (`src/codegenie/plugins/tccm.py` — additive)

- **Provenance:** Synthesis (critic roadmap-6).
- **Purpose:** TCCMs need a way to reference function calls like `vuln.provenance(...)` distinctly from `must_read` (which is evidence to load). Phase 7 adds a `derived_queries:` band to the TCCM Pydantic schema — additive.
- **Interface:** TCCM YAML grows one new optional band:
  ```yaml
  derived_queries:
    - name: provenance
      compute: vuln.provenance
      args: {cve_id: $workflow.cve, package_id: $workflow.package, image_ref: $repo.base_image}
  ```
- **Internal design:** TCCM loader resolves `compute: vuln.provenance` to the imported callable at plugin-load time. Existing TCCMs without `derived_queries:` continue to parse unchanged (default empty list).
- **Tradeoffs:** TCCM Pydantic schema gains one field. ADR Phase-7-0008 records this; the Phase 3 TCCM gets one `derived_queries:` entry as the additive `requires:` line (technically a different band — but the principle is that `vuln.provenance` is now first-class TCCM vocabulary).

---

## Data flow

### One end-to-end distroless-migration run (single-plugin route, `BaseImage` variant)

```
1. operator: codegenie remediate <repo> --cve CVE-2026-XXXX
                  │
2. orchestrator loads RepoContext (Phase 2)
                  │
3. orchestrator loads plugins (PluginRegistry); resolves on (task, lang, build)
                  │
4. orchestrator dispatches probe coordinator for any task-class-specific probes
   not yet cached:
     - BaseImageProbe (static; ≤ 60 ms cold)
     - ShellInvocationTraceProbe (microVM boot + container boot; seconds)
                  │
5. RemediationOrchestrator drives 5 stages; TCCM derived_query fires:
   assemble_provenance(cve, pkg, image, sbom) → BaseImage(...)
                  │
6. assemble_provenance:
   - Walks _ADAPTER_DISPATCH_ORDER
   - Layer.APP: NpmVulnProvenanceAdapter.attribute(...) → Unknown(reason="sbom_layer_attribution_absent")
   - Layer.BASE_IMAGE: AlpineVulnProvenanceAdapter.attribute(...) → BaseImage(image_digest=..., layer_digest=..., distro_pkg=...)
   - Returns BaseImage(...) (single-plugin route)
                  │
7. Plugin's match step: DockerfileBaseImageSwapTransform applies
                  │
8. Recipe renders new Dockerfile diff (≤ 80 ms, pure AST)
                  │
9. DockerfilePolicyGate (strict-AND): pass
                  │
10. SandboxClient.spawn(role=Role.GATE) → DistrolessBuildGate runs docker buildx
    inside microVM; npm test runs in same microVM; ShellInvocationDeltaGate
    re-runs trace and asserts count == 0
                  │
11. ObjectiveSignals → TrustScorer (strict-AND) → Validated
                  │
12. remediation-report.yaml written; events flushed
                  │
13. all microVMs DESTROYED
```

### One `Both`-variant slice (CVE in app layer AND base image)

```
1.-5. as above; but step 6 differs:
6. assemble_provenance:
   - Layer.APP: NpmVulnProvenanceAdapter.attribute(...) → AppTransitive(...)
   - Layer.BASE_IMAGE: AlpineVulnProvenanceAdapter.attribute(...) → BaseImage(...)
   - Returns Both(app_record=AppTransitive(...), base_record=BaseImage(...))
                  │
7. Plugin's match step receives Both; returns Applicability.PendingCoordination
   with both records cited
                  │
8. RemediationOrchestrator emits typed event:
   RequiresMultiPluginCoordination(workflow_id=..., app_record=..., base_record=...)
                  │
9. Phase 7 workflow STOPS. No PR opened. No 24h watchdog. No child workflows.
   The event lands in the spanning event log for Phase 8's Planner to consume.
                  │
10. CLI exits with documented exit code 8 ("requires multi-plugin coordination —
    awaiting Phase 8 Planner") and writes a structured operator-readable
    coordination-summary.yaml.
```

**This Both-variant slice is the load-bearing roadmap-coherence test.** Phase 7 produces the typed evidence; Phase 8 consumes it. Phase 11 enforces atomic-or-nothing at PR merge time. None of those three responsibilities is dragged into Phase 7.

---

## Failure modes & recovery

| Failure | Source | Detection | Recovery |
|---|---|---|---|
| `Unknown(reason="sbom_layer_attribution_absent")` | `[B]` | Adapter explicit return | Workflow returns `Applicability.NotApplicable`; routes to universal HITL fallback (Phase 3) |
| `Unknown(reason="no_adapter_resolved")` | `[synth]` | `assemble_provenance` walked all layers, all returned `Unknown` | Same: HITL escalation with evidence bundle |
| `ShellInvocationTraceProbe` cannot complete (microVM boot fails) | `[S]` | `SandboxClient.spawn` raises | Probe reports `confidence: Unavailable(reason=BUILD_FAILED)`; plugin refuses to auto-propose; HITL |
| `ShellInvocationTraceProbe` observes shell calls in the migrated image | `[S]` | `ShellInvocationDeltaGate` fails | Trust score fails strict-AND; workflow does not produce PR; recipe ships `Applicability.NotApplicable(reason=SHELL_INVOCATION_NOT_REWRITABLE)` |
| `DockerfilePolicyGate` fails (USER removed, cap added, etc.) | `[S]` | Gate emits `DockerfilePolicyGateFailed(failing_invariants=[...])` | Strict-AND fail; workflow halts at gate; no override |
| `Both` provenance returned | `[synth — critic Perf-1+Sec-1]` | `assemble_provenance` returns `Both(...)` | Emit `RequiresMultiPluginCoordination` event; exit code 8; Phase 8 owns next step |
| `docker buildx` fails in gate microVM (Chainguard image cold pull, network issue) | `[B+P]` | Build returns nonzero | Phase 5 retry envelope (ADR-0014); 3rd failure escalates |
| Poisoned SBOM (`locations[].layerID` doesn't match manifest) | `[S]` | `sbom_verifier.py` cross-check | Adapter returns `Unknown(reason="sbom_layer_attribution_absent")`; emits `sbom.routing_anomaly` event |
| Adapter raises unexpected exception | `[B+synth]` | `assemble_provenance` catches `ProvenanceError` (typed) and converts to `Unknown(reason="adapter_error", details=...)`. **All other exceptions propagate** (Rule 12 — fail loud) | Workflow surfaces typed error; HITL with the diagnostic |
| Duplicate adapter registration | `[B]` | `@register_provenance_adapter` raises `RegistryError` at import | Plugin loader fast-fails at Supervisor startup with file/line diagnostic |
| `dockerfile-parse` cannot parse Dockerfile (heredoc, ARG-driven FROM) | `[P]` | Parser exception | Recipe returns `RecipeOutcome(kind="not_applicable", reason="dockerfile_parse_failed")`; HITL |
| Chainguard image not in lookup table | `[B]` | `lookup.recommend(...)` returns `None` | Plugin returns `Applicability.NotApplicable(reason="no_distroless_counterpart")`; HITL |
| `tccm.yaml derived_queries` references unknown `compute` | `[synth]` | TCCM loader fails at plugin-load with file/line diagnostic | Plugin doesn't load; Supervisor refuses to start |
| Phase 3 plugin behavior drifts (`bench/vuln-remediation/` replay fails) | `[B+synth]` | CI hard gate | PR cannot merge; regression must be fixed |

---

## Resource & cost profile

| Item | Value | Source |
|---|---|---|
| LLM spend per Phase 7 workflow | $0.00 | Hard zero; fence-asserted |
| `BaseImageProbe` cold | ≤ 60 ms (1 `docker manifest inspect` per unique FROM) | `[P]` corrected for Stage 0 honesty per critic |
| `BaseImageProbe` warm | ≤ 2 ms (cache hit) | `[P]` |
| `ShellInvocationTraceProbe` cold | ~seconds (Firecracker + container boot) | `[S]` — accepted; warm-pool is Phase 8 |
| `ShellInvocationTraceProbe` warm | ≤ 100 ms (content-cache hit) | `[P]` |
| `assemble_provenance` per call | ≤ 50 ms (uncached; ADR-0038 §Tradeoffs honored) | `[B+S]` |
| `DockerfileBaseImageSwapTransform` | ≤ 80 ms | `[P]` |
| `DockerfileMultiStageRefactorTransform` | ≤ 350 ms (synchronous) | `[synth — rejected asyncio.gather]` |
| `DistrolessBuildGate` (warm Chainguard cache) | ≤ 14 s in microVM | `[P]` |
| Net-new Python deps | 1 (`dockerfile-parse`) | `[B]` |
| Net-new CLI binaries in `ALLOWED_BINARIES` | 2 (`dive`, `docker buildx`) | `[B]` |
| Worker memory ceiling delta | +60 MB over Phase 6.5 baseline | `[P]` |
| CI runtime added to `make check` | ~30 s (new probe goldens + property tests) | `[B]` |
| CI runtime for opt-in `phase07_e2e` | ~3 min (one migration run) | `[B]` |

---

## Test plan

### Unit (fast, bulk)
- `tests/unit/primitives/vuln_provenance/test_types.py` — every variant constructs/round-trips; `Both` rejects `Both(both, ...)` at validation; smart constructor rejects malformed dicts.
- `tests/unit/primitives/vuln_provenance/test_registry.py` — duplicate registration raises `RegistryError`; non-conforming class fails at registration; lookup by `(Layer, Ecosystem)` works; registry-isolation fixture restores state.
- `tests/unit/primitives/vuln_provenance/test_assembly.py` — every combinatorial path (`Unknown×Unknown→Unknown`, `app×Unknown→app`, `Unknown×base→base`, `app×base→Both`); `_ADAPTER_DISPATCH_ORDER` walked in declared order independent of registration order; explicit `registry` param overrides default.
- `tests/unit/probes/base_image/test_base_image.py` — fixture Dockerfiles for distroless/alpine/debian-slim/scratch/multi-stage/unknown; multi-stage emits a list; schema slice validates.
- `tests/unit/probes/shell_invocation_trace/test_shell_trace.py` — fixture trace JSON inputs; classification correct; image-digest declared-input invalidates cache.
- `tests/unit/plugins/distroless_migration_node_npm/test_alpine_provenance.py` — fixture SBOMs with and without `locations[].layerID`; correct `BaseImage` or `Unknown(reason="sbom_layer_attribution_absent")`.
- `tests/unit/plugins/vulnerability_remediation_node_npm/test_npm_provenance.py` — fixture lockfiles; `AppDirect` for direct, `AppTransitive` for transitive, `Unknown` for absent.
- `tests/unit/transforms/recipes/test_dockerfile_base_image_swap.py` — fixture Dockerfiles; correct swap; no-op detection for already-distroless; multi-stage handling.

### Integration (moderate)
- `tests/integration/test_plugin_resolution_phase7.py` — Dockerfile + `package.json` fixture; resolver returns `distroless-migration--node--npm`.
- `tests/integration/test_provenance_assembly_via_plugins.py` — full plugin-load → adapter-registration → `assemble_provenance(...)` → typed result; Phase 3's `NpmVulnProvenanceAdapter` + Phase 7's `AlpineVulnProvenanceAdapter` both loaded.
- `tests/integration/test_tccm_distroless_derived_queries_loads.py` — TCCM YAML loads, validates against the extended Pydantic schema, `derived_queries.compute` resolves to the imported callable.
- `tests/integration/test_sandbox_client_role_probe.py` — `SandboxClient.spawn(role=Role.PROBE)` boots a microVM identical to `Role.GATE` plus the probe-side eBPF host-trace.

### Property (high-signal)
- `tests/property/vuln_provenance/test_both_invariant.py` — for any (`AppKind`, `BaseKind`) pair where both are non-`Unknown`, `assemble_provenance(...)` returns `Both(app_record, base_record)`; no recursion.
- `tests/property/vuln_provenance/test_idempotence.py` — calling `assemble_provenance` twice with identical inputs returns equal `Provenance` instances.
- `tests/property/vuln_provenance/test_sbom_tampering.py` — **100+ generated SBOMs with malformed/poisoned `locations[].layerID`**; every case lands in `Unknown(reason="sbom_layer_attribution_absent")` or typed result. No `KeyError`, no silent `app_direct`.
- `tests/property/vuln_provenance/test_dispatch_order_invariant.py` — registration order shuffled across 50 permutations; `assemble_provenance` result is byte-identical. **Locks the critic's BP-1 attack at the property level.**

### Golden (regression)
- `tests/golden/probes/base_image/{distroless-target,alpine,multi-stage,scratch,unknown}.json`
- `tests/golden/probes/shell_invocation_trace/{distroless-target,with-shell,no-trace-available}.json`
- `tests/golden/provenance/{app-direct,app-transitive,base-image-alpine,both,unknown}.json`

### End-to-end (opt-in, gated)
- `tests/e2e/test_distroless_migration_e2e.py` — `@pytest.mark.phase07_e2e`; vulnerable Node.js fixture; assert local branch carries `FROM cgr.dev/chainguard/node`, `remediation-report.yaml` written, `npm test` passes in `SubprocessJail`. CI runs separately on `--privileged` Linux runners.
- `tests/e2e/test_both_provenance_emits_coordination_event_e2e.py` — fixture repo with CVE in both layers; assert `assemble_provenance` returns `Both`; assert `RequiresMultiPluginCoordination` event lands in spanning log; assert exit code 8. **No PR is opened — this is the Phase-7-stops-here behavior.**

### Fence / structural
- `tests/fence/test_kernel_frozen.py` — extended additively with the Phase 7 allowlist file list (enumerated below). Any diff against Phase 0–6.5 outside the allowlist fails CI.
- `tests/fence/test_phase7_no_llm.py` — `import_linter` contract: `src/codegenie/primitives/vuln_provenance/`, `plugins/distroless-migration--*/` may not import LLM SDKs.
- `tests/fence/test_shell_trace_probe_isolation.py` — AST-walks `shell_trace_probe.py`; asserts only `SandboxClient.spawn(...)` is reachable; no `subprocess.run`, `os.system`, `os.popen`, `shell=True`.
- `tests/fence/test_provenance_primitive_in_plugin_directory.py` — asserts the new probes live under `plugins/distroless-migration--node--npm/probes/`, not under `src/codegenie/probes/` (locks ADR-0031).
- `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` — for every file under `plugins/vulnerability-remediation--node--npm/` except the two allowlisted additions (`adapters/npm_provenance.py` + the new `tccm.yaml requires:` line), assert byte-identity against the Phase 6.5 baseline.

### Phase 7 fence allowlist (exhaustive)

The Phase 7 PR is permitted to write/touch ONLY these existing paths beyond its own new directories:

1. `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` (new file)
2. `plugins/vulnerability-remediation--node--npm/tccm.yaml` (one new `derived_queries:` block — exactly one entry)
3. `src/codegenie/__init__.py` (one import line for the new primitive)
4. `src/codegenie/schema/repo_context.schema.json` (two `$ref` insertions — one per new probe)
5. `src/codegenie/plugins/tccm.py` (one new optional band: `derived_queries: list[DerivedQuery] = []`)
6. `src/codegenie/sandbox/client.py` (one new `role: SandboxRole = Role.GATE` parameter to `spawn(...)`)
7. `src/codegenie/sandbox/__init__.py` (one new export: `Role` enum)
8. `src/codegenie/exec/__init__.py` (`ALLOWED_BINARIES` gains `dive` and `docker buildx`)
9. `pyproject.toml` (one new dep: `dockerfile-parse`)
10. `src/codegenie/plugins/loader.py` (one new explicit-import line for the new plugin's adapter module)

Any other byte-edit to a Phase 0–6.5 file is a fence failure.

---

## Design patterns applied

| Decision | Pattern | Why here | Source | Pattern NOT applied |
|---|---|---|---|---|
| `Provenance` seven-variant union | **Tagged union with discriminator** (ADR-0033, ADR-0038) | Make illegal states unrepresentable; `match`/`assert_never` enforces exhaustive handling | `[B+S]` | Not flat record with optional fields (half-valid states); not class hierarchy (illegal `Both(both, ...)` becomes possible) |
| `VulnProvenanceAdapter` | **Protocol over inheritance** (ADR-0032) | Duck-typed; adapters don't inherit; matches existing convention | `[B]` | Not ABC (would force base-class import); not with `cost_band + applies_when` Protocol extension (kernel-contract drift — critic Perf-5) |
| `@register_provenance_adapter` | **Plugin/Registry** (mirrors `@register_probe`, `@register_dep_graph_strategy`) | Established seam; the next engineer reads four examples and knows the shape | `[B]` | Not `importlib.metadata` entry-points (supply-chain hygiene — explicit-import per CLAUDE.md); not stored as instances (DI-hostile — critic BP-3) |
| `assemble_provenance` | **Free function with explicit dispatch-order table** | 60 LOC; no DSL, no class; operators predict behavior by reading one tuple | `[B+synth]` | Not Chain-of-Responsibility class (premature pluggability — Phase 7 has 2 adapters); not implicit `dict.items()` iteration (smuggles registration order — critic BP-1); not asyncio fan-out over CPU-bound work (theatrical) |
| Adapter dispatch order | **Strategy via data, not code** (`Final` tuple) | Adding a new `Layer` is an ADR-worthy event; adding a new `Ecosystem` is free (registry-only) | `[synth]` | Not `confidence × cost_band × applies_when` runtime sort (kernel-contract drift); not first-hit-wins (footgun on `Both` detection) |
| `Both` exit shape | **Typed event into the log; orchestrator returns `PendingCoordination`** | ADR-0042 owner is Phase 8; Phase 7 produces evidence, doesn't sequence | `[synth — critic Perf-1, Sec-1]` | Not `MultiPluginCoordinator` class (Phase 8 owns it); not 24h watchdog (Phase 11 owns enforcement); not `asyncio.gather` over child workflows (Phase 8/9 own composition) |
| Dockerfile rewriter engine | **Pure-Python AST manipulation via `dockerfile-parse`** | JVM cold-start tax disqualifies OpenRewrite for this file type; per-workflow budget holds | `[P+B]` | Not OpenRewrite Dockerfile recipes (Phase 7 ADR-0005 records rationale); not regex (lossy on multi-stage) |
| `ShellInvocationTraceProbe` execution surface | **Microvm-isolated via Phase 5 sandbox stack** with `role=Role.PROBE` | First gather-time code execution; threat model is binding | `[S]` | Not in-process reducer (Phase 2 ships no runtime trace today); not `strace` in shared kernel (`CAP_SYS_PTRACE`); not separate `probe-control` process (doubles supervision tree) |
| Dockerfile policy enforcement | **Strict-AND objective-signal gate** | Trust score uses objective signals only; no override flag | `[S]` | Not warning-only (silent regression); not configurable threshold (not honest-confidence) |
| CVE→Chainguard lookup | **Frozen YAML data file in plugin** | One YAML; refresh via PR; CODEOWNERS protects diff | `[B]` | Not Sigstore-bundled signed artifact (rejected per critic Sec-3); not embeddings (string mapping); not live API call (network dependency violates Phase 5 isolation) |
| TCCM `derived_queries` | **Additive band on existing schema** | Separates "evidence to load" from "computation to invoke" — critic roadmap-6 | `[synth]` | Not stuffing function calls into `must_read` (conflates two TCCM bands) |
| Phase 5 spawn role | **Open/Closed via additive enum value** (`SandboxRole`) | One amendment to Phase 5; future task classes add roles without further amendment | `[synth — critic Sec-5]` | Not parallel `probe-control` process (doubles credential boundary count) |
| `RequiresMultiPluginCoordination` event | **Event sourcing — typed Pydantic event into spanning log** (ADR-0034) | Phase 7 produces; Phase 8 projects | `[synth]` | Not in-process state machine (Phase 8 owns); not separate coordinator table (single source of truth is the event log) |

### Patterns considered and deliberately rejected
- **Adapter chain DSL** — Phase 7 has two adapters; YAML-declared chains solve a problem we don't have.
- **`ProvenanceAssemblyBuilder` fluent class** — fluent builder for a free function with named args is 3× the code, zero indirection.
- **Provenance as flat record with optional fields** — re-introduces half-valid states ADR-0033 forbids.
- **`importlib.metadata` entry-point plugin discovery** — CLAUDE.md mandates explicit-import collection (supply-chain hygiene).
- **`MultiPluginCoordinator` class in Phase 7** — Phase 8's job per ADR-0042 (critic-mandated).
- **`vuln.provenance` cache in Phase 7** — ADR-0038 §Tradeoffs deferred to Phase 14; performance's SQLite cache rejected (critic Perf-3).
- **Sigstore-bundled CVE-to-image artifact** — security expanded a one-line roadmap item into 7 components without ADR; deferred to Phase 7 ADR-0007 follow-up story.
- **Chainguard STS/OIDC token client** — Chainguard distroless images are public; the credential class doesn't need to exist (critic Sec-4).
- **`asyncio.gather` over per-stage CPU-bound Dockerfile AST work** — theatrical without `run_in_executor`; performance's claim was wrong (critic Perf "Hot path memoizable" rebuttal).
- **Parallel `probe-control` process** — security's apparatus doubles the supervision tree; `SandboxRole` enum is the open/closed answer (critic Sec-5, roadmap-3).
- **OpenRewrite for Dockerfile transforms** — JVM cold-start tax. Phase 7 ADR-0005 records the engine-split rationale.
- **`MultiStageRefactorRecipe` `asyncio.gather`** — CPU-bound work in async without executor pool; rejected.

### Anti-patterns avoided (toolkit's flag-on-sight)
- **Stringly-typed identifiers** — `Layer`, `Ecosystem`, `BaseImageKind` are `Enum`s; `ImageRef`, `ImageDigest`, `LayerDigest`, `DistroPackage` are newtypes per ADR-0033.
- **Premature pluggability** — `assemble_provenance` is a free function; no chain DSL; no fluent builder.
- **Boolean flag where sum type belongs** — `BaseImageKind` is a `Literal` discriminator, not a `bool is_distroless`. Security's `is_distroless: bool` rejected.
- **Primitive obsession** — `upstream_repo TEXT` in performance's SQLite catalog rejected; the lookup is YAML keyed on `ImageRef` newtype.
- **Anaemic model** — `Both` carries `app_record` + `base_record` but the coordination semantics are *intentionally* offloaded to Phase 8's Planner via an event — Phase 7 owns the data shape, not the behavior. Documented explicitly.
- **Smart constructor bypass** — `Provenance.parse_from_adapter_result(...)` is the only external-data entry. CI fence asserts no `model_construct()` call sites in `src/codegenie/primitives/vuln_provenance/`.
- **Hexagonal claim smuggling I/O into core** — `vuln.provenance` primitive is pure; no SQLite write at the call site. Cache deferred to Phase 14 keeps the kernel pure (critic flagged performance's violation).

---

## Risks (top 5)

1. **Phase 5 `SandboxClient.spawn(role=...)` amendment is the highest-leverage external dependency.** Phase 5's `SandboxClient` was designed for gates; adding a `Role.PROBE` parameter is a Phase 5 amendment Phase 5 hasn't ratified. **Mitigation:** Phase 7 ADR-0003 is filed against Phase 5's ADR set; if Phase 5 rejects the amendment, Phase 7 ships `ShellInvocationTraceProbe` as a `runs_last=True, heaviness="heavy"` probe that calls `SandboxClient.spawn()` with the existing `Role.GATE` (semantically wrong but operationally identical) and accepts the audit-clarity cost. The fallback is documented in the Phase 7 attempt log.
2. **`Both`-variant evidence is never consumed** because Phase 8 lands 3+ months later. The `RequiresMultiPluginCoordination` event accumulates in the spanning log unread. **Mitigation:** Phase 7 ships an operator-facing CLI `codegenie list-coordination-candidates` that walks the spanning log and prints pending `Both` events — operators get visibility without Phase 8. This is a tiny script, not a Phase 8 fragment.
3. **`syft` schema drift breaks `AlpineVulnProvenanceAdapter`** (a future syft drops `locations[].layerID`). **Mitigation:** `SyftSbom.extra="allow"` (Phase 2 deliberate decision); `sbom_verifier.py` cross-checks; `Unknown(reason="sbom_layer_attribution_absent")` surfaces loudly in audit logs.
4. **`ShellInvocationTraceProbe` cost at Phase 10 portfolio scale.** Phase 7 doesn't run portfolio scans, but Phase 10 will. Per-repo microVM boots scale linearly. **Mitigation:** content-cache hit rate ≥ 95% on second run for the same `(repo, image-digest)`. Phase 10 inherits this cost; Phase 8's warm-pool reuse can lower it further. The risk is named in Phase 10's design pipeline, not solved here.
5. **`assemble_provenance` polyglot ambiguity (npm + yarn-berry both resolving).** Phase 7 ships one app adapter per ecosystem; future polyglot repos hit "two app-layer adapters both resolve" with no tiebreaker. **Mitigation:** `_ADAPTER_DISPATCH_ORDER` walks by `Layer`; within a `Layer`, the registry is iterated in `Ecosystem`-enum-sorted order, deterministically. First non-`Unknown` per layer wins. A property test pins this. A follow-on story (deferred) addresses real polyglot detection when a polyglot plugin lands.

---

## Synthesis ledger

### Vertex count

- **Performance design vertices extracted: 38**
  - `[P-v1]` `MultiPluginCoordinator` ships in Phase 7 with PR-ordering policy; `[P-v2]` `CoordinatedOutcome` sum type ships in Phase 7; `[P-v3]` `asyncio.gather` two children pre-Phase-9; `[P-v4]` `VulnProvenancePrimitive` class; `[P-v5]` `VulnProvenanceCache` SQLite-backed cross-process LRU; `[P-v6]` 5-tuple cache key with `repo_snapshot_sha+cve_id+vuln_index_digest+sbom_digest+image_digest`; `[P-v7]` 24h TTL; `[P-v8]` `VulnProvenanceChainAssembler` with `confidence × cost_band × applies_when` ordering; `[P-v9]` extends Adapter Protocol with `cost_band`; `[P-v10]` `BaseImageProbe` in plugin directory, `cache_strategy="content"`; `[P-v11]` `ShellInvocationTraceProbe` as reducer over Phase 2 runtime trace; `[P-v12]` `DockerfileBaseSwapRecipe` via `dockerfile-parse`; `[P-v13]` `MultiStageRefactorRecipe` with `asyncio.gather` per-stage; `[P-v14]` `recommend_distroless` as additive SQL migration to `VulnIndex` with `chainguard_image_catalog` table; `[P-v15]` `catalog_digest` as declared-input token; `[P-v16]` `NpmVulnProvenanceAdapter` ships in Phase 7 plugin, re-exported from Phase 3; `[P-v17]` event variants `BaseImageSwapApplied`, `MultiPluginCoordinated`, `VulnProvenanceComputed`; `[P-v18]` 60 wph cold throughput target; `[P-v19]` 22s warm p95 single-plugin; `[P-v20]` 110s warm p95 Both; `[P-v21]` 92% cache hit on provenance; `[P-v22]` ≥850 MB worker RSS ceiling; `[P-v23]` 60 MB Phase 7 delta; `[P-v24]` `vuln.provenance` p99 ≤ 25 ms warm; `[P-v25]` `crane manifest` for digest resolution; `[P-v26]` `docker buildx --cache-from/--cache-to`; `[P-v27]` cassette replay determinism; `[P-v28]` `tests/fence/test_kernel_frozen.py` extended; `[P-v29]` `multi_plugin_coordinator.yaml` data-driven PR-ordering; `[P-v30]` `coordination.composite`-as-pattern claim; `[P-v31]` `chain.assemble` short-circuit on first non-Unknown; `[P-v32]` Stage 0 pre-warm `docker pull` background prefetch; `[P-v33]` chain order is per-CVE-class; `[P-v34]` SQLite WAL + batch-flush every 250ms / 64 entries; `[P-v35]` `_validate_stage6` runs `docker buildx build --target=runtime` in jail; `[P-v36]` BLAKE3-checksum cache integrity; `[P-v37]` HITL fallback identical for single and Both Unknown; `[P-v38]` `±5% cost ledger ±10% wall-clock` regression budget.

- **Security design vertices extracted: 42**
  - `[S-v1]` `ShellInvocationTraceProbe` runs inside Phase 5 microVM; `[S-v2]` separate `probe-control` process; `[S-v3]` Chainguard credentials short-TTL ≤10 min; `[S-v4]` CVE-to-image lookup signed Sigstore-bundled, digest-pinned; `[S-v5]` `tools/cve-image-lookup.yaml` + `.sigstore` artifact; `[S-v6]` `cveimage/lookup.py + publish.py + quarantine.py`; `[S-v7]` `ChainguardPullToken` SecretStr newtype + logger redaction; `[S-v8]` `registry/chainguard/sts_client.py + pull_proxy.py + token.py`; `[S-v9]` `DockerfilePolicyGate` hard-fail no-override 6 invariants; `[S-v10]` no LLM fallback in Phase 7; `[S-v11]` `multiplugin/coordinator.py` with `CoordinationState` sum + 24h watchdog; `[S-v12]` Phase 11 merge-gate dependency; `[S-v13]` SBOM cross-verifier `sbom_verifier.py`; `[S-v14]` `vuln/provenance/` package under `src/codegenie/`; `[S-v15]` `chain.py` class with deterministic order + AdapterConfidence cross-check; `[S-v16]` 12 audit-chain event types; `[S-v17]` `import_linter` contract extended; `[S-v18]` no overrides flags; `[S-v19]` shell-call-rewriter recipe; `[S-v20]` `gate_isolation_class=shared_kernel` propagation; `[S-v21]` no-credentials-in-microVM fence; `[S-v22]` `Capability tokens` pattern claim; `[S-v23]` `Provenance` 7-variant tagged union; `[S-v24]` `Smart constructor / Newtype` for token/digest; `[S-v25]` ports-and-adapters claim for VulnProvenanceAdapter; `[S-v26]` strict-AND objective-signal gate; `[S-v27]` `Command pattern for privileged actions`; `[S-v28]` `Tagged union for trust state` `CoordinationState`; `[S-v29]` chain assembly question answered in `chain.py` (deterministic); `[S-v30]` `AdapterConfidence` (High|Degraded|Unavailable); `[S-v31]` `BaseImageProbe` static-only in plugin; `[S-v32]` no caching of provenance (ADR-0038 honored); `[S-v33]` `DistrolessBuildGate` + `ShellInvocationDeltaGate`; `[S-v34]` org-allowlisted registries (`cgr.dev/chainguard/*` only); `[S-v35]` SBOM `extra="allow"` accepted; `[S-v36]` policy gate sigstore-fail → orchestrator-refuse-start; `[S-v37]` `is_distroless: bool` on `base_image.json`; `[S-v38]` per-CVE adapter chain assembly determinism property test; `[S-v39]` ADR-0042 cited 6+ times; `[S-v40]` MultiPluginCoordination atomic-or-nothing; `[S-v41]` `ChainguardScope` enum; `[S-v42]` no `--allow-policy-violations` flag.

- **Best-practices design vertices extracted: 45**
  - `[B-v1]` `vuln.provenance` at `src/codegenie/primitives/vuln_provenance/`; `[B-v2]` `Provenance` 7-variant discriminated union with nested `Both`; `[B-v3]` `VulnProvenanceAdapter` Protocol mirrors ADR-0032; `[B-v4]` `@register_provenance_adapter` decorator; `[B-v5]` instances stored in registry (critic-rejected); `[B-v6]` `_REGISTRY: Final[dict[tuple[Layer, Ecosystem], Adapter]]`; `[B-v7]` `assemble_provenance(...)` free function ≤ 80 LOC; `[B-v8]` declared registration order (critic-rejected — replaced by explicit tuple); `[B-v9]` `Layer` Enum + `Ecosystem` Enum; `[B-v10]` `BaseImageProbe` in `src/codegenie/probes/layer_c/` (critic-rejected — moved to plugin); `[B-v11]` `ShellInvocationTraceProbe` in `src/codegenie/probes/layer_d/` (critic-rejected — moved to plugin); `[B-v12]` `dive + strace + docker buildx` ALLOWED_BINARIES additions; `[B-v13]` `NpmVulnProvenanceAdapter` in Phase 3 plugin (additive new file); `[B-v14]` `AlpineVulnProvenanceAdapter` in Phase 7 plugin; `[B-v15]` `DockerfileBaseImageSwapTransform` extends Phase 3 `Transform` ABC; `[B-v16]` `DockerfileMultiStageRefactor`; `[B-v17]` `chainguard_image_recommendation_table.yaml` in plugin's `data/` dir; `[B-v18]` `tccm.yaml` schema reused from Phase 3; `[B-v19]` `derived` query block in TCCM; `[B-v20]` `Plain Pydantic v2 frozen=True extra="forbid"`; `[B-v21]` `mypy --strict` clean; `[B-v22]` `match/assert_never` exhaustive; `[B-v23]` `ProvenanceError(CodegenieError)` hierarchy; `[B-v24]` adapter exception → typed `Unknown(reason="adapter_error")`; `[B-v25]` `--task-class` CLI flag (critic-flagged — synth deferred to plugin inference); `[B-v26]` 3-plugin contract test (Phase 3 + Phase 7 + synthetic); `[B-v27]` net-new Python deps: 1 (`dockerfile-parse`); `[B-v28]` ≥ 90% line coverage on primitive; `[B-v29]` `@pytest.mark.phase07_e2e` opt-in; `[B-v30]` `tests/fence/test_kernel_frozen.py` allowlist extension; `[B-v31]` `tests/fence/test_phase7_no_llm.py`; `[B-v32]` `Newtype every domain primitive`; `[B-v33]` `Tagged union with discriminator`; `[B-v34]` `Protocol over inheritance`; `[B-v35]` `Plugin/Registry mirroring @register_probe`; `[B-v36]` `Smart constructor for external data`; `[B-v37]` `Free function for chain assembly`; `[B-v38]` Caching `vuln.provenance` deliberately avoided (ADR-0038 honored); `[B-v39]` OpenRewrite for Dockerfile deliberately avoided; `[B-v40]` `BaseImageMigrationPlanner` class deliberately avoided; `[B-v41]` `is_distroless: bool` (critic-rejected); `[B-v42]` SyftSbom `extra="allow"`; `[B-v43]` no LLM in Phase 7; `[B-v44]` `tccm.yaml requires:` line additive to Phase 3 plugin; `[B-v45]` Both case emits coordination event for Phase 8.

- **Total: 125 vertices extracted across three designs.**

### Edges

- **AGREE: 22** (e.g., `[P-v4] ≡ [S-v14] ≡ [B-v1]` — all three agree on a `vuln.provenance` primitive; `[P-v9-Provenance] ≡ [S-v23] ≡ [B-v2]` — all three adopt ADR-0038's seven-variant union; `[S-v9] ≡ [B-implied]` Dockerfile policy gate; `[P-v10] ≡ [S-v31] ≡ [B-v10]` `BaseImageProbe` shape — but disagree on location; `[B-v42] ≡ [S-v35]` SBOM `extra="allow"`; etc.)
- **CONFLICT: 14** (the load-bearing decisions):
  1. `MultiPluginCoordinator` ownership — `[P-v1, P-v2, P-v3]` vs `[S-v11, S-v12, S-v40]` vs `[B-v45]` (3-way).
  2. `ShellInvocationTraceProbe` definition — `[P-v11]` reducer vs `[S-v1, S-v2]` microVM-executor vs `[B-v11+dive/strace]` static-wrapper (3-way).
  3. `vuln.provenance` cache — `[P-v5, P-v6, P-v7, P-v34]` SQLite cache vs `[S-v32]` uncached vs `[B-v38]` uncached.
  4. CVE-to-image lookup — `[P-v14, P-v15]` SQL table in `VulnIndex` vs `[S-v4, S-v5, S-v6, S-v34]` Sigstore-bundled vs `[B-v17]` plugin-data YAML (3-way).
  5. Probe location — `[P-v10, P-v11]` in plugin vs `[S-v31]` in plugin vs `[B-v10, B-v11]` in core probes (2-vs-1).
  6. Chain assembly shape — `[P-v8]` policy class with cost_band vs `[S-v15]` class with confidence cross-check vs `[B-v7, B-v8]` free function over dict.items() (3-way).
  7. Chainguard auth — `[P-implied-no-auth]` vs `[S-v3, S-v7, S-v8]` full STS apparatus vs `[B-implied-no-auth]`.
  8. Phase 3 plugin edit story — `[P-v16]` re-export inversion vs `[S-implied]` no edits vs `[B-v13, B-v44]` one new file + one line.
  9. `--task-class` CLI flag — `[B-v25]` add flag vs (others) infer.
  10. `Both` PR ordering policy — `[P-v29]` `multi_plugin_coordinator.yaml` data vs `[S-v40]` atomic-or-nothing hardcoded vs `[B-v45]` defer to Phase 8.
  11. Adapter registry storage — `[B-v5]` instances vs (critic-mandated) classes.
  12. Adapter Protocol surface — `[P-v9]` extends with `cost_band` vs `[S-v25, S-v30]` adds `AdapterConfidence` vs `[B-v3]` ADR-0032 verbatim.
  13. `_ADAPTER_DISPATCH_ORDER` policy — `[P-v33]` per-CVE-class vs `[S-v29]` deterministic vs `[B-v8]` dict insertion order.
  14. `MultiStageRefactor` parallelism — `[P-v13]` `asyncio.gather` vs (others) synchronous.
- **COMPLEMENT: 18** (e.g., `[S-v9] + [P-v12]` policy gate runs over recipe output; `[S-v13] + [B-v14]` SBOM verifier composes with Alpine adapter; `[S-v33] + [P-v35]` distroless-build-gate runs after recipe applies; `[B-v18] + [S-v19]` shell-rewriter as plugin recipe; `[S-v16] + [P-v17]` audit events are additive; etc.)
- **SUBSUME: 9** (e.g., `[P-v14] ⊃ [B-v17]` — SQL table subsumes YAML, but YAML wins per critic Perf-4; `[S-v8] ⊃ [P-no-auth]` — STS apparatus subsumes no-auth, but no-auth wins per critic Sec-4; `[S-v11] ⊃ [B-v45]` — coordinator-class subsumes event-emission, but event wins per critic Perf-1/Sec-1; etc.)

### Conflict-resolution table

| # | Dimension | `[P]` picks | `[S]` picks | `[B]` picks | **Winner** | Exit-fit | Roadmap-fit | Commit-fit | Critic-fit | Pattern-fit | Sum |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Multi-plugin coordinator ownership | `MultiPluginCoordinator` class | `multiplugin/coordinator.py` + watchdog | Defer to Phase 8 via event | **`[B]`** | 3 | 3 | 3 (veto: ADR-0042) | 3 | 3 | **15** |
| 2 | `ShellInvocationTraceProbe` definition | reducer over Phase 2 trace | microVM-isolated executor | `dive`+`strace` wrapper | **`[S]`** | 3 | 2 | 3 | 3 | 2 | **13** |
| 3 | `vuln.provenance` cache | SQLite cross-process cache | uncached | uncached | **`[S]/[B]`** | 3 | 3 | 3 (veto: ADR-0038) | 3 | 3 | **15** |
| 4 | CVE-to-image lookup shape | SQL table in `VulnIndex` | Sigstore-bundled artifact | Plugin-data YAML | **`[B]`** | 2 | 3 | 3 | 3 (critic Sec-3) | 2 | **13** |
| 5 | Probe location (core vs plugin) | in plugin | in plugin | in `src/codegenie/probes/` | **`[P]/[S]`** | 3 | 3 | 3 (veto: ADR-0031) | 3 | 3 | **15** |
| 6 | Chain assembly shape | class with `cost_band` policy | class with confidence-cross-check | free function over dict.items() | **`[B]` + synth (explicit tuple)** | 3 | 3 | 3 | 3 (critic BP-1) | 3 | **15** |
| 7 | Chainguard auth | no auth (implicit) | full STS/token apparatus | no auth (implicit) | **`[P]/[B]`** | 3 | 2 | 3 (veto: Chainguard public) | 3 (critic Sec-4) | 2 | **13** |
| 8 | Phase 3 plugin "edit" story | re-export inversion | no edit | one new file + one `requires:` line | **`[B]`** (synth — file path explicitly allowlisted) | 3 | 3 | 2 | 3 | 3 | **14** |
| 9 | `--task-class` CLI flag | (silent) | (silent) | add flag | **synth: no flag; infer from plugin resolution** | 3 | 3 | 3 | 2 (critic BP open Q5) | 2 | **13** |
| 10 | `Both` PR ordering | `multi_plugin_coordinator.yaml` data | hardcoded atomic-or-nothing | defer to Phase 8 | **`[B]`** | 3 | 3 | 3 (veto: ADR-0042) | 3 | 3 | **15** |
| 11 | Adapter registry storage | (n/a) | (n/a) | instances | **synth: classes (DI-friendly)** | 3 | 2 | 3 | 3 (critic BP-3) | 3 | **14** |
| 12 | Adapter Protocol surface | + `cost_band` + `applies_when` | + `AdapterConfidence` | ADR-0032 verbatim | **`[B]+[S]`** (keep `confidence()`, reject `cost_band`) | 3 | 3 | 3 | 3 (critic Perf-5) | 3 | **15** |
| 13 | Dispatch order policy | per-CVE-class | deterministic order | dict insertion order | **synth: explicit `Final` tuple** | 3 | 3 | 3 | 3 (critic BP-1) | 3 | **15** |
| 14 | `MultiStageRefactor` parallelism | `asyncio.gather` | synchronous | synchronous | **`[S]/[B]`** | 2 | 2 | 2 | 3 (theatrical claim) | 2 | **11** |

### Shared blind spots considered

The critic flagged three shared blind spots all three designs share. For each:

1. **"All three add new top-level packages to `src/codegenie/` but treat wiring lines as 'not edits.'"** **Carried forward as a binding constraint.** The Phase 7 fence allowlist (§"Test plan → Fence allowlist") enumerates *every* byte-edit Phase 7 is permitted to make to existing files. Any other touch is a CI failure. This makes "additive" mechanically enforced rather than aspirational.
2. **"All three treat `applies_to_tasks=["distroless-migration"]` as enough to gate probe execution cost at Stage 0."** **Acknowledged and deferred.** Phase 7 does not solve portfolio-scale dispatch cost — Phase 10 will. The risk is named explicitly (§Risks #4) and the cost model in §Resource & cost profile honestly admits `ShellInvocationTraceProbe` is heavy at portfolio scale. Phase 8's warm-pool reuse is the planned mitigation; Phase 10's design pipeline must explicitly address this rather than inheriting an unsolved problem.
3. **"All three trust the syft SBOM at the byte level for layer attribution."** **Partially addressed.** Security's `sbom_verifier.py` cross-checks `locations[].layerID` against image manifest digests — adopted into the synthesis (it lives in `src/codegenie/primitives/vuln_provenance/sbom_verifier.py`). The byte-level trust beyond layer attribution (e.g., poisoned `extra="allow"` fields) is *not* fully solved — `SyftSbom` Pydantic model honors Phase 2's deliberate `extra="allow"` decision; adversarial fields land in unknown space and are not consumed by the typed adapter logic. This is a Phase 12 concern (validation depth) and is documented as a deferred surface.

### Pattern reconciliation

| Pattern | Performance | Security | Best-practices | **Synthesis** |
|---|---|---|---|---|
| `Provenance` 7-variant union | tagged union | tagged union | tagged union, nested `Both` | **nested `Both` (`[B]`); ADR-0038 verbatim** |
| Adapter contract | Protocol + `cost_band + applies_when` | Protocol + `AdapterConfidence` | Protocol mirror of ADR-0032 | **Protocol + `confidence()` (`[B]+[S]`); reject `cost_band` per critic Perf-5** |
| Registry storage | not specified | not specified | instance at decorator | **class at decorator (DI-friendly per critic BP-3)** |
| Chain assembly | class with policy table | class with cross-check | free function over `dict.items()` | **free function with explicit `Final` tuple of dispatch order (rejects implicit `dict` order per critic BP-1)** |
| Probe placement | in plugin | in plugin | in core `src/codegenie/probes/` | **in plugin (ADR-0031 explicit; critic BP-5)** |
| `Both` ownership | coordinator class ships in Phase 7 | coordinator + watchdog in Phase 7 | defer to Phase 8 via event | **defer to Phase 8 (`[B]`; critic Perf-1/Sec-1; ADR-0042 veto)** |
| Caching | SQLite cross-process | none | none | **none (`[S]+[B]`; ADR-0038 §Tradeoffs veto)** |
| Sandbox role | new isolation tech (none) | new `probe-control` process | (n/a) | **additive `SandboxRole` enum on existing `SandboxClient` (synth — critic Sec-5/roadmap-3)** |
| Lookup artifact | SQL table | Sigstore-bundled | YAML in plugin | **YAML in plugin (`[B]`; critic Sec-3)** |
| Chainguard auth | no auth | STS+pull-proxy | no auth | **no auth (`[P]+[B]`; critic Sec-4 — public images)** |
| Dockerfile recipe engine | `dockerfile-parse` | `dockerfile-parse` | `dockerfile-parse` | **`dockerfile-parse` (`[P]+[S]+[B]`)** |
| Dockerfile policy gate | (not present) | strict-AND no-override 6 invariants | (not present) | **strict-AND 6 invariants (`[S]`)** |
| Adapter exception handling | retry envelope + event | (silent) | typed `Unknown(reason="adapter_error")`; others propagate | **typed catch + propagate per Rule 12 (`[B]`)** |
| TCCM band for derived queries | (n/a) | `must_read: vuln.provenance(...)` | `derived` block in TCCM | **`derived_queries:` band — additive Pydantic schema field (synth; critic roadmap-6)** |
| Anti-pattern: `is_distroless: bool` | (n/a) | present | (n/a) | **reject — `BaseImageKind` discriminator is the sum-type answer (critic toolkit)** |
| Anti-pattern: smart constructor bypass via `model_construct()` | (not addressed) | (not addressed) | (not asserted) | **CI fence asserts no `model_construct()` in `vuln_provenance/` tree (critic toolkit)** |

### Departures from all three inputs

Documenting positions none of the three proposed:

1. **`_ADAPTER_DISPATCH_ORDER` as a `Final` tuple instead of either implicit `dict` order (best-practices) or runtime-sorted policy (performance) or unspecified (security).** This is a synthesis position that closes critic BP-1 cleanly. None of the three proposed it explicitly.
2. **Registry stores classes, not instances.** Best-practices stored instances. The critic landed BP-3 hard; synthesis flips this.
3. **`SandboxRole` additive enum on Phase 5's existing `SandboxClient.spawn(...)`.** Security shipped a parallel `probe-control` process; performance ignored isolation entirely; best-practices punted with "Phase-2-shaped sandbox." Synthesis picks the minimal Phase 5 amendment — one parameter — and records it in Phase 7 ADR-0003.
4. **`derived_queries:` as a new TCCM band** instead of embedding function calls in `must_read` (security) or `derived:` (best-practices). Critic roadmap-6 made this an explicit need; synthesis adds it as a typed additive band.
5. **Exit code 8 ("requires multi-plugin coordination — awaiting Phase 8 Planner")** and a `coordination-summary.yaml` artifact when `Both` is returned. None of the three named this CLI shape; synthesis introduces it to make the Phase 7 stops here behavior operator-legible.
6. **`codegenie list-coordination-candidates` CLI subcommand.** None of the three proposed this; synthesis adds it so operators can read pending `Both` events out of the spanning log in the months before Phase 8 lands.
7. **Phase 7 fence allowlist enumerated as 10 specific byte-edit allowances.** None of the three enumerated explicitly; synthesis makes "additive" mechanically defined per critic roadmap-4.
8. **`MultiStageRefactorTransform` is synchronous, not `asyncio.gather`-parallelized.** Performance shipped the async fan-out; critic flagged it as theatrical. None of the others addressed it; synthesis takes the simpler shape.

---

## Exit-criteria checklist

Per the roadmap §Phase 7:

| Exit criterion | Satisfied by |
|---|---|
| Both task classes run from the same orchestration | Phase 3 `RemediationOrchestrator` is unchanged; resolver dispatches to the new plugin when scope matches. `tests/e2e/test_distroless_migration_e2e.py` exercises this end-to-end. |
| Existing plugins and stable existing behavior unchanged | Fence allowlist enumerates the 10 permitted byte-edits; `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` asserts byte-identity for everything else. `bench/vuln-remediation/` cassette replay gates merge. |
| Any shared primitive added is bounded, additive, ADR-backed, regression-tested | `vuln.provenance` lands at `src/codegenie/primitives/vuln_provenance/` under Phase 7 ADR-0001 (Adopt `vuln.provenance` as bounded additive core primitive). Property tests + unit + integration coverage ≥ 90% line / 80% branch. |
| New probes ship (`BaseImageProbe`, `ShellInvocationTraceProbe`) | Both in `plugins/distroless-migration--node--npm/probes/`. |
| New Skills (distroless-migration playbook) ship | `plugins/distroless-migration--node--npm/skills/` with YAML-frontmatter recipe-selection hints. |
| New recipes (Dockerfile base-image swap, multi-stage refactor) ship | `DockerfileBaseImageSwapTransform` + `DockerfileMultiStageRefactorTransform` in plugin's `recipes/`. |
| `vuln.provenance` primitive lands per ADR-0038 | Seven-variant Pydantic discriminated union, app-layer adapter (`NpmVulnProvenanceAdapter`) + base-image adapter (`AlpineVulnProvenanceAdapter`), `Both` exercised in fixtures. |
| `Both` variant exercised | `tests/e2e/test_both_provenance_emits_coordination_event_e2e.py` + golden `tests/golden/provenance/both.json`. |
| Adapter-chain assembly question answered for Phase 7 | `assemble_provenance` free function with explicit `_ADAPTER_DISPATCH_ORDER` tuple. |
| End-to-end migration test passes | `tests/e2e/test_distroless_migration_e2e.py` gated by `@pytest.mark.phase07_e2e`. |
| `bench/migration-chainguard-distroless/cases/` ≥ 10 cases with `bench_score.lower_bound_95 ≥ tier_threshold[bronze]` (per Phase 6.5 exit) | New bench cases added (3 single-stage swap, 3 multi-stage refactor, 2 `Both`-variant, 1 already-distroless no-op, 1 universal-fallback `Unknown`). |

---

## Load-bearing commitments check

| §2 commitment | Honored by |
|---|---|
| §2.1 No LLM in gather pipeline | `import_linter` contract extended to `src/codegenie/primitives/vuln_provenance/` and `plugins/distroless-migration--*/`. Fence asserts. |
| §2.2 Facts, not judgments | Probes report typed slices (`base_image: {kind: 'alpine'}`, `shell_invocations: {count: 3}`). Judgments stay in Stage 3 planning. `BaseImageProbe` uses a `Final` marker catalog, never heuristics. |
| §2.3 Honest confidence | Every adapter implements `confidence() -> AdapterConfidence`. Provenance variants carry typed `reason`. `Unknown(reason="sbom_layer_attribution_absent")` surfaces loudly. |
| §2.4 Determinism over probabilism | All recipes are deterministic `Transform` subclasses. Property test pins idempotence. No LLM path in Phase 7. |
| §2.5 Extension by addition | Fence allowlist enumerates the 10 byte-edits explicitly; `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` enforces. `vuln.provenance` adopted under Phase 7 ADR-0001 per ADR-0039. |
| §2.6 Organizational uniqueness as data | `chainguard_image_recommendation_table.yaml` is data; refresh via PR; Skills are YAML-frontmatter. |
| §2.7 Progressive disclosure | TCCM `must_read` indexes (not inlines) Dockerfile, SBOM, base-image slice. `derived_queries:` separates "computation to invoke" from "evidence to load" (new band per critic roadmap-6). |
| §2.8 Humans always merge | Workflow ends at PR creation (or `RequiresMultiPluginCoordination` event for `Both`); no auto-merge anywhere. |
| §2.9 Cost is observable end-to-end and bounded | Per-workflow event log carries cost-ledger entries; LLM spend is zero (fence-asserted); Phase 6.5 bench replay enforces byte-equality on cost ledger. |

---

## Roadmap coherence check

**What prior phases established that this depends on:**
- Phase 0 — Probe ABC (frozen per ADR-0007); `@register_probe` decorator; `tests/fence/test_kernel_frozen.py` infrastructure; explicit-import collection.
- Phase 1 — `package.json` / `package-lock.json` parsers (consumed by `NpmVulnProvenanceAdapter`); identifier newtypes module.
- Phase 2 — `syft-sbom.json` raw artifact with `locations[].layerID`; `image-digest:<resolved>` declared-input token; `image_digest_resolver` capability; `ALLOWED_BINARIES` infrastructure.
- Phase 3 — `Transform` ABC; `RemediationOrchestrator`; `ApplyContext`; `TrustScorer`; `plugins/` directory shape; `@register_signal_kind`; `Applicability.NotApplicable(reason=CVE_NOT_IN_APP_LAYER)` refuse-mode shape (ADR-0038 consequence); typed exception hierarchy; `EventLog` with two streams (workflow-internal vs spanning).
- Phase 5 — `SandboxClient.spawn(...)`; microVM stack (Firecracker/gVisor/Lima); strict-AND `Gate` ABC; `gate_isolation_class` annotation; eBPF host-side trace view; ADR-0014 three-retry envelope.
- Phase 6 — LangGraph subgraph topology per plugin; ADR-0010 sum-type discipline (AdapterConfidence).
- Phase 6.5 — `bench/{task-class}/` directory contract; `@register_task_class`; `bench/migration-chainguard-distroless/cases/` skeleton; cassette-replay infrastructure.

**What this establishes that later phases need:**
- Phase 8 (Planner) — `RequiresMultiPluginCoordination` event consumer; ADR-0042 coordination ownership; `vuln.provenance` primitive for routing; `assemble_provenance` callable from Stage 3.
- Phase 9 (Temporal) — event-log spanning stream model (Phase 7 emits typed events that survive to spanning log).
- Phase 10 (Stage 0/1) — `vuln.provenance` primitive for portfolio-scale eligibility scoring; `BaseImageProbe` slice; the portfolio-scale cost story Phase 7 honestly admits.
- Phase 11 (first PR at scale) — `Both`-coordination merge gate enforcement (consuming Phase 7's `RequiresMultiPluginCoordination` events plus Phase 8's Planner output).
- Phase 14 (Continuous gather + caching) — `vuln_provenance_cache` keyed on `(sbom_digest, vuln_index_digest)` per ADR-0038 §Tradeoffs.
- Phase 15 (agentic recipe authoring) — pattern for adding new task classes by adding plugins, not editing kernel; the third real test of extension-by-addition.

**New ADRs implied (titles only — architect skill drafts them):**
- Phase 7 ADR-0001 — Adopt `vuln.provenance` as bounded additive core primitive (per ADR-0039).
- Phase 7 ADR-0002 — Adopt `dockerfile-parse` as the Dockerfile recipe engine; defer OpenRewrite Dockerfile recipes.
- Phase 7 ADR-0003 — Amend Phase 5 `SandboxClient.spawn(...)` with `role: SandboxRole` parameter (additive enum; default `Role.GATE`).
- Phase 7 ADR-0004 — `Both` provenance routes to a typed `RequiresMultiPluginCoordination` event; coordination ownership stays Phase 8 per ADR-0042.
- Phase 7 ADR-0005 — Engine split: `dockerfile-parse` for Dockerfile recipes, OpenRewrite for language-level transforms.
- Phase 7 ADR-0006 — Chainguard credentials NOT required in Phase 7 (public images); deferred to a future ADR if private-registry support arrives.
- Phase 7 ADR-0007 — CVE-to-image lookup ships as plugin-internal YAML; Sigstore-bundled signed-artifact upgrade deferred to future story.
- Phase 7 ADR-0008 — TCCM `derived_queries:` band (additive Pydantic schema field) separates derived-query invocations from `must_read` evidence-load entries.
- Phase 7 ADR-0009 — Adapter-chain assembly is a free function over an explicit `_ADAPTER_DISPATCH_ORDER` `Final` tuple; registration order is NOT load-bearing.
- Phase 7 ADR-0010 — `@register_provenance_adapter` stores adapter classes (not instances); construction is dispatch-time with DI-aware kwargs.
- Phase 7 ADR-0011 — `dive` and `docker buildx` added to `ALLOWED_BINARIES`; `strace` is explicitly NOT added.
- Phase 7 ADR-0012 — Phase 7 fence allowlist of byte-edits to existing files (enumerated 10 paths); defines what "additive" mechanically means.

---

## Open questions deferred to implementation

1. **Exact shape of the `coordination-summary.yaml` artifact when exit code 8 fires.** Phase 7 needs a typed schema, but the precise field set (`prs_pending: []` vs `pending_branches: []` vs a third shape) depends on Phase 8's Planner interface — which doesn't exist yet. Defer to first story under Phase 7 implementation; document the shape as Pydantic schema with `extra="forbid"` once Phase 8's contract surfaces.
2. **Whether `codegenie list-coordination-candidates` should write to stdout, a YAML report, or both.** Operator ergonomics question; pick at story-writing time. Default to YAML for parseability + stdout summary.
3. **`AdapterFactory` DI kwarg names.** The synthesis says "well-known dependency names" (`sbom_reader`, `logger`, `image_manifest_cache`) — exact set to be pinned in Phase 7 ADR-0010's draft.
4. **`_ADAPTER_DISPATCH_ORDER` for the `Layer.RUNTIME` family.** Phase 7 ships no runtime adapter; the order entry is reserved. First runtime adapter (JRE-bundled, in a future phase) will exercise it. Phase 7 includes a property test that asserts the empty runtime layer behaves correctly.
5. **`bench/migration-chainguard-distroless/cases/` expansion to 10 cases.** Phase 6.5 ships 3 seed cases; Phase 7 expands to 10. Exact case distribution (% single-plugin vs `Both` vs `Unknown`) to be calibrated against the bench tier threshold during implementation.
6. **CI matrix split for `@pytest.mark.phase07_e2e`.** Whether to run on every PR (per-label opt-in) or only on `main`-merge is an ops-team call; the design supports both and the harness gate (`--privileged` Linux runner) is the constraint, not the design.
7. **Story ordering for the Phase 7 fence amendment.** The fence test extension must land *before* any of the new files exist (otherwise the first PR adding new files fails CI for being unallowlisted). Plan: Phase 7 story S0 lands the fence amendment with an empty Phase 7 allowlist; subsequent stories add files and grow the allowlist row-by-row, with each addition gated by ADR review.

---

**End of design of record.**

---

# Amendment A — distroless-migration gather / transform / refusal gaps (2026-05-20)

**Status:** Accepted amendment. Additive to the design of record above — no
section above this line is altered.
**Trigger:** Design review found the gather pipeline does not collect the
context a *correct* distroless migration needs. A naive `FROM` swap can ship an
image that builds clean, passes the gate, merges — then fails at runtime
(missing shell, missing toolchain, dropped secret-acquisition path, redundant
layers). The original design's `ShellInvocationTraceProbe` observes shell *during
the build*; `DockerfilePolicyGate` checks invariants *after* the recipe runs.
Neither inventories what the source repo actually does, nor what the target
Chainguard image already provides.

## A.1 — Governing principle

Phase 7 must, for every migration it attempts, either **gather enough context to
transform the case correctly**, or **refuse with typed evidence** (a
`RemediationOutcome.PendingHumanReview` variant naming the exact source
location). Shipping a broken image is the one unacceptable outcome. Every gap
below resolves to one of three dispositions:

- **GATHER** — a new probe slice the recipe/gate consumes to transform correctly.
- **REFUSE** — a typed refusal variant when the case cannot be transformed
  deterministically (M2 taxonomy).
- **WARN** — a non-blocking finding surfaced in the PR description (M3).

## A.2 — Gap inventory

| Gap | Summary | Disposition | Component | ADR | Step |
|---|---|---|---|---|---|
| G1 | Source-side secret acquisition: `--mount=type=secret`, `ARG`/`ENV` token injection, `COPY .npmrc`/`.yarnrc`, auth-header `curl`/`wget`, `COPY`'d external scripts | GATHER + REFUSE (opaque scripts) | `DockerfileSecretPatternProbe` | 0018 | 13 |
| G2 | Target Chainguard image content inventory: preinstalled packages, `nonroot` user, CA certs, `shell_present: false` → drop redundant `RUN apk add` | GATHER | `TargetImageContentProbe` | 0019 | 13 |
| G3 | Native modules (`binding.gyp`, `*.node`) + build-time-only toolchain (`gcc`, `make`, `python3`) vs runtime libraries | GATHER | `apk/apt` classification catalog + `NodeManifestProbe` native-module slice | 0020 | 14 |
| G4 | Runtime shell-out from app code (`child_process.exec`/`spawn`, `execSync`) — distroless has no `/bin/sh` at runtime | GATHER + REFUSE (`src/**` hits) | `RuntimeShellInvocationProbe` (tree-sitter JS/TS) | 0021 | 15 |
| G5 | Shell-form `ENTRYPOINT`/`CMD`, `sh -c` wrappers, `npm start` | GATHER + REFUSE (non-deterministic) | recipe transformation contract | 0025 | 16 |
| G6 | Healthcheck `curl`/`wget` + K8s/Compose/helm `exec` probes — migration blast-radius widens beyond the `Dockerfile` | GATHER | `ContainerProbeCompatProbe` over deployment manifests | 0022 | 15 |
| G7–G10 | uid/user delta (root→`nonroot` 65532), PID-1/signal handling, filesystem assumptions (`/etc/passwd`, `/tmp`), locale/timezone | GATHER + WARN | `RuntimeCompatProbe` | 0023 | 15 |
| G11 | Multi-architecture coverage delta (source supports armv7; Chainguard may not) | GATHER + REFUSE (arch loss) | `BaseImageProbe` extension | 0024 | 17 |
| G12 | Test-infra shell-out causes false-negative build-gate failures — classify `tests/**` advisory vs `src/**` blocking | GATHER | `RuntimeShellInvocationProbe` path classification | 0021 | 15 |
| G13 | Pre-existing patches in a non-public mirror base image — the CVE may already be patched differently | GATHER + WARN | `BaseImageProbe` non-public-registry detection → `AdapterConfidence.Degraded` | 0024 | 17 |
| G14 | Image-size delta (multi-stage refactor can balloon the image) | WARN | migration observability event | 0027 | 18 |
| G15 | Rollback runbook in the PR (redeploy `pre_migration_image_ref`) | WARN | migration observability | 0027 | 18 |
| G16 | Compliance attestation diff (Chainguard ships signed SBOM + SLSA provenance) | WARN | migration observability | 0027 | 18 |
| G17 | Cross-CVE caching of the heavy `ShellInvocationTraceProbe` (keyed `Dockerfile`+`package.json`+`image-digest`) | GATHER (perf) | content-cache reuse | 0027 | 18 |
| M1 | `MigrationConfidence` aggregation — single sum-type rollup the orchestrator can refuse against when any probe/adapter is `Degraded` | GATHER | `MigrationConfidence` aggregator | 0026 | 17 |
| M2 | Refusal taxonomy — closed `RemediationOutcome.PendingHumanReview` variant set, each with a structured source-location payload | REFUSE | `outcomes.py` additive variants | 0025 | 16 |
| M3 | Structured `transformations_applied` list for the PR description (what was swapped/dropped/rewritten) | WARN | migration observability | 0027 | 18 |

## A.3 — Departures the amendment makes from the design of record

1. **The migration's blast radius is not just the `Dockerfile`.** G6 widens it to
   K8s/Compose/helm deployment manifests. `DeploymentProbe` (Phase 2) already
   *locates* these; the new `ContainerProbeCompatProbe` *analyses* them. A
   migration PR may now include a deployment-manifest change.
2. **The recipe consumes gather output it did not before.** `DockerfileBaseImageSwapTransform`
   and `DockerfileMultiStageRefactorTransform` (design-of-record §9–10) gain
   typed inputs — `SecretPatternInventory`, `TargetImageContents`,
   `NativeModuleSlice` — and gain the ability to **refuse**. The recipe is no
   longer "always produces a diff"; it produces a diff *or* a typed refusal.
   This amends the still-`Ready` recipe stories S10-01/S10-02/S10-03.
3. **`tree-sitter-bash` is deliberately NOT added.** G1 detects that a `COPY`'d
   shell script is *invoked* and classifies it `opaque → refuse`; it does not
   parse the script. G4 uses the existing `javascript`/`typescript` grammars
   (`src/codegenie/grammars/lock.py`). Net-new runtime deps from this amendment:
   `crane` (CLI, `ALLOWED_BINARIES`, ADR-0028) — zero new Python packages.
4. **`ALLOWED_BINARIES` gains `crane`** (target-image manifest + SBOM fetch for
   G2), in addition to the design-of-record's `dive` + `docker buildx`.
5. **ADR-0009's byte-edit allowlist is amended** (ADR-0029) to enumerate every
   new source file this amendment's stories create — the fence stays the
   mechanical definition of "additive."

## A.4 — Scope, sequencing, non-goals

- **In scope:** all gather probes (G1–G13), the refusal taxonomy (M2), the
  confidence rollup (M1), and the observability bundle (G14–G17, M3).
- **Sequencing:** the gather probes (Steps 13–15) must land *before* the
  recipe stories (existing Step 10) execute — the recipes consume the new
  slices. Steps 16–18 layer after. See `High-level-impl.md` Steps 13–18.
- **Non-goals (unchanged):** no LLM anywhere; no multi-plugin coordination
  (Phase 8); no signed-artifact publishing (deferred ADR). The amendment adds
  *gather depth and refusal honesty*, not new autonomy.

**End of Amendment A.**
