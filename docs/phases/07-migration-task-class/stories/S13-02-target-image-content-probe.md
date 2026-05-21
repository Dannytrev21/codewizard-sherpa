# Story S13-02 — `TargetImageContentProbe` + `crane` daemonless OCI introspection

**Step:** Step 13 — Amendment-A gather deepening: source-side secret acquisition (G1) + target-image content inventory (G2)
**Status:** Ready
**Effort:** M
**Depends on:** S13-01 (the Amendment-A probe pattern is established under `plugins/distroless-migration--node--npm/probes/`; the test-tree markers and the plugin's `probes/` layout are warm; the `crane` allowlist row this story adds is the first Amendment-A edit to `src/codegenie/exec/__init__.py`, sequenced after S13-01's net-new-files-only landing)

**ADRs honored:** [ADR-0019](../ADRs/0019-target-image-content-probe.md) (the `TargetImageContentProbe` decision — `crane manifest` + `crane config` + Chainguard-published SBOM via the existing `SbomProbe` machinery; content-cached on the immutable target digest); [ADR-0028](../ADRs/0028-allowed-binaries-amendment-crane.md) (`ALLOWED_BINARIES` gains exactly one row — `crane`); [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) (the `crane` allowlist row is enumerated as row-category 4 of the Amendment-A byte-edit allowlist — this story makes the `src/codegenie/exec/__init__.py` edit; S13-03 amends the **fence** to permit it); [ADR-0005](../ADRs/0005-probes-live-under-plugin-not-core-tree.md) (the probe lives under the plugin, NOT `src/codegenie/probes/`); [Phase 0 ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md) (frozen Probe ABC — two-arg `run(self, repo, ctx)`); [Phase 2 ADR-0001](../../02-context-gather-layers-b-g/ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md) (closed-allowlist subprocess discipline — all invocation through `codegenie.exec.run_external_cli`); [Phase 2 ADR-0004](../../02-context-gather-layers-b-g/ADRs/0004-image-digest-as-declared-input-token.md) (`image-digest:` special-token `declared_inputs`); [Phase 1 ADR-0007](../../01-context-gather-layer-a-node/ADRs/0007-warnings-id-pattern.md) (warning-ID regex).

## Context

Amendment A (`../final-design.md §Amendment A §A.2`, Gap **G2**) found the gather pipeline inventories what the *source* repo does but **never inventories what the recommended Chainguard target image already provides**. Without that inventory the recipe re-imports the present: it keeps a `RUN apk add ca-certificates` the target already ships, keeps a `RUN adduser` when the target already has `nonroot` (uid 65532), or assumes a `/bin/sh` the distroless target does not have. The result is a larger image, redundant layers, or — worst of all — a build that depends on a shell that is not there ([ADR-0019](../ADRs/0019-target-image-content-probe.md) §Context).

`TargetImageContentProbe` is the **static, Layer E** probe that closes G2. It is the typed inventory of the *target*: `preinstalled_packages`, `preinstalled_users` (including `nonroot` uid 65532), a `ca_certificates` flag, `shell_present: bool` (load-bearing — it drives whether shell-form `ENTRYPOINT` can survive), `default_workdir`, `default_entrypoint`, `supported_architectures`, and `already_satisfied_run_lines` — the exact-text source `RUN` lines the target image makes redundant. The `DockerfileBaseImageSwapTransform` and `DockerfileMultiStageRefactorTransform` recipes (S10-01 / S10-02) gain a typed `TargetImageContents` input and consult `already_satisfied_run_lines` to drop redundant lines (`../final-design.md §A.3 ¶2`).

The probe is **not pure-Python** — it makes a network fetch — but it is **daemonless and read-only**. [ADR-0019](../ADRs/0019-target-image-content-probe.md) rejected `docker pull` + filesystem inspection (Option C — couples a read-only inventory to a running Docker daemon). It adopts `crane` (the go-containerregistry OCI CLI): `crane manifest` + `crane config` fetch the target image's manifest and config for the **resolved digest**; the Chainguard-published SBOM is read through the **existing `SbomProbe` machinery** (`src/codegenie/probes/layer_c/sbom.py`) pointed at the *target* image — no second SBOM reader is written ([ADR-0019](../ADRs/0019-target-image-content-probe.md) §Pattern fit, "Reuse over reinvention"). It is a pure parse — no build.

