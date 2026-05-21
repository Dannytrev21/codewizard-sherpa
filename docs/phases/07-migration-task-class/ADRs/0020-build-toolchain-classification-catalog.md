# ADR-0020: Build-time-only toolchain vs runtime libraries is a frozen data catalog, not a heuristic

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** amendment-a · g3 · frozen-catalog · data-not-branching · native-modules
**Related:** [0005](0005-probes-live-under-plugin-not-core-tree.md), [0009](0009-phase-7-byte-edit-allowlist-fence.md), [0010](0010-chainguard-cve-image-lookup-frozen-yaml.md), [0029](0029-amend-byte-edit-allowlist-for-amendment-a.md), [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md), [production ADR-0031](../../../production/adrs/0031-plugin-architecture.md)

## Context

`final-design.md §Amendment A §A.2` gap G3: the multi-stage refactor recipe must place each dependency in the correct Dockerfile stage. Build-time-only toolchain (`gcc`, `make`, `python3`, `*-dev` headers) belongs in the `cgr.dev/chainguard/node:*-dev` builder stage and **must not** leak into the distroless runner; runtime libraries (`libstdc++`, `icu-libs`) belong in the runner. A misclassification ships either a bloated image (toolchain in the runner) or a `dlopen` failure at runtime (runtime library dropped). Native modules (`binding.gyp`, `*.node`, `node-gyp`) are the trigger that forces a builder stage in the first place — a pure-JS dependency tree needs no compiler.

