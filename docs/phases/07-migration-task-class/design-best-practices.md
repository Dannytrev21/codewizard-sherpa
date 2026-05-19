# Phase 7 — Add migration task class (Chainguard distroless): Best-practices design

**Lens:** Best practices — idiomatic, maintainable, conventional, well-tested.
**Designed by:** Best-practices design subagent
**Date:** 2026-05-19

---

## Lens summary

Phase 7 is the *first* test of extension-by-addition under realistic conditions. The right answer under the best-practices lens is: **ship the new task class as boring, idiomatic addition** — new probes in the established layer dirs, a new plugin in the already-shaped `plugins/{task}--{lang}--{build}/` bundle, the `vuln.provenance` primitive in its own module-level package mirroring `src/codegenie/depgraph/`, adapters registered the same way `@register_dep_graph_strategy` is registered today. The discipline ADR-0033 lays down (newtype every domain primitive; Pydantic discriminated unions for state machines; smart constructors for parseable values) is the spine. Premature pluggability — adapter chains, chain-assembly DSLs, "future-proof" multi-tenant manifests — is the trap this lens is sharpest at refusing. Phase 7 ships *one* base-image adapter and *one* app-layer adapter end-to-end; the chain assembly is a small typed function that calls them in a documented order. Anything fancier than that is Phase 8's Planner problem, not Phase 7's.

The phase's load-bearing risk is **silent edits to Phase 3–6.5 code masquerading as addition**. The defense is a CI fence that diffs Phase 3–6.5 file lists against an ADR-anchored allowlist (Phase 3 already ships `tests/fence/test_kernel_frozen.py` — Phase 7 extends it with its own additive allowlist row). The second risk is **provenance variants becoming a footgun**: `Both` is the headline case and is easy to write wrong unless `Both.app_record` and `Both.base_record` are typed sub-unions with their own discriminator, which we adopt verbatim from ADR-0038's sketch.

---

## Conventions honored

