# Attempt log: S3-02 — `NpmVulnProvenanceAdapter` body + DI kwargs

## Attempt 1 — 2026-05-20 — BLOCKED (stopped at Stage 1 hard gate)

**Outcome:** No code shipped. The `phase-story-executor` Context-Loader hard
gate fired: Stage 1 surfaced multiple unsatisfiable preconditions and
contract contradictions that no correct implementation can resolve without a
story rewrite + a missing upstream phase. Per global Rule 12 (fail loud) and
the executor's own failure-mode table ("story references a file that doesn't
exist → log it / surface"), the story is marked **BLOCKED** rather than
forcing a partial, contract-divergent adapter through.

### Blocker A (root cause) — the Phase 3 npm plugin directory does not exist

S3-02's deliverable is
`plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py`,
described throughout the story as "an additive new file under an **existing**
Phase 3 plugin directory" and pinned by Phase 7 ADR-0009 row #1 as "new file
(additive new file under Phase 3 plugin directory)".

That directory **does not exist.** `plugins/` today contains only
`PLUGINS.lock`, `PLUGINS.lock.README.md`, `__init__.py` — no
`vulnerability-remediation--node--npm/` subtree, no `plugin.yaml`, no
`api.py`, no `recipes/`. CLAUDE.md is explicit: *"Phases 3, 5, 6.5 — Designed
(final-design + arch + ADRs + stories) but not implemented."*

The Phase 7 executor pipeline has run ahead of its real dependency. S1-01..
S1-06, S2-01..S2-05, and S3-01 were all self-contained inside
`src/codegenie/primitives/vuln_provenance/` + tests — none needed Phase 3.
S3-02 is the **first** Phase 7 story that crosses into `plugins/` and
materially requires the Phase 3 npm plugin to be implemented. S3-02's
`Depends on:` line lists only Phase 7 stories; it never declares the implicit
hard dependency on Phase 3's `vulnerability-remediation--node--npm` plugin
existing. It does.

### Blocker B — `bench/vuln-remediation/` cassette does not exist

