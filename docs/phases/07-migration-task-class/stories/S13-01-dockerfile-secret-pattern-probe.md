# Story S13-01 — `DockerfileSecretPatternProbe` + `_SECRET_PATTERN_RULES` open/closed catalog

**Step:** Step 13 — Amendment-A gather deepening: source-side secret acquisition (G1) + target-image content inventory (G2)
**Status:** Ready
**Effort:** M
**Depends on:** S7-03 (the Phase-7 plugin's `schema/` directory exists with the `base_image` / `shell_invocation_trace` sub-schemas + `_models.py` Pydantic-mirror precedent; the `dockerfile-parse` runtime dep is installable per S7-04; the plugin's `probes/` directory and test-tree markers exist from S7-01)
**ADRs honored:** [ADR-0018](../ADRs/0018-dockerfile-secret-pattern-probe.md) (the `DockerfileSecretPatternProbe` decision — `external_script` is opaque-by-design, no `tree-sitter-bash`); [ADR-0005](../ADRs/0005-probes-live-under-plugin-not-core-tree.md) (probes live under the plugin, NOT `src/codegenie/probes/`); [ADR-0009](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) + [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) (this story is **net-new-files-only** under `plugins/distroless-migration--node--npm/` and `tests/` — no Phase 0–6.5 byte-edit; the sub-schema + envelope `$ref` + fence-allowlist rows are S13-03's surface); [Phase 0 ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md) (frozen Probe ABC — two-arg `run(self, repo, ctx)`); [Phase 1 ADR-0004](../../01-context-gather-layer-a-node/ADRs/0004-per-probe-subschema-additional-properties-false.md) (per-probe sub-schema `additionalProperties: false` — S13-03 owns the schema; this story owns the slice shape); [Phase 1 ADR-0007](../../01-context-gather-layer-a-node/ADRs/0007-warnings-id-pattern.md) (warning-ID regex); [ADR-0013](../ADRs/0013-dockerfile-recipe-engine-dockerfile-parse.md) (`dockerfile-parse` is the canonical Dockerfile parser for Phase 7).

## Context

Amendment A (`../final-design.md §Amendment A §A.2`, Gap **G1**) found the gather pipeline never inventories **how the source repo acquires secrets during the build**. A naive `FROM` swap that does not know a build pulls a registry token via `RUN --mount=type=secret`, or injects an `npm` auth token through an `ARG`/`ENV`, or `COPY`s an `.npmrc`, can ship an image that builds clean, passes the gate, merges — then fails at runtime because the secret-acquisition path was silently dropped or carried into the new image in a less-safe form. Shipping a broken (or secret-leaking) image is the one unacceptable outcome (`../final-design.md §A.1`).

`DockerfileSecretPatternProbe` is the **light, static, Layer C** probe that closes G1. It is the cheap evidence that says "this Dockerfile acquires secrets in these N ways, at these instruction indices." The `DockerfileBaseImageSwapTransform` (S10-01) and `DockerfileMultiStageRefactorTransform` (S10-02) consume its `SecretPatternSlice`: the recipe **REFUSES** on any `external_script` record (`RefusedOpaqueSecretScript`, M2 / [ADR-0025](../ADRs/0025-migration-refusal-taxonomy.md)) and rewrites `env_arg_injection` into a portable `--mount=type=secret` form where deterministic (`../phase-arch-design.md §Component design — Amendment A §15`). Without this probe the recipe cannot tell a credential-bearing `ARG` from a build-version `ARG` and either drops it (broken build) or carries it (leaked secret).

The probe is **pure-Python** (no subprocess, no network). It uses `dockerfile-parse` (the Phase 7 canonical Dockerfile parser, [ADR-0013](../ADRs/0013-dockerfile-recipe-engine-dockerfile-parse.md)) to AST-walk every Dockerfile under the repo, and for each secret-acquisition pattern emits a typed `SecretPattern` record: the `kind`, the 0-based instruction index, and the referenced env-var name or filesystem path. Classification is driven by a module-level `_SECRET_PATTERN_RULES: Final[tuple[SecretRule, ...]]` — an **Open/Closed marker catalog** (toolkit pattern; iterated, never branched on) that **reuses the Phase 2 sanitizer's secret-shaped-name regexes** (`src/codegenie/output/sanitizer.py`) so "what looks like a secret" has exactly one definition repo-wide.

The five `kind` values are a **closed set**: `{buildkit_secret_mount, env_arg_injection, file_copy_credential, auth_header_fetch, external_script}`. `external_script` is the load-bearing **opaque** case (`../final-design.md §A.3 departure #3`): a `COPY`'d shell script that is then `RUN` is detected and **its invocation recorded** — but the probe **does not parse the script** (no `tree-sitter-bash`; departure #3 says it deliberately is not added). An opaque script is honest evidence of "we cannot statically know what this does"; the recipe refuses on it rather than guessing.

The probe lives at `plugins/distroless-migration--node--npm/probes/dockerfile_secret_pattern_probe.py` — **NOT** under `src/codegenie/probes/`. [ADR-0005](../ADRs/0005-probes-live-under-plugin-not-core-tree.md) is explicit; the S5-02 fence (`tests/fence/test_provenance_primitive_in_plugin_directory.py`) AST-asserts placement and would fail if the file lived in core. This is a net-new file in the migration-plugin's existing `probes/` directory (created by S7-01).

`cache_strategy="content"`; `declared_inputs=["**/Dockerfile", "**/Dockerfile.*", "**/Containerfile"]` — the same Dockerfile glob set S7-01's `BaseImageProbe` uses, minus the `image-digest:` token (this probe reads only Dockerfile bytes; no digest resolution).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — Amendment A §15 (DockerfileSecretPatternProbe)` — names the five `kind` values, the `_SECRET_PATTERN_RULES` catalog shape, the opaque-`external_script` rule, the slice fields (`kind`, instruction index, referenced env/path), and the GATHER+REFUSE disposition.
  - `../final-design.md §Amendment A §A.2 Gap G1` — the gap row: `--mount=type=secret`, `ARG`/`ENV` token injection, `COPY .npmrc`/`.yarnrc`, auth-header `curl`/`wget`, `COPY`'d external scripts → GATHER + REFUSE (opaque scripts).
  - `../final-design.md §A.3 departure #3` — `tree-sitter-bash` is deliberately NOT added; a `COPY`'d script is detected as *invoked* and classified `opaque → refuse`, never parsed.
  - `../final-design.md §A.1` — the governing principle: gather enough to transform correctly, or refuse with typed evidence; shipping a broken image is the one unacceptable outcome.
- **Phase ADRs:**
  - `../ADRs/0018-dockerfile-secret-pattern-probe.md` — the probe decision; `external_script` opaque-by-design, no `tree-sitter-bash`, reuse the sanitizer's secret-shaped regexes.
  - `../ADRs/0005-probes-live-under-plugin-not-core-tree.md` — `plugins/distroless-migration--node--npm/probes/dockerfile_secret_pattern_probe.py` is the canonical location.
  - `../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md` — this story adds files only under `plugins/distroless-migration--node--npm/probes/` and `tests/`; the sub-schema + envelope `$ref` + fence-allowlist rows land in S13-03.
  - `../ADRs/0013-dockerfile-recipe-engine-dockerfile-parse.md` — `dockerfile-parse` is the canonical Dockerfile parser for Phase 7.
  - `../ADRs/0025-migration-refusal-taxonomy.md` — `RefusedOpaqueSecretScript` is the M2 refusal variant the recipe raises on an `external_script` record. (This story emits the *evidence*; S16's refusal taxonomy + recipe own the refusal.)
- **Existing code / precedents:**
  - `src/codegenie/probes/base.py` — the frozen Probe ABC. `DockerfileSecretPatternProbe(Probe)`; two-arg `run(self, repo, ctx)`.
  - `src/codegenie/output/sanitizer.py` — the Phase 2 sanitizer's secret-shaped-field regexes (the `RedactedSlice` smart constructor, Phase 2 ADR-0010). **Import and reuse** the secret-name pattern set — do NOT fork it. "What looks like a secret" has exactly one definition.
  - `plugins/distroless-migration--node--npm/probes/base_image_probe.py` (S7-01) — the **structural precedent**: `dockerfile-parse` AST walk, `_FILE_GLOBS`, the `_WARNING_IDS` import-time `raise AssertionError` block, the Open/Closed marker catalog (`_BASE_IMAGE_KIND_RULES`), the confidence ladder, the `async def run` sync-body shape. Mirror it.
  - `src/codegenie/probes/layer_c/dockerfile.py` — the Phase 2 line-by-line Dockerfile probe; precedent for `find_dockerfiles` (sorted output). Do NOT import its private parser — `dockerfile-parse` is the Phase 7 choice.
  - `src/codegenie/probes/registry.py` — `@register_probe` (defaults — `heaviness="light"`, `runs_last=False`).
  - `src/codegenie/types/identifiers.py` — newtype identifiers (Phase 7 S1-01). The `instruction_index` and any referenced-path field go through the existing newtype discipline — never raw `str`/`int` for a domain ID where a newtype exists.
- **Story-pipeline neighbors:**
  - `S7-01-base-image-probe.md` — the probe-shape precedent this story mirrors most closely.
  - `S13-02-target-image-content-probe.md` — the sibling Amendment-A Step-13 probe (target-image inventory).
  - `S13-03-amendment-a-schemas-and-fence.md` — owns the `secret_pattern.schema.json` sub-schema, the envelope `$ref`, the golden fixtures under `tests/golden/probes/secret_pattern/`, and the ADR-0029 fence-allowlist amendment. **This story ships the slice shape; S13-03 ships the schema.**
  - `S10-01-dockerfile-base-image-swap-recipe.md` / `S10-02-dockerfile-multi-stage-recipe.md` — the recipe consumers (REFUSE on `external_script`, rewrite `env_arg_injection`).

## Goal

Land `DockerfileSecretPatternProbe` at `plugins/distroless-migration--node--npm/probes/dockerfile_secret_pattern_probe.py` as a Probe-ABC-conformant, `@register_probe`-decorated, Layer-C, `tier="task_specific"`, `applies_to_tasks=["distroless-migration"]` probe that AST-walks every Dockerfile under the repo via `dockerfile-parse`, classifies each secret-acquisition pattern into one of the five closed `kind` values via the `_SECRET_PATTERN_RULES` Open/Closed catalog (reusing the Phase 2 sanitizer's secret-shaped-name regexes), records each `COPY`'d-then-`RUN` external script as **opaque** (invocation recorded, script unparsed), and emits a deterministic `SecretPatternSlice` — an ordered tuple of typed `SecretPattern` records — that the S10 recipes consume to preserve, rewrite, or refuse on every secret path. Net-new files only.

## Acceptance criteria

**Probe ABC conformance (AC-1 through AC-3)**
- [ ] **AC-1** `plugins/distroless-migration--node--npm/probes/dockerfile_secret_pattern_probe.py` exists. `DockerfileSecretPatternProbe(Probe)` is defined with class attributes `name = "dockerfile_secret_pattern"`, `layer = "C"`, `tier = "task_specific"`, `applies_to_tasks = ["distroless-migration"]`, `applies_to_languages = ["*"]`, `requires = []`, `declared_inputs = ["**/Dockerfile", "**/Dockerfile.*", "**/Containerfile"]`, `cache_strategy = "content"`, `timeout_seconds = 30`. Verified by `tests/unit/plugins/distroless_migration_node_npm/probes/test_secret_pattern_probe_metadata.py::test_probe_metadata_shape`, which reads `DockerfileSecretPatternProbe.__dict__` and asserts each field byte-equal to the declared value.
- [ ] **AC-2** `DockerfileSecretPatternProbe` is registered via `@register_probe` (defaults — `heaviness="light"`, `runs_last=False`), decorated at class scope. Verified by `test_secret_pattern_probe_metadata.py::test_registry_entry_present`: constructs a fresh `Registry`, imports the module, asserts `entry.probe_cls is DockerfileSecretPatternProbe AND entry.heaviness == "light" AND entry.runs_last is False`.
- [ ] **AC-3** `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` is the only abstract-method override; the parameter list is exactly `["self", "repo", "ctx"]`. Verified by an AST signature test `test_run_signature_matches_abc` — a one-arg `run` is a `TypeError` at dispatch and fails this AC.

**Slice shape (AC-4 through AC-6)**
- [ ] **AC-4** Slice shape (returned in `ProbeOutput.schema_slice["dockerfile_secret_pattern"]`):
  ```python
  {
      "patterns": [
          {
              "dockerfile_path": "<repo-relative-posix-path>",
              "kind": "buildkit_secret_mount|env_arg_injection|file_copy_credential|auth_header_fetch|external_script",
              "instruction_index": <int>,        # 0-based index into the file's instruction list
              "instruction": "<RUN|COPY|ARG|ENV|...>",
              "referenced_env": "<str | None>",  # env-var name, when the kind references one
              "referenced_path": "<str | None>", # filesystem path, when the kind references one
              "opaque": <bool>,                  # True iff kind == "external_script"
          }, ...
      ],
      "confidence": "high|medium|low",
  }
  ```
  `patterns` is an **ordered** list — sorted by `(dockerfile_path, instruction_index)` so the slice is deterministic across runs. Field set + ordering is pinned by this AC; `tests/golden/probes/secret_pattern/*.json` (owned by S13-03) is the canonical expected payload.
- [ ] **AC-5** `_SECRET_PATTERN_RULES: Final[tuple[SecretRule, ...]]` is a module-level Open/Closed marker catalog. Each `SecretRule` is a frozen dataclass with fields `(instruction: Literal["RUN", "COPY", "ARG", "ENV"], matcher: Callable[[str], SecretMatch | None], kind: SecretPatternKind)`. The catalog is iterated in `_classify_instruction(instruction, value) -> SecretMatch | None`, **never branched on with a chained `if`/`elif`** against `kind` literals. Verified by `test_classification_uses_catalog::test_no_if_chain_on_secret_kind`: AST-walks `_classify_instruction` and asserts no `elif` arm performs string equality against a `kind` literal — classification is catalog iteration. The catalog covers at minimum: `RUN --mount=type=secret` → `buildkit_secret_mount`; `ARG`/`ENV` whose name matches a Phase 2 sanitizer secret-shaped regex → `env_arg_injection`; `COPY` whose source basename is in `{.npmrc, .yarnrc, .yarnrc.yml, .netrc, .pypirc}` → `file_copy_credential`; `RUN` containing a `curl`/`wget` invocation with an `Authorization:`/`-H` auth-header flag → `auth_header_fetch`; a `RUN` of a script path previously `COPY`'d into the image → `external_script`.
- [ ] **AC-6** The five `kind` values are a **closed set** — `SecretPatternKind` is a `StrEnum` (or `Literal`) with exactly `{buildkit_secret_mount, env_arg_injection, file_copy_credential, auth_header_fetch, external_script}` and no other members. Verified by `test_secret_pattern_kind_is_closed::test_exactly_five_kinds` which asserts `set(SecretPatternKind.__members__.values()) == {...the five...}`. Adding a sixth kind without an ADR amendment fails this test.

**Secret-regex reuse (AC-7)**
- [ ] **AC-7** The `env_arg_injection` rule's matcher **imports and reuses** the Phase 2 sanitizer's secret-shaped-name regex set from `src/codegenie/output/sanitizer.py` — it does NOT define its own copy of `(?i)(token|secret|password|api_?key|...)`. Verified by `test_secret_regex_reused::test_no_local_secret_name_regex`: AST-walks `dockerfile_secret_pattern_probe.py` and asserts no module-level `re.compile(...)` literal contains a secret-shaped word list (the only source of that pattern is the imported sanitizer symbol). A behavioral companion: `ENV NPM_TOKEN=...` → classified `env_arg_injection`; `ENV APP_VERSION=1.2.3` → **not** classified (the version arg is not a secret).

**Behavior — one AC per kind + opaque + empty (AC-8 through AC-14)**
- [ ] **AC-8** `buildkit_secret_mount` — golden Dockerfile `tests/fixtures/portfolio/secret-buildkit-mount/Dockerfile` with `RUN --mount=type=secret,id=npmtoken npm ci` → slice has one pattern, `kind == "buildkit_secret_mount"`, `instruction == "RUN"`, `referenced_env == "npmtoken"` (the mount `id`), `opaque is False`, `confidence == "high"`.
- [ ] **AC-9** `env_arg_injection` — golden Dockerfile `tests/fixtures/portfolio/secret-env-arg/Dockerfile` with `ARG NPM_TOKEN` + `ENV NPM_TOKEN=$NPM_TOKEN` → slice has the `ARG`-instruction pattern (and/or the `ENV` one) with `kind == "env_arg_injection"`, `referenced_env == "NPM_TOKEN"`, `opaque is False`. The non-secret control `ARG APP_VERSION` in the same fixture produces **no** pattern.
- [ ] **AC-10** `file_copy_credential` — golden Dockerfile `tests/fixtures/portfolio/secret-copy-npmrc/Dockerfile` with `COPY .npmrc /app/.npmrc` → slice has one pattern, `kind == "file_copy_credential"`, `instruction == "COPY"`, `referenced_path == ".npmrc"`, `opaque is False`.
- [ ] **AC-11** `auth_header_fetch` — golden Dockerfile `tests/fixtures/portfolio/secret-auth-header/Dockerfile` with `RUN curl -H "Authorization: Bearer $TOKEN" https://registry.internal/pkg.tgz -o /tmp/pkg.tgz` → slice has one pattern, `kind == "auth_header_fetch"`, `instruction == "RUN"`, `referenced_env == "TOKEN"` (the env var referenced in the header), `opaque is False`.
- [ ] **AC-12** `external_script` (opaque) — golden Dockerfile `tests/fixtures/portfolio/secret-external-script/Dockerfile` with `COPY fetch-creds.sh /tmp/fetch-creds.sh` then `RUN /tmp/fetch-creds.sh` → slice has one pattern, `kind == "external_script"`, `instruction == "RUN"`, `referenced_path == "/tmp/fetch-creds.sh"`, **`opaque is True`**. The probe **does not read or parse `fetch-creds.sh`** — verified by `test_external_script_is_opaque::test_script_file_not_opened`: a fixture whose `fetch-creds.sh` content is `exit 7` is run through the probe, and the test asserts the script's bytes never appear in the slice and that the probe makes no file read of `fetch-creds.sh` (instrument the fixture's filesystem or assert the probe's discovered-file set excludes it). `confidence` for a slice containing any opaque pattern is downgraded to `"medium"` (we have the invocation but not the behavior).
- [ ] **AC-13** Empty case — `tests/fixtures/portfolio/node-vulnerable-alpine/Dockerfile` (a Dockerfile that acquires no secrets) → slice has `patterns == []`, `confidence == "high"`. An empty slice is a positive result ("no secret acquisition observed"), not a degraded one.
- [ ] **AC-14** Parse-failure path — fixture with a malformed Dockerfile → probe returns `ProbeOutput` with `confidence == "low"`, `warnings == ["dockerfile_secret_pattern.dockerfile_parse_failed"]` (matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` per Phase 1 ADR-0007), the failing file contributes no patterns, and **no exception escapes `run()`**. Verified by `test_parse_failure::test_warning_id_format` (regex-checks the ID) and `test_parse_failure::test_no_exception_escapes` (`pytest.raises(BaseException)` asserts nothing fires). The probe catches the **specific** `dockerfile-parse` exception class — a bare `except Exception` fails `mypy --strict` config and Rule 12.

**Warning-ID + cache discipline (AC-15, AC-16)**
- [ ] **AC-15** Module-level `_WARNING_IDS: Final[frozenset[str]] = frozenset({"dockerfile_secret_pattern.dockerfile_parse_failed"})` exists; an import-time `raise AssertionError(...)` (NOT a bare `assert` — the `forbidden-patterns` hook rejects bare `assert`) checks each ID matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. Mirrors S7-01's `_WARNING_IDS` block.
- [ ] **AC-16** `cache_key` is **not overridden** — the probe uses the default content-addressed `Probe.cache_key` over `declared_inputs`. Verified by AST: `test_no_cache_key_override::test_method_not_redefined` asserts `DockerfileSecretPatternProbe.cache_key is Probe.cache_key`.

**Fence + lint discipline (AC-17 through AC-20)**
- [ ] **AC-17** AST-walk purity fence: `tests/fence/test_secret_pattern_probe_purity.py` walks `dockerfile_secret_pattern_probe.py` and rejects `subprocess.run`, `subprocess.Popen`, `os.system`, `os.popen`, `shell=True`, `requests.*`, `urllib.request.urlopen`, `httpx.*`, and any LLM-SDK import (`anthropic`, `openai`, `langchain`, `langgraph`, `transformers`). It **additionally** rejects any import of a `tree_sitter`/`tree-sitter-bash` symbol (departure #3 — the probe must never parse a shell script). Three planted-violation parametrized cases (red-by-construction inside the test) prove the walker fires; one of them is a planted `import tree_sitter`. The fence file uses `raise AssertionError("...")` — bare `assert` is forbidden.
- [ ] **AC-18** `make lint-imports` green — the new file introduces no forbidden import path. The S5-03 import-linter contract already covers `plugins/distroless-migration--*/` against LLM SDKs.
- [ ] **AC-19** `ruff check`, `ruff format --check`, `mypy --strict plugins/distroless-migration--node--npm/probes/dockerfile_secret_pattern_probe.py` all clean. **No `Any` in annotations** — the Phase 7 `test_no_any_in_plugin_surface` discipline (S5-03) applies to the migration plugin tree.
- [ ] **AC-20** Phase 7 byte-edit allowlist fence (`tests/fence/test_phase7_no_byte_edits_to_locked_files.py`) green: this story adds files **only** under `plugins/distroless-migration--node--npm/probes/` and `tests/`; no Phase 0–6.5 file is touched. The sub-schema, envelope `$ref`, and the ADR-0029 fence-allowlist rows are S13-03's surface — explicitly out of scope here.

## Implementation outline

1. **Net-new files only — no edits to Phase 0–6.5 or to S13-03's surface.** Create:
   - `plugins/distroless-migration--node--npm/probes/dockerfile_secret_pattern_probe.py` — the probe + private helpers.
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_secret_pattern_probe_metadata.py`
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_secret_pattern_probe_behavior.py`
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_classification_uses_catalog.py` (or extend the S7-01 file — prefer a new file to keep the diff additive).
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_secret_regex_reused.py`
   - `tests/fence/test_secret_pattern_probe_purity.py` (AST fence).
   - Fixture Dockerfiles under `tests/fixtures/portfolio/{secret-buildkit-mount,secret-env-arg,secret-copy-npmrc,secret-auth-header,secret-external-script,secret-parse-failed}/Dockerfile` (plus, for AC-12, the unparsed `fetch-creds.sh` companion file).

2. **Module-level types + Open/Closed catalog in `dockerfile_secret_pattern_probe.py`:**
   ```python
   from typing import Final, Literal
   from dataclasses import dataclass
   from collections.abc import Callable
   from enum import StrEnum
   import re

   from codegenie.output.sanitizer import SECRET_NAME_PATTERN  # reuse — AC-7

   class SecretPatternKind(StrEnum):
       BUILDKIT_SECRET_MOUNT = "buildkit_secret_mount"
       ENV_ARG_INJECTION = "env_arg_injection"
       FILE_COPY_CREDENTIAL = "file_copy_credential"
       AUTH_HEADER_FETCH = "auth_header_fetch"
       EXTERNAL_SCRIPT = "external_script"

   @dataclass(frozen=True)
   class SecretMatch:
       kind: SecretPatternKind
       referenced_env: str | None
       referenced_path: str | None

   @dataclass(frozen=True)
   class SecretRule:
       instruction: Literal["RUN", "COPY", "ARG", "ENV"]
       matcher: Callable[[str], SecretMatch | None]
       kind: SecretPatternKind

   _CREDENTIAL_FILE_BASENAMES: Final[frozenset[str]] = frozenset(
       {".npmrc", ".yarnrc", ".yarnrc.yml", ".netrc", ".pypirc"}
   )
   _SECRET_PATTERN_RULES: Final[tuple[SecretRule, ...]] = (
       SecretRule("RUN", _match_buildkit_secret_mount, SecretPatternKind.BUILDKIT_SECRET_MOUNT),
       SecretRule("ARG", _match_env_arg_injection, SecretPatternKind.ENV_ARG_INJECTION),
       SecretRule("ENV", _match_env_arg_injection, SecretPatternKind.ENV_ARG_INJECTION),
       SecretRule("COPY", _match_file_copy_credential, SecretPatternKind.FILE_COPY_CREDENTIAL),
       SecretRule("RUN", _match_auth_header_fetch, SecretPatternKind.AUTH_HEADER_FETCH),
       # external_script is resolved by a two-pass scan (COPY-then-RUN), not a single-instruction matcher.
   )

   _WARNING_IDS: Final[frozenset[str]] = frozenset({"dockerfile_secret_pattern.dockerfile_parse_failed"})
   _WARNING_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
   for _id in _WARNING_IDS:
       if not _WARNING_ID_RE.fullmatch(_id):
           raise AssertionError(f"warning id {_id!r} violates Phase 1 ADR-0007 regex")
   ```

3. **`_classify_instruction(instruction, value) -> SecretMatch | None`** — iterate `_SECRET_PATTERN_RULES`, skip rules whose `instruction` does not match, call the rule's `matcher`, return on first non-`None` `SecretMatch`. No chained `if`/`elif` against `kind` literals (AC-5).

4. **`external_script` is a two-pass scan** (it spans two instructions and cannot be a single-instruction rule):
   - Pass 1 — walk `COPY` instructions; collect the set of in-image destination paths whose source basename ends in `.sh` (or has no extension and is `COPY`'d into a path later `RUN`).
   - Pass 2 — walk `RUN` instructions; if the `RUN` argv invokes a path collected in pass 1, emit an `external_script` `SecretMatch` with `referenced_path` = the script's in-image path, `opaque=True`. **Never open the script file.**

5. **`async def run(self, repo, ctx) -> ProbeOutput`:**
   - `t0 = time.perf_counter()`.
   - Discover Dockerfiles via the glob set (mirror S7-01's `find_dockerfiles`; sorted output).
   - For each file: parse via `dockerfile_parse.DockerfileParser`. Catch the **specific** `dockerfile-parse` exception; on failure append `"dockerfile_secret_pattern.dockerfile_parse_failed"` to warnings, contribute no patterns, continue.
   - Run `_classify_instruction` over `parser.structure` for the single-instruction kinds; run the two-pass `external_script` scan.
   - Sort the collected `SecretPattern` records by `(dockerfile_path, instruction_index)`.
   - `confidence`: `"high"` if no warnings and no `opaque` pattern; `"medium"` if any `opaque` pattern (we have the invocation, not the behavior); `"low"` if any file failed to parse.
   - Return `ProbeOutput(schema_slice={"dockerfile_secret_pattern": ...}, raw_artifacts=[], confidence=..., duration_ms=..., warnings=warnings, errors=[])`.

6. **Fixtures** — one Dockerfile per kind (AC-8..AC-12), the empty case reuses an existing fixture (AC-13), one malformed Dockerfile (AC-14). The `secret-external-script` fixture carries a `fetch-creds.sh` whose content is a sentinel (`exit 7`) so AC-12 can assert it is never read.

7. **Tests** — metadata (AC-1..AC-3), behavior (AC-8..AC-14), catalog-AST (AC-5, AC-6), regex-reuse (AC-7), purity fence (AC-17).

## TDD plan — red / green / refactor

**Red 1** — write `test_secret_pattern_probe_metadata.py::test_probe_metadata_shape` first. It does `from plugins.distroless_migration_node_npm.probes.dockerfile_secret_pattern_probe import DockerfileSecretPatternProbe` and asserts every metadata field. Run pytest — it fails with `ModuleNotFoundError` (the file does not exist). This is the right failure: the artifact is absent.

**Green 1** — create `dockerfile_secret_pattern_probe.py` with the class skeleton (metadata only; `async def run` raising `NotImplementedError`). Metadata test green; behavior tests still red.

**Red 2** — write `test_secret_pattern_probe_behavior.py::test_buildkit_secret_mount` (AC-8) against the `secret-buildkit-mount` fixture. Pytest fails on `NotImplementedError` — `run()` is not implemented. Right failure.

**Green 2** — implement `run()` + the `_match_buildkit_secret_mount` matcher. The AC-8 test passes. Iterate the remaining four kind matchers + the two-pass `external_script` scan + the degraded paths, one behavior AC at a time (each is its own red → green).

**Red 3** — write `test_external_script_is_opaque::test_script_file_not_opened` (AC-12) with the `exit 7` sentinel script. Initially red because the two-pass scan is not yet written; once written, the test must stay green AND prove the script bytes never reach the slice.

**Red 4** — write `test_secret_pattern_probe_purity.py` with a planted `import tree_sitter` parametrize row. Pytest fails because the AST walker is not written.

**Green 4** — implement the AST walker; the three planted-violation rows (`subprocess.run`, `urllib.request.urlopen`, `import tree_sitter`) all show red-by-construction; the real probe file passes.

**Refactor** — extract `_classify_instruction`, the five matchers, the two-pass `external_script` scanner, and the Dockerfile-discovery helper into module-level functions. AST-assert `_classify_instruction` has no `kind`-literal `if`/`elif` chain (AC-5). Confirm `ruff` + `mypy --strict` clean and the full `make check` regression suite green.

## Files to touch

**New files (no Phase 0–6.5 byte-edits):**

| Path | Purpose |
|---|---|
| `plugins/distroless-migration--node--npm/probes/dockerfile_secret_pattern_probe.py` | The probe + `_SECRET_PATTERN_RULES` catalog + matchers + two-pass `external_script` scan |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_secret_pattern_probe_metadata.py` | AC-1, AC-2, AC-3 |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_secret_pattern_probe_behavior.py` | AC-8 through AC-14 |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_classification_uses_catalog.py` | AC-5, AC-6 (catalog-AST + closed-kind-set) |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_secret_regex_reused.py` | AC-7 (sanitizer-regex reuse, AST + behavioral) |
| `tests/fence/test_secret_pattern_probe_purity.py` | AC-17 (purity fence incl. `tree_sitter` ban) |
| `tests/fixtures/portfolio/secret-buildkit-mount/Dockerfile` | AC-8 fixture |
| `tests/fixtures/portfolio/secret-env-arg/Dockerfile` | AC-9 fixture |
| `tests/fixtures/portfolio/secret-copy-npmrc/Dockerfile` | AC-10 fixture |
| `tests/fixtures/portfolio/secret-auth-header/Dockerfile` | AC-11 fixture |
| `tests/fixtures/portfolio/secret-external-script/Dockerfile` + `fetch-creds.sh` | AC-12 fixture (script is sentinel `exit 7`, never read) |
| `tests/fixtures/portfolio/secret-parse-failed/Dockerfile` | AC-14 fixture (malformed) |

**Files NOT touched** (would fail the Phase 7 byte-edit fence / belong to S13-03): `src/codegenie/probes/`, `src/codegenie/output/sanitizer.py` (imported, never edited), `src/codegenie/schema/repo_context.schema.json`, `plugins/distroless-migration--node--npm/schema/`, `tests/fence/test_phase7_no_byte_edits_to_locked_files.py`, `tests/golden/probes/secret_pattern/`.

## Out of scope

- **The `secret_pattern.schema.json` sub-schema + envelope `$ref` + golden fixtures** — S13-03 owns all of it. This story ships the **slice shape** (AC-4); S13-03 ships the **schema** + the goldens under `tests/golden/probes/secret_pattern/`.
- **The ADR-0029 fence-allowlist amendment** — S13-03 amends `tests/fence/test_phase7_no_byte_edits_to_locked_files.py`. This story's edits are net-new-files-only and need no allowlist row.
- **The `RefusedOpaqueSecretScript` refusal variant + the recipe's REFUSE-on-`external_script` behavior** — `outcomes.py` additive variants are M2 / [ADR-0025](../ADRs/0025-migration-refusal-taxonomy.md); the recipe consumption is S10-01 / S10-02. This story emits the *evidence* (an `external_script` record with `opaque=True`); the refusal is downstream.
- **Rewriting `env_arg_injection` into `--mount=type=secret`** — that is the `DockerfileBaseImageSwapTransform` recipe's job (S10-01). This story only *detects* the `env_arg_injection`.
- **Parsing the `COPY`'d external script** — explicitly forbidden by `../final-design.md §A.3 departure #3`. `external_script` is opaque-by-design; AC-12 + AC-17 enforce that the probe never reads or parses it and never imports a `tree_sitter` symbol.
- **`TargetImageContentProbe`** — S13-02 owns the target-image inventory probe.
- **Plugin loader explicit-import wiring + `api.py` side-effect imports** — S8-03 / S13-03 own the loader row; the `from .probes import dockerfile_secret_pattern_probe  # noqa: F401` side-effect import lands in the plugin's `api.py`, not in this story.

## Notes for the implementer

- **Rule 11 — match the existing convention.** S7-01's `BaseImageProbe` (`plugins/distroless-migration--node--npm/probes/base_image_probe.py`) is the precedent for the `dockerfile-parse` walk, `find_dockerfiles`, the `_WARNING_IDS` import-time block, the Open/Closed marker catalog, and the `async def run` sync-body shape. Mirror it; do not fork it. The one difference is the classification target — secret-acquisition patterns rather than base-image kinds.
- **Rule 8 — read before you write.** Before writing the `env_arg_injection` matcher, read `src/codegenie/output/sanitizer.py` and find the **exact** secret-shaped-name symbol the Phase 2 sanitizer exports. AC-7 requires you to *import* it, not re-derive it. If the sanitizer's pattern is private (`_`-prefixed) and not importable, surface that in `_attempts/S13-01.md` — the fix is to widen the sanitizer's public surface (a separate, ADR-reviewed question), not to copy the regex.
- **Rule 12 — fail loud.** A `dockerfile-parse` exception is a typed warning, not a swallowed error (AC-14). An `external_script` is honest evidence of "we cannot statically know what this does" — it is `opaque=True`, `confidence` drops to `medium`, and the recipe refuses. The opaque case is the design *working*, not failing.
- **Rule 9 — tests verify intent.** The behavior tests assert business semantics: "an `.npmrc` `COPY` is a credential file path" and "an `APP_VERSION` `ARG` is **not** a secret." The AST tests (AC-5, AC-7) verify the design intent we want preserved across refactors — Open/Closed via catalog iteration, and one repo-wide definition of "what looks like a secret."
- **`external_script` is opaque by design.** `../final-design.md §A.3 departure #3` is explicit: a `COPY`'d script is detected as *invoked* and classified `opaque → refuse`; it is **never parsed**. `tree-sitter-bash` is deliberately not added. AC-12 + AC-17 are the load-bearing enforcers — without them a future engineer "improves" the probe by parsing the script and reintroduces the exact non-determinism departure #3 closes.
- **Open/Closed marker catalog (toolkit pattern).** `_SECRET_PATTERN_RULES` is the open/closed seam — adding a new secret-acquisition pattern (e.g., a `--secret` flag on a future build tool) is **one new tuple row + one matcher function**, not an edit to `_classify_instruction`. The closed-kind-set test (AC-6) is the deliberate counterweight: the *kinds* are closed (adding one is an ADR amendment), but the *rules that map to a kind* are open. That asymmetry is intentional — five kinds is the contract the recipe matches `assert_never` against; the matchers behind them can grow.
- **The two-pass `external_script` scan.** A single-instruction `SecretRule` cannot express `external_script` because it spans a `COPY` and a later `RUN`. Keep it as a separate two-pass helper (`_scan_external_scripts(structure) -> list[SecretMatch]`) — do NOT contort the rule catalog to fit it. This is Rule 7: the two patterns (single-instruction matcher vs cross-instruction scan) genuinely differ in shape; do not average them into one awkward abstraction.
- **No async I/O.** The probe is sync-in-async-shell — `async def run` is required by the ABC, but the body is pure file reads + parsing. No `await` calls. `asyncio_mode = "auto"` handles test invocation.
- **`confidence` ladder.** `high` = no warnings, no opaque pattern; `medium` = at least one opaque `external_script` (invocation known, behavior unknown); `low` = a Dockerfile failed to parse. This mirrors the S7-01 / Phase 1 `IndexHealthProbe` honest-confidence discipline.
- **Effort budget.** Probe body ≈ 130 LOC (the two-pass scan adds ~30 over a pure single-pass probe); tests ≈ 280 LOC; fence ≈ 70 LOC. If the body grows past 160 LOC, extract the five matchers into `_secret_matchers.py`. Token-budget guard (Rule 6): single-session-implementable at ~4k tokens — if `dockerfile-parse` surprises you on `RUN --mount` flag parsing, STOP, surface, and consider a narrow regex pre-scan of the raw `RUN` line as fallback (the AST fence already forbids subprocess, so the parser layer is replaceable).