- **No LLM in the gather pipeline → ADR-0005 / fence CI.** New probes (`BaseImageProbe`, `ShellInvocationTraceProbe`) live under `src/codegenie/probes/layer_c/` and `src/codegenie/probes/layer_d/` and obey the frozen Probe ABC (Phase 0 ADR-0007). The Phase 0 fence (`tests/unit/test_pyproject_fence.py`) is extended only to whitelist the *new* tools (`dockerfile-parse`, `dive`); the LLM blocklist stays intact. `import-linter` (`make lint-imports`) gets a new contract `phase7_no_llm_in_plugin` for `plugins/distroless-migration--node--npm/` mirroring Phase 3's `vulnerability-remediation--node--npm` contract.
- **Facts, not judgments → §2 of `production/design.md`.** Probes capture evidence (`shell_invocations: 0`, `base_image_ref: cgr.dev/chainguard/node:latest@sha256:…`). Judgments ("this repo is migration-ready") are Phase 8's Planner, never a probe output. The `BaseImageProbe` reports `base_image_kind: Literal["distroless", "alpine", "debian-slim", "debian", "ubuntu", "scratch", "unknown"]` — a typed sum, not a free-form string.
- **Extension by addition → ADR-0031 + ADR-0039.** Zero edits to existing plugins. The Phase 3 plugin (`vulnerability-remediation--node--npm`) is touched exactly once: a new TCCM `requires:` line picks up `vuln.provenance` from the shared primitive, and that line is itself optional (Phase 3's plugin works without it; the line just sharpens its Stage-1 routing once Phase 10 lands). Even that edit is gated by ADR-0039's bounded-primitive exception, recorded in this phase's ADR-0001 ("Adopt `vuln.provenance` as a bounded additive core primitive — first home").
- **Newtype identifiers → ADR-0033.** Every new domain primitive uses `typing.NewType`: `ImageRef`, `ImageDigest`, `LayerDigest`, `BaseImageKind` (wrapper around the `Literal` above), `DistroPackage` (a `BaseModel`, not a raw string — has its own structured fields), `ShellPathRef`, `MigrationCandidateId`. The pattern matches Phase 3's `src/codegenie/types/identifiers.py` exactly; new IDs land in the same module.
- **Tagged unions for state → ADR-0033 + ADR-0038.** The seven `Provenance` variants ship as a Pydantic discriminated union (`Annotated[…, Discriminator("kind")]`) under `src/codegenie/primitives/vuln_provenance/types.py`. `Both` is a *nested* discriminated union — its `app_record` field is `AppDirect | AppTransitive | AppVendored` (own discriminator) and `base_record` is `BaseImage | RuntimeBundled` (own discriminator). Exhaustiveness is enforced via `match`/`assert_never` in every consumer; `mypy --strict` catches missing arms at PR time.
- **Composition over inheritance.** `VulnProvenanceAdapter` is a `Protocol` (structural duck-typing), not an ABC. Mirrors `DepGraphAdapter` in ADR-0032 exactly. The chain-assembly function `assemble_provenance(...)` is a plain free function — no `ChainAssembler` class, no builder, no DSL.
- **Plain data over clever types.** TCCMs stay YAML. Plugin manifests stay YAML. Adapter registration is a one-line decorator. No metaclasses, no DI containers, no abstract factories.
- **`mypy --strict`, no `dict[str, Any]` across boundaries.** Every public function in `src/codegenie/primitives/vuln_provenance/` takes and returns typed values. `syft` output is parsed at the boundary into `SyftSbom` (Pydantic, `extra="allow"` per Phase 2 S5-04 — syft schema evolves outside our control); the adapter sees `SyftSbom`, never raw JSON.
- **Match the existing convention.** Phase 3's `src/codegenie/transforms/` package shape — `protocols.py`, `registry.py`, `errors.py`, typed sum types in `types.py` — is the template `src/codegenie/primitives/vuln_provenance/` follows. Phase 6.5's `@register_task_class` decorator shape is the template `@register_provenance_adapter` follows.

---

## Goals (concrete, measurable)

| # | Goal | Source |
|---|---|---|
| G1 | **Zero edits to Phase 3–6.5 plugin code or stable existing behavior.** The CI fence `tests/fence/test_kernel_frozen.py` (Phase 3) extends its allowlist additively with `vuln.provenance` import sites only. A PR that modifies `plugins/vulnerability-remediation--node--npm/` outside the allowlisted `tccm.yaml requires:` line fails CI with the file path named. | `[B+synth]` |
| G2 | **Phase 3–6.5 regression suite green.** `make check` plus the full `bench/vuln-remediation/` replay (Phase 6.5 cassettes) runs as a hard pre-merge gate. Any red is a Phase 7 blocker. | `[B]` |
| G3 | **`vuln.provenance` primitive lands at `src/codegenie/primitives/vuln_provenance/` with the full seven-variant `Provenance` discriminated union.** Pydantic v2 `frozen=True, extra="forbid"`; smart constructor `Provenance.parse(...)` validates external data; `mypy --strict` clean; ruff `C901` complexity ≤ 8/function. | `[B+ADR-0033]` |
| G4 | **Two concrete `VulnProvenanceAdapter` implementations ship and are wired through the chain-assembly function.** `NpmVulnProvenanceAdapter` (lives in `plugins/vulnerability-remediation--node--npm/adapters/`, additive — does not edit Phase 3's existing adapters) and `AlpineVulnProvenanceAdapter` (lives in `plugins/distroless-migration--node--npm/adapters/`). The Phase 3 NpmVulnProvenanceAdapter promotion is *additive*: it ships in the existing plugin's `adapters/` directory but is reachable only when `vuln.provenance` is invoked — Phase 3's existing recipe path never touches it. | `[B+ADR-0038]` |
| G5 | **Chain-assembly is a small typed function, not a framework.** `assemble_provenance(cve_id, package_id, image_ref, adapters: Sequence[VulnProvenanceAdapter]) -> Provenance` calls each adapter in declared order (app-layer adapters first, then base-image adapters), composes the `Both` variant when both return non-`Unknown`, and returns `Unknown(reason=...)` when no adapter resolves. Plain `for` loop. Under 80 LOC. | `[B+synth]` |
| G6 | **TCCM for `distroless-migration` ships as one YAML file** at `plugins/distroless-migration--node--npm/tccm.yaml`. `must_read` covers Dockerfile, base-image reference, SBOM, and the `vuln.provenance` derived query. `should_read` covers shell-invocation traces. `may_read` covers the long-tail entrypoint/CMD analysis. Hard token budget cap. Validated against the same Pydantic schema Phase 3 uses (`src/codegenie/plugins/tccm.py`). | `[B+ADR-0029]` |
| G7 | **Two new probes land under `src/codegenie/probes/layer_c/`** (`BaseImageProbe`) and `src/codegenie/probes/layer_d/` (`ShellInvocationTraceProbe`). Both obey the frozen Probe ABC (Phase 0 ADR-0007) with `applies_to_tasks=["distroless-migration"]` and `applies_to_languages=["*"]`. Each has its own JSON sub-schema under `src/codegenie/schema/probes/`. Golden fixtures under `tests/golden/probes/{base_image,shell_invocation_trace}/`. | `[B]` |
| G8 | **Dockerfile recipes ship as deterministic `Transform` subclasses.** `DockerfileBaseImageSwapTransform` and `DockerfileMultiStageRefactorTransform` extend Phase 3's `Transform` ABC (`src/codegenie/transforms/transform.py`). They write to a typed `TransformOutcome` discriminated union. Pure-Python AST manipulation via `dockerfile-parse`; no `docker build` invocations during the recipe itself (build is Phase 5's gate). | `[B+synth]` |
| G9 | **The `Both` case is exercised end-to-end in tests.** A fixture repo (`tests/fixtures/portfolio/distroless-and-app-vuln/`) declares a CVE that resolves to both an npm transitive dep AND an Alpine package in the base image. The Phase 7 e2e slice asserts `assemble_provenance(...)` returns `Both(app_record=AppTransitive(...), base_record=BaseImage(...))`. | `[B+ADR-0038]` |
| G10 | **End-to-end migration test passes for a vulnerable Node.js service.** `tests/e2e/test_distroless_migration_e2e.py` drives the existing `codegenie remediate` CLI (Phase 3's S6-05; no CLI edits) with a `--task-class=distroless-migration` flag (the flag is the only CLI surface change and is gated by an ADR amendment). End state: a local branch carrying a Dockerfile that uses `cgr.dev/chainguard/node` plus passing `npm test` inside `SubprocessJail`. | `[B+synth]` |
| G11 | **Plugin contract tested against three plugins.** Phase 3's synthetic third plugin (`tests/fixtures/plugins/example--noop--*/`) stays in place. Phase 7's new plugin (`plugins/distroless-migration--node--npm/`) is the second *production* plugin. The plugin-contract surface is therefore validated against the Phase 3 plugin + the Phase 7 plugin + the synthetic noop — three different shapes, three different scopes. | `[B+synth]` |
| G12 | **Net-new runtime dependencies in `[project].dependencies`: 1 (`dockerfile-parse`).** `dive` and `docker buildx` are CLI tools added to `ALLOWED_BINARIES` via Phase 2 ADR-0001-style amendment (one new ADR row). No new Python packages beyond `dockerfile-parse`. | `[B]` |
| G13 | **Test pyramid healthy.** ≥ 90% line / 80% branch on `src/codegenie/primitives/vuln_provenance/`; ≥ 95% line on the two new probes; integration tests cover plugin resolution + adapter dispatch + chain assembly; one e2e per task class (vuln-rem stays green, distroless-migration is new); property tests over `Both` invariants (the synthesizer mandates: if `Both` is returned, both sub-adapters returned non-`Unknown`; symmetric — no `Both(both, both)` recursion). | `[B]` |
| G14 | **`$0.00` in LLM spend per Phase 7 workflow.** Hard zero, asserted by CI fence. Phase 7 stays deterministic (no LLM fallback yet; that's Phase 8). | `[B+ADR-0005]` |

---

## Architecture

```
                  codegenie remediate <repo> --task-class=distroless-migration
                                          │
                                          ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ src/codegenie/cli/remediate.py     [Phase 3 — UNCHANGED except 1 flag]   │
   │   accepts --task-class=<vulnerability-remediation | distroless-migration>│
   │   default unchanged; new value gated by --task-class flag                │
   └────────────────────────────────────┬─────────────────────────────────────┘
                                        │
                                        ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ src/codegenie/plugins/   [Phase 3 — UNCHANGED]                           │
   │   resolver.py     dispatches on (task, language, build) tuple           │
   │   PluginRegistry  now contains both production plugins                  │
   └──────────────────────────────────────┬───────────────────────────────────┘
                                          │
                                          ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ src/codegenie/transforms/   [Phase 3 — UNCHANGED contract surface]       │
   │   RemediationOrchestrator drives the 5 in-code stages                    │
   │   Transform ABC accepts new subclasses by addition                       │
   └──────────────────────────────────────┬───────────────────────────────────┘
                                          │
                                          ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ src/codegenie/primitives/vuln_provenance/      [NEW — Phase 7 owns it]   │
   │   __init__.py       public surface (≤ 6 re-exports)                      │
   │   types.py          Provenance discriminated union (7 variants);         │
   │                     AppDirect / AppTransitive / AppVendored /            │
   │                     BaseImage / RuntimeBundled / Both / Unknown          │
   │   protocols.py      VulnProvenanceAdapter Protocol (mirrors ADR-0032)    │
   │   registry.py       @register_provenance_adapter decorator + registry    │
   │                     (mirrors @register_dep_graph_strategy shape)         │
   │   assembly.py       assemble_provenance(...) — small free function       │
   │   errors.py         ProvenanceError hierarchy under CodegenieError       │
   │   syft_reader.py    SyftSbom Pydantic model (extra="allow"); reads       │
   │                     <raw_dir>/syft-sbom.json (Phase 2 already writes it) │
   └──────────────────────────────────────┬───────────────────────────────────┘
                                          │
                                          ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ src/codegenie/probes/   [ADDITIVE — same dirs Phase 2 established]       │
   │   layer_c/base_image.py             BaseImageProbe (extends frozen ABC)  │
   │   layer_d/shell_invocation_trace.py ShellInvocationTraceProbe            │
   │   registry.py     UNCHANGED — new probes register via @register_probe    │
   │                                                                           │
   │   schema/probes/base_image.schema.json           NEW                     │
   │   schema/probes/shell_invocation_trace.schema.json NEW                   │
   │   schema/repo_context.schema.json    one additive $ref per probe         │
   └──────────────────────────────────────┬───────────────────────────────────┘
                                          │
                                          ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ plugins/distroless-migration--node--npm/      [NEW — second prod plugin] │
   │   plugin.yaml         scope: (distroless-migration, [ts,js], npm)        │
   │                       precedence: 100                                    │
   │                       extends: [distroless-migration--node--*]           │
   │                       requirements.external_tools: [docker, dive,        │
   │                                                     docker-buildx]       │
   │   tccm.yaml           must_read: dockerfile, base_image, sbom,           │
   │                                  vuln.provenance(cve_id, pkg_id, image)  │
   │                       should_read: shell_invocation_trace                │
   │                       may_read: entrypoint_cmd_analysis                  │
   │                       budget: {max_files:50, max_tokens:30000, ...}      │
   │   adapters/                                                              │
   │     alpine_provenance.py    AlpineVulnProvenanceAdapter (registered      │
   │                              @register_provenance_adapter(               │
   │                                layer=Layer.BASE_IMAGE,                   │
   │                                ecosystem=Ecosystem.APK))                 │
   │   subgraph/api.py     5-stage shape mirrors Phase 3's plugin             │
   │   recipes/                                                               │
   │     dockerfile_base_image_swap.py    DockerfileBaseImageSwapTransform    │
   │     dockerfile_multi_stage.py        DockerfileMultiStageRefactor        │
   │   skills/             YAML-frontmatter Skills (recipe selection hints)   │
   │   PLUGINS.lock entry  sha256(dir_tree)                                   │
   │                                                                           │
   │   distroless-migration--node--*/        BASE for inheritance — wildcard  │
   │     plugin.yaml       precedence: 50; scope: (distroless-migration,      │
   │                                              [ts,js], *)                 │
   │     subgraph/         shared subgraph nodes (extension point only)       │
   └──────────────────────────────────────┬───────────────────────────────────┘
                                          │
                                          ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ plugins/vulnerability-remediation--node--npm/                            │
   │   [Phase 3 — UNCHANGED except tccm.yaml `requires:` adds one line]       │
   │   adapters/                                                              │
   │     npm_provenance.py    NpmVulnProvenanceAdapter — additive NEW file    │
   │                          registered @register_provenance_adapter(        │
   │                            layer=Layer.APP,                              │
   │                            ecosystem=Ecosystem.NPM)                      │
   │                          DOES NOT touch the existing recipe path         │
   └──────────────────────────────────────────────────────────────────────────┘
```

**Three load-bearing architectural lines:**

1. **`vuln.provenance` is a module, not a method.** It lives at `src/codegenie/primitives/vuln_provenance/`, exported on `src/codegenie/primitives/__init__.py`, and is callable from any plugin that imports it. Premature pluggability ("primitive families could be plugin-contributed via entry-points!") is rejected — Phase 7 has exactly one primitive family to ship; the `src/codegenie/primitives/` directory becomes the additive home for future bounded primitives under ADR-0039.
2. **Adapters are plugin-contributed and decorator-registered.** `@register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)` ships in `src/codegenie/primitives/vuln_provenance/registry.py`. The shape mirrors `@register_dep_graph_strategy(PackageManager)` (`src/codegenie/depgraph/registry.py`) bytes-for-bytes — same `Final` registry dict, same `register(...)` smart constructor, same `KeyError` semantics on duplicate. The Phase 3 plugin's `NpmVulnProvenanceAdapter` registers as `(Layer.APP, Ecosystem.NPM)`; the Phase 7 plugin's `AlpineVulnProvenanceAdapter` registers as `(Layer.BASE_IMAGE, Ecosystem.APK)`. The chain-assembly function looks them up by tuple key.
3. **Chain assembly is a free function, not a class.** `assemble_provenance(cve_id, package_id, image_ref, adapters)` is a 60-LOC pure function in `src/codegenie/primitives/vuln_provenance/assembly.py`. It calls app-layer adapters first (in registration order), collects the first non-`Unknown` result, then calls base-image adapters in declared order, collects the first non-`Unknown` result, then composes `Both` if both succeeded, returns the single result if only one succeeded, or `Unknown(reason=...)` if none did. The "in what order" question ADR-0038 explicitly defers is answered here as **declared registration order** — operators can read the registry to predict behavior. No DSL, no chain-builder class, no priority graph.

---

## Components

### 1. `Provenance` discriminated union (`src/codegenie/primitives/vuln_provenance/types.py`)

- **Purpose:** The seven-variant typed return value of `vuln.provenance(...)`. Verbatim from ADR-0038; the shape is non-negotiable.
- **Public interface:** Read-only re-exports from `src/codegenie/primitives/vuln_provenance/__init__.py`: `AppDirect`, `AppTransitive`, `AppVendored`, `BaseImage`, `RuntimeBundled`, `Both`, `Unknown`, `Provenance`.
- **Internal design:**
  ```python
  # Pydantic v2 discriminated union — exhaustiveness enforced via match + assert_never
  AppKind = Annotated[
      AppDirect | AppTransitive | AppVendored,
      Discriminator("kind"),
  ]
  BaseKind = Annotated[
      BaseImage | RuntimeBundled,
      Discriminator("kind"),
  ]

  class Both(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      kind: Literal["both"] = "both"
      app_record: AppKind
      base_record: BaseKind

  Provenance = Annotated[
      AppDirect | AppTransitive | AppVendored
      | BaseImage | RuntimeBundled | Both | Unknown,
      Discriminator("kind"),
  ]
  ```
  `Both` is a nested discriminated union — both inner fields carry their own `kind` discriminator. This makes `Both(app_record=Both(...), ...)` a type error at construction time (illegal-states-unrepresentable per ADR-0033 §4).
- **Smart constructor:** `Provenance.parse_from_adapter_result(...)` is the only path external code can build a `Provenance` from raw dicts. Internal adapter code constructs the typed variants directly.
- **Dependencies:** Pydantic v2 (already pinned). `codegenie.types.identifiers` for `CveId`, `PackageId`, `ImageDigest`, `LayerDigest` newtypes.
- **Where it lives:** `src/codegenie/primitives/vuln_provenance/types.py`.
- **Tradeoffs:** Adopting the ADR-0038 shape verbatim means accepting `Both` as a nested union — slightly more complex than seven flat variants, but rules out the recursive footgun cleanly. The alternative (Both as a flat record with two optional fields) would re-introduce half-valid states ADR-0033 forbids.

### 2. `VulnProvenanceAdapter` Protocol (`src/codegenie/primitives/vuln_provenance/protocols.py`)

- **Purpose:** The structural contract every adapter satisfies. One adapter per `(Layer, Ecosystem)` slice. Mirrors ADR-0032's `DepGraphAdapter` / `ImportGraphAdapter` shapes.
- **Public interface:**
  ```python
  from typing import Protocol, runtime_checkable

  @runtime_checkable
  class VulnProvenanceAdapter(Protocol):
      """One adapter per (Layer, Ecosystem) slice."""

      def attribute(
          self,
          cve_id: CveId,
          package_id: PackageId,
          image_ref: ImageRef | None,
          sbom: SyftSbom,
      ) -> Provenance:
          """Return the typed Provenance for this CVE / package in this layer.
          Adapters return Unknown(...) — never None — when they can't resolve."""

      def confidence(self) -> AdapterConfidence:
          """High / Degraded / Unavailable — mirrors Phase 3 ADR-0010 sum type."""
  ```
- **Internal design:** Duck-typed — no inheritance required. `@runtime_checkable` lets the registry assert conformance at registration time without forcing adapters to inherit.
- **Dependencies:** `AdapterConfidence` is imported from `src/codegenie/adapters/confidence.py` (Phase 3 shipped it). `SyftSbom` from `src/codegenie/primitives/vuln_provenance/syft_reader.py` (new).
- **Where it lives:** `src/codegenie/primitives/vuln_provenance/protocols.py`. Public via `src/codegenie/primitives/vuln_provenance/__init__.py`.
- **Tradeoffs:** Protocol vs ABC: chose Protocol to match ADR-0032 exactly. Cost: `mypy --strict` won't catch missing methods at adapter-class definition time unless authors declare conformance explicitly (we mandate `# type: ignore[type-arg]` -free conformance via a tests/fence test that does `isinstance(adapter, VulnProvenanceAdapter)` for every registered adapter).

### 3. `@register_provenance_adapter` + registry (`src/codegenie/primitives/vuln_provenance/registry.py`)

- **Purpose:** Decorator-registration of adapters. Mirrors `@register_dep_graph_strategy(PackageManager)` (`src/codegenie/depgraph/registry.py`) and `@register_probe` (`src/codegenie/probes/registry.py`).
- **Public interface:**
  ```python
  from enum import Enum

  class Layer(str, Enum):
      APP = "app"
      BASE_IMAGE = "base_image"
      RUNTIME = "runtime"

  class Ecosystem(str, Enum):
      NPM = "npm"
      YARN_BERRY = "yarn-berry"
      MAVEN = "maven"
      APK = "apk"
      DPKG = "dpkg"
      RPM = "rpm"
      # ... open to additive enum values per ADR

  _REGISTRY: Final[dict[tuple[Layer, Ecosystem], VulnProvenanceAdapter]] = {}

  def register_provenance_adapter(
      *, layer: Layer, ecosystem: Ecosystem
  ) -> Callable[[type[VulnProvenanceAdapter]], type[VulnProvenanceAdapter]]:
      def _wrap(cls):
          key = (layer, ecosystem)
          if key in _REGISTRY:
              raise ValueError(f"duplicate adapter for {key!r}")
          if not isinstance(cls(), VulnProvenanceAdapter):  # runtime structural check
              raise TypeError(f"{cls.__name__} does not satisfy VulnProvenanceAdapter")
          _REGISTRY[key] = cls()
          return cls
      return _wrap

  def adapters_for_layer(layer: Layer) -> list[VulnProvenanceAdapter]: ...
  def all_adapters() -> Mapping[tuple[Layer, Ecosystem], VulnProvenanceAdapter]: ...
  ```
- **Internal design:** Module-level `_REGISTRY` dict, populated at plugin-load time via explicit-import collection (`src/codegenie/plugins/loader.py` calls `import plugins.distroless_migration__node__npm.adapters.alpine_provenance` as part of its load pass — no `importlib.metadata` entry-point scan, per CLAUDE.md's explicit-import rule). Test isolation is via a `pytest` fixture that snapshots and restores `_REGISTRY` per test (same shape Phase 3 uses for `PluginRegistry`).
- **Dependencies:** `VulnProvenanceAdapter` Protocol.
- **Where it lives:** `src/codegenie/primitives/vuln_provenance/registry.py`.
- **Tradeoffs:** Two-axis key (`Layer`, `Ecosystem`) instead of a free-form string. Slightly more typing ceremony at registration time, but rules out adapter-key drift and gives the chain-assembly function a typed iteration shape.

### 4. `assemble_provenance(...)` (`src/codegenie/primitives/vuln_provenance/assembly.py`)

- **Purpose:** Compose adapter results into a single `Provenance`. ADR-0038 explicitly defers the "what order, which adapters" question to this phase. Best-practices answer: **declared registration order, app-layer first then base-image, plain `for` loop**.
- **Public interface:**
  ```python
  def assemble_provenance(
      cve_id: CveId,
      package_id: PackageId,
      image_ref: ImageRef | None,
      sbom: SyftSbom,
      *,
      registry: Mapping[tuple[Layer, Ecosystem], VulnProvenanceAdapter] | None = None,
  ) -> Provenance:
      """App adapters first, base adapters second; compose Both if both succeed."""
  ```
- **Internal design:**
  ```python
  def assemble_provenance(...) -> Provenance:
      registry = registry or all_adapters()
      app_result: AppKind | None = None
      base_result: BaseKind | None = None
      for (layer, ecosystem), adapter in registry.items():
          if layer is Layer.APP and app_result is None:
              r = adapter.attribute(cve_id, package_id, image_ref, sbom)
              if r.kind in {"app_direct", "app_transitive", "app_vendored"}:
                  app_result = r
          elif layer is Layer.BASE_IMAGE and base_result is None:
              r = adapter.attribute(cve_id, package_id, image_ref, sbom)
              if r.kind == "base_image":
                  base_result = r
          elif layer is Layer.RUNTIME and base_result is None:
              r = adapter.attribute(cve_id, package_id, image_ref, sbom)
              if r.kind == "runtime_bundled":
                  base_result = r
      match (app_result, base_result):
          case (None, None):
              return Unknown(reason="no_adapter_for_distro")  # or similar; see G3
          case (app, None):
              return app
          case (None, base):
              return base
          case (app, base):
              return Both(app_record=app, base_record=base)
  ```
- **Dependencies:** Registry, the seven typed variants.
- **Where it lives:** `src/codegenie/primitives/vuln_provenance/assembly.py`.
- **Tradeoffs:** Declared-registration-order is operator-predictable but doesn't handle "two app-layer adapters both resolve" (e.g., npm + yarn-berry on a polyglot repo). For Phase 7 — one app adapter, one base adapter, one ecosystem each — the simplicity wins. Future ecosystems will demand a tiebreaker; the function takes an optional `registry` param so an explicit selector can be passed when needed. Premature DSL averted.

### 5. `BaseImageProbe` (`src/codegenie/probes/layer_c/base_image.py`)

- **Purpose:** Capture the *literal* base image reference(s) from every Dockerfile in the repo, with kind classification. Facts, not judgments.
- **Public interface:** Standard Probe ABC. `name = "BaseImage"`, `layer = "C"`, `tier = "task_specific"`, `applies_to_tasks = ["distroless-migration"]`, `applies_to_languages = ["*"]`, `declared_inputs = ["**/Dockerfile", "**/Dockerfile.*", "**/Containerfile", "**/*.dockerfile"]`. Schema slice under `probes.base_image`.
- **Internal design:** Reuses Phase 2's `parse_dockerfile_text` (already supply-chain-safe — no shell eval, no `${VAR}` expansion). Walks the parsed AST for `FROM` directives; classifies each by a `Final` dict catalog `_BASE_IMAGE_KIND_RULES` (e.g., `cgr.dev/chainguard/*` → `distroless`; `*alpine*` → `alpine`; `debian:*-slim` → `debian-slim`; `scratch` → `scratch`; unknown → `unknown`). Multi-stage Dockerfiles report a list with `stage_name` per FROM. Schema slice: `{base_image: {dockerfiles: [{path, stages: [{name, ref, digest, kind}]}], confidence}}`.
- **Dependencies:** Phase 2's `_dockerfile_parse`. `codegenie.probes.base.Probe`. `codegenie.probes.registry.register_probe`.
- **Where it lives:** `src/codegenie/probes/layer_c/base_image.py`. Sub-schema at `src/codegenie/schema/probes/base_image.schema.json`. `$ref` wired into the envelope.
- **Tradeoffs:** "Kind" is enumerated by a marker catalog rather than learned — adding a new distro family is one row in `_BASE_IMAGE_KIND_RULES` and one test fixture. Anti-`unknown` heuristics (regex chains, registry lookups) are explicitly rejected — they're judgments, not facts.

### 6. `ShellInvocationTraceProbe` (`src/codegenie/probes/layer_d/shell_invocation_trace.py`)

- **Purpose:** Capture every shell invocation observed when the container's entrypoint runs. Critical for distroless migration — distroless has no shell.
- **Public interface:** Probe ABC. `name = "ShellInvocationTrace"`, `layer = "D"`, `tier = "task_specific"`, `applies_to_tasks = ["distroless-migration"]`, `cache_strategy = "content"`, `declared_inputs = ["Dockerfile", "image-digest:<resolved>", "package.json", "ENTRYPOINT", "CMD"]` (the image-digest token is Phase 2 ADR-0004's already-shipped invalidation mechanism — base-image rotations naturally invalidate trace).
- **Internal design:** Runs `dive` for layer inspection plus a `strace`-shaped wrapper that observes `execve` calls during a short container boot in a Phase-2-shaped sandbox (Phase 2 ADR-0001 omnibus binary). Outputs `{shell_invocations: [{path, args, source_layer}], shell_present_in_final_layer: bool, confidence}`. Phase 5 will reuse this signal kind via `@register_signal_kind`.
- **Dependencies:** `dive`, `strace`, `docker buildx` — all gated via `codegenie.exec.run_external_cli` + `ALLOWED_BINARIES`. ADR amendment row for each.
- **Where it lives:** `src/codegenie/probes/layer_d/shell_invocation_trace.py`. Sub-schema + golden fixtures.
- **Tradeoffs:** Real container boot is slow (~10–30s); the probe declares `heaviness="heavy"` and `runs_last=True` per Phase 2 ADR-0003. The slow path is paid only when relevant (`applies_to_tasks=["distroless-migration"]` — vuln-remediation workflows never run this probe).

### 7. `NpmVulnProvenanceAdapter` (`plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py`)

- **Purpose:** Resolve `(cve_id, package_id)` against the npm dep tree. Returns `AppDirect` / `AppTransitive` / `Unknown(reason)`. Lives inside the Phase 3 plugin but is *additive* — the existing Phase 3 recipe path never reaches this file.
- **Public interface:** Satisfies `VulnProvenanceAdapter`. Decorated `@register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)`.
- **Internal design:** Reads `package.json` + `package-lock.json` from the gathered `RepoContext` (Phase 1 already produces these). Walks the resolved tree to find every chain ending at `package_id`. If chain length 1 → `AppDirect`. If chain length > 1 → `AppTransitive`. If `package_id` not in the tree → `Unknown(reason="sbom_layer_attribution_absent")` (the SBOM's app-layer attribution was missing or the package is base-image-only).
- **Dependencies:** Phase 1's lockfile parsers (already shipped). The `VulnProvenanceAdapter` Protocol from `src/codegenie/primitives/vuln_provenance/`.
- **Where it lives:** `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py`. NEW file added to existing plugin — additive only.
- **Tradeoffs:** Living inside an existing plugin means Phase 7's PR touches Phase 3's plugin directory. The CI fence (`tests/fence/test_kernel_frozen.py`) is amended additively to allow new files under `plugins/vulnerability-remediation--node--npm/adapters/` — the existing files stay locked.

### 8. `AlpineVulnProvenanceAdapter` (`plugins/distroless-migration--node--npm/adapters/alpine_provenance.py`)

- **Purpose:** Resolve `(cve_id, package_id)` against an Alpine base-image's apk database. Returns `BaseImage` / `Unknown(reason)`.
- **Public interface:** Satisfies `VulnProvenanceAdapter`. Decorated `@register_provenance_adapter(layer=Layer.BASE_IMAGE, ecosystem=Ecosystem.APK)`.
- **Internal design:** Reads the `SyftSbom`'s `locations[].layerID` field for the affected package. If at least one location has `layerID` matching the base-image layer set (from the gathered Dockerfile + image inspection), returns `BaseImage(image_digest=..., layer_digest=..., distro_pkg=DistroPackage(name=..., version=...), stage=...)`. Otherwise returns `Unknown(reason="sbom_layer_attribution_absent")` per ADR-0038's typed variant.
- **Dependencies:** `SyftSbom` reader. The `BaseImageProbe`'s output for the layer-to-image-digest mapping.
- **Where it lives:** `plugins/distroless-migration--node--npm/adapters/alpine_provenance.py`. New plugin, new file.
- **Tradeoffs:** Alpine-specific. Future Debian / RHEL adapters ship as new files in their own plugins (or in a shared `base-image-tooling` plugin per ADR-0038). Each registers under its own `(Layer.BASE_IMAGE, Ecosystem.*)` key — no edits to this adapter.

### 9. `DockerfileBaseImageSwapTransform` (`plugins/distroless-migration--node--npm/recipes/dockerfile_base_image_swap.py`)

- **Purpose:** The Phase 7 workhorse recipe. Swap `FROM node:18-alpine` for `FROM cgr.dev/chainguard/node:latest@sha256:<digest>` (plus the multi-stage runner-stage adjustments distroless requires — `COPY --from=builder`, no shell, `USER nonroot`).
- **Public interface:** Extends Phase 3's `Transform` ABC. `transform_id`, `diff_bytes`, `files_changed: list[SandboxedPath]`, `provenance: TransformProvenance`.
- **Internal design:** Pure-Python `dockerfile-parse` AST manipulation. No `docker build` invocation in the recipe — building is the Phase 5 gate's job (the recipe just produces the diff). Reads a `chainguard_image_recommendation_table.yaml` (small static data file in the plugin's `data/` dir; future Phase 7 stories may make this live-updated from Chainguard's API but for v1 it's frozen data).
- **Dependencies:** `dockerfile-parse` (new dep, sole net-new). Phase 3's `Transform` ABC.
- **Where it lives:** `plugins/distroless-migration--node--npm/recipes/dockerfile_base_image_swap.py`.
- **Tradeoffs:** Frozen recommendation table means new base-image releases require a PR to update the data file. Acceptable for v1; the alternative (live API call to Chainguard) introduces a runtime network dependency that the fence forbids.

### 10. `distroless-migration` TCCM (`plugins/distroless-migration--node--npm/tccm.yaml`)

- **Purpose:** Declarative context selection for distroless migration. One YAML, no code.
- **Public interface:** Validated at plugin-load time by `src/codegenie/plugins/tccm.py`'s Pydantic schema (already shipped in Phase 3).
- **Internal design (sketch):**
  ```yaml
  task_class: distroless-migration
  must_read:
    repo_context_keys: [dockerfile, base_image, sbom, language_detection]
    derived:
      - name: provenance_for_this_cve
        compute: vuln.provenance
        args: {cve_id: $workflow.cve, package_id: $workflow.package, image_ref: $repo.base_image}
        max_files: 1
  should_read:
    repo_context_keys: [shell_invocation_trace, node_build_system]
  may_read:
    repo_context_keys: [entrypoint_cmd_analysis, runtime_trace]
  bootstrap_globs: [Dockerfile, Dockerfile.*, .dockerignore, package.json]
  budget:
    max_files: 50
    max_tokens: 30000
    per_file_max_tokens: 2000
  ```
- **Dependencies:** None at YAML level; the loader resolves `vuln.provenance` to the primitive function at plugin-load time.
- **Where it lives:** `plugins/distroless-migration--node--npm/tccm.yaml`.
- **Tradeoffs:** TCCM evolution requires care — the `$workflow.cve` interpolation syntax must match Phase 3's existing interpolation (one source of truth). The chosen syntax is `$workflow.<field>` and `$repo.<field>`, matching Phase 3's already-shipped resolver.

---

## Data flow

```
   gather (Phase 2 — UNCHANGED)
        │
        ▼
   .codegenie/context/raw/syft-sbom.json   ← Phase 2 already writes this
        │
        ├──────────────────────────────────────────────────┐
        ▼                                                   ▼
   probes/layer_c/base_image.py              probes/layer_d/shell_invocation_trace.py
        │   (writes RepoContext.probes.base_image)             │
        │                                                       │
        ▼                                                       ▼
   .codegenie/context/repo-context.yaml      .codegenie/context/repo-context.yaml
        │                                                       │
        └────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼
              codegenie remediate --task-class=distroless-migration
                                 │
                                 ▼
              plugins/distroless-migration--node--npm/ resolves
                                 │
                                 ▼
              BundleBuilder builds Context Bundle via TCCM
                                 │
                                 ▼
              TCCM derived query → assemble_provenance(...)
                                 │
                                 ├─→ NpmVulnProvenanceAdapter.attribute(...) → AppKind | Unknown
                                 └─→ AlpineVulnProvenanceAdapter.attribute(...) → BaseKind | Unknown
                                 │
                                 ▼ (composes)
                            Provenance (one of 7 variants)
                                 │
                                 ▼
              RemediationOrchestrator drives 5 stages (Phase 3 — UNCHANGED)
                                 │
                                 ▼
              DockerfileBaseImageSwapTransform produces a typed Transform
                                 │
                                 ▼
              Stage 6 Validate runs npm build + npm test in SubprocessJail
                                 │
                                 ▼
              remediation-report.yaml on disk; local branch ready for review
```

Convention highlights along the flow:

- **Probe contract preserved.** Two new probes, zero edits to the ABC. The Coordinator picks them up via `@register_probe` and runs them when `applies_to_tasks` matches.
- **`syft-sbom.json` read, not rewritten.** Phase 2's raw artifact is the single source of truth for layer attribution; this phase adds *consumers*, not *producers*.
- **TCCM is data.** The new distroless TCCM is one YAML file; the loader's existing Pydantic schema validates it without code edits.
- **Adapter dispatch is registry lookup.** No `match` statements on ecosystem; no `if-elif` chains. The `(Layer, Ecosystem)` tuple keys the dict and the chain-assembly walks it.
- **Idempotent recipe.** The Dockerfile transform is pure — same `(repo_snapshot_sha, cve_record_digest, plugin_version, recipe_version, vuln_index_digest)` → byte-identical diff. Property-tested (G13).

---

## Failure modes & recovery

- **`Unknown(reason="no_adapter_for_distro")`** — no adapter registered for the detected base-image ecosystem. The orchestrator emits `RequiresHumanReview` (Phase 3's universal HITL fallback) with the evidence bundle attached. Recovery: ship a new adapter in a follow-up phase (e.g., `DebianVulnProvenanceAdapter`); existing adapters and behavior unchanged.
- **`Unknown(reason="sbom_layer_attribution_absent")`** — syft output lacks `locations[].layerID` for the affected package (e.g., a future syft version drops this field). The orchestrator escalates to HITL with the specific reason logged. Recovery: pin syft version in the Phase 2 `ALLOWED_BINARIES`-adjacent dependency manifest until adapters are amended. The typed `reason` variant means the symptom surfaces in audit logs as a *named* failure, not a silent mis-routing — ADR-0038's forcing-function consequence.
- **Dockerfile recipe produces a no-op diff.** The repo is already on a distroless image. The transform returns `RecipeOutcome(kind="not_applicable", reason="already_distroless")`. The orchestrator marks the workflow `Skipped` and writes the audit record. No PR is opened.
- **`npm test` fails inside `SubprocessJail` after the swap.** Phase 3's existing retry envelope handles this — Phase 5 wraps it. Phase 7 ships zero new retry logic. The test failure surfaces as a typed `TestSignal(passed=False)` to the existing `TrustScorer`.
- **A registered adapter raises an unexpected exception.** The chain-assembly function catches `ProvenanceError` (the typed exception hierarchy under `src/codegenie/primitives/vuln_provenance/errors.py`) and converts it to `Unknown(reason="adapter_error", details=...)`. *All other exceptions propagate* — silent error-swallowing is forbidden per Rule 12 (fail loud).
- **Duplicate adapter registration.** `@register_provenance_adapter` raises `ValueError` at import time. The plugin loader's existing fast-fail logic (ADR-0031 §"Schema enforcement and validation") surfaces this at Supervisor startup with a clear file/line diagnostic.

**Custom vs stdlib exceptions:** `ProvenanceError(CodegenieError)` for adapter-internal failures; `RegistryError(CodegenieError)` for registration conflicts. No bare `Exception`; no `RuntimeError` for domain errors. Matches Phase 3's `transforms/errors.py` shape.

---

## Resource & cost profile

- **LLM spend per workflow:** $0.00. Hard zero (G14). The CI fence asserts no LLM SDK import reachable from `src/codegenie/primitives/vuln_provenance/` or `plugins/distroless-migration--*`.
- **Probe cost:**
  - `BaseImageProbe` — pure-Python Dockerfile parse, <50 ms on a typical repo. `heaviness="light"`.
  - `ShellInvocationTraceProbe` — container boot + `strace` capture, 10–30 s. `heaviness="heavy"`, `runs_last=True`. Only fires when `applies_to_tasks` matches.
- **Provenance query cost:** Adapter calls are O(SBOM size) walks — milliseconds for typical repos, sub-second for the largest. No inter-workflow cache (ADR-0038 explicitly defers `vuln_provenance_cache` to Phase 14).
- **Recipe application:** Pure-Python AST manipulation, <100 ms. The expensive step is Phase 5's gate `docker build`, unchanged.
- **Net-new runtime deps:** `dockerfile-parse` (small; well-maintained; permissive license). Three new CLI binaries (`dive`, `docker buildx`, `strace` — the last already present on Linux) in `ALLOWED_BINARIES`, each requiring an ADR amendment row.
- **CI runtime impact:** New probes' goldens add ~30 s to `make check`. New e2e adds ~3 min (one full migration run) but is opt-in via a pytest marker (`@pytest.mark.phase07_e2e`) and gated separately so the dev loop isn't slowed.

---

## Test plan

The test pyramid is the load-bearing safety net for "extension by addition." If we can't tell whether Phase 7 broke Phase 3 in 5 minutes, the phase has failed regardless of new functionality.

**Unit tests (the bulk, fast):**
- `tests/unit/primitives/vuln_provenance/test_types.py` — every variant constructs / serializes / round-trips; `Both` rejects `Both(both, ...)` recursion at validation time; smart constructor rejects malformed dicts.
- `tests/unit/primitives/vuln_provenance/test_registry.py` — duplicate registration raises; non-conforming adapter raises `TypeError`; lookup by `(Layer, Ecosystem)` works; registry-isolation fixture restores state.
- `tests/unit/primitives/vuln_provenance/test_assembly.py` — every combinatorial path (`Unknown × Unknown → Unknown`, `app × Unknown → app`, `Unknown × base → base`, `app × base → Both`); order of registration is honored; injecting an explicit `registry` overrides default.
- `tests/unit/probes/layer_c/test_base_image.py` — fixture Dockerfiles for distroless / alpine / debian-slim / scratch / multi-stage / unknown; classification correct; multi-stage emits a list; schema slice validates.
- `tests/unit/probes/layer_d/test_shell_invocation_trace.py` — fixture trace JSON inputs; classification correct; image-digest declared-input invalidates cache.
- `tests/unit/plugins/distroless_migration_node_npm/test_alpine_provenance.py` — fixture SBOMs with and without `locations[].layerID`; correct `BaseImage` or `Unknown(sbom_layer_attribution_absent)`.
- `tests/unit/plugins/vulnerability_remediation_node_npm/test_npm_provenance.py` — fixture lockfiles; `AppDirect` for direct deps, `AppTransitive` for transitive, `Unknown` for absent.
- `tests/unit/transforms/recipes/test_dockerfile_base_image_swap.py` — fixture Dockerfiles; correct swap; no-op detection for already-distroless; multi-stage handling.

**Integration tests (moderate, slower):**
- `tests/integration/test_plugin_resolution_phase7.py` — given a fixture repo with Dockerfile + `package.json`, resolver returns `distroless-migration--node--npm` (precedence + scope correct).
- `tests/integration/test_provenance_assembly_via_plugin.py` — full plugin-load → adapter-registration → `assemble_provenance(...)` → typed result. Both Phase 3's NpmVulnProvenanceAdapter and Phase 7's AlpineVulnProvenanceAdapter loaded; chain executes.
- `tests/integration/test_tccm_distroless_loads.py` — TCCM YAML loads, validates against the Pydantic schema, derived query references resolve.

**Property tests (a few, high signal):**
- `tests/property/vuln_provenance/test_both_invariant.py` — for any (`AppKind`, `BaseKind`) pair where both are non-`Unknown`, `assemble_provenance(...)` returns `Both(app_record=..., base_record=...)` and `Both.app_record.kind ∈ {app_direct, app_transitive, app_vendored}` and `Both.base_record.kind ∈ {base_image, runtime_bundled}`. No recursion. Hypothesis strategies over the variants.
- `tests/property/vuln_provenance/test_idempotence.py` — calling `assemble_provenance` twice with identical inputs returns equal (`__eq__`) `Provenance` instances.

**Golden tests (regression):**
- `tests/golden/probes/base_image/distroless-target.json`, `alpine.json`, `multi-stage.json`, `scratch.json`, `unknown.json` — schema-validated.
- `tests/golden/probes/shell_invocation_trace/distroless-target.json`, `with-shell.json`, `no-trace-available.json`.
- `tests/golden/provenance/app-direct.json`, `app-transitive.json`, `base-image-alpine.json`, `both.json`, `unknown.json`.

**End-to-end (few, slow, gated):**
- `tests/e2e/test_distroless_migration_e2e.py` — fixture Node.js service with vulnerable Alpine-based Dockerfile. Drive `codegenie remediate <repo> --cve <id> --task-class=distroless-migration`. Assert: local branch carries a Dockerfile FROM `cgr.dev/chainguard/node`; `remediation-report.yaml` written; `npm test` passes in `SubprocessJail`. Gated by `@pytest.mark.phase07_e2e`; CI runs it separately from the main `make check`.
- `tests/e2e/test_both_provenance_e2e.py` — fixture repo with a CVE that hits both an npm transitive dep AND an Alpine apk package. Assert: `Provenance` returned by the chain-assembly is `Both(...)`; orchestrator emits a coordination event (consumed by Phase 8's future Planner; here we assert the event is on disk).

**Regression suite (THE PHASE'S TEST):**
- `make check` plus `bench/vuln-remediation/` cassette replay (Phase 6.5's `codegenie eval run --task-class=vuln-remediation`) runs as a pre-merge hard gate. The pre-commit hook stays unchanged; CI runs both in parallel.
- `tests/fence/test_kernel_frozen.py` (Phase 3) extends its allowlist to permit Phase 7's exact additions (the new files listed above) and *nothing else* — any unauthorized edit to existing plugin files fails CI with a specific diagnostic.
- `tests/fence/test_phase7_no_llm.py` — new `import-linter` contract: `src/codegenie/primitives/vuln_provenance/` and `plugins/distroless-migration--*/` may not import `anthropic`, `openai`, `langchain`, `langgraph`, `transformers`.

**Coverage targets:**
- 95% line / 90% branch on `src/codegenie/primitives/vuln_provenance/`.
- 95% line on the two new probes.
- 90% line on the plugin adapters.
- ≥ 85% line repo-wide (existing gate).

---

## Design patterns applied

| Pattern | Where | Why | Defense against premature pluggability |
|---|---|---|---|
| **Newtype every domain primitive** (ADR-0033 §1) | `ImageRef`, `ImageDigest`, `LayerDigest`, `BaseImageKind`, `DistroPackage`, `MigrationCandidateId` in `src/codegenie/types/identifiers.py` | Stop the next engineer from passing a `WorkflowId` where an `ImageRef` is expected. Catches drift at `mypy --strict` time. | Each newtype maps 1:1 to a real concept Phase 7 uses *today*. Not speculative. |
| **Tagged union with discriminator** (ADR-0033 §3, ADR-0038) | `Provenance` discriminated union; `RecipeOutcome` extension; `BaseImageKind` enum | Make illegal states unrepresentable. `Both(both, ...)` is a type error; missing-variant handling is a `mypy --strict` error via `assert_never`. | Variants are the seven ADR-0038 commits to — no speculative "future variant" slots. |
| **Protocol over inheritance** (`VulnProvenanceAdapter`) | `src/codegenie/primitives/vuln_provenance/protocols.py` | Mirrors ADR-0032 exactly. Adapters duck-type; tests use `isinstance(...)` with `@runtime_checkable`. No "AbstractProvenanceAdapter" base class. | Two adapters ship in Phase 7. The pattern proves itself with N=2 before being extended. Idiomatic Python (PEP 544). |
| **Plugin/Registry mirroring `@register_probe`** | `@register_provenance_adapter` in `src/codegenie/primitives/vuln_provenance/registry.py` | Established seam (Phase 0 probe registry, Phase 1 dep-graph strategy registry, Phase 6.5 task-class registry). The next engineer reads four examples and knows the shape. | The pattern is well-worn in the codebase. Adopting a fifth registry of the same shape is *not* premature pluggability — it's matching convention (Rule 11). |
| **Smart constructor for external data** (ADR-0033 §2) | `SyftSbom.parse(...)`, `Provenance.parse_from_adapter_result(...)` | External boundary validation. Adapters take typed values; raw JSON dies at the boundary. | Used only at the boundaries the data actually crosses. Internal construction skips the constructor. |
| **Free function for chain assembly** | `assemble_provenance(...)` in `assembly.py` — plain `def`, no `ChainAssembler` class | Composition over inheritance, plain data over clever types. 60 LOC. Operators can predict behavior by reading the registry. | **This is the lens's main "no" answer.** Phase 7's chain has two adapters; a class hierarchy / builder / DSL would all be premature. |

---

## Patterns deliberately avoided

- **Adapter chain DSL.** A YAML-declared "first try X, then Y, then Z" chain was tempting. Rejected — Phase 7 has two adapters, and registration order is enough. A DSL solves a problem we don't have yet, and ADRs would have to bless it.
- **Strategy/Builder for provenance assembly.** A `ProvenanceAssemblyBuilder().with_app_layer(...).with_base_layer(...).build()` shape was tempting because Pythonic builder patterns are popular. Rejected — a free function with named args is 1/3 the code and zero indirection. Premature pluggability ADR-0033 catches.
- **`Provenance` as a flat record with optional fields.** Tempting because Pydantic accepts it. Rejected — half-valid states (`Both.app_record=None`, `Both.base_record=None`) become representable, and ADR-0033 §4 forbids that.
- **`importlib.metadata` entry-point plugin discovery.** Tempting for "extensibility." Rejected — CLAUDE.md mandates explicit-import collection for supply-chain hygiene. Adding a probe is one new module + one additive import line; Phase 7 follows that convention.
- **A second `vuln.*` primitive ("vuln.risk_score").** ADR-0038's tradeoff table flags this as out-of-scope. Confirmed rejected — TCCMs own risk scoring; primitives stay narrow.
- **A `BaseImageMigrationPlanner` class.** Phase 8 will own this. Phase 7 ships a recipe + an adapter and lets Stage 3 (which doesn't yet exist) compose them in Phase 8.
- **Live Chainguard registry API call inside the recipe.** Tempting for "always-fresh recommendations." Rejected — introduces runtime network dependency and breaks Phase 5's sandbox isolation contract. Frozen data table; refresh via PR.
- **Caching `vuln.provenance` results.** ADR-0038 defers `vuln_provenance_cache` to Phase 14. Confirmed — the lookup is fast enough at Phase 7 scale; caching is the premature optimization the lens is sharpest at refusing.
- **OpenRewrite for Dockerfile transforms.** OpenRewrite scaffolding ships in Phase 3 (`OpenRewriteRecipeEngine` stub). Phase 7 *could* extend it for real, but pure-Python `dockerfile-parse` manipulation is simpler, has zero JVM overhead, and matches Phase 3's `NpmLockfileRecipeEngine` shape. OpenRewrite stays a Phase 8+ option for genuinely-multi-language structural transforms.

---

## Risks (top 5)

1. **Silent edits to Phase 3 plugin via the `tccm.yaml requires:` line.** Mitigated by the CI fence's per-file allowlist — any edit outside the explicit `tccm.yaml` line fails CI. The fence test's failure message must name the offending file path to avoid debugging via grep.
2. **`Unknown(reason="no_adapter_for_distro")` becomes the default outcome for any non-Alpine base image.** Mitigated by ADR-0038's typed-reason variant — the symptom is loud (audit log + HITL escalation), not silent. Phase 8+ plugins ship the missing adapters.
3. **`syft` schema drift breaks `AlpineVulnProvenanceAdapter`.** Mitigated by `SyftSbom`'s `extra="allow"` (Phase 2 deliberate decision per S5-04) and a `syft --version` pin in the Phase 2 binary allowlist. A `syft` upgrade goes through ADR review.
4. **The `Both` case's coordination is under-specified.** Phase 7 emits the `Both` `Provenance` and a `RequiresCoordination` event; the actual two-PR sequencing is Phase 8's Planner job. The risk is operators expect Phase 7 to ship multi-PR sequencing. Mitigated by clear docs (`README.md` in the plugin and `Notes-for-implementer`) plus an explicit non-goal in this design.
5. **`ShellInvocationTraceProbe` requires Docker + `strace` + boot time, which CI runners may lack.** Mitigated by `@pytest.mark.phase07_e2e` gating and a CI matrix split — the trace probe's unit tests use recorded fixture trace JSON; the integration test runs only on Linux runners with `--privileged` (separate CI job).

---

## Acknowledged blind spots

- **No Yarn / pnpm / Java / Python adapters yet.** Future phases. Phase 7 proves the pattern with npm + Alpine; the *shape* of adding new ecosystems is known but unverified beyond N=2.
- **Chainguard image recommendation table is frozen.** A fresh CVE on Chainguard's own distroless image (or a deprecation) requires a PR. Acceptable for v1; live API integration is a future story.
- **Multi-architecture (linux/amd64 vs linux/arm64) base-image swapping is not addressed.** The recipe assumes the source Dockerfile is single-arch. Multi-arch is a future story.
- **`Both` case detection depends on syft's per-package `locations[].layerID`.** If syft ever produces an SBOM where the app-layer and base-layer instances of the same package are merged into one record, the `Both` case will silently degrade to whichever layer syft picked. Detection: a property-test that asserts every package with `locations.length > 1` produces non-`Unknown` provenance.
- **The `assemble_provenance` "declared order" semantics depend on `dict` insertion order.** Python 3.7+ guarantees this, but a future refactor to a `defaultdict` or a sorted dict could change the order silently. Mitigation: a unit test asserts the order of `registry.items()` matches registration order over a small fixture.

---

## Open questions for the synthesizer

1. **Adapter registration order — is "registration order" the right "in what order" answer ADR-0038 defers, or should this phase ship an explicit declarative ordering (e.g., a YAML chain in `plugin.yaml`)?** Best-practices says registration order; security may want a manifest declaration for auditability; performance may want a precedence integer. Synthesizer's call.
2. **`vuln.provenance` location — `src/codegenie/primitives/vuln_provenance/` vs `src/codegenie/provenance/` vs lifting it into `src/codegenie/transforms/`?** Best-practices argues for `primitives/vuln_provenance/` because ADR-0039 anticipates more bounded primitives, and a `primitives/` parent makes that intent visible. Security/performance may prefer flat. Synthesizer's call.
3. **`Layer` and `Ecosystem` as `Enum` vs `NewType(str)`?** Best-practices picked `Enum` because adapter dispatch wants exhaustiveness checks (`match Layer.APP: ...`). Performance may prefer `NewType` for hot-path comparison. Synthesizer reconciles.
4. **`assemble_provenance` order: app-first-then-base, or base-first-then-app, or topological?** Best-practices picked app-first because Phase 3 was app-only and the precedent favors app routing; Phase 7's `Both` case detection is symmetric so either order works. Locking the order in code prevents drift but constrains future plugins.
5. **Does Phase 7 ship a `--task-class=distroless-migration` CLI flag (a tiny CLI surface change), or does the orchestrator infer the task class from the resolved plugin?** Best-practices ships the flag for operator clarity; the implicit-inference alternative has zero CLI changes but worse debuggability. Synthesizer picks.
6. **Should `BaseImageProbe` and `ShellInvocationTraceProbe` register a `_WARNING_IDS: Final[frozenset[str]]` set per Phase 1 ADR-0007?** Yes by convention, but the specific IDs (`base_image.unknown_classification`, `shell_trace.boot_timeout`, etc.) deserve synthesizer sign-off.
7. **CI: should the e2e `test_distroless_migration_e2e.py` run on every PR or only on `main` merges?** Best-practices says PRs (catches regressions early); cost says merges only (~3 min e2e per PR). Synthesizer reconciles against the cost commitment §2.9.
