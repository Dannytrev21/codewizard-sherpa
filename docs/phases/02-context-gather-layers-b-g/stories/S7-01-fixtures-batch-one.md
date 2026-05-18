# Story S7-01 — Fixtures batch 1: `minimal-ts` + `native-modules` + `distroless-target`

**Step:** Step 7 — Plant five-repo fixture portfolio + per-probe golden files + remaining adversarial corpus
**Status:** GREEN (shipped 2026-05-18) — see `_attempts/S7-01.md`
**Effort:** M
**Depends on:** S4-07 (Layer B sub-schemas — goldens-to-come reference them), S6-08 (Layer D/E/G sub-schemas + freshness registrations — `minimal-ts` smokes every probe)
**ADRs honored:** ADR-0001 (allowlisted binaries — `regenerate.sh` invokes only allowlisted tools), ADR-0003 (heaviness sort — `distroless-target` exercises a heavy probe path), ADR-0004 (image-digest declared-input token — `distroless-target`'s `Dockerfile` produces a real digest the regen script resolves), ADR-0005 (no plaintext persisted — fixture trees commit zero `.codegenie/cache/` blobs), ADR-0007 (no plugin loader — no fixture seeds `plugins/`), ADR-0009 (pytest-xdist veto — closed-set fixture trees so parallelism never tempts).

## Validation notes (2026-05-17)

Hardened by phase-story-validator (scheduled task: `story-validation-corrector`). Verdict: **HARDENED**.

Summary of changes (full audit log in [`_validation/S7-01-fixtures-batch-one.md`](_validation/S7-01-fixtures-batch-one.md)):

- **Block-tier — `pnpm` is NOT in `ALLOWED_BINARIES`** (current closed set per ADR-0001 + S1-06 AC-10 amendment: `git, node, semgrep, syft, grype, gitleaks, scip-typescript, ast-grep, ripgrep, tree-sitter, docker, strace`). Original AC-31 + Implementation Outline §4 said `native-modules/regenerate.sh` invokes `pnpm install --ignore-scripts`; that would either fail the static AC-31 check or force a silent ALLOWED_BINARIES expansion (forbidden by ADR-0001 §Decision). **Fix:** mirror Phase 1's `node_typescript_helm/` precedent — `pnpm-lock.yaml` is hand-authored bytes committed to the fixture; no `pnpm install` invocation in `regenerate.sh`. `.npmrc` ships `ignore-scripts=true` as defense-in-depth for any operator who later runs `pnpm install` locally; the regen script asserts `build/Release/` is absent as a stale-output check, never as a post-install verification. AC-15, AC-16 rewritten; Implementation Outline §4 rewritten.
- **Block-tier — shell scripts can't call Python.** Original AC-22 said `regenerate.sh` invokes `docker build` "via `run_allowlisted("docker", ...)`". `run_allowlisted` is a Python function in `src/codegenie/exec/__init__.py`; bash scripts cannot call it. **Fix:** AC-22 rewritten — `regenerate.sh` invokes `docker build` directly; the AC-31 static-check is the structural guarantee (binary appears in `ALLOWED_BINARIES`).
- **Harden-tier — `built-image.digest` would dirty AC-26's closed-set test.** `distroless-target/regenerate.sh` writes `built-image.digest` (gitignored). The closed-set complement test (modeled on Phase 1's `_enumerate_tracked` → `rglob`) would observe the file in the working tree and FAIL after the first regen run. **Fix:** AC-26 rewritten — enumerate the fixture tree via `git ls-files <fixture-path>` (subprocess invocation through `run_allowlisted("git", ...)` from the test). This makes the closed-set test honor `.gitignore` automatically; a stray *tracked* file still fails. Noise frozenset retained as defense-in-depth for the small subset of names that escape `git ls-files` (e.g., `.DS_Store` if a future contributor force-adds one).
- **Harden-tier — `_ProbeName` Literal drift.** If a Phase-2 probe is renamed (`skills_index` → `skills_indexer`, say), the `_ProbeName` Literal as a hand-rolled string set will diverge from the actual probe registry silently — closed-set tests still pass, but `_FILE_SPECS` consumers no longer line up with real probe names. **Fix:** AC-37 added — `test_probe_name_literal_matches_phase_2_registry` asserts `set(get_args(_ProbeName)) ⊇ {probe.name for probe in default_registry.all()}` (subset semantics so future-probe Phase-3+ additions don't break Phase 2 fixtures retroactively). Mirrors Phase 1's `test_probe_name_literal_matches_phase_1_closed_set`.
- **Harden-tier — `binding.gyp` parser surface.** Original AC-13 said the file "parses via `safe_json.load`". `binding.gyp` is a permissive format (`node-gyp` accepts Python-style comments + trailing commas). A minimal hand-authored fixture body is pure JSON, so `safe_json.load` is correct *for this fixture* — but the AC must pin the body to the strict-JSON subset explicitly so a future "tidy-up" of the binding.gyp doesn't break the parser path. **Fix:** AC-13 amended — pin "no comments, no trailing commas; pure RFC-8259 JSON".
- **Harden-tier — Dockerfile digest pin lifted from mutation table to AC.** AC-21b added: final-stage `FROM` line for `distroless-target/Dockerfile` matches `@sha256:[0-9a-f]{64}` (regex pinned). Without this as an AC, the mutation table is descriptive but not enforced.
- **Harden-tier — `built-image.digest` content shape contract.** `ProbeContext.image_digest_resolver: Callable[[Path], str | None]` (ADR-0004) consumes this file. The bytes-on-disk shape must be a stable contract so any future resolver implementation can read it via `Path.read_text().strip()` without per-probe parser drift. **Fix:** AC-38 added — `built-image.digest` (when present) contains exactly one line: `sha256:[0-9a-f]{64}\n` (matching the `docker inspect --format='{{.Id}}'` output shape).
- **Harden-tier — AC-31 static-check needs a spec.** What counts as "a binary invocation in shell"? Without a concrete spec the static check is fragile. **Fix:** AC-31 amended — define the parser: first whitespace-delimited token of each non-blank, non-comment, non-`set`/`if`/`for`/`while`/`case`/`function`/`local`/`export`/`echo`/`return`/`exit`/`true`/`false`/`source`/`.`/`cd`/`[`/`[[`/`test`/`trap`/`shift`/`break`/`continue` line; assert each such token is in `ALLOWED_BINARIES ∪ _SHELL_COREUTILS_ALLOWLIST` where the latter is a small frozenset (`mkdir`, `rm`, `cp`, `mv`, `chmod`, `cat`, `sed`, `awk`, `grep`, `sort`, `uniq`, `tr`, `find`, `xargs`, `sha256sum`, `printf`, `tee`, `dirname`, `basename`, `pwd`, `head`, `tail`, `wc`) declared once in the shared check module.
- **Harden-tier — closed-set noise frozenset explicit.** Original AC-26 said "excluding `__pycache__`, `.pytest_cache`, dotfiles created by editors". Pin to the exact Phase 1 frozenset.
- **Harden-tier — AC-30 byte-identical scope.** "Tree" is implicit. **Fix:** AC-30 rewritten — scope is the set of `git ls-files`-enumerated tracked files only; gitignored artifacts (`.codegenie/`, `built-image.digest`, local image tarballs) are out of scope.
- **Design-pattern lift recorded as Notes-for-implementer (NOT promoted to AC).** Per-fixture content predicates duplicate across three shape tests. Three is Rule-of-Three boundary; the predicate-kernel extraction is deferred to S7-02 (5 consumers) alongside the `_FILE_SPECS` walker kernel. Documented in Notes §"Patterns DELIBERATELY deferred".
- **Consistency — Layer D probe enumeration.** Confirmed `_ProbeName` Literal Layer D members (`skills_index, conventions, adrs, repo_notes, repo_config, policy, exceptions, external_docs`) match the per-probe `name = "..."` declarations under `src/codegenie/probes/layer_d/` (skills_index, conventions Done GREEN; adrs/exceptions/policy/repo_config/repo_notes Done GREEN per Layer D marker modules; `external_docs` lands via S6-04 HARDENED, name pinned at probe-creation time). The runtime-registry check (AC-37) catches any future drift.

Full audit log: [`_validation/S7-01-fixtures-batch-one.md`](_validation/S7-01-fixtures-batch-one.md).

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
- [ ] **AC-13 — `binding.gyp`** exists at fixture root with a minimal `{ "targets": [{"target_name": "addon", "sources": ["src/addon.cc"]}] }` body; parses via `safe_json.load`. **The body is pure RFC-8259 JSON — no Python-style comments, no trailing commas.** (`node-gyp` accepts a more permissive grammar, but the fixture pins to strict-JSON so the `safe_json.load` AC remains the load-bearing parser contract; a future tidy-up cannot regress to a permissive shape without an explicit AC edit.)
- [ ] **AC-14 — `src/addon.cc`** exists as a trivial empty C++ source (3 lines: `#include <node.h>` + empty `Initialize` + `NODE_MODULE` macro). **Never compiled at regen time.**
- [ ] **AC-15 — `pnpm-lock.yaml`** exists with the dependency frozen at the version declared in `package.json`; **the lockfile is hand-authored bytes committed to the fixture (Phase 1 `node_typescript_helm/` precedent — no `pnpm install` invocation at regen time)**. Implementer picks pnpm to match Phase 1's lockfile-precedence happy path. Body is minimal: `lockfileVersion: '6.0'` header plus a single `packages:` entry for the chosen C-extension dep at the exact pinned version. Parses via `safe_yaml.load`.
- [ ] **AC-16 — `.npmrc`** at fixture root contains the single line `ignore-scripts=true\n`. This is **defense-in-depth** for any operator who later runs `pnpm install`/`npm install` locally; the fixture itself ships pre-resolved lockfile bytes (AC-15) and `regenerate.sh` does NOT invoke pnpm/npm. AC-16b — `regenerate.sh` asserts `build/Release/` is absent in the fixture tree before exiting (a stale-output check that catches a local contributor having accidentally compiled the native module despite `.npmrc`); exits non-zero with a clear message if found.
- [ ] **AC-17 — `README.md`** lists every file by relpath; explicitly documents "no compilation at regen time" with the rationale (CI determinism — `node-gyp` outputs differ across platforms).

**`distroless-target/` fixture tree shape**

- [ ] **AC-18.** `tests/fixtures/portfolio/distroless-target/` directory exists.
- [ ] **AC-19 — `package.json`** declares minimal Node app — no `dependencies`, `"main": "index.js"`, `"scripts": {"start": "node index.js"}`.
- [ ] **AC-20 — `index.js`** is 5 lines: `console.log("ok"); process.exit(0);` (plus a `#!/usr/bin/env node` shebang and a comment).
- [ ] **AC-21 — `Dockerfile`** has two stages — `FROM node:20-slim AS build` (does `npm ci` against the empty manifest, copies `index.js`) and `FROM gcr.io/distroless/nodejs20-debian12@sha256:<pinned-digest>` (or `cgr.dev/chainguard/node:latest@sha256:<pinned-digest>`) for the final stage; final stage `COPY --from=build /app /app`; `WORKDIR /app`; `CMD ["index.js"]`; no `USER` directive (distroless images run as non-root by default — `RuntimeTraceProbe` records this).
- [ ] **AC-21b — final-stage digest pin is structural.** The `FROM` line for the final stage of `distroless-target/Dockerfile` matches the regex `^FROM\s+\S+@sha256:[0-9a-f]{64}\b`. A content predicate `_dockerfile_final_stage_pins_digest` in the shape test asserts this on `Dockerfile` bytes. A `:latest`-style unpinned tag is a test failure, not a regen-time discovery.
- [ ] **AC-22 — `regenerate.sh`** is reviewed-as-code; invokes `docker build -t distroless-target-fixture:latest .` directly (bash; `docker` is in `ALLOWED_BINARIES` per ADR-0001 + AC-31's static check is the structural guarantee); on success writes the resolved image digest to `built-image.digest` (the file is `.gitignored` per AC-23); tears the image down with `docker image rm distroless-target-fixture:latest`. Exits non-zero with a clear message if `docker` is unavailable on the host. **`run_allowlisted` is a Python function and is NOT callable from bash — this AC explicitly does NOT prescribe Python-side dispatch from inside the regen script.**
- [ ] **AC-23 — `.gitignore`** includes `.codegenie/` AND `built-image.digest` AND any local image tarball.
- [ ] **AC-24 — `README.md`** explicitly notes "Phase 7 forward-looking — exercises Layer C against an already-distroless base; primary user is `RuntimeTraceProbe` + `SbomProbe` + `CveProbe`."

**`_FILE_SPECS` SSoT + closed-set per fixture**

- [ ] **AC-25 — `_FILE_SPECS: tuple[_FileSpec, ...]` per fixture.** Each shape test (`tests/unit/test_fixture_<name>_shape.py`) declares a module-level closed-set typed manifest identical in shape to Phase 1's S2-03 pattern: `_FileSpec(relpath, consumers, parser, content_checks)`. `_ProbeName = Literal[...]` lists every Phase-2 probe name (Layer A + Layer B + Layer C + Layer D + Layer E + Layer G) — the closed set is **mypy --strict** typo-resistant.
- [ ] **AC-26 — closed-set complement test per fixture.** `test_fixture_<name>_tree_is_closed_set` enumerates the fixture's *tracked* files via `git ls-files <fixture-path>` (invoked through `run_allowlisted("git", "ls-files", str(_FIXTURE))`; `git` is in `ALLOWED_BINARIES`) and asserts the set equals `{spec.relpath for spec in _FILE_SPECS}`. Using `git ls-files` rather than `rglob` makes the test honor `.gitignore` automatically — so `distroless-target`'s `built-image.digest` (gitignored, written by `regenerate.sh`) does not dirty the closed set. **A stray *tracked* file still fails.** As defense-in-depth for the small subset of names that `git ls-files` does not catch (e.g., a force-added `.DS_Store`), the test also walks `rglob("*")` and filters via the explicit Phase-1 noise frozenset `_FIXTURE_NOISE_NAMES = frozenset({"__pycache__", ".pytest_cache", ".DS_Store"})` plus names starting with `.pytest`; any file outside `_FILE_SPECS` and outside the noise filter is also a failure.
- [ ] **AC-27 — no forbidden subpaths per fixture.** None of `node_modules/`, `.codegenie/`, `dist/`, `coverage/`, `build/`, `build/Release/` (the `node-gyp` output dir), `.DS_Store` exist inside any fixture tree.
- [ ] **AC-28 — line endings.** Every text file in every fixture is UTF-8, LF-only, ends with `b"\n"` — no CRLF, no BOM. Parametrized over every `_FILE_SPECS` entry.
- [ ] **AC-29 — README references every spec.relpath per fixture.** `test_fixture_<name>_readme_references_every_spec` asserts every `spec.relpath` and every probe name in `spec.consumers` appears literally in the fixture's `README.md`.

**`regenerate.sh` reviewed-as-code discipline**

- [ ] **AC-30 — `regenerate.sh` byte-identical across runs (tracked-files scope).** For each fixture, two consecutive `bash regenerate.sh` invocations produce a *tracked-files* tree whose `git ls-files <fixture-path> | sort | xargs sha256sum` is identical. **Verified locally** before opening the Step 7 PR (manual; documented in `regenerate.sh`'s top-of-file comment; not a CI assertion because some operations involve `docker pull` whose underlying images get repushed by upstream maintainers — see Notes-for-implementer). Gitignored artifacts (`.codegenie/`, `built-image.digest`, local image tarballs) are out of scope by design — they regenerate on every CI run and are *not* part of the fixture contract.
- [ ] **AC-31 — `regenerate.sh` invokes only allowlisted binaries (with concrete static-check spec).** A pytest under `tests/unit/test_fixture_<name>_regenerate_allowlist.py` (one per fixture, parametrized over the same `_FILE_SPECS` module) tokenizes the script as follows: for each non-blank, non-`#`-comment line, take the first whitespace-delimited token; drop tokens that are shell control-flow / builtins / variable assignments (`set, if, then, fi, elif, else, for, do, done, while, case, esac, function, local, export, declare, readonly, echo, printf, return, exit, true, false, source, ., cd, [, [[, test, trap, shift, break, continue, eval-NEVER` plus tokens matching `^[A-Z_][A-Z0-9_]*=` shell variable assignments); the remaining tokens form the script's invoked-binary set. Assert this set ⊆ `codegenie.exec.ALLOWED_BINARIES ∪ _SHELL_COREUTILS_ALLOWLIST`, where `_SHELL_COREUTILS_ALLOWLIST: Final[frozenset[str]] = frozenset({"mkdir", "rm", "cp", "mv", "chmod", "cat", "sed", "awk", "grep", "sort", "uniq", "tr", "find", "xargs", "sha256sum", "tee", "dirname", "basename", "pwd", "head", "tail", "wc"})` lives in **one shared module** under `tests/unit/_fixture_regen_allowlist.py` (one source of truth for all fixtures; S7-02 reuses unchanged). For `distroless-target`, the non-builtin / non-coreutil set must contain only `docker` + (optionally) `git`. **No `curl`, no `wget`, no `git clone https://github.com/...`, no `eval`, no `pnpm`, no `npm`, no `node-gyp`** — explicit failure if observed.
- [ ] **AC-32 — `regenerate.sh` is idempotent.** Re-running over an already-regenerated fixture must not error and must not change the tree. Verified by a CI-skipped pytest under `tests/fixtures/portfolio/<name>/test_regenerate_is_idempotent.py` (skipped unless `CODEGENIE_REGEN_FIXTURES=1` because it shells out).

**`.codegenie/cache/` NOT committed (load-bearing CI check)**

- [ ] **AC-33 — `.gitignore` per fixture** includes the line `.codegenie/` (no leading `/`, no trailing `*` — exactly that line, so a future contributor who adds `tests/fixtures/portfolio/<name>/.codegenie/manifest/something.json` for a legitimate Layer-D-test fixture cannot accidentally also add `.codegenie/cache/`).
- [ ] **AC-34 — no `.codegenie/cache/` under any fixture tree.** A pytest `tests/unit/test_no_committed_codegenie_cache_under_portfolio_fixtures.py` walks `tests/fixtures/portfolio/` and asserts no `.codegenie/cache/` directory or file exists in the tree as committed. This is the precursor to S8-03's `portfolio` CI job startup check.

**Determinism, audit hygiene, type cleanliness**

- [ ] **AC-35 — every shape test passes `mypy --strict`.** No `Any` outside the explicit `payload: Any` parser-dispatch lines.
- [ ] **AC-36 — `image_digest_resolver` happy-path smoke.** For `distroless-target`, a manual smoke (documented in `README.md`, not a CI test) `codegenie gather tests/fixtures/portfolio/distroless-target/` (after S5-02 lands) completes with exit 0 and resolves the image digest via `ProbeContext.image_digest_resolver`.

**Closed-set probe-name pin + image-digest contract**

- [ ] **AC-37 — `_ProbeName` Literal matches the live probe registry.** Each fixture's shape test declares `test_probe_name_literal_matches_phase_2_registry`: imports `codegenie.probes.default_registry`, calls `default_registry.all_probe_names()` (or the equivalent existing accessor — implementer aligns to actual API), and asserts `{p for p in registered_names} ⊆ set(get_args(_ProbeName))`. **Subset semantics**: Phase-3+ probes added later do NOT retroactively break Phase-2 fixtures, but a Phase-2 probe rename / addition that fails to update the Literal IS a test failure. (Phase 1's `test_probe_name_literal_matches_phase_1_closed_set` uses equality because Phase 1 is closed; Phase-2 fixtures need to anticipate downstream additions and use subset.) This is the runtime backstop for the mypy --strict closed-set type contract.
- [ ] **AC-38 — `built-image.digest` content-shape contract.** When `distroless-target/regenerate.sh` writes `built-image.digest`, the file contents match the regex `^sha256:[0-9a-f]{64}\n$` (one line, sha256-prefixed, trailing LF). A unit test under `tests/unit/test_distroless_target_built_image_digest_shape.py` skipped unless `CODEGENIE_REGEN_FIXTURES=1` (or unless the file exists from a prior local regen) asserts the shape. **Why pinned**: `ProbeContext.image_digest_resolver: Callable[[Path], str | None]` (Phase 2 ADR-0004) consumes this file; any future resolver implementation reads it via `Path.read_text().strip()` and relies on the prefixed shape. The bytes-on-disk shape is part of the cross-probe contract.

## Implementation outline

1. Read Phase 1's `tests/fixtures/node_typescript_helm/` + `tests/unit/test_fixture_node_typescript_helm_shape.py`. The closed-set complement + `_FILE_SPECS` pattern transfers wholesale.
2. **TDD red first.** For each fixture, write its shape test (`tests/unit/test_fixture_<name>_shape.py`) — the `_FILE_SPECS` tuple, the parametrized `test_fixture_file_exists`, `test_fixture_file_parses`, `test_fixture_file_content_invariants`, `test_fixture_file_line_endings`, `test_no_forbidden_subpaths`, `test_fixture_tree_is_closed_set`, `test_readme_references_every_spec`. All cases fail red because the fixture tree does not yet exist.
3. **`minimal-ts/`.** Plant the directory tree per AC-1..AC-10. Copy `Chart.yaml`/`values.yaml`/`values-prod.yaml` verbatim from `node_typescript_helm/`. Plant the `Dockerfile`. Write the `README.md` + `regenerate.sh` + `.gitignore`. Run the shape test (`pytest tests/unit/test_fixture_minimal_ts_shape.py -v`). Green.
4. **`native-modules/`.** Plant the directory tree per AC-11..AC-17. Pick the stable C-extension dep (recommendation: `bcrypt@5.1.0` — has been pinned for years, manifest shape is stable). Plant `binding.gyp` (strict-JSON body per AC-13), `src/addon.cc`, `.npmrc` with `ignore-scripts=true`. **Hand-author `pnpm-lock.yaml`** with a minimal valid pnpm v6 body pinning the chosen dep at exact version (Phase 1 `node_typescript_helm/` precedent — `pnpm-lock.yaml` is fixture bytes, not regenerated). Write `regenerate.sh` that performs only: idempotent `mkdir -p`/`touch` of any tree skeleton + a final `build/Release/` absent-assertion (per AC-16b). **`regenerate.sh` does NOT invoke `pnpm install`/`npm install`/`node-gyp`** — none of those binaries is in `ALLOWED_BINARIES` per ADR-0001, and AC-31's static check would (correctly) fail. Green.
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
| Use `FROM gcr.io/distroless/nodejs20-debian12:latest` (unpinned tag) instead of pinned digest in `distroless-target/Dockerfile` | `test_fixture_file_content_invariants[Dockerfile]` via the **`_dockerfile_final_stage_pins_digest`** predicate (now AC-21b) that asserts the regex `^FROM\s+\S+@sha256:[0-9a-f]{64}\b` matches the final-stage line |
| Use `FROM ...@sha256:abc123` (short / invalid-length digest) | `_dockerfile_final_stage_pins_digest` predicate (AC-21b) — regex requires exactly 64 hex chars |
| Rename probe `skills_index → skills_indexer` in `src/codegenie/probes/layer_d/skills_index.py` without updating `_ProbeName` Literal | `test_probe_name_literal_matches_phase_2_registry` (AC-37) — `default_registry.all_probe_names()` returns the new name, subset check fails |
| Stray `tests/fixtures/portfolio/minimal-ts/.codegenie/cache/x.json` committed | `test_no_committed_codegenie_cache_under_portfolio_fixtures` |
| `regenerate.sh` invokes `curl https://...` | `test_regenerate_invokes_only_allowlisted_binaries` (AC-31; tokenizer-based static check) |
| `regenerate.sh` invokes `pnpm install --ignore-scripts` (i.e., implementer ignores the hand-author-the-lockfile pattern) | `test_regenerate_invokes_only_allowlisted_binaries` (AC-31) — `pnpm` is NOT in `ALLOWED_BINARIES` |
| `regenerate.sh` invokes `eval ...` (shell injection avenue) | `test_regenerate_invokes_only_allowlisted_binaries` (AC-31) — `eval` listed in explicit "never" set |
| `built-image.digest` written as `abc...` (missing `sha256:` prefix) | `test_distroless_target_built_image_digest_shape` (AC-38) — regex requires `^sha256:[0-9a-f]{64}\n$` |
| README drops the `runtime_trace` consumer reference for `Dockerfile` | `test_readme_references_every_spec` |
| `binding.gyp` gains a Python-style `# comment` (permissive parser tempted) | `test_fixture_file_parses[binding.gyp]` — `safe_json.load` errors on `#` |
| Add `node-gyp` to `ALLOWED_BINARIES` for the `native-modules` regen | Caught at S1-06 review (out of scope for this story); the fixture-side guard is AC-16b's `build/Release/` absent-assertion |
| CRLF endings sneak into a `pnpm-lock.yaml` via Windows editor | `test_fixture_file_line_endings[pnpm-lock.yaml]` |
| `built-image.digest` ends up tracked in git (gitignore broken) | `test_fixture_<name>_tree_is_closed_set` (AC-26) — `built-image.digest` is not in `_FILE_SPECS`; if it appears in `git ls-files` output the closed-set check fails |

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
| `tests/unit/test_fixture_minimal_ts_shape.py` | Shape test — closed-set complement (via `git ls-files`), line endings, content invariants, AC-37 registry pin |
| `tests/unit/test_fixture_native_modules_shape.py` | Same shape pattern; closed-set + `build/Release/` forbidden + AC-37 registry pin |
| `tests/unit/test_fixture_distroless_target_shape.py` | Same shape pattern; `Dockerfile` content predicate `_dockerfile_final_stage_pins_digest` (AC-21b) + AC-37 registry pin |
| `tests/unit/_fixture_regen_allowlist.py` | **Shared module** — single source of truth for `_SHELL_COREUTILS_ALLOWLIST` + the `regenerate.sh` tokenizer; reused unchanged by S7-02 (no premature kernel; this is the rule-of-two-where-the-policy-is-load-bearing carve-out) |
| `tests/unit/test_fixture_minimal_ts_regenerate_allowlist.py` | AC-31 static check for minimal-ts; consumes the shared module |
| `tests/unit/test_fixture_native_modules_regenerate_allowlist.py` | AC-31 static check for native-modules; explicitly asserts `pnpm`/`npm`/`node-gyp` NOT in invoked set |
| `tests/unit/test_fixture_distroless_target_regenerate_allowlist.py` | AC-31 static check for distroless-target; explicitly asserts `docker` IS in invoked set |
| `tests/unit/test_distroless_target_built_image_digest_shape.py` | AC-38 content-shape check for `built-image.digest` (skipped unless file exists or `CODEGENIE_REGEN_FIXTURES=1`) |
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

- **Shared `_shape_test_kernel.py`** — defers to S7-02 (5 consumers; Rule of Three conclusively past). When S7-02 lifts the kernel, it should subsume Phase 1's `tests/unit/test_fixture_node_typescript_helm_shape.py` so the policy is one source for *all* fixture shape tests.
- **Shared content-predicate module per fixture (`_predicates.py`)** — defers to S7-02. Three fixtures' worth of predicate functions live inline in each shape test file (Phase 1 precedent); the predicates become extractable when the kernel lifts and they can be exposed as helpers (composition over inheritance — pure functions consumed by the parametrized kernel).
- **YAML-based `MANIFEST.yaml` SSoT per fixture** — never lands while Python-as-SSoT works (Phase 1 S2-03 precedent).
- **`FixtureConsumer` sum type** — not needed; `_ProbeName` Literal carries the closed set. AC-37's registry pin is the runtime backstop.
- **Pre-built image-digest cache in `tests/fixtures/portfolio/_image_cache/`** — premature; the regen-each-run policy is what S7-01 ships. The escape valve lives in `final-design.md §"Open questions"` #6 and triggers only if the hosted-runner bench in S8-03 fails the build-fail threshold.

### Why the `_fixture_regen_allowlist.py` module DOES lift now (Rule-of-Three carve-out)

Three fixtures × one tokenizer + one coreutils frozenset is technically the Rule of Three boundary, not past it — but the *policy* is load-bearing (it is the structural enforcement of ADR-0001 at the fixture boundary). A copy-pasted tokenizer across three test files is the worst case for the rule that protects ADR-0001: a future contributor "tidying up" two of the three could silently weaken the third. The shared module is one short file with two exported names; introducing it costs one import per consumer and pays back the load-bearing invariant ownership. S7-02 reuses it without further change.

### Why `_ProbeName` Literal uses subset semantics in AC-37 (not equality)

Phase 1's analogous test uses set equality because Phase 1 is closed. Phase 2 is still landing probes; the Literal is the *fixture's* closed view of probe names. Equality would force every Phase-3+ probe addition to also edit every Phase-2 fixture shape test — wrong direction. Subset semantics (`registered ⊆ literal`) catches: a renamed/added Phase-2 probe whose name does not appear in the fixture's Literal. It does NOT catch a Phase-2 probe that no longer exists at all (would be caught by mypy --strict because `_FILE_SPECS` consumers tuples reference the literal members directly — a name removed from the Literal but still used in `consumers=("foo", ...)` is a build error). Together, the two checks are exhaustive without forcing churn on downstream phases.
