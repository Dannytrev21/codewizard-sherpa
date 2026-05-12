# ADR-0011: No Helm template rendering, no HCL parsing, no `npm ls` invocation in Phase 1

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** scope · determinism · supply-chain · cve-surface · facts-not-judgments
**Related:** ADR-0009, [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md)

## Context

`DeploymentProbe` parses Helm, Kustomize, raw Kubernetes manifests, and Terraform. `NodeManifestProbe` enumerates dependencies from lockfiles. The full information needed by downstream consumers includes:

- **Rendered Helm output** — what the deployed manifests *actually* look like after `helm template` substitutes values. The probe instead records the `image_reference` *path* (e.g., `image.repository`) and the value at that path, leaving rendering to the Planner.
- **Resolved Terraform plan** — what infrastructure Terraform would create. The probe instead records `*.tf` paths only; no parse, no plan.
- **Installed dependency tree** — what `npm ls` / `pnpm list` would report after install. The probe instead reads the lockfile (the deterministic source of truth).

Each of the three has a tempting "just do it" path that all three lens designs explicitly rejected:

- **Helm template rendering** requires the `helm` binary on `$PATH` and the rendered template depends on the Helm version, the locally-resolved chart dependency tree, and the values context — non-deterministic with respect to the caller's environment. It also opens a probe-time subprocess attack surface (Phase 0 ADR-0012's allowlist would need `helm`).
- **HCL parsing via `python-hcl2`** historically has CVEs (the security lens flagged this explicitly); no Phase 1 consumer requires Terraform parsing.
- **`npm ls` / `pnpm list`** require `node_modules` to be installed, which means running `npm install` — full-on supply-chain exposure at probe time. Plus version-dependent output.