S3-02 AC ("Phase 3–6.5 regression suite green … byte-identical against the
`bench/vuln-remediation/` cassette replay … ε ≤ \$0.01 … the load-bearing
assertion") and High-level-impl Step 3 done-criterion #3 both require a
`bench/vuln-remediation/` cassette replay. There is **no `bench/` directory
at all.** The load-bearing regression assertion cannot be evaluated.

### Blocker C — the landed `attribute(...)` contract has no `repo_context` / no lockfile

The story's Context, Implementation outline, and AC-7 specify
`attribute(self, *, cve_id, package_id, image_ref, sbom, repo_context:
RepoContext) -> Provenance` and an implementation that "reads `package.json`
+ `package-lock.json` from the gathered `RepoContext`" and runs a
`_walk_lockfile_chain(...)` over the npm lockfile.

The **landed** Protocol (`src/codegenie/primitives/vuln_provenance/
protocols.py`, shipped by S1-04 / swapped by S2-04) is:

```python
def attribute(self, cve_id: CveId, package_id: PackageId,
              image_ref: ImageRef | None, sbom: SyftSbom) -> Provenance: ...
```

— **positional** args, **no `repo_context`**, **no lockfile access**.
`assemble_provenance` (S2-04, `assembly.py:167`) calls it positionally:
`factory(cls).attribute(cve_id, package_id, image_ref, sbom)`. The only
evidence the adapter receives is the `SyftSbom`. There is no `RepoContext`,
no `package.json`, no `package-lock.json`. The story's entire "lockfile
walk" implementation outline is inconsistent with the landed contract — the
design diverged between High-level-impl (Step 3, "reads gathered
`RepoContext`") and what S1-04/S2-04 actually shipped (SBOM-only).

A correct npm adapter against the landed contract must classify direct-vs-
transitive from `SyftArtifact.locations[].path` `node_modules/` nesting
(`node_modules/lodash/...` = direct; `node_modules/express/node_modules/
lodash/...` = transitive, chain `[express, lodash]`). That is a sound design
— but it is **not the design S3-02 describes**, so executing S3-02 as
written is impossible; the story needs a rewrite first.

### Blocker D — `Provenance` variant fields contradict the story ACs

Story AC-8 / AC for unit tests reference `AppDirect(package_id, version,
locked_version, location)` and `AppTransitive(package_id, version,
locked_version, location, chain)`. The **landed** `types.py` (S1-03) variants
are:

- `AppDirect(kind, manifest_path: Path, package: PackageId, confidence:
  AdapterConfidence)`
- `AppTransitive(kind, manifest_path: Path, package: PackageId, chain:
  tuple[PackageId, ...] (min_length=2), confidence: AdapterConfidence)`

There is **no `version`, no `locked_version`, no `location`** field anywhere.
The S3-01 integration test already encodes the landed shape
(`app.package`, `app.chain`). The story's field vocabulary is stale.

### Blocker E — `AdapterConfidence` is a plain `StrEnum`, not payload-carrying

Story AC-7 specifies `confidence()` returns `AdapterConfidence.High` /
`AdapterConfidence.Degraded(reason="package_not_in_lockfile")` /
`AdapterConfidence.Unavailable(reason="lockfile_missing")` — i.e. a
payload-carrying sum type. The **landed** `AdapterConfidence` (S1-02) is a
flat `StrEnum`: `HIGH`, `DEGRADED`, `UNAVAILABLE` — no constructor, no
payload. `confidence(self) -> AdapterConfidence` can only return a bare
member. The three "documented conditions" the story attaches to confidence
values are also lockfile-derived (Blocker C), so they are unimplementable as
specified regardless.

### Blocker F — S3-01's integration test is internally contradictory

`tests/integration/test_provenance_assembly_via_plugins.py` (the S3-01
deliverable, named by S3-02 as "the canonical contract") contains two
positive-path tests that **both query `PackageId("lodash")`** and assert
**contradictory** outcomes:

- `test_npm_adapter_returns_app_direct_for_root_dependency` →
  `_assemble(PackageId("lodash"))` must be `AppDirect`.
- `test_npm_adapter_returns_app_transitive_for_deep_dependency` →
  `_assemble(PackageId("lodash"))` must be `AppTransitive` with
  `chain[0] == express`.

`assemble_provenance` is deterministic — the same `(package_id, sbom)` query
resolves to exactly one `Provenance`. No adapter can satisfy both. The S3-01
attempt log acknowledges the fixture contents "do not affect behavior" in the
red state and were never reconciled. S3-02 AC-12 demands all three go GREEN
while the TDD plan says "Do NOT silently widen S3-01's test fixtures" — the
two requirements are mutually exclusive given the fixture
(`npm_lodash_app.json`) carries only two top-level-`node_modules` artifacts
(`lodash`, `express` — both *direct*; no transitive package at all).

Recommended fix (for the rewrite, not done here): restructure
`npm_lodash_app.json` to the real-world CVE-2021-23337 shape — `express`
direct at `node_modules/express/package.json`, `lodash` transitive at
`node_modules/express/node_modules/lodash/package.json` — and point the
direct test at `express`, the transitive test at `lodash`. This corrects a
copy-paste defect (the transitive test queries the wrong package id); it is
not "widening to accommodate a wrong implementation."

### Blocker G — AC-12 (S3-01 tests GREEN) contradicts S3-02's own Out-of-scope

AC-12 requires S3-02 to flip S3-01's three integration scenarios to GREEN and
remove their `xfail` markers. But S3-02's Out-of-scope places the `api.py`
import-wiring in S3-03 ("This story's adapter is registered only when S3-03's
`api.py` import fires"). S3-01's test drives registration through
`load_plugins(_PLUGIN_ROOT, _PLUGIN_LOCK)` — which discovers plugins via
`plugin.yaml` and runs their `api.py`. With no plugin scaffold and no `api.py`
(Blocker A) and the wiring deferred to S3-03, `load_plugins` registers
nothing, `assemble_provenance` returns `Unknown(no_adapter_resolved)`, and
removing the `xfail` markers turns three passing-xfail tests into three hard
CI failures. S3-02 cannot make the integration suite green; that is
structurally S3-03's (and Phase 3's) job.

## Resolution path (ordered)

1. **Implement Phase 3** — at minimum the `vulnerability-remediation--node--
   npm` plugin tree (`plugin.yaml`, `api.py`, `recipes/`, manifest,
   `PLUGINS.lock` entry) and the `bench/vuln-remediation/` cassette fixtures.
   S3-02/S3-03 cannot land before this. This is a roadmap-ordering issue:
   Phase 3 must precede Phase 7's Step 3.
2. **Rewrite S3-02 via `/phase-story-writer` (or amend via `/phase-architect`
   + an ADR)** to match the *landed* contract:
   - `attribute(self, cve_id, package_id, image_ref, sbom)` — positional, no
     `repo_context`; classify from `SyftArtifact.locations[].path`
     `node_modules/` nesting, not a lockfile walk.
   - `AppDirect` / `AppTransitive` field names: `manifest_path`, `package`,
     `chain`, `confidence` — drop `version` / `locked_version` / `location`.
   - `confidence() -> AdapterConfidence` returns a bare `StrEnum` member.
   - Reconcile the DI-kwarg `__init__` AC: the SBOM-walk adapter receives the
     `sbom` as a call argument and needs no `sbom_reader` /
     `image_manifest_cache`; decide whether it declares any DI kwargs at all.
3. **Fix the S3-01 integration-test defect (Blocker F)** as part of, or just
   before, the S3-02 rewrite.
4. Only then re-run `phase-story-executor` on the rewritten S3-02.

## What was NOT done and why

- No adapter file created. Creating `plugins/vulnerability-remediation--node--
  npm/adapters/npm_provenance.py` would have produced a half-built plugin
  directory (an `adapters/` subdir with no surrounding `plugin.yaml` / `api.py`
  / `recipes/`), unreferenced by any loader, against a contract the story does
  not describe — incoherent and likely to collide with the eventual Phase 3
  plugin implementation.
- No edits to `tests/integration/test_provenance_assembly_via_plugins.py`.
  Removing the `xfail` markers without a registered adapter would turn CI red.
- No commit of code. Only this attempt log, the `_lessons.md` entry, and the
  story `Status:` line change are committed (docs-only, CI-safe).

## Gate status

`make check` not run for S3-02 changes (no code changed). The repo is at
master `0c4725c` with all CI green; this attempt adds documentation only.