`crane` is a closed-allowlist addition. `codegenie.exec.ALLOWED_BINARIES` is a closed `frozenset`; adding a binary requires an ADR amendment ([Phase 2 ADR-0001](../../02-context-gather-layers-b-g/ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md)'s omnibus discipline). [ADR-0028](../ADRs/0028-allowed-binaries-amendment-crane.md) ratifies exactly one new row — `crane` — chosen over `skopeo` (heavier, broader surface) and `docker manifest` (experimental subcommand, daemon-coupled). **This story makes the one-line `src/codegenie/exec/__init__.py` edit.** That edit is authorized by [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) row-category 4; the corresponding amendment to the byte-edit **fence** (`tests/fence/test_phase7_no_byte_edits_to_locked_files.py`) is owned by S13-03. Story ordering is load-bearing — if this story's `exec/__init__.py` edit lands before S13-03's fence-allowlist row, CI fails. **Land S13-03's fence row in the same PR window, or land S13-03 first.**

Because the target image digest is **immutable**, `cache_strategy="content"` keyed on `image-digest:<target-resolved>` makes the `crane` fetch a one-time cost per digest across the entire portfolio — one fetch reused across every CVE and every repo that targets the same Chainguard image ([ADR-0019](../ADRs/0019-target-image-content-probe.md) §Decision ¶3). The `image-digest:` special token rides as a `declared_inputs` entry per the [Phase 2 ADR-0004](../../02-context-gather-layers-b-g/ADRs/0004-image-digest-as-declared-input-token.md) precedent — the snapshot system treats it as a content-addressable input.

The probe lives at `plugins/distroless-migration--node--npm/probes/target_image_content_probe.py` — **NOT** under `src/codegenie/probes/` ([ADR-0005](../ADRs/0005-probes-live-under-plugin-not-core-tree.md); the S5-02 placement fence enforces this).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — Amendment A §16 (TargetImageContentProbe)` — names the slice fields, the `crane manifest` + `crane config` + `SbomProbe`-machinery internal structure, Layer E, `cache_strategy="content"`, `declared_inputs=["image-digest:<target-resolved>"]`, "Requires `crane` in `ALLOWED_BINARIES`."
  - `../final-design.md §Amendment A §A.2 Gap G2` — the gap row: preinstalled packages, `nonroot` user, CA certs, `shell_present: false` → drop redundant `RUN apk add`.
  - `../final-design.md §A.3 ¶2` (recipe consumes `already_satisfied_run_lines`), `§A.3 ¶4` (`ALLOWED_BINARIES` gains `crane`), `§Resource & cost profile` (`crane` provisioned into the Phase 5 runner image).
- **Phase ADRs:**
  - `../ADRs/0019-target-image-content-probe.md` — the probe decision; Option B (live `crane` introspection, content-cached on the digest) over Option A (static table — silent drift) and Option C (`docker pull` — daemon-coupled).
  - `../ADRs/0028-allowed-binaries-amendment-crane.md` — `ALLOWED_BINARIES` gains exactly one row, `crane`; `crane` over `skopeo` / `docker manifest`.
  - `../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md` — row-category 4 enumerates the `crane` `ALLOWED_BINARIES` edit; the fence-allowlist amendment is S13-03's.
  - `../ADRs/0005-probes-live-under-plugin-not-core-tree.md` — `plugins/distroless-migration--node--npm/probes/target_image_content_probe.py` is the canonical location.
  - `../ADRs/0015-allowed-binaries-amendment-dive-buildx.md` — the in-phase precedent for a focused ADR amending the allowlist (`dive` + `docker buildx`).
- **Existing code / precedents:**
  - `src/codegenie/exec/__init__.py` — the `ALLOWED_BINARIES` closed `frozenset` and `run_external_cli`. **Read its current state before editing.** This story adds exactly one row: `"crane"`. Mirror the `dive` / `docker-buildx` row format ([ADR-0015](../ADRs/0015-allowed-binaries-amendment-dive-buildx.md) is the precedent).
  - `src/codegenie/probes/layer_c/sbom.py` + `src/codegenie/probes/layer_c/_sbom_models.py` — the existing `SbomProbe` machinery. [ADR-0019](../ADRs/0019-target-image-content-probe.md) says it must accept being pointed at a *target image*, not only the source repo — "a small additive parameter, no contract break." **Read the `SbomProbe` SBOM-reading entry point** and consume it; do NOT write a second SBOM parser.
  - `plugins/distroless-migration--node--npm/probes/dockerfile_secret_pattern_probe.py` (S13-01) + `base_image_probe.py` (S7-01) — the structural precedents: `_WARNING_IDS` import-time block, the `async def run` shape, the confidence ladder.
  - `src/codegenie/probes/registry.py` — `@register_probe`. This probe is **not** `runs_last`; it is a static Layer-E inventory. Heaviness: `medium` (a network fetch, content-cached) — confirm against the [ADR-0003](../../02-context-gather-layers-b-g/ADRs/0003-coordinator-heaviness-sort-annotation.md) heaviness ladder.
  - `src/codegenie/types/identifiers.py` — `ImageDigest`, and the Phase 7 S1-01 newtypes. `preinstalled_users` uid values and the digest go through newtypes — never raw `int`/`str` for a domain ID where a newtype exists.
  - `plugins/distroless-migration--node--npm/plugin.yaml` — `requirements.external_tools`. This story adds `crane` to that list so the resolver fails fast if the runner image lacks it ([ADR-0028](../ADRs/0028-allowed-binaries-amendment-crane.md) §Decision).
- **Story-pipeline neighbors:**
  - `S13-01-dockerfile-secret-pattern-probe.md` — the sibling Amendment-A Step-13 probe; established the probe pattern.
  - `S13-03-amendment-a-schemas-and-fence.md` — owns `target_image_content.schema.json`, the envelope `$ref`, the goldens under `tests/golden/probes/target_image_content/`, **and the ADR-0029 fence-allowlist amendment that permits this story's `exec/__init__.py` edit.**
  - `S7-04-allowed-binaries-dive-buildx.md` — the precedent allowlist-amendment story (`dive` + `docker buildx`); mirror its `ALLOWED_BINARIES`-edit + fence-test discipline.
  - `S10-01-dockerfile-base-image-swap-recipe.md` / `S10-02-dockerfile-multi-stage-recipe.md` — the recipe consumers of `already_satisfied_run_lines`.

## Goal

Land `TargetImageContentProbe` at `plugins/distroless-migration--node--npm/probes/target_image_content_probe.py` as a Probe-ABC-conformant, `@register_probe`-decorated, Layer-E, `tier="task_specific"`, `applies_to_tasks=["distroless-migration"]`, `cache_strategy="content"`, `declared_inputs=["image-digest:<target-resolved>"]` probe that fetches the recommended Chainguard image's manifest + config via `crane` (added to `ALLOWED_BINARIES` per [ADR-0028](../ADRs/0028-allowed-binaries-amendment-crane.md)), reads the Chainguard-published SBOM through the existing `SbomProbe` machinery pointed at the target image, and emits a deterministic `TargetImageContentSlice` (`preinstalled_packages`, `preinstalled_users`, `ca_certificates`, `shell_present`, `default_workdir`, `default_entrypoint`, `supported_architectures`, `already_satisfied_run_lines`) that the S10 recipes consult to drop redundant `RUN` lines and never re-import the present. Add `crane` to `ALLOWED_BINARIES` and to `plugin.yaml requirements.external_tools`.

## Acceptance criteria

**Probe ABC conformance (AC-1 through AC-3)**
- [ ] **AC-1** `plugins/distroless-migration--node--npm/probes/target_image_content_probe.py` exists. `TargetImageContentProbe(Probe)` is defined with class attributes `name = "target_image_content"`, `layer = "E"`, `tier = "task_specific"`, `applies_to_tasks = ["distroless-migration"]`, `applies_to_languages = ["*"]`, `requires = []`, `declared_inputs = ["image-digest:<target-resolved>"]`, `cache_strategy = "content"`, `timeout_seconds = 120` (a network fetch warrants the larger budget). Verified by `tests/unit/plugins/distroless_migration_node_npm/probes/test_target_image_content_metadata.py::test_probe_metadata_shape`.
- [ ] **AC-2** `TargetImageContentProbe` is registered via `@register_probe(heaviness="medium")` (a network fetch, content-cached on the immutable digest; `runs_last=False`), decorated at class scope. Verified by `test_target_image_content_metadata.py::test_registry_entry_present`: fresh `Registry`, import the module, assert `entry.probe_cls is TargetImageContentProbe AND entry.heaviness == "medium" AND entry.runs_last is False`.
- [ ] **AC-3** `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` is the only abstract-method override; the parameter list is exactly `["self", "repo", "ctx"]`. Verified by an AST signature test `test_run_signature_matches_abc`.

**`crane` allowlist membership (AC-4 through AC-6) — ADR-0028 / ADR-0029 row 4**
- [ ] **AC-4** `src/codegenie/exec/__init__.py` `ALLOWED_BINARIES` `frozenset` gains exactly **one** new member: `"crane"`. Verified by `tests/unit/test_allowed_binaries.py` (or the existing `ALLOWED_BINARIES` membership test) — its expected-membership assertion is extended to include `"crane"`; `crane` is a member, and the `frozenset` grew by exactly one row relative to the Phase-7-pre-Amendment-A baseline. A diff-shape sub-assertion confirms the only change to `exec/__init__.py` is the single `crane` row (no other binary added, none removed).
- [ ] **AC-5** All `crane` invocation goes through `codegenie.exec.run_external_cli` — never a bare `subprocess.run`. Verified by `tests/fence/test_target_image_content_probe_purity.py`: AST-walks `target_image_content_probe.py` and asserts (a) no `subprocess.run`/`subprocess.Popen`/`os.system`/`os.popen`/`shell=True`, (b) every external-process call site routes through a `run_external_cli` symbol, (c) no LLM-SDK import. Planted-violation parametrized cases (a planted `subprocess.run(["crane", ...])`) prove the walker fires. The probe invokes `crane` only with the read-only subcommands `manifest` and `config` — a behavioral test asserts the probe never constructs a `crane` argv whose first subcommand is outside `{"manifest", "config"}`.
- [ ] **AC-6** `plugins/distroless-migration--node--npm/plugin.yaml` `requirements.external_tools` lists `crane`, joining `docker`, `dive`, `docker-buildx`. Verified by `test_plugin_manifest::test_crane_in_external_tools` which loads `plugin.yaml` and asserts `"crane" in requirements.external_tools`. This makes the plugin resolver fail fast if the runner image lacks `crane` ([ADR-0028](../ADRs/0028-allowed-binaries-amendment-crane.md) §Decision).

**Slice shape (AC-7, AC-8)**
- [ ] **AC-7** Slice shape (returned in `ProbeOutput.schema_slice["target_image_content"]`):
  ```python
  {
      "target_image": "<resolved image ref>",
      "target_digest": "sha256:<64 hex>",
      "preinstalled_packages": ["<name@version>", ...],     # sorted; from the Chainguard SBOM
      "preinstalled_users": [
          {"name": "<str>", "uid": <int>, "gid": <int>}, ... # includes {"name": "nonroot", "uid": 65532, ...}
      ],
      "ca_certificates": <bool>,
      "shell_present": <bool>,                               # load-bearing
      "default_workdir": "<str | None>",
      "default_entrypoint": ["<str>", ...],                  # config's Entrypoint, [] if none
      "supported_architectures": ["<os/arch>", ...],         # sorted; e.g. ["linux/amd64", "linux/arm64"]
      "already_satisfied_run_lines": ["<exact source RUN line>", ...],
      "confidence": "high|medium|low",
  }
  ```
  Field set + ordering pinned by this AC; `tests/golden/probes/target_image_content/*.json` (owned by S13-03) is the canonical expected payload.
- [ ] **AC-8** `preinstalled_users` always includes the Chainguard `nonroot` user with `uid == 65532` when the target image is a Chainguard distroless image. Verified by `test_target_image_content_behavior.py::test_nonroot_user_uid_65532` against a Chainguard-distroless golden fixture: the slice's `preinstalled_users` contains exactly one record with `name == "nonroot" AND uid == 65532`.

**Behavior — `shell_present`, redundant `RUN` detection, arch list (AC-9 through AC-14)**
- [ ] **AC-9** `shell_present == False` — fixture: a recorded `crane config` for a Chainguard **distroless** image (no `/bin/sh`). The probe inspects the config + SBOM and emits `shell_present: false`. Verified by `test_shell_present_false` against `tests/golden/probes/target_image_content/chainguard-distroless.json`. **`shell_present` is load-bearing** — the recipe uses it to decide whether shell-form `ENTRYPOINT` can survive.
- [ ] **AC-10** `shell_present == True` — fixture: a recorded `crane config`/SBOM for a Chainguard image that **does** ship a shell (e.g. a `*-dev`/`busybox`-bearing variant). The probe emits `shell_present: true`. Verified by `test_shell_present_true` against `tests/golden/probes/target_image_content/chainguard-with-shell.json`. AC-9 + AC-10 together prove `shell_present` is *computed from evidence*, not hardcoded.
- [ ] **AC-11** Redundant-`RUN`-line detection — given a source Dockerfile (from `repo`) containing `RUN apk add --no-cache ca-certificates` and a target whose SBOM lists a `ca-certificates` package + whose slice has `ca_certificates: true`, the slice's `already_satisfied_run_lines` contains the **exact source line text** `RUN apk add --no-cache ca-certificates`. Verified by `test_already_satisfied_run_lines::test_ca_certificates_run_line_detected`: the redundant line is present with byte-exact text; a non-redundant `RUN npm ci` line in the same Dockerfile is **absent** from `already_satisfied_run_lines`.
- [ ] **AC-12** `supported_architectures` — fixture: a recorded multi-arch `crane manifest` (an OCI image index listing `linux/amd64` + `linux/arm64`). The slice's `supported_architectures` is the sorted list `["linux/amd64", "linux/arm64"]`. A single-arch fixture (`linux/amd64` only) yields `["linux/amd64"]`. Verified by `test_supported_architectures` parametrized over both fixtures.
- [ ] **AC-13** Registry-outage / fetch-failure path — the `crane` invocation fails (stub `run_external_cli` returns a non-zero exit / raises). The probe returns `ProbeOutput` with `confidence == "low"`, `warnings == ["target_image_content.target_fetch_failed"]` (matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`), an empty-but-well-typed slice (all list fields `[]`, all bool fields `false`, `target_digest` carrying whatever was resolved), and **no exception escapes `run()`**. Verified by `test_fetch_failure::test_no_exception_escapes` + `test_fetch_failure::test_warning_id_format`. (`MigrationConfidence` / [ADR-0026](../ADRs/0026-migration-confidence-aggregation.md) rolls a `low` here up to `Degraded`, escalating to HITL rather than guessing — that rollup is downstream.)
- [ ] **AC-14** SBOM-machinery reuse — the probe reads the Chainguard-published SBOM **through the existing `SbomProbe` machinery** (`src/codegenie/probes/layer_c/sbom.py`), not a second SBOM parser. Verified by `test_sbom_machinery_reused::test_no_local_sbom_parser`: AST-walks `target_image_content_probe.py` and asserts the SBOM-reading symbol it calls is imported from `codegenie.probes.layer_c.sbom` (or its `_sbom_models`) — no module-level `json.loads` of an SBOM document and no re-implemented CycloneDX/SPDX walker live in the probe file.

**Caching + warning discipline (AC-15, AC-16)**
- [ ] **AC-15** `declared_inputs` is exactly `["image-digest:<target-resolved>"]`. A round-trip test (`test_declared_inputs::test_digest_token_admitted`) feeds the literal `image-digest:<target-resolved>` token to `src/codegenie/cache/keys.py` and asserts the snapshot system admits it as a content-addressable input (the [Phase 2 ADR-0004](../../02-context-gather-layers-b-g/ADRs/0004-image-digest-as-declared-input-token.md) precedent). `cache_key` is **not overridden** — `test_no_cache_key_override` asserts `TargetImageContentProbe.cache_key is Probe.cache_key`.
- [ ] **AC-16** Module-level `_WARNING_IDS: Final[frozenset[str]] = frozenset({"target_image_content.target_fetch_failed"})` exists; an import-time `raise AssertionError(...)` (NOT bare `assert`) checks each ID against `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. Mirrors S13-01 / S7-01.

**Fence + lint discipline (AC-17 through AC-19)**
- [ ] **AC-17** `make lint-imports` green — the new file introduces no forbidden import path; the S5-03 import-linter contract covers the plugin tree.
- [ ] **AC-18** `ruff check`, `ruff format --check`, `mypy --strict` clean for both `target_image_content_probe.py` and the edited `src/codegenie/exec/__init__.py`. **No `Any` in annotations** in the plugin surface (S5-03's `test_no_any_in_plugin_surface`).
- [ ] **AC-19** Phase 7 byte-edit allowlist fence (`tests/fence/test_phase7_no_byte_edits_to_locked_files.py`) green **after S13-03's fence-allowlist row lands**. This story's only Phase-0–6.5 edit is the single `crane` row in `src/codegenie/exec/__init__.py`; that edit is authorized by [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) row-category 4, and the corresponding fence-allowlist row is added by S13-03. **Story-ordering dependency (Rule 12 — fail loud):** if this story's `exec/__init__.py` edit merges before S13-03's fence row, the fence fails CI. The two must land in the same PR window, or S13-03 first. `_attempts/S13-02.md` records the chosen sequencing.

## Implementation outline

1. **Sequence the one Phase-0–6.5 edit carefully.** This story makes exactly one byte-edit to a locked file — `src/codegenie/exec/__init__.py`, adding `"crane"` to `ALLOWED_BINARIES`. That edit is authorized by [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) row-category 4 but the **fence** that enforces the allowlist is amended by S13-03. Coordinate: land S13-03's fence-allowlist row in the same PR, or land S13-03 first. Everything else this story creates is net-new files under `plugins/distroless-migration--node--npm/` and `tests/`.

2. **Edit `src/codegenie/exec/__init__.py`** — surgical, one row. Add `"crane"` to the `ALLOWED_BINARIES` `frozenset`, mirroring the `dive` / `docker-buildx` row format from [ADR-0015](../ADRs/0015-allowed-binaries-amendment-dive-buildx.md). Do not reformat, do not reorder existing members — the diff is one line.

3. **Edit `plugins/distroless-migration--node--npm/plugin.yaml`** — add `crane` to `requirements.external_tools` (this file is plugin-owned, net-new to Phase 7, outside the byte-edit fence scope). One YAML list row.

4. **Module-level types in `target_image_content_probe.py`:**
   ```python
   from typing import Final
   from dataclasses import dataclass
   import re

   from codegenie.exec import run_external_cli
   from codegenie.probes.layer_c.sbom import read_sbom_packages  # reuse — AC-14; confirm the real symbol name

   @dataclass(frozen=True)
   class PreinstalledUser:
       name: str
       uid: int
       gid: int

   _CRANE_READONLY_SUBCOMMANDS: Final[frozenset[str]] = frozenset({"manifest", "config"})
   _NONROOT_UID: Final[int] = 65532

   _WARNING_IDS: Final[frozenset[str]] = frozenset({"target_image_content.target_fetch_failed"})
   _WARNING_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
   for _id in _WARNING_IDS:
       if not _WARNING_ID_RE.fullmatch(_id):
           raise AssertionError(f"warning id {_id!r} violates Phase 1 ADR-0007 regex")
   ```

5. **`async def run(self, repo, ctx) -> ProbeOutput`:**
   - `t0 = time.perf_counter()`.
   - Resolve the target image digest from the `image-digest:<target-resolved>` snapshot input.
   - Fetch the manifest via `run_external_cli(["crane", "manifest", <digest>])` and the config via `run_external_cli(["crane", "config", <digest>])`. Catch a non-zero exit / the specific exception; on failure append `"target_image_content.target_fetch_failed"`, return the empty-but-well-typed slice with `confidence="low"`, and **do not raise**.
   - Parse the config JSON: `default_workdir` (`Config.WorkingDir`), `default_entrypoint` (`Config.Entrypoint`), the `User` value → `preinstalled_users`. Parse the manifest (an OCI image index, if multi-arch) for `supported_architectures`.
   - Read the Chainguard-published SBOM **through the `SbomProbe` machinery** pointed at the target image → `preinstalled_packages`, the `ca-certificates` presence → `ca_certificates`, and the `nonroot` user (uid 65532) cross-check.
   - Compute `shell_present`: inspect the SBOM package list / config for a `/bin/sh`-providing package (`busybox`, `bash`, a shell apk). Distroless → `false`.
   - Compute `already_satisfied_run_lines`: walk the source Dockerfile(s) under `repo`, and for each `RUN` line whose effect the target already satisfies (`apk add ca-certificates` when `ca_certificates`; `adduser`/`addgroup` when the target ships the user; `apk add` of a package already in `preinstalled_packages`), record the **exact source line text**.
   - `confidence`: `"high"` if the `crane` fetch + SBOM read both succeeded; `"low"` if the fetch failed; `"medium"` if the fetch succeeded but the SBOM was absent/unreadable (manifest+config only — partial inventory).
   - Return `ProbeOutput(schema_slice={"target_image_content": ...}, raw_artifacts=[<recorded crane responses>], confidence=..., duration_ms=..., warnings=warnings, errors=[])`.

6. **Fixtures** — record real `crane manifest` / `crane config` responses + the Chainguard SBOM once and check them in under `tests/fixtures/target-images/{chainguard-distroless,chainguard-with-shell,multi-arch,single-arch}/` so tests are **hermetic** (no network in CI). The stub `run_external_cli` replays the recorded responses keyed by argv. (`../ADRs/0019` §Consequences: "Golden fixtures land … with recorded `crane` manifest/config + SBOM responses so tests are hermetic.")

7. **Tests** — metadata (AC-1..AC-3), `crane`-allowlist (AC-4..AC-6), behavior (AC-8..AC-14), caching/warning (AC-15, AC-16), purity fence (AC-5, AC-17).

## TDD plan — red / green / refactor

**Red 1** — write `test_allowed_binaries`-extension first: extend the existing `ALLOWED_BINARIES` membership test (or write `test_target_image_content_metadata.py`'s `test_crane_in_allowed_binaries`) to assert `"crane" in ALLOWED_BINARIES`. Run pytest — it fails because `crane` is not yet a member. Right failure: the allowlist edit has not landed.

**Green 1** — add the one `"crane"` row to `src/codegenie/exec/__init__.py`. The membership test passes.

**Red 2** — write `test_target_image_content_metadata.py::test_probe_metadata_shape`. It does `from plugins.distroless_migration_node_npm.probes.target_image_content_probe import TargetImageContentProbe` and asserts every metadata field. Pytest fails with `ModuleNotFoundError` — the probe file does not exist.

**Green 2** — create `target_image_content_probe.py` with the metadata-only skeleton (`async def run` raising `NotImplementedError`). Metadata test green.

**Red 3** — write `test_target_image_content_behavior.py::test_shell_present_false` (AC-9) with the recorded `chainguard-distroless` fixture + the replaying stub `run_external_cli`. Pytest fails on `NotImplementedError`.

**Green 3** — implement `run()`: the `crane` fetch, the config parse, the SBOM-machinery read, and `shell_present` computation. AC-9 passes. Iterate AC-8, AC-10, AC-11, AC-12, AC-13, AC-14 one at a time (each its own red → green).

**Red 4** — write `test_target_image_content_probe_purity.py` with a planted `subprocess.run(["crane", "manifest", ...])` parametrize row. Pytest fails because the AST walker is not written.

**Green 4** — implement the AST walker (subprocess ban + `run_external_cli`-routing assertion + LLM-SDK ban). The planted rows show red-by-construction; the real probe file passes.

**Refactor** — extract the `crane`-fetch helper, the config parser, the SBOM-reader call, and the `already_satisfied_run_lines` computation into module-level functions. AST-assert the SBOM symbol is imported from core (`codegenie.probes.layer_c.sbom`), not re-implemented (AC-14). Confirm `ruff` + `mypy --strict` clean for both the probe and the edited `exec/__init__.py`, and that `make check` regression suite is green (run **after** S13-03's fence row, or coordinate the PR window).

## Files to touch

**New files:**

| Path | Purpose |
|---|---|
| `plugins/distroless-migration--node--npm/probes/target_image_content_probe.py` | The probe + `crane` fetch + config/manifest parse + SBOM-machinery read |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_target_image_content_metadata.py` | AC-1, AC-2, AC-3, AC-4 (`crane` in `ALLOWED_BINARIES`), AC-6 |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_target_image_content_behavior.py` | AC-8 through AC-14 |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_sbom_machinery_reused.py` | AC-14 (AST — no second SBOM parser) |
| `tests/fence/test_target_image_content_probe_purity.py` | AC-5, AC-17 (purity fence + `run_external_cli`-routing) |
| `tests/fixtures/target-images/chainguard-distroless/{manifest.json,config.json,sbom.json}` | AC-9 fixture (recorded `crane`/SBOM responses) |
| `tests/fixtures/target-images/chainguard-with-shell/{manifest.json,config.json,sbom.json}` | AC-10 fixture |
| `tests/fixtures/target-images/multi-arch/manifest.json` | AC-12 multi-arch fixture |
| `tests/fixtures/target-images/single-arch/manifest.json` | AC-12 single-arch fixture |

**Edited files (authorized — Amendment-A byte-edit allowlist, [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) row-category 4):**

| Path | Edit | Authorizing ADR |
|---|---|---|
| `src/codegenie/exec/__init__.py` | `ALLOWED_BINARIES` gains exactly one row: `"crane"` | [ADR-0028](../ADRs/0028-allowed-binaries-amendment-crane.md) / [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) |
| `plugins/distroless-migration--node--npm/plugin.yaml` | `requirements.external_tools` gains `crane` (plugin-owned file, outside fence scope) | [ADR-0028](../ADRs/0028-allowed-binaries-amendment-crane.md) |

**Files NOT touched** (belong to S13-03 or out of scope): `src/codegenie/schema/repo_context.schema.json`, `plugins/distroless-migration--node--npm/schema/`, `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` (S13-03 amends the fence allowlist), `tests/golden/probes/target_image_content/`, `src/codegenie/probes/layer_c/sbom.py` (imported, never edited — if the `SbomProbe` machinery genuinely needs an additive target-image parameter, surface it; per [ADR-0019](../ADRs/0019-target-image-content-probe.md) it is "a small additive parameter, no contract break" but it would consume its own allowlist consideration).

## Out of scope

- **The `target_image_content.schema.json` sub-schema + envelope `$ref` + golden fixtures** — S13-03 owns all of it. This story ships the **slice shape** (AC-7); S13-03 ships the **schema** + the goldens under `tests/golden/probes/target_image_content/`.
- **The ADR-0029 fence-allowlist amendment** — S13-03 amends `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` to permit this story's `crane` `exec/__init__.py` row. This story makes the *edit*; S13-03 makes the *fence* allow it.
- **The recipe consumption of `already_satisfied_run_lines`** — `DockerfileBaseImageSwapTransform` / `DockerfileMultiStageRefactorTransform` (S10-01 / S10-02) drop the redundant lines. This story only *detects* them.
- **`MigrationConfidence` aggregation** — rolling a `low` target-fetch confidence up to `Degraded` is M1 / [ADR-0026](../ADRs/0026-migration-confidence-aggregation.md), a downstream Step-17 concern.
- **An additive target-image parameter on `SbomProbe`** — [ADR-0019](../ADRs/0019-target-image-content-probe.md) names it as "a small additive parameter, no contract break." If the existing `SbomProbe` SBOM-reading entry point already accepts an arbitrary SBOM document path, no edit is needed and this is a non-issue. If it is hard-coupled to the source repo, surface that in `_attempts/S13-02.md` — widening it is its own ADR-reviewed question.
- **Provisioning `crane` into the Phase 5 runner image** — out of Phase 7's surface; named in `../final-design.md §Resource & cost profile`. `plugin.yaml requirements.external_tools` is this story's contribution — the resolver fails fast if `crane` is absent.
- **`DockerfileSecretPatternProbe`** — S13-01.

## Notes for the implementer

- **Rule 11 — match the existing convention.** S13-01's `DockerfileSecretPatternProbe` and S7-01's `BaseImageProbe` are the structural precedents for `_WARNING_IDS`, the `async def run` shape, and the confidence ladder. For the `ALLOWED_BINARIES` edit, S7-04 (`dive` + `docker buildx`) is the precedent — mirror its one-row-edit + membership-test discipline exactly.
- **Rule 8 — read before you write.** Two reads are mandatory before coding: (1) `src/codegenie/exec/__init__.py` — find the exact `ALLOWED_BINARIES` row format and `run_external_cli` signature; (2) `src/codegenie/probes/layer_c/sbom.py` + `_sbom_models.py` — find the **exact** SBOM-reading entry point you must reuse (AC-14). Do not write a second SBOM parser; [ADR-0019](../ADRs/0019-target-image-content-probe.md) §Pattern fit ("Reuse over reinvention") is explicit.
- **Rule 12 — fail loud, and mind the story ordering.** A `crane` fetch failure is a typed `low`-confidence warning, never a swallowed error or a guessed-empty inventory presented as `high` confidence (AC-13). And: this story's one Phase-0–6.5 edit (`exec/__init__.py`) **will fail the byte-edit fence** unless S13-03's fence-allowlist row lands first or in the same PR. State the chosen sequencing in `_attempts/S13-02.md` — do not let the dependency be implicit.
- **`crane` is read-only and daemonless — keep it that way.** [ADR-0028](../ADRs/0028-allowed-binaries-amendment-crane.md) chose `crane` precisely because `crane manifest` / `crane config` are stable, non-experimental, daemonless subcommands. The probe must invoke `crane` **only** with `manifest` and `config` (AC-5's `_CRANE_READONLY_SUBCOMMANDS` frozenset enforces this). Never `crane pull`, `crane push`, `crane copy` — those would couple the probe to write capability it has no business holding.
- **`shell_present` is load-bearing.** [ADR-0019](../ADRs/0019-target-image-content-probe.md) calls it out: it drives whether shell-form `ENTRYPOINT` can survive the migration. AC-9 + AC-10 are deliberately a true/false pair so the test proves `shell_present` is *computed from the SBOM/config*, not hardcoded `false` for "distroless." A Chainguard `*-dev` variant ships a shell — the probe must say so.
- **Content-cache on the immutable digest is the whole performance story.** The target image digest never changes for a given Chainguard image build; `cache_strategy="content"` keyed on `image-digest:<target-resolved>` means the `crane` fetch happens once per digest and is reused across every CVE and every repo in the portfolio ([ADR-0019](../ADRs/0019-target-image-content-probe.md) §Decision ¶3). Do not override `cache_key` (AC-15) — the default content-addressed key over `declared_inputs` is exactly right.
- **Hermetic tests — record, don't fetch.** CI must never reach a registry. Record `crane manifest` / `crane config` and the Chainguard SBOM once, check the JSON into `tests/fixtures/target-images/`, and have the stub `run_external_cli` replay them keyed by argv ([ADR-0019](../ADRs/0019-target-image-content-probe.md) §Consequences). A test that hits the network is flaky-by-construction and fails Rule 9 (intent: "the probe parses a Chainguard manifest correctly," not "the registry is up today").
- **Rule 9 — tests verify intent.** AC-11 asserts the *exact source `RUN` line text* is recorded — not "some redundant line was found." The recipe consumes the byte-exact text to delete the line; a slice that records a paraphrase is useless. The redundant `apk add ca-certificates` must be present **and** the non-redundant `npm ci` absent — both halves prove the detection discriminates.
- **`already_satisfied_run_lines` reads the source Dockerfile too.** This probe is Layer E (target inventory) but it cross-references the *source* Dockerfile under `repo` to compute which source `RUN` lines the target makes redundant. That cross-reference is the probe's job — it is not a layering violation, it is the gather depth G2 exists to add.
- **Effort budget.** Probe body ≈ 150 LOC (the `crane` fetch + config/manifest parse + SBOM read + `already_satisfied_run_lines` cross-reference); tests ≈ 300 LOC; fence ≈ 70 LOC. If the body grows past 180 LOC, extract `_crane_fetch.py` (the fetch + JSON parse) from the classification logic. Token-budget guard (Rule 6): if the `SbomProbe` machinery turns out to be hard-coupled to the source repo and not reusable as-is, STOP and surface — do not write a second SBOM parser to route around it; that violates [ADR-0019](../ADRs/0019-target-image-content-probe.md) and AC-14.