The synthesizer collected these into a single non-goal cluster (`final-design.md "Components"` #4, #6, "Non-goals" #4, #5, #6).

## Options considered

- **Render / parse / invoke during gather.** Fullest information; non-deterministic, CVE-prone, supply-chain-exposed, breaks `production/design.md §2.4` ("Determinism over probabilism for structural changes").
- **Render / parse / invoke during Planner only (Phase 3+).** Planner has the budget, the deliberate scope, and the right place to take on those tradeoffs.
- **Record evidence-not-judgment in Phase 1: paths, references, lockfile-resolved data.** Probe records facts; Planner decides.

## Decision

**Phase 1's `NodeManifestProbe` and `DeploymentProbe` capture evidence, not resolved state:**

1. **No `helm template` / `helm install` invocation.** `DeploymentProbe` parses `Chart.yaml` and `values*.yaml` via `safe_yaml.load`; records `image_reference` as a `{path, value}` block from the values file; does not substitute templates. Helm template rendering is deferred to Phase 3+'s Planner (`recipe-first → RAG → LLM-fallback`, production ADR-0011).
2. **No `kustomize build` invocation.** `DeploymentProbe` parses `kustomization.yaml` and follows `resources:` one level deep with `repo_root` containment; does not invoke the `kustomize` binary; does not resolve overlays beyond the cap (depth 5, 50 files total).
3. **No `python-hcl2` / Terraform parsing.** `DeploymentProbe` enumerates `*.tf` files by path only. `terraform_present: true, terraform_files: list[relative_path]`; `confidence: low` if Terraform alone is detected. A richer parser lands in Phase 2 with an opt-in flag if a consumer demands.
4. **No `npm ls` / `pnpm list` / `yarn install`.** `NodeManifestProbe` reads lockfiles (`pnpm-lock.yaml`, `package-lock.json`, `yarn.lock`) directly. Lockfile is the deterministic source. No `node_modules` exists during gather (and `node_modules/*/package.json` is explicitly **not** in `declared_inputs`).
5. **No `helm` / `kustomize` / `terraform` binaries added to `ALLOWED_BINARIES`.** Only `git` (required) and `node` (optional, ADR-0001) live there at the end of Phase 1.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 1 stays deterministic — same inputs always produce same slices; the `production/design.md §2.4` commitment holds | Helm-heavy repos report `image_reference` paths without resolved tag values; downstream consumers must render if they need the resolved string |
| `python-hcl2`'s historic CVEs avoided; no Terraform parser ships in Phase 1 | Terraform-heavy repos get `confidence: low` Phase 1 slices; Phase 2 closes if/when a consumer demands |
| No supply-chain exposure from `npm install` / `node_modules` parsing — adversarial-bytes-at-scale threat closed by construction | Lockfile is the source of truth; lockfile drift from `node_modules` is invisible (deliberate; lockfile is what the resolver committed to) |
| `ALLOWED_BINARIES` stays at two entries (`git`, `node`); minimum subprocess attack surface | A Phase-3 recipe that needs rendered Helm must invoke `helm` from the Planner, gated by its own ADR amendment |
| Multi-environment Helm captured as `environments: list` (ADR-0012) — facts captured, rendering deferred | Multi-env consumers handle list shape; the singleton-vs-list question is resolved additively |
| Composes with ADR-0008 — no new external-process surface beyond `node --version` | The "what would this deployment actually deploy" question is unanswered by Phase 1; the Planner is responsible |
| Composes with ADR-0009 — no new C-extension or PyPI parser deps for Helm/Kustomize/Terraform | Some Phase-3 consumers may discover Phase 1 records insufficient evidence; the response is a new probe in a later phase, not a Phase 1 invocation |

## Consequences

- `DeploymentProbe`'s slice records `chart_path`, `image_reference: {path, value}`, `environments: list[EnvironmentEntry]`, `terraform_present`, `terraform_files`, `kustomization_resource_path_outside_repo`, `security_context`, `exposed_ports`, `required_env_vars` — facts only.
- `NodeManifestProbe`'s slice records `direct_dependencies`, `declared_engines`, `lockfile`, `native_modules`, `optional_dependencies`, `bundled_dependencies` — lockfile-resolved facts.
- `ALLOWED_BINARIES` at the end of Phase 1 = `{"git", "node"}`. Any future binary addition follows the ADR-0001 workflow.
- Phase 2's `IndexHealthProbe` may flag "Helm chart present but no rendered output is captured" as a confidence signal; the data shape supports this without re-gather.
- Phase 3's `recipe-first` planner (production ADR-0011) is responsible for invoking `helm template` / `kustomize build` if a recipe needs rendered state — at Planner time, gated by Planner-layer policy, not at gather time.
- Phase 7's Chainguard distroless migration consumes the `native_modules` slice + the catalog (ADR-0006). The catalog's `system_deps_required` is the load-bearing input; no `npm ls` is required.
- Phase 14's continuous gather inherits the determinism — replaying a gather on the same SHA produces the same slices.

## Reversibility

**Medium.** Adding any of `helm`, `kustomize`, `terraform` to `ALLOWED_BINARIES` is mechanically the ADR-0001 workflow. Adding `python-hcl2` (or a maintained successor) is the ADR-0009 amendment workflow. Cached `repo-context.yaml` artifacts produced under Phase 1 do not become invalid — the new fields are additive in future sub-schemas. The reverse direction (e.g., a Phase-3 team adds `helm template` invocation and the gather drifts into non-determinism) is the exact failure mode this ADR pins against.

## Evidence / sources

- `../final-design.md "Components" #4` — `NodeManifestProbe`'s no-`npm-ls` decision
- `../final-design.md "Components" #6` — `DeploymentProbe`'s no-Helm-render / no-HCL decision
- `../final-design.md "Load-bearing commitments check"` — facts vs. judgments
- `../final-design.md "Synthesis ledger" "AGREE"` — all three lenses agreed on no-script-eval, no-Helm-render, no-`npm-ls`
- `../phase-arch-design.md "Non-goals"` #4, #5, #6 — explicit anti-scope
- `../phase-arch-design.md "Component design" #6 DeploymentProbe` — interface
- ADR-0001 — `ALLOWED_BINARIES` extension workflow
- ADR-0009 — parser dependency policy
- [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md) — the determinism commitment
