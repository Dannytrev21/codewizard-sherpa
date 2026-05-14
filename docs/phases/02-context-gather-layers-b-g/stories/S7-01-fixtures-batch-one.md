# Story S7-01 — Fixtures batch 1: `minimal-ts` + `native-modules` + `distroless-target`

**Step:** Step 7 — Plant five-repo fixture portfolio + per-probe golden files + remaining adversarial corpus
**Status:** Ready
**Effort:** M
**Depends on:** S4-07 (Layer B sub-schemas — goldens-to-come reference them), S6-08 (Layer D/E/G sub-schemas + freshness registrations — `minimal-ts` smokes every probe)
**ADRs honored:** ADR-0001 (allowlisted binaries — `regenerate.sh` invokes only allowlisted tools), ADR-0003 (heaviness sort — `distroless-target` exercises a heavy probe path), ADR-0004 (image-digest declared-input token — `distroless-target`'s `Dockerfile` produces a real digest the regen script resolves), ADR-0005 (no plaintext persisted — fixture trees commit zero `.codegenie/cache/` blobs), ADR-0007 (no plugin loader — no fixture seeds `plugins/`), ADR-0009 (pytest-xdist veto — closed-set fixture trees so parallelism never tempts).

## Context

Step 7 lands the **five-repo fixture portfolio** Phase 2's golden-file lane and CI-gated `portfolio` job both depend on. This story ships **three of the five fixtures** in dependency order — the two that are pure smoke targets (`minimal-ts`, `native-modules`) plus the Phase-7-forward-looking `distroless-target` that proves Layer C runtime-trace and SBOM probes work on an already-distroless base image. The other two fixtures — `monorepo-pnpm` and the **load-bearing** `stale-scip` — land in S7-02 because they depend on additional probe surface (`DepGraphProbe` cross-package edges and the staleness-fixture regeneration ritual respectively).

`minimal-ts` is the **smallest happy path**: every Phase-2 language-agnostic probe runs against it without producing a `confidence="unavailable"` result for spurious reasons. It is ≤ 200 files. It is the smoke anchor for the eventual `portfolio` CI job (S8-03) — if any probe regresses, this fixture's golden diff fails first. The shape is one tier larger than Phase 1's `node_typescript_helm/` (which is the seed canonical fixture; reuse its README + `_FILE_SPECS` pattern verbatim).

`native-modules` covers the **C-extension manifest edge case** Phase 1 deliberately deferred (`localv2.md` §5.1 native-module catalog). Manifests with `node-gyp` triggers + `binding.gyp` markers + an `install` script that would normally invoke compilation. The fixture **must not actually compile anything** at golden regen time (the regen script must skip `npm install --build-from-source`); the manifest's presence alone is what `NodeManifestProbe` (Phase 1) and `NodeReflectionProbe` (Phase 2 S4-06) detect.

`distroless-target` is the **Phase-7 forward-looking fixture**. It ships a `Dockerfile` whose final stage is `FROM gcr.io/distroless/nodejs20-debian12@sha256:<pinned>` (or the equivalent — chainguard.dev's `cgr.dev/chainguard/node:latest` works equivalently for Phase 2). The image, once built, exercises `RuntimeTraceProbe`'s "already-distroless" code path — zero `sh` invocations, zero `mount` syscalls beyond startup, terse `strace` output. This is the only Phase-2 fixture that builds a real container image; the regen-time cost is amortized across goldens for `dockerfile`, `entrypoint`, `shell_usage`, `certificate`, `runtime_trace`, `sbom`, and `cve`.

The contract this story establishes — and that S7-02 / S7-03 inherit — is: **every fixture's bytes are part of the contract.** Adding or removing a file changes one or more goldens. The shape test for each fixture (one per fixture, modeled on Phase 1's `test_fixture_node_typescript_helm_shape.py`) is the closed-set guard.

`.codegenie/cache/` is **NOT committed** to any fixture. CI regenerates the cache on every run. The fixture-side `.gitignore` enforces it (one line: `.codegenie/`); a CI check (S8-03's `portfolio` job startup) greps any committed `tests/fixtures/portfolio/*/\.codegenie/` paths and fails loud.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Testing strategy" → "Fixture portfolio engineering"` — fixture tree rules (≤ 200 files; `regenerate.sh` reviewed-as-code; no committed `.codegenie/cache/`).
  - `../phase-arch-design.md §"Testing strategy" → "Golden files"` — five-fixture table; `minimal-ts` / `native-modules` / `distroless-target` rows.
  - `../phase-arch-design.md §"Component design" #6` (`RuntimeTraceProbe` — the `distroless-target` smoke target).
  - `../phase-arch-design.md §"Edge cases"` rows 1–10 (the typical-probe smoke cases `minimal-ts` exercises).
- **Phase ADRs:** ADR-0001 (`ALLOWED_BINARIES` — `regenerate.sh` invokes only these), ADR-0004 (image-digest resolution — `distroless-target` produces the canonical token), ADR-0007 (no plugin loader — no fixture seeds `plugins/`).
- **Implementation plan:** `../High-level-impl.md §"Step 7"` — fixture portfolio bullets, regenerate-each-run policy, `.codegenie/cache/` NOT committed.
- **Source design:** `../final-design.md §"Open questions"` #6 (per-fixture cache pre-warming policy escape valve — read so a future regression to "let's commit caches" goes through the named door).
- **Existing code:**
  - `tests/fixtures/node_typescript_helm/` (Phase 1's canonical fixture — copy README + shape-test conventions).
  - `docs/phases/01-context-gather-layer-a-node/stories/S2-03-fixture-node-typescript-helm.md` — the `_FILE_SPECS` pattern + closed-set complement test (AC-14 there is what this story's AC-X-closed-set inherits).

## Goal

Three fixtures exist under `tests/fixtures/portfolio/`:

1. **`minimal-ts/`** — ≤ 200 files; ships `package.json`, `pnpm-lock.yaml`, `tsconfig.json`, `.nvmrc`, `src/index.ts`, `.github/workflows/ci.yml`, plus a minimal `Dockerfile` so Layer C probes have a target; minimal Helm chart so Layer A `DeploymentProbe` populates. Smoke for every Phase-2 language-agnostic probe. No `binding.gyp`, no `node-gyp` triggers, no monorepo workspaces.
2. **`native-modules/`** — manifest declares a dependency that normally triggers `node-gyp` (e.g., `node-sass@4.x` or `bcrypt@5.x` — pick one with a stable installer surface); `binding.gyp` present at root; `install` script in `package.json` references `node-gyp rebuild`. **No compilation occurs at regen time** — the regen script uses `npm install --ignore-scripts`.
3. **`distroless-target/`** — Dockerfile final stage = `FROM gcr.io/distroless/nodejs20-debian12@sha256:<digest>` (or `cgr.dev/chainguard/node:latest@sha256:<digest>` — equivalent); minimal Node app that prints + exits; `regenerate.sh` builds the image, captures the resolved digest into `built-image.digest` (used by `ProbeContext.image_digest_resolver` in CI), and tears the image down.

Each fixture ships:

- `README.md` — table of `relpath` → consuming probe(s); references `../phase-arch-design.md`.
- `regenerate.sh` — reviewed-as-code; idempotent; produces byte-identical output across two consecutive runs locally before any merge.
- `.gitignore` — at minimum `.codegenie/` and (for `distroless-target`) `built-image.digest`'s tarball if cached locally.
- A shape test under `tests/unit/test_fixture_<name>_shape.py` modeled on Phase 1's `test_fixture_node_typescript_helm_shape.py` (closed-set complement, no forbidden subpaths, line-ending hygiene).

## Acceptance criteria

**`minimal-ts/` fixture tree shape**

- [ ] **AC-1.** `tests/fixtures/portfolio/minimal-ts/` directory exists; file count ≤ 200.
- [ ] **AC-2 — `package.json`** declares `"name": "minimal-ts"`, `"version": "0.0.1"`, `"dependencies": {"express": "^4.18.2"}`, `"devDependencies": {"typescript": "^5.3.0", "vitest": "^1.0.0"}`, `"engines": {"node": ">=20.0.0"}`, `"scripts": {"build": "tsc -p .", "test": "vitest run", "start": "node dist/index.js"}`; `parsers.safe_json.load(...)` returns no exception.
- [ ] **AC-3 — `pnpm-lock.yaml`** exists with minimal valid pnpm v6 header (`lockfileVersion: '6.0'`); parses via `safe_yaml.load`.
- [ ] **AC-4 — `tsconfig.json`** is valid JSONC with at least one `//` line comment AND one `/* */` block comment; parses via `parsers.jsonc.load`.
- [ ] **AC-5 — `.nvmrc`** exists with content `v20.11.0\n` (exact bytes).
- [ ] **AC-6 — `src/index.ts`** has a 3-line `import express; ... server.listen(3000)` body.
- [ ] **AC-7 — `.github/workflows/ci.yml`** declares one `build` job with `run: pnpm install && pnpm test`; parses via `safe_yaml.load`.
- [ ] **AC-8 — `Dockerfile`** exists at fixture root; final stage `FROM node:20-slim`; `USER node`; `EXPOSE 3000`; `CMD ["node", "dist/index.js"]`. No multi-stage; minimal so `dockerfile`, `entrypoint`, `shell_usage`, `certificate` probes produce a populated slice without exotic edge cases.
- [ ] **AC-9 — `deploy/chart/{Chart.yaml,values.yaml,values-prod.yaml}`** exist with the Phase 1 ADR-0012 multi-environment shape (copy from `node_typescript_helm/` verbatim; this is the canonical multi-env exemplar).
- [ ] **AC-10 — `README.md`** lists every file in `_FILE_SPECS` (AC-25) by relpath and names every probe in its `consumers` tuple.

**`native-modules/` fixture tree shape**

- [ ] **AC-11.** `tests/fixtures/portfolio/native-modules/` directory exists.
- [ ] **AC-12 — `package.json`** declares one C-extension dependency (`"bcrypt": "^5.1.0"` or `"node-sass": "^4.14.1"` — implementer picks the stable one); declares `"scripts": {"install": "node-gyp rebuild"}` in the manifest (the trigger marker the `NodeManifestProbe` and `NodeReflectionProbe` detect); parses via `safe_json.load`.
- [ ] **AC-13 — `binding.gyp`** exists at fixture root with a minimal `{ "targets": [{"target_name": "addon", "sources": ["src/addon.cc"]}] }` body; parses via `safe_json.load`.
- [ ] **AC-14 — `src/addon.cc`** exists as a trivial empty C++ source (3 lines: `#include <node.h>` + empty `Initialize` + `NODE_MODULE` macro). **Never compiled at regen time.**
- [ ] **AC-15 — `pnpm-lock.yaml` OR `package-lock.json`** exists with the dependency frozen at the version declared in `package.json` (implementer picks pnpm to match Phase 1's lockfile-precedence happy path).
- [ ] **AC-16 — `.npmrc`** (or `regenerate.sh` `npm install` invocation) explicitly disables `node-gyp` compilation: `ignore-scripts=true`. The regen script verifies post-install that `build/Release/` does not exist.
- [ ] **AC-17 — `README.md`** lists every file by relpath; explicitly documents "no compilation at regen time" with the rationale (CI determinism — `node-gyp` outputs differ across platforms).

**`distroless-target/` fixture tree shape**

- [ ] **AC-18.** `tests/fixtures/portfolio/distroless-target/` directory exists.
- [ ] **AC-19 — `package.json`** declares minimal Node app — no `dependencies`, `"main": "index.js"`, `"scripts": {"start": "node index.js"}`.
- [ ] **AC-20 — `index.js`** is 5 lines: `console.log("ok"); process.exit(0);` (plus a `#!/usr/bin/env node` shebang and a comment).
- [ ] **AC-21 — `Dockerfile`** has two stages — `FROM node:20-slim AS build` (does `npm ci` against the empty manifest, copies `index.js`) and `FROM gcr.io/distroless/nodejs20-debian12@sha256:<pinned-digest>` (or `cgr.dev/chainguard/node:latest@sha256:<pinned-digest>`) for the final stage; final stage `COPY --from=build /app /app`; `WORKDIR /app`; `CMD ["index.js"]`; no `USER` directive (distroless images run as non-root by default — `RuntimeTraceProbe` records this).
- [ ] **AC-22 — `regenerate.sh`** is reviewed-as-code; invokes `docker build -t distroless-target-fixture:latest .` via `run_allowlisted("docker", ...)`; on success writes the resolved image digest to `built-image.digest` (the file is `.gitignored`); tears the image down with `docker image rm distroless-target-fixture:latest`. Exits non-zero with a clear message if `docker` is unavailable on the host.
- [ ] **AC-23 — `.gitignore`** includes `.codegenie/` AND `built-image.digest` AND any local image tarball.
- [ ] **AC-24 — `README.md`** explicitly notes "Phase 7 forward-looking — exercises Layer C against an already-distroless base; primary user is `RuntimeTraceProbe` + `SbomProbe` + `CveProbe`."

**`_FILE_SPECS` SSoT + closed-set per fixture**

- [ ] **AC-25 — `_FILE_SPECS: tuple[_FileSpec, ...]` per fixture.** Each shape test (`tests/unit/test_fixture_<name>_shape.py`) declares a module-level closed-set typed manifest identical in shape to Phase 1's S2-03 pattern: `_FileSpec(relpath, consumers, parser, content_checks)`. `_ProbeName = Literal[...]` lists every Phase-2 probe name (Layer A + Layer B + Layer C + Layer D + Layer E + Layer G) — the closed set is **mypy --strict** typo-resistant.
- [ ] **AC-26 — closed-set complement test per fixture.** `test_fixture_<name>_tree_is_closed_set` walks the fixture tree (excluding `__pycache__`, `.pytest_cache`, dotfiles created by editors) and asserts the set equals `{spec.relpath for spec in _FILE_SPECS}`. A stray file added by mistake fails the test before it can dirty an S7-03 golden silently.
- [ ] **AC-27 — no forbidden subpaths per fixture.** None of `node_modules/`, `.codegenie/`, `dist/`, `coverage/`, `build/`, `build/Release/` (the `node-gyp` output dir), `.DS_Store` exist inside any fixture tree.
- [ ] **AC-28 — line endings.** Every text file in every fixture is UTF-8, LF-only, ends with `b"\n"` — no CRLF, no BOM. Parametrized over every `_FILE_SPECS` entry.
- [ ] **AC-29 — README references every spec.relpath per fixture.** `test_fixture_<name>_readme_references_every_spec` asserts every `spec.relpath` and every probe name in `spec.consumers` appears literally in the fixture's `README.md`.

**`regenerate.sh` reviewed-as-code discipline**

- [ ] **AC-30 — `regenerate.sh` byte-identical across runs.** For each fixture, two consecutive `bash regenerate.sh` invocations produce a tree whose `find tests/fixtures/portfolio/<name> -type f | sort | xargs sha256sum` is identical. **Verified locally** before opening the Step 7 PR (manual; documented in `regenerate.sh`'s top-of-file comment; not a CI assertion because some operations involve `docker pull` whose underlying images get repushed by upstream maintainers — see Notes-for-implementer).
- [ ] **AC-31 — `regenerate.sh` invokes only allowlisted binaries.** Static check: `grep` the script for binary invocations; assert every one is in `ALLOWED_BINARIES` (S1-06). For `distroless-target`, this means `docker` (per ADR-0001). No `curl`, no `wget`, no `git clone https://github.com/...`.
- [ ] **AC-32 — `regenerate.sh` is idempotent.** Re-running over an already-regenerated fixture must not error and must not change the tree. Verified by a CI-skipped pytest under `tests/fixtures/portfolio/<name>/test_regenerate_is_idempotent.py` (skipped unless `CODEGENIE_REGEN_FIXTURES=1` because it shells out).

**`.codegenie/cache/` NOT committed (load-bearing CI check)**

- [ ] **AC-33 — `.gitignore` per fixture** includes the line `.codegenie/` (no leading `/`, no trailing `*` — exactly that line, so a future contributor who adds `tests/fixtures/portfolio/<name>/.codegenie/manifest/something.json` for a legitimate Layer-D-test fixture cannot accidentally also add `.codegenie/cache/`).
- [ ] **AC-34 — no `.codegenie/cache/` under any fixture tree.** A pytest `tests/unit/test_no_committed_codegenie_cache_under_portfolio_fixtures.py` walks `tests/fixtures/portfolio/` and asserts no `.codegenie/cache/` directory or file exists in the tree as committed. This is the precursor to S8-03's `portfolio` CI job startup check.

**Determinism, audit hygiene, type cleanliness**

- [ ] **AC-35 — every shape test passes `mypy --strict`.** No `Any` outside the explicit `payload: Any` parser-dispatch lines.
- [ ] **AC-36 — `image_digest_resolver` happy-path smoke.** For `distroless-target`, a manual smoke (documented in `README.md`, not a CI test) `codegenie gather tests/fixtures/portfolio/distroless-target/` (after S5-02 lands) completes with exit 0 and resolves the image digest via `ProbeContext.image_digest_resolver`.

## Implementation outline

1. Read Phase 1's `tests/fixtures/node_typescript_helm/` + `tests/unit/test_fixture_node_typescript_helm_shape.py`. The closed-set complement + `_FILE_SPECS` pattern transfers wholesale.
2. **TDD red first.** For each fixture, write its shape test (`tests/unit/test_fixture_<name>_shape.py`) — the `_FILE_SPECS` tuple, the parametrized `test_fixture_file_exists`, `test_fixture_file_parses`, `test_fixture_file_content_invariants`, `test_fixture_file_line_endings`, `test_no_forbidden_subpaths`, `test_fixture_tree_is_closed_set`, `test_readme_references_every_spec`. All cases fail red because the fixture tree does not yet exist.
3. **`minimal-ts/`.** Plant the directory tree per AC-1..AC-10. Copy `Chart.yaml`/`values.yaml`/`values-prod.yaml` verbatim from `node_typescript_helm/`. Plant the `Dockerfile`. Write the `README.md` + `regenerate.sh` + `.gitignore`. Run the shape test (`pytest tests/unit/test_fixture_minimal_ts_shape.py -v`). Green.
4. **`native-modules/`.** Plant the directory tree per AC-11..AC-17. Pick the stable C-extension dep (recommendation: `bcrypt@5.1.0` — has been pinned for years, manifest shape is stable). Plant `binding.gyp`, `src/addon.cc`, `.npmrc` with `ignore-scripts=true`. Write `regenerate.sh` that invokes `pnpm install --ignore-scripts` (via `run_allowlisted` only — no `curl`/`wget`). Verify post-install that `build/Release/` does not exist (script asserts). Green.
5. **`distroless-target/`.** Plant the directory tree per AC-18..AC-24. Pick the distroless digest (`gcr.io/distroless/nodejs20-debian12@sha256:<digest>`) — pin to the digest at fixture-creation time, never `latest`. Plant the `Dockerfile`, `index.js`, `package.json`. Write `regenerate.sh` invoking `docker build` + capturing digest. Add `.gitignore` entries. Green.
6. **Add the central no-committed-cache test** (`tests/unit/test_no_committed_codegenie_cache_under_portfolio_fixtures.py`) — walks `tests/fixtures/portfolio/` and asserts AC-34.
7. Run all three fixtures' shape tests + the central no-cache test. All green.
8. Run each fixture's `regenerate.sh` twice locally (AC-30 manual verification). Document the result in the PR description (Phase 1 Step 6 discipline). For `distroless-target`, document any digest mismatch as a known-flake source (upstream Google may repush the distroless tag; the regen script MUST pin to a specific digest, never a tag, to avoid this).

## TDD plan — red / green / refactor

### Red — write the failing shape tests first

For each fixture, the shape test follows the Phase 1 S2-03 pattern:

```python
# tests/unit/test_fixture_minimal_ts_shape.py (excerpt)
from __future__ import annotations
from pathlib import Path
from typing import Any, Callable, Literal, NamedTuple, get_args
import pytest
from codegenie.parsers import jsonc, safe_json, safe_yaml

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "portfolio" / "minimal-ts"

_ProbeName = Literal[
    # Layer A (Phase 1)
    "language_detection", "node_build_system", "node_manifest", "ci", "deployment", "test_inventory",
    # Layer B (Phase 2)
    "index_health", "scip_index", "tree_sitter_import_graph", "dep_graph",
    "generated_code", "node_reflection", "semantic_index_meta",
    # Layer C (Phase 2)
    "runtime_trace", "dockerfile", "entrypoint", "shell_usage", "certificate", "sbom", "cve",
    # Layer D (Phase 2)
    "skills_index", "conventions", "adrs", "repo_notes", "repo_config", "policy", "exceptions", "external_docs",
    # Layer E (Phase 2)
    "ownership", "service_topology_stub", "slo_stub",
    # Layer G (Phase 2)
    "semgrep", "ast_grep", "ripgrep_curated", "gitleaks", "test_coverage_mapping",
]

_ParserKind = Literal["safe_json", "safe_yaml", "jsonc", "text"]

class _FileSpec(NamedTuple):
    relpath: str
    consumers: tuple[_ProbeName, ...]
    parser: _ParserKind | None
    content_checks: tuple[Callable[[Any], None], ...]
```

The `_ProbeName` Literal is the **closed-set** type-level contract — adding a Phase-2 probe forces an edit to this list (a deliberate one). Mypy --strict catches any consumer-tuple typo.

Parametrized tests modeled exactly on S2-03:

- `test_fixture_file_exists[spec]`
- `test_fixture_file_parses[spec]`
- `test_fixture_file_content_invariants[spec]`
- `test_fixture_file_line_endings[spec]`
- `test_no_forbidden_subpaths[forbidden]`
- `test_fixture_tree_is_closed_set`
- `test_readme_references_every_spec`

### Green — make it pass

Plant the directory trees, one fixture at a time. Run that fixture's shape test. Green.

### Mutation-resistance witness table

| Mutation | Test that catches it |
|---|---|
| Drop `Dockerfile` from `minimal-ts/` | `test_fixture_file_exists[Dockerfile]` |
| Add `build/Release/addon.node` to `native-modules/` (silent `node-gyp` ran) | `test_no_forbidden_subpaths[build]` + `test_fixture_tree_is_closed_set` |
| Use `FROM gcr.io/distroless/nodejs20-debian12:latest` (unpinned tag) instead of pinned digest in `distroless-target/Dockerfile` | `test_fixture_file_content_invariants[Dockerfile]` via a `_dockerfile_pins_digest` predicate that asserts `@sha256:` is in the FROM line |
| Stray `tests/fixtures/portfolio/minimal-ts/.codegenie/cache/x.json` committed | `test_no_committed_codegenie_cache_under_portfolio_fixtures` |
| `regenerate.sh` invokes `curl https://...` | `test_regenerate_invokes_only_allowlisted_binaries` (a static check; reads the script + greps) |
| README drops the `runtime_trace` consumer reference for `Dockerfile` | `test_readme_references_every_spec` |
| Add `node-gyp` to `ALLOWED_BINARIES` for the `native-modules` regen | Caught at S1-06 review (out of scope for this story); the fixture-side guard is AC-16's post-install `build/Release/` assertion |
| CRLF endings sneak into a `pnpm-lock.yaml` via Windows editor | `test_fixture_file_line_endings[pnpm-lock.yaml]` |

### Refactor — clean up

- The three shape-test files duplicate large chunks (the `_ProbeName` Literal, the parametrized test bodies). **DO NOT extract a kernel yet** — three fixtures is at the Rule-of-Three boundary; S7-02 will add two more (`monorepo-pnpm`, `stale-scip`), and only then is the kernel extraction earned. Document the deferral in this story's Notes-for-implementer and in S7-02's Notes-for-implementer; the kernel lifts at S7-02 (when the count reaches 5, conclusively past Rule of Three).
- Each fixture's `regenerate.sh` is reviewed-as-code with a top-of-file comment explaining the deterministic-output contract (AC-30 manual local check). Reference the Phase 1 Step 6 discipline by URL.
- The central no-committed-cache test (`tests/unit/test_no_committed_codegenie_cache_under_portfolio_fixtures.py`) is one test, not three — it walks `tests/fixtures/portfolio/` once, asserts the invariant globally.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/portfolio/minimal-ts/` (tree per AC-2..AC-10) | Smallest happy-path fixture; smoke for every Phase-2 probe |
| `tests/fixtures/portfolio/native-modules/` (tree per AC-12..AC-17) | C-extension manifest edge cases (`NodeManifestProbe` + `NodeReflectionProbe`) |
| `tests/fixtures/portfolio/distroless-target/` (tree per AC-19..AC-24) | Layer C runtime-trace against an already-distroless base (Phase 7 forward-looking) |
| `tests/unit/test_fixture_minimal_ts_shape.py` | Shape test — closed-set complement, line endings, content invariants |
| `tests/unit/test_fixture_native_modules_shape.py` | Same shape pattern; closed-set + `build/Release/` forbidden |
| `tests/unit/test_fixture_distroless_target_shape.py` | Same shape pattern; `Dockerfile` content predicate asserts `@sha256:` pinning |
| `tests/unit/test_no_committed_codegenie_cache_under_portfolio_fixtures.py` | Global guard — `.codegenie/cache/` NOT committed to any portfolio fixture |

## Out of scope

- **`monorepo-pnpm/` and `stale-scip/` fixtures** — S7-02.
- **Golden file regeneration script + ~70 goldens** — S7-03.
- **Adversarial corpus** (`hostile_skills_yaml`, `concurrent_gather_race`, `no_inmemory_secret_leak`, `phase3_handoff_smoke`) — S7-04.
- **Property tests** — S7-05.
- **A shared `tests/fixtures/portfolio/_shape_test_kernel.py`** — premature; lifts in S7-02 (5 consumers; conclusively past Rule of Three).
- **A YAML-based `MANIFEST.yaml` SSoT inside each fixture** — same premature-abstraction guard.
- **CI wiring of `portfolio` job** — S8-03.

## Notes for the implementer

- **The fixture's bytes are part of the contract.** Adding or removing a file changes one or more goldens. Resist the urge to "round out" a fixture with extra files for completeness. AC-26 enforces this mechanically per-fixture.
- **`distroless-target`'s digest pin is load-bearing.** Use `FROM <image>@sha256:<digest>`, never a tag. The implementer must record the digest in the `Dockerfile` literal at fixture creation time (look up the digest via `docker manifest inspect gcr.io/distroless/nodejs20-debian12:nonroot` once, paste it in). Re-pinning to a newer digest is a deliberate fixture-update PR that regenerates affected goldens — not a silent background operation.
- **`regenerate.sh` byte-identical-twice is verified locally, not in CI.** Why: some operations (`docker pull` against upstream registries, `pnpm install --ignore-scripts` against the public registry) can produce non-deterministic byte output if upstream maintainers repush artifacts. The local verification — run the script twice on the implementer's box, diff — is the discipline; document the result in the PR. (Same discipline Phase 1 Step 6 used; reference that PR's notes.)
- **Why no shared shape-test kernel yet (Rule of Three).** Three fixtures is the Rule-of-Three boundary, not past it. S7-02 lands two more fixtures (5 total); the kernel extraction earns its keep then. If you find yourself tempted to extract now, write the kernel in the S7-02 PR — that's the cleanest landing point, because it can also subsume `node_typescript_helm/` from Phase 1 if the shape generalizes.
- **`native-modules` choice (`bcrypt@5.1.0`).** The dependency choice is implementer's call; the criteria are (a) stable manifest format that does not change between versions; (b) `node-gyp rebuild` trigger via `install` script; (c) binding.gyp marker. `bcrypt@5.1.0` has all three; so do `sqlite3@5.x`, `node-sass@4.x`. Pick one, pin tight (exact version, not range), document in the fixture's `README.md`.
- **`distroless-target/Dockerfile` MUST NOT declare `USER`.** Distroless images set non-root by default; declaring a `USER` directive on top is either a no-op or a contradiction. `RuntimeTraceProbe` records the running UID from `strace`; the assertion that the image runs as non-root with no `USER` directive in the Dockerfile is a real Phase-7 invariant.
- **`.codegenie/` line in the per-fixture `.gitignore` matters for future contributors.** A Layer D test fixture in Phase 4 might want to commit `tests/fixtures/portfolio/<name>/.codegenie/policy.yaml` (a non-cache marker file). The current `.gitignore` line `.codegenie/` would block that. **DO NOT** change it to `.codegenie/cache/` preemptively — when (if) Phase 4 needs the policy file, the contributor will explicitly carve an exception in the gitignore (`!\.codegenie/policy.yaml`) and re-run AC-34. The simpler line wins until that day.

### Patterns DELIBERATELY deferred (premature-abstraction guard, per Rule 2)

- **Shared `_shape_test_kernel.py`** — defers to S7-02 (5 consumers; Rule of Three conclusively past).
- **YAML-based `MANIFEST.yaml` SSoT per fixture** — never lands while Python-as-SSoT works (Phase 1 S2-03 precedent).
- **`FixtureConsumer` sum type** — not needed; `_ProbeName` Literal carries the closed set.
- **Pre-built image-digest cache in `tests/fixtures/portfolio/_image_cache/`** — premature; the regen-each-run policy is what S7-01 ships. The escape valve lives in `final-design.md §"Open questions"` #6 and triggers only if the hosted-runner bench in S8-03 fails the build-fail threshold.