`apk add` / `apt-get install` package names do not announce their nature. `gcc` is build-time; `gcompat` is runtime; `python3` is build-time *for node-gyp* but could be a runtime dep elsewhere. The naive reading — "names containing `dev` or `gcc` are build-time" — is a heuristic, and the codebase has a standing position against heuristics where a frozen catalog will do (`_GENERATOR_HEADER_MARKERS`, `_LOCKFILE_PRECEDENCE`, and Phase 7 [ADR-0010](0010-chainguard-cve-image-lookup-frozen-yaml.md)'s CVE-to-image YAML). `phase-arch-design.md §Component design — Amendment A §17` resolves G3 to a data catalog plus a `NodeManifestProbe` slice extension.

## Options considered

- **Option A — Heuristic package-name matching.** Classify by substring (`dev`, `gcc`, `-headers`) or a small regex. **Pattern:** Stringly-typed heuristic. **Rejected** — fragile, false-positive prone (`libdevmapper` is a runtime library; `nodejs-dev` overlaps both meanings), and unauditable: an operator cannot see *why* a package was staged where it was.
- **Option B — Frozen YAML classification catalogs.** `data/apk_classification.yaml` and `data/apt_classification.yaml`, each a flat map of package name → `build_toolchain | runtime_library | diagnostic`, CODEOWNERS-gated and file-hash fenced. **Pattern:** Final-tuple / data-as-config marker catalog — data declares the classification, code reads it; no branching.
- **Option C — Query the package database inside the built image at runtime.** Run `apk info` / `dpkg -l` against the assembled image to learn each package's role. **Pattern:** Runtime introspection. **Rejected** — needs the built image to exist, which defeats a static gather pipeline; circular (the recipe needs the classification to *produce* the image).

## Decision

Adopt **Option B.** Ship two frozen catalogs under the plugin:

- `plugins/distroless-migration--node--npm/data/apk_classification.yaml`
- `plugins/distroless-migration--node--npm/data/apt_classification.yaml`

Each maps a package name to one of `build_toolchain | runtime_library | diagnostic` (`diagnostic` covers `curl`/`strace`-class packages that belong in neither production stage and signal a refactor smell). The catalogs are CODEOWNERS-gated and file-hash fenced, mirroring [ADR-0010](0010-chainguard-cve-image-lookup-frozen-yaml.md)'s frozen-catalog discipline and the S9-02 hash-fence pattern. They load through the established catalog-loader seam — no per-call file parse, no branching `if/elif` on package name.

The `NodeManifestProbe` slice gains an additive field `native_modules: tuple[NativeModule, ...]`. Each `NativeModule` records the detection signal (`binding.gyp`, a `*.node` artifact, or a `node-gyp` dependency in the resolved tree). The slice extension is additive to the existing sub-schema (`additionalProperties: false` preserved) and is enumerated in the [ADR-0029](0029-amend-byte-edit-allowlist-for-amendment-a.md) byte-edit allowlist.

The multi-stage recipe consumes both: it walks the resolved `apk`/`apt` dependency set against the catalogs to stage each package, and selects the `cgr.dev/chainguard/node:*-dev` builder image when `native_modules` is non-empty, then COPYs the compiled `node_modules` into the distroless runner.

## Tradeoffs

| Gain | Cost |
|---|---|
| Classification is auditable — an operator reads one YAML row to see why `gcc` landed in the builder stage; no inference to reverse-engineer | The catalog must be curated and kept current as Alpine/Debian packages evolve; a missing package is a gather gap, surfaced as `unclassified` rather than guessed |
| Matches the codebase's marker-catalog discipline (`_LOCKFILE_PRECEDENCE`, ADR-0010 CVE YAML) — one consistent extension shape, data not code | Two catalog files to maintain (`apk` + `apt`); a Node project rarely touches both, but the recipe must pick the right one per base-image family |
| File-hash fence makes an unreviewed catalog edit a CI break — the classification cannot drift silently | The fence adds one CI assertion and the hash must be re-baselined on every legitimate catalog PR (CODEOWNERS-gated, so the friction is intentional) |
| `native_modules` slice lets the recipe decide builder-image selection from gather data alone — no build-then-inspect round trip | The slice extends an existing Phase 1 probe's output; the edit is allowlisted ([ADR-0029](0029-amend-byte-edit-allowlist-for-amendment-a.md)) but is a byte-edit to a stable file, accepted under the additive-field reading |
| `diagnostic` as a third class names the "belongs in neither stage" case explicitly instead of forcing a binary build/runtime guess | Three-way classification means the recipe must handle the `diagnostic` case (drop + WARN), not just two stages |

## Pattern fit

Implements **Strategy via data / marker catalog** (toolkit §Behavioral — strategy expressed as a typed table, not branching code): the build-vs-runtime policy is a frozen map iterated at one call site; new packages are data additions, never code branches. Mirrors the established `_GENERATOR_HEADER_MARKERS` / `_LOCKFILE_PRECEDENCE` catalogs and Phase 7 [ADR-0010](0010-chainguard-cve-image-lookup-frozen-yaml.md). The `NativeModule` slice obeys newtype + sum-type domain-modeling discipline; the probe slice extension stays within the frozen Probe ABC ([production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)) — extension by additive field, never an ABC edit.

## Consequences

- `plugins/distroless-migration--node--npm/data/apk_classification.yaml` and `apt_classification.yaml` are net-new files under CODEOWNERS.
- A file-hash fence test asserts each catalog's content hash against a baseline; an unreviewed edit fails `make check`.
- The `NodeManifestProbe` sub-schema gains the additive `native_modules` array; the envelope `$ref` is unchanged (the probe already has a `$ref`).
- The byte-edit to `NodeManifestProbe` and its schema is enumerated in [ADR-0029](0029-amend-byte-edit-allowlist-for-amendment-a.md).
- The multi-stage refactor recipe ([ADR-0014](0014-multi-stage-refactor-recipe-synchronous.md)) consumes the catalogs and the `native_modules` slice as typed inputs; an `unclassified` package surfaces as a WARN in the PR description rather than a silent stage guess.
- Golden fixtures cover a pure-JS project (no builder stage), a native-module project (builder stage selected), and a project with a `diagnostic`-class package.

## Reversibility

**High.** The catalogs are data — correcting a misclassification is a one-row PR plus a hash re-baseline, no code change. The `native_modules` slice shape is the only contract a downstream recipe binds to; changing it is one schema edit. Replacing the catalog approach entirely (e.g., switching to upstream package metadata) would not propagate past the catalog-loader seam.

## Evidence / sources

- `../final-design.md §Amendment A §A.2` (gap G3), §A.3 departure #2
- `../phase-arch-design.md §Component design — Amendment A §17`
- [ADR-0010 — CVE-to-image lookup frozen YAML](0010-chainguard-cve-image-lookup-frozen-yaml.md) (frozen-catalog discipline precedent)
- [ADR-0029 — Amendment A byte-edit allowlist extension](0029-amend-byte-edit-allowlist-for-amendment-a.md)
- [production ADR-0007 — Probe contract preserved POC→service](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)
- [production ADR-0031 — Plugin architecture](../../../production/adrs/0031-plugin-architecture.md)
