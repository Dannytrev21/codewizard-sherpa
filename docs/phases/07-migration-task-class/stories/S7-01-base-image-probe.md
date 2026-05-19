# Story S7-01 — `BaseImageProbe` + Dockerfile parsing + `_BASE_IMAGE_KIND_RULES`

**Step:** Step 7 — `BaseImageProbe` + `ShellInvocationTraceProbe` under the plugin (sandboxed)
**Status:** Ready
**Effort:** M
**Depends on:** S6-02 (`SandboxClient.spawn(role=SandboxRole.GATE)` additive parameter shipped — the plugin's probes directory exists by then and the loader can collect)
**ADRs honored:** Phase 7 ADR-0005 (probes live under plugin, NOT `src/codegenie/probes/`); Phase 7 ADR-0009 (no byte-edit to Phase 0–6.5 files outside the allowlist — this story is **net-new-files-only**); Phase 0 ADR-0007 (frozen Probe ABC — two-arg `run(self, repo, ctx)`); Phase 1 ADR-0004 (per-probe sub-schema `additionalProperties: false`); Phase 1 ADR-0007 (warning-ID regex); Phase 2 ADR-0004 (`image_digest_resolver` capability on `ProbeContext`); production ADR-0031 (plugin architecture).

## Context

`BaseImageProbe` is the **light, static, Layer C** probe in Phase 7 — the cheap evidence that says "what does the `FROM` line resolve to?" The migration-task-class plugin can only swap a base image if it knows which one is in use; the `AlpineVulnProvenanceAdapter` (S4-02) and `DistrolessVulnProvenanceAdapter` (S4-03) both consume this probe's slice as a precondition; the `DockerfileBaseImageSwapTransform` (S10-01) and `DockerfilePolicyGate` (S10-03) read the parsed AST output downstream.

The probe is **pure-Python** (no subprocess, no network). It uses the new `dockerfile-parse` runtime dependency (the one net-new Python runtime dep this entire phase is permitted to add per Phase 7 ADR-0009 row #9) to walk each Dockerfile under the repo, and for each `FROM` directive emits a typed record: the parsed image reference, the resolved digest (via `ctx.image_digest_resolver` — the Phase 2 ADR-0004 capability), the stage name (if any), and a `kind: Literal["alpine", "debian", "ubuntu", "rhel", "distroless", "scratch", "chainguard", "unknown"]` derived from a module-level `_BASE_IMAGE_KIND_RULES: Final[tuple[BaseImageRule, ...]]` (Open/Closed marker catalog — iterated, never branched on). Open question §8 from the phase manifest is **pinned in this story (per S7-03 manifest text, but the slice shape lives here)**: `unresolved FROM ARG` is folded into `kind="unknown"` carrying a typed `reason: UnknownReason`, avoiding schema-variant explosion.

The probe lives under `plugins/distroless-migration--node--npm/probes/base_image_probe.py` — **NOT** under `src/codegenie/probes/`. Phase 7 ADR-0005 is explicit; the fence test from S5-02 (`tests/fence/test_provenance_primitive_in_plugin_directory.py`) AST-asserts placement and would fail if the file lived in core. This is the first net-new Python file inside the migration-plugin's `probes/` directory.

The fast path matters: warm-cache budget is ≤ 2 ms; cold-path budget is ≤ 60 ms (per S12-05 `tests/perf/test_base_image_probe.py`). `cache_strategy="content"`; `declared_inputs=["**/Dockerfile", "**/Dockerfile.*", "**/Containerfile", "image-digest:<resolved>"]`. The `image-digest:<resolved>` special token rides alongside the file globs per the Phase 2 ADR-0004 precedent — the snapshot system treats it as a content-addressable input so a base-image-pin change invalidates the cache without a Dockerfile-byte change.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §8 (BaseImageProbe)` — names the slice fields (`from_image`, `image_digest`, `stage_name`, `kind`, `reason?`), the `_BASE_IMAGE_KIND_RULES` catalog shape, and the warning-ID emission.
  - `../phase-arch-design.md §Edge cases #1 (unresolved FROM ARG)` and `#13 (dockerfile-parse exceptions)` — both fold to `kind="unknown"` with a typed `reason`.
  - `../phase-arch-design.md §Testing strategy §Fence / structural` — `tests/fence/test_provenance_primitive_in_plugin_directory.py` AST-walks probe placement.
- **Phase ADRs:**
  - `../ADRs/0005-probes-live-under-plugin-not-core-tree.md` — `plugins/distroless-migration--node--npm/probes/base_image_probe.py` is the canonical location.
  - `../ADRs/0009-phase-7-byte-edit-allowlist-fence.md` — this story is **net-new-files only**; no allowlist row is consumed. The new file lives under `plugins/` (a directory that's net-new to Phase 7) so the kernel-frozen fence is silent on it.
  - `../ADRs/0013-dockerfile-recipe-engine-dockerfile-parse.md` — the `dockerfile-parse` library is the canonical parser for Phase 7; S7-04 adds it to `pyproject.toml`.
- **Existing code / precedents:**
  - `src/codegenie/probes/base.py` — the frozen Probe ABC. `BaseImageProbe(Probe)` consumes `ProbeContext.image_digest_resolver` (Phase 2 ADR-0004); two-arg `run(self, repo, ctx)`.
  - `src/codegenie/probes/layer_c/dockerfile.py` — the Phase 2 line-by-line Dockerfile probe (hand-rolled parser). Useful as a precedent for `_FILE_GLOBS` and the slice-emitter shape; **do not** import its private parser — `dockerfile-parse` is the Phase 7 choice (richer AST; supports stage names; supports `COPY --from=<stage>`).
  - `src/codegenie/probes/registry.py` — `register_probe(heaviness="light")` is the default; `BaseImageProbe` ships **light + no `runs_last`** (the heavy + `runs_last=True` probe is S7-02).
  - `src/codegenie/types/identifiers.py` — `ImageRef`, `ImageDigest`, `DockerStageName` newtypes (Phase 7 S1-01). The slice's typed fields go through smart constructors.
- **Story-pipeline neighbors:**
  - `S6-02-sandbox-spawn-role-parameter.md` — must land first (the plugin's probes module imports `Role` indirectly via `api.py`'s side-effect imports in S8-03).
  - `S7-03-probe-sub-schemas-and-goldens.md` — owns the JSON sub-schema + envelope `$ref` insertion + golden files. This story ships the slice **shape**; S7-03 ships the schema.
  - `S4-02-alpine-vuln-provenance-adapter.md` — consumer; reads `base_image.image_digest` to match Syft `layerID`.

## Goal

Land `BaseImageProbe` under `plugins/distroless-migration--node--npm/probes/base_image_probe.py` as a Probe-ABC-conformant, `@register_probe`-decorated, layer-C, `task_specific`, `applies_to_tasks=["distroless-migration"]` probe that parses every Dockerfile under the repo via `dockerfile-parse`, resolves each `FROM` to its image digest via `ctx.image_digest_resolver`, classifies each base via the `_BASE_IMAGE_KIND_RULES` open/closed marker catalog, and emits a deterministic schema slice that downstream adapters + recipes + gates consume. Warm-cache p99 ≤ 2 ms; cold p99 ≤ 60 ms.

## Acceptance criteria

**Probe ABC conformance (AC-1 through AC-3)**
- [ ] **AC-1** `plugins/distroless-migration--node--npm/probes/base_image_probe.py` exists. `BaseImageProbe(Probe)` is defined with class attributes `name = "base_image"`, `layer = "C"`, `tier = "task_specific"`, `applies_to_tasks = ["distroless-migration"]`, `applies_to_languages = ["*"]`, `requires = []`, `declared_inputs = ["**/Dockerfile", "**/Dockerfile.*", "**/Containerfile", "image-digest:<resolved>"]`, `cache_strategy = "content"`, `timeout_seconds = 30`. Verified by `tests/unit/plugins/distroless_migration_node_npm/probes/test_base_image_probe_metadata.py::test_probe_metadata_shape` (reads `BaseImageProbe.__dict__` and asserts each field byte-equal to the declared value).
- [ ] **AC-2** `BaseImageProbe` is registered via `@register_probe` (defaults — `heaviness="light"`, `runs_last=False`). `register_probe` decoration is **at class scope** in `base_image_probe.py`. Verified by `test_probe_metadata.py::test_registry_entry_present` which constructs a fresh `Registry`, imports the module, and asserts `entry.probe_cls is BaseImageProbe AND entry.heaviness == "light" AND entry.runs_last is False`.
- [ ] **AC-3** `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` is the only abstract-method override; signature matches the frozen Phase 0 ABC byte-for-byte. A signature-shape AST test (`test_run_signature_matches_abc`) asserts the parameter list is exactly `["self", "repo", "ctx"]` — a one-arg `run` is a `TypeError` at dispatch and fails this AC.

**Slice shape (AC-4 through AC-6)**
- [ ] **AC-4** Slice shape (returned in `ProbeOutput.schema_slice["base_image"]`):
  ```python
  {
      "dockerfiles": [
          {
              "path": "<repo-relative-posix-path>",
              "stages": [
                  {
                      "stage_index": <int>,
                      "stage_name": "<str | None>",
                      "from_image": "<str>",            # raw FROM argument
                      "image_digest": "<sha256:...| None>",  # via image_digest_resolver
                      "kind": "alpine|debian|ubuntu|rhel|distroless|scratch|chainguard|unknown",
                      "reason": "<None | typed UnknownReason>",  # populated iff kind == "unknown"
                  }, ...
              ],
          }, ...
      ],
      "confidence": "high|medium|low",
  }
  ```
  Verified against `tests/golden/probes/base_image/*.json` (S7-03 owns goldens, but the **field set + key order** is pinned by this story's AC).
- [ ] **AC-5** `_BASE_IMAGE_KIND_RULES: Final[tuple[BaseImageRule, ...]]` is a module-level open/closed marker catalog (Open/Closed at the file boundary — toolkit pattern). Each `BaseImageRule` is a frozen dataclass with fields `(pattern: re.Pattern[str], kind: Literal[...], applies_to: Literal["repository", "digest", "tag"])`. The catalog is iterated in `_classify_from(from_image, image_digest) -> tuple[Kind, UnknownReason | None]`, **never branched on with chained `if`**. Verified by `test_classification_uses_catalog::test_no_if_chain_on_image_kind` (AST-walks `_classify_from` and asserts ≤ 1 `if` statement — the early-return for the `scratch` literal — and no `elif` arms on string equality against image names). The catalog covers at minimum: `alpine`, `debian` (any `debian:*`, `debian-slim`), `ubuntu`, `rhel` / `redhat/ubi*`, Google distroless (`gcr.io/distroless/*`), Chainguard (`cgr.dev/chainguard/*`, `chainguard/*`), `scratch`.
- [ ] **AC-6** `kind == "unknown"` always carries a typed `reason: UnknownReason`. Permitted values for this probe's reasons: `"unresolved_from_arg"` (the `FROM` arg is `$VARIABLE` and ARG resolution couldn't be completed statically — open question §8 pinned here), `"unrecognized_image"` (image name doesn't match any rule), `"dockerfile_parse_failed"` (the whole file failed to parse — recorded once per file at the top stage). A `tests/unit/.../test_unknown_reasons_are_typed.py::test_no_freeform_unknown_reasons` reads the slice from a `dockerfile_parse_failed` fixture and asserts `reason in UnknownReason.__members__`. Freeform `reason` strings fail this test.

**Behavior — happy + degraded paths (AC-7 through AC-11)**
- [ ] **AC-7** Happy path — single-FROM Alpine: fixture `tests/fixtures/portfolio/node-vulnerable-alpine/Dockerfile` (one `FROM node:18-alpine`) → slice has one dockerfile entry, one stage, `kind == "alpine"`, `image_digest == "sha256:<pinned>"`, `confidence == "high"`. The pinned digest comes from the fixture's static `image-digest:` token (the resolver is stubbed in unit tests; the integration test in S7-05 uses the real resolver).
- [ ] **AC-8** Multi-stage path — fixture `tests/fixtures/portfolio/multi-stage-dockerfile/Dockerfile` (FROM node:18-alpine AS builder; FROM gcr.io/distroless/nodejs:18 AS runtime) → two stages with `stage_name in {"builder", "runtime"}`, `kind` values `{"alpine", "distroless"}`, both with resolved digests; the runtime stage's `from_image` is parsed as the `FROM` argument and the `stage_name` is the `AS` argument.
- [ ] **AC-9** `scratch` path — `FROM scratch` → `kind == "scratch"`, `image_digest == None` (no resolver call), `reason == None`.
- [ ] **AC-10** Parse-failure path — fixture with a malformed Dockerfile (`FROM` with no argument; backslash-truncated line) → probe returns `ProbeOutput` with `confidence == "low"`, `warnings = ["base_image.dockerfile_parse_failed"]` (matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` per Phase 1 ADR-0007), the failing file's slice carries `kind == "unknown", reason == "dockerfile_parse_failed"` for the top stage. **No exception escapes `run()`.** Verified by `test_dockerfile_parse_failed::test_warning_id_format` (regex-checks the warning ID) and `test_dockerfile_parse_failed::test_no_exception_escapes` (uses `pytest.raises(BaseException)` to assert nothing fires).
- [ ] **AC-11** Resolver-missing path — `ctx.image_digest_resolver is None` → probe runs to completion; every stage has `image_digest == None` and `kind` is still computed (from the `from_image` repository/tag). `confidence` is downgraded to `"medium"` (we have static evidence but no digest pin). Verified by `test_resolver_none::test_confidence_medium_when_no_resolver`.

**Warning-ID + cache discipline (AC-12 through AC-14)**
- [ ] **AC-12** Module-level `_WARNING_IDS: Final[frozenset[str]] = frozenset({"base_image.dockerfile_parse_failed"})` exists; an import-time `raise AssertionError(...)` (NOT a bare `assert` — the `forbidden-patterns` pre-commit hook rejects bare `assert`) checks each ID matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. Pattern mirrors existing Phase 1 / Phase 2 probes.
- [ ] **AC-13** `cache_key(self, repo, task)` uses the default `Probe.cache_key` (content-addressed over `declared_inputs`) — overriding `cache_key` is forbidden here. Verified by AST: `test_no_cache_key_override::test_method_not_redefined` asserts `BaseImageProbe.cache_key` is `Probe.cache_key`.
- [ ] **AC-14** `declared_inputs` includes the `image-digest:<resolved>` token verbatim (no whitespace, no trailing colon variant). A round-trip test feeds the literal token to `cache/keys.py` and asserts the token is admitted by the snapshot system as a content-addressable input.

**Fence + lint discipline (AC-15 through AC-18)**
- [ ] **AC-15** AST-walk fence: `tests/fence/test_base_image_probe_purity.py` walks `base_image_probe.py` and rejects `subprocess.run`, `os.system`, `os.popen`, `subprocess.Popen`, `shell=True`, `requests.*`, `urllib.request.urlopen`, `httpx.*`, and any LLM-SDK import (`anthropic`, `openai`, `langchain`, `langgraph`, `transformers`). Three planted-violation parametrized cases (red-by-construction inside the test) prove the walker actually fires. **The fence file uses `raise AssertionError("...")` — bare `assert` is forbidden.**
- [ ] **AC-16** `make lint-imports` green; the new file does not introduce a forbidden import path. The import-linter contract from S5-03 already covers `plugins/distroless-migration--*/` against LLM SDKs.
- [ ] **AC-17** `ruff check`, `ruff format --check`, `mypy --strict plugins/distroless-migration--node--npm/probes/base_image_probe.py` all clean. **No `Any` in annotations** — the Phase 3 / Phase 7 `test_no_any_in_plugin_surface` discipline applies to the migration plugin tree (extended in S5-03 via a Phase 7 import-linter / fence pass).
- [ ] **AC-18** Phase 7 ADR-0009 byte-edit allowlist fence (`tests/fence/test_phase7_no_byte_edits_to_locked_files.py`) green: this story adds files only under `plugins/distroless-migration--node--npm/` and `tests/`; no Phase 0–6.5 file is touched. (S7-03 / S7-04 own the envelope-schema + ALLOWED_BINARIES edits.)

**Perf budget (AC-19)**
- [ ] **AC-19** A `@pytest.mark.bench` perf test (the body lands in S12-05; the **AC** is reserved here) asserts cold p99 ≤ 60 ms across 100 trials on the multi-stage fixture, warm p99 ≤ 2 ms after one prior run hits the content-cache. Reserved-AC text in `_attempts/S7-01.md` records the deferred coverage path so S12-05's executor pulls it in.

## Implementation outline

1. **Net-new files only — no edits to Phase 0–6.5.** Create:
   - `plugins/distroless-migration--node--npm/probes/__init__.py` (empty; package marker).
   - `plugins/distroless-migration--node--npm/probes/base_image_probe.py` — the probe + private helpers.
   - `tests/unit/plugins/distroless_migration_node_npm/__init__.py` + `tests/unit/plugins/distroless_migration_node_npm/probes/__init__.py` (test-tree markers).
   - `tests/fence/test_base_image_probe_purity.py` (AST fence).
   - Fixture files (one Dockerfile per fixture variant) under `tests/fixtures/portfolio/{node-vulnerable-alpine,multi-stage-dockerfile,base-image-scratch,base-image-unknown,base-image-parse-failed}/Dockerfile`.

2. **Module-level data (Open/Closed catalog) in `base_image_probe.py`:**
   ```python
   from typing import Final, Literal
   from dataclasses import dataclass
   import re

   BaseImageKind = Literal["alpine", "debian", "ubuntu", "rhel", "distroless", "scratch", "chainguard", "unknown"]

   class UnknownReason(StrEnum):
       UNRESOLVED_FROM_ARG = "unresolved_from_arg"
       UNRECOGNIZED_IMAGE = "unrecognized_image"
       DOCKERFILE_PARSE_FAILED = "dockerfile_parse_failed"

   @dataclass(frozen=True)
   class BaseImageRule:
       pattern: re.Pattern[str]
       kind: BaseImageKind
       applies_to: Literal["repository", "digest", "tag"]

   _BASE_IMAGE_KIND_RULES: Final[tuple[BaseImageRule, ...]] = (
       BaseImageRule(re.compile(r"^(?:[\w.-]+/)?alpine(:|$)"), "alpine", "repository"),
       BaseImageRule(re.compile(r"^(?:[\w.-]+/)?(?:node|python|nginx)[\w.-]*-alpine"), "alpine", "tag"),
       BaseImageRule(re.compile(r"^debian(?::|$)"), "debian", "repository"),
       BaseImageRule(re.compile(r":[\w.-]*-slim$"), "debian", "tag"),
       BaseImageRule(re.compile(r"^ubuntu(?::|$)"), "ubuntu", "repository"),
       BaseImageRule(re.compile(r"^(?:registry\.access\.redhat\.com/)?ubi\d+"), "rhel", "repository"),
       BaseImageRule(re.compile(r"^gcr\.io/distroless/"), "distroless", "repository"),
       BaseImageRule(re.compile(r"^cgr\.dev/chainguard/"), "chainguard", "repository"),
       BaseImageRule(re.compile(r"^chainguard/"), "chainguard", "repository"),
   )

   _WARNING_IDS: Final[frozenset[str]] = frozenset({"base_image.dockerfile_parse_failed"})
   _WARNING_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
   for _id in _WARNING_IDS:
       if not _WARNING_ID_RE.fullmatch(_id):
           raise AssertionError(f"warning id {_id!r} violates Phase 1 ADR-0007 regex")
   ```

3. **`_classify_from(from_image, image_digest) -> tuple[BaseImageKind, UnknownReason | None]`:**
   - Early-return for `from_image == "scratch"` → `("scratch", None)`.
   - Early-return for `from_image.startswith("$")` → `("unknown", UnknownReason.UNRESOLVED_FROM_ARG)`.
   - Iterate `_BASE_IMAGE_KIND_RULES` and return on first match.
   - Fall through → `("unknown", UnknownReason.UNRECOGNIZED_IMAGE)`.

4. **`async def run(self, repo, ctx) -> ProbeOutput`:**
   - `t0 = time.perf_counter()`.
   - Discover Dockerfiles via the glob set (mirror `src/codegenie/probes/layer_c/dockerfile.py::find_dockerfiles` pattern; sorted output).
   - For each file:
     - Parse via `dockerfile_parse.DockerfileParser(fileobj=...)`. Catch the **specific** exceptions `dockerfile-parse` raises (look at the library's source; typically a `DockerfileParseError` subclass — use a narrow `except`); on parse failure append `"base_image.dockerfile_parse_failed"` to warnings, emit a single `stage` with `kind="unknown", reason="dockerfile_parse_failed"`, continue.
     - For each `FROM` directive (use `parser.structure` to get the line list; filter to `instruction == "FROM"`): extract `from_image`, `stage_name` (parse `AS <name>`), `stage_index` (0-based), call `ctx.image_digest_resolver(repo.root / dockerfile_path / from_image)` if the resolver is non-None (signature is `Callable[[Path], str | None]` per the Phase 2 ADR; treat the argument as a logical lookup key), classify via `_classify_from`, append the stage record.
   - `confidence`: `"high"` if every stage has a resolved digest AND no warnings; `"medium"` if any digest is `None` (resolver returned `None` or resolver itself was `None`); `"low"` if any file failed to parse.
   - Return `ProbeOutput(schema_slice=..., raw_artifacts=[], confidence=..., duration_ms=..., warnings=warnings, errors=[])`.

5. **Fixtures + golden seeds (golden JSON files land in S7-03):**
   - `tests/fixtures/portfolio/node-vulnerable-alpine/Dockerfile` — single `FROM node:18-alpine`.
   - `tests/fixtures/portfolio/multi-stage-dockerfile/Dockerfile` — `FROM node:18-alpine AS builder` + `FROM gcr.io/distroless/nodejs:18 AS runtime`.
   - `tests/fixtures/portfolio/base-image-scratch/Dockerfile` — `FROM scratch`.
   - `tests/fixtures/portfolio/base-image-unknown/Dockerfile` — `FROM internal.registry/secret-corp:v1`.
   - `tests/fixtures/portfolio/base-image-parse-failed/Dockerfile` — malformed (e.g., `FROM` with no argument, mid-line dangling backslash).
   - Each fixture carries a `_pinned_digest.json` alongside the Dockerfile so the test's resolver-stub returns the expected `sha256:...` per repository (deterministic — no network).

6. **Tests (unit + fence; golden-validation lives in S7-03):**
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_base_image_probe_metadata.py` — covers AC-1, AC-2, AC-3.
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_base_image_probe_behavior.py` — covers AC-7, AC-8, AC-9, AC-10, AC-11.
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_classification_uses_catalog.py` — covers AC-5 + AC-6 (AST-walks `_classify_from`).
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_unknown_reasons_are_typed.py` — covers AC-6 freeform-rejection.
   - `tests/fence/test_base_image_probe_purity.py` — AST fence, covers AC-15.

## TDD plan (red → green → refactor)

**Red** — write `test_base_image_probe_metadata.py::test_probe_metadata_shape` first. It imports `from plugins.distroless_migration_node_npm.probes.base_image_probe import BaseImageProbe` and asserts every metadata field. Run pytest — it fails with `ModuleNotFoundError`.

**Green** — minimum code to satisfy the metadata test:
- Create the directory tree + empty `__init__.py` files.
- Create `base_image_probe.py` with the class skeleton (only metadata, `async def run` raising `NotImplementedError`).
- Re-run pytest — metadata test now green; behavior tests still fail (no `run`).

**Red+** — write `test_base_image_probe_behavior.py::test_alpine_happy_path`. Pytest fails on `NotImplementedError`.

**Green+** — implement `run()` for the Alpine + multi-stage cases (Steps 3 + 4 above). Iterate over the remaining behavior tests, adding rule rows + degraded paths.

**Red++** — write `test_base_image_probe_purity.py::test_no_subprocess_call_in_run` with a planted-violation parametrize case. Pytest fails because the walker isn't written.

**Green++** — implement the AST walker. Three planted-violation parametrize rows (`subprocess.run`, `os.system`, `urllib.request.urlopen`) all show red-by-construction.

**Refactor** — extract `_classify_from`, the catalog, and the Dockerfile-discovery helper into module-level functions. AST-assert `_classify_from` has no chained `if/elif` (AC-5).

## Files to touch

**New files (no Phase 0–6.5 byte-edits):**
- `plugins/distroless-migration--node--npm/probes/__init__.py`
- `plugins/distroless-migration--node--npm/probes/base_image_probe.py`
- `tests/unit/plugins/distroless_migration_node_npm/__init__.py`
- `tests/unit/plugins/distroless_migration_node_npm/probes/__init__.py`
- `tests/unit/plugins/distroless_migration_node_npm/probes/test_base_image_probe_metadata.py`
- `tests/unit/plugins/distroless_migration_node_npm/probes/test_base_image_probe_behavior.py`
- `tests/unit/plugins/distroless_migration_node_npm/probes/test_classification_uses_catalog.py`
- `tests/unit/plugins/distroless_migration_node_npm/probes/test_unknown_reasons_are_typed.py`
- `tests/fence/test_base_image_probe_purity.py`
- Five Dockerfile fixtures under `tests/fixtures/portfolio/...` (paths above).

**Files NOT touched** (would fail Phase 7 ADR-0009 fence): `src/codegenie/probes/`, `src/codegenie/exec/`, `src/codegenie/plugins/loader.py`, `pyproject.toml`, `src/codegenie/schema/repo_context.schema.json`. Those edits live in S7-03 / S7-04 / S8-03.

## Out of scope

- **The JSON sub-schema + envelope `$ref` + golden files** — S7-03 owns these. This story ships the **slice shape**; S7-03 ships the **schema**.
- **The `ALLOWED_BINARIES` amendment + `dockerfile-parse` runtime dep** — S7-04 owns the `pyproject.toml` and `src/codegenie/exec/__init__.py` edits. **However, `dockerfile-parse` must be installable in dev for the unit tests to run.** Implementer note: install it via `uv pip install dockerfile-parse` locally for green-on-laptop, but the **production** `pyproject.toml` row lands in S7-04. The story executor should coordinate sequencing — landing S7-01 without S7-04 leaves the unit tests `ImportError`-ing on CI. Acceptable mitigation: land both in the same PR window, or land S7-04 first (it's `S` effort + only edits `pyproject.toml` and `ALLOWED_BINARIES`).
- **The `ShellInvocationTraceProbe`** — S7-02 owns the heavy probe + sandbox integration + AST isolation fence.
- **Plugin loader explicit-import wiring** — S8-03 (`src/codegenie/plugins/loader.py` row #10).
- **`api.py` side-effect imports** — S8-03 declares `plugins/distroless-migration--node--npm/api.py`; the side-effect import of `from .probes import base_image_probe  # noqa: F401` lives there, NOT in this story.
- **Recipe / gate consumers** — S10-01 (swap), S10-03 (policy gate), S10-04 (build gate) read the slice; they're downstream.

## Notes for the implementer

- **Rule 11 — match the existing convention.** Phase 2's `DockerfileProbe` (`src/codegenie/probes/layer_c/dockerfile.py`) is the precedent for `_FILE_GLOBS`, `find_dockerfiles`, and the `_slice_for` shape. Mirror it; don't fork it. **One difference**: that probe uses a hand-rolled parser (no third-party dep); this one uses `dockerfile-parse`. The hand-rolled version stays in core; this one lives under the plugin.
- **Rule 12 — fail loud.** A `dockerfile-parse` exception is a typed warning, not a swallowed error. The slice carries `kind="unknown", reason="dockerfile_parse_failed"` so the AlpineVulnProvenanceAdapter (S4-02) lands in `Unknown(reason="sbom_layer_attribution_absent")` rather than producing a wrong `BaseImage`. Catch the **specific** exception class `dockerfile-parse` raises — check the library source. A bare `except Exception` is forbidden by `mypy --strict` configuration and would also break Rule 12 ("default to surfacing uncertainty").
- **Rule 9 — tests verify intent.** The behavior tests assert business semantics: "Alpine fixture → `kind=alpine` AND digest pinned" — NOT "function returns a dict with key `kind`". The AST tests verify the design intent (Open/Closed via catalog iteration) that we want preserved across refactors.
- **Open/Closed marker catalog (toolkit pattern).** `_BASE_IMAGE_KIND_RULES` is the open/closed seam — adding a new base-image-kind (e.g., `wolfi`, `bottlerocket`) is **one new tuple row**, not an edit to `_classify_from`. The AST fence (AC-5) is the load-bearing enforcer; without it future engineers will add `if "wolfi" in from_image: return "wolfi"` and the catalog becomes dead code.
- **Confidence ladder.** `high` requires both static evidence (the FROM line parsed) AND digest pinning (resolver returned a non-None digest); `medium` is "static evidence only"; `low` is "parse failed somewhere." This ladder matches Phase 1's `IndexHealthProbe` discipline — `B2`'s confidence is the canonical reference.
- **`ctx.image_digest_resolver` is optional.** Phase 2 ADR-0004 declares it as `Callable[[Path], str | None] | None` on `ProbeContext`. Treat `None` as "no resolver wired" — degrade gracefully. The integration test in S7-05 exercises the wired-resolver path; this story's unit tests use a stub returning the fixture's pinned digest.
- **`dockerfile-parse` API note.** The library exposes `DockerfileParser(fileobj=...)` and a `.structure` attribute that's a list of `{instruction, value, startline, ...}` dicts. Use `.structure`, filter `instruction == "FROM"`. For `AS <stage>` parsing: split the `value` on whitespace + `re.IGNORECASE` match on `r"\bAS\b"`. This is a known weak spot in the library (it doesn't surface `AS` separately); the test-fence catches drift via golden-file parity.
- **No async I/O.** The probe is sync-in-async-shell — `async def run` is required by the ABC, but the body is pure file reads. No `await` calls. `mypy --strict` will permit this; the `asyncio_mode = "auto"` pytest setting handles test invocation.
- **Effort budget.** Probe body ≤ 120 LOC; tests ≈ 250 LOC; fence ≈ 60 LOC. If the body grows past 150 LOC, extract the Dockerfile-parsing layer into `_dockerfile_parse_helpers.py` (precedent: `src/codegenie/probes/layer_c/_dockerfile_parse.py`).
- **Token-budget guard (Rule 6).** This story is single-session-implementable at ~4k tokens. If `dockerfile-parse` surprises you (e.g., it requires a `tempfile` write to parse a string), STOP, surface, and consider a hand-rolled `FROM`-line scanner as fallback — the AST fence already forbids subprocess so the parser layer is replaceable.
