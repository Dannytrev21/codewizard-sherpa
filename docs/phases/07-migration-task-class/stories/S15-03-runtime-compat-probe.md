# Story S15-03 — `RuntimeCompatProbe` + four-family runtime-hazard analysis + advisory WARN disposition

**Step:** Step 15 — Runtime-compatibility gather (G4, G6, G7–G10, G12)
**Status:** Ready
**Effort:** M
**Depends on:** S13-03 (`S13-03-amendment-a-schemas-and-fence.md` — the Amendment-A probe sub-schema directory `plugins/distroless-migration--node--npm/schema/` exists, the envelope `$ref`-wiring precedent is established, and `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` is already amended per ADR-0029 so this story's new files land inside an already-allowlisted tree)

**ADRs honored:** Phase 7 [ADR-0023](../ADRs/0023-runtime-compat-probe.md) (`RuntimeCompatProbe` folds uid/PID-1/filesystem/locale assumptions into one advisory probe); Phase 7 [ADR-0005](../ADRs/0005-probes-live-under-plugin-not-core-tree.md) (probes live under the plugin, NOT `src/codegenie/probes/`); Phase 7 [ADR-0009](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) + [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) (this story is **net-new-files-only** under the already-allowlisted plugin tree); Phase 7 [ADR-0026](../ADRs/0026-migration-confidence-aggregation.md) (`RuntimeCompatProbe.confidence` is a load-bearing input to `aggregate_migration_confidence` — the aggregator is S17-01, not this story); Phase 7 [ADR-0027](../ADRs/0027-migration-observability-bundle.md) (the grouped findings render in the PR-description WARN bundle — the WARN *surface* is S18; this story emits the slice the bundle reads); Phase 0 ADR-0007 / [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md) (frozen Probe ABC — two-arg `run(self, repo, ctx)`); Phase 1 ADR-0004 (per-probe sub-schema `additionalProperties: false`); Phase 1 ADR-0007 (warning-ID regex); production ADR-0033 (sum-type domain-modeling discipline — the `family` discriminant is a closed enum).

## Context

`RuntimeCompatProbe` is the **Layer C, static, plugin-internal** probe that closes Amendment A gaps **G7–G10** (`../final-design.md §Amendment A §A.2`). Amendment A's governing principle (§A.1) is that Phase 7 must, for every migration, either **gather enough context to transform correctly** or **refuse with typed evidence** — shipping a broken image is the one unacceptable outcome. Gaps G7–G10 catalogue **four runtime-environment hazard families** a naive `FROM` swap silently breaks, because the Chainguard distroless target runs as `nonroot` (uid 65532) with a minimal filesystem:

- **G7 — uid/user delta.** The source builds as root; the target is `nonroot`. `COPY` without `--chown`, writes outside `$HOME`/`/tmp`, and a privileged `EXPOSE` < 1024 all fail post-migration.
- **G8 — PID-1/signal handling.** An app with no `SIGTERM` listener, run as PID 1, gets a slow (kill-timeout) shutdown instead of a graceful drain.
- **G9 — filesystem assumptions.** Literal-path `fs.readFile` of `/etc/passwd`, `/etc/timezone`, or `/tmp` assumes a full base image; distroless trims these.
- **G10 — locale/timezone.** `process.env.TZ` and ICU-dependent dependencies assume locale data the distroless image may not carry.

Unlike G1/G4 (which produce typed *refusals*), G7–G10 are mostly **non-deterministic to auto-fix** — whether a missing `--chown` matters depends on what the app writes, and a missing `SIGTERM` handler is a code change no recipe can author safely. ADR-0023 resolves all four into a **single `RuntimeCompatProbe`** (Option B — one cohesive advisory probe over four separate ones; the findings are uniformly advisory, so 4× the registry dispatch / sub-schema / `$ref` / fence rows would buy nothing). The disposition is **WARN** — every finding is surfaced in the PR description (M3); none blocks; the recipe never refuses on a `RuntimeCompatSlice` finding. The human merger decides, because the fixes (add a `SIGTERM` handler, parameterise a hardcoded path) are code changes no deterministic recipe can author.

The probe combines a **`dockerfile-parse` pass** (for `COPY` without `--chown`, writes outside `$HOME`/`/tmp`, privileged `EXPOSE`) with a **tree-sitter JS/TS pass** over the existing `javascript`/`typescript` grammars (for literal-path `fs.readFile`, `process.env.TZ`, ICU-dependent deps) — **no new grammar, no `tree-sitter-bash`** (Amendment A §A.3 departure #3). It emits `RuntimeCompatSlice`: typed findings grouped under a **closed `family` sum type** (`user_uid | pid1_signals | filesystem | locale_tz`), each with a source-location payload, plus the probe's own `confidence`.

**A documented subtlety** (ADR-0023 Tradeoffs row 4): the *finding disposition* is WARN (advisory), but the *probe's `confidence`* is **load-bearing** — a `low`-confidence `RuntimeCompatProbe` (e.g. an unparseable Dockerfile) degrades `MigrationConfidence` like any other probe. Advisory findings + load-bearing probe-health are not a contradiction; this story keeps them distinct.

The probe lives under `plugins/distroless-migration--node--npm/probes/runtime_compat_probe.py` — **NOT** under `src/codegenie/probes/`. [ADR-0005](../ADRs/0005-probes-live-under-plugin-not-core-tree.md) is explicit; the S5-02 placement fence AST-asserts it.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — Amendment A §20 (RuntimeCompatProbe)` — names the slice (`findings grouped user_uid | pid1_signals | filesystem | locale_tz`), the two-parser internal structure (`dockerfile-parse` + tree-sitter JS/TS), and the GATHER + WARN disposition.
  - `../phase-arch-design.md §Component design — Amendment A` preamble — every Amendment-A probe obeys the frozen Probe ABC.
- **Phase ADRs:**
  - `../ADRs/0023-runtime-compat-probe.md` — **the governing ADR.** Option B (one combined probe, findings grouped by family) was adopted; Option A (four separate probes) and Option C (let the build gate catch it) were rejected. The closed `family` sum type, the WARN disposition, the two-parser structure, and the "advisory finding vs load-bearing probe-confidence" distinction all come from here.
  - `../ADRs/0005-probes-live-under-plugin-not-core-tree.md` — `plugins/distroless-migration--node--npm/probes/runtime_compat_probe.py` is the canonical location.
  - `../ADRs/0009-phase-7-byte-edit-allowlist-fence.md` + `../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md` — ADR-0029 already enumerates `runtime_compat_probe.py` and its sub-schema; S13-03 landed those rows.
  - `../ADRs/0026-migration-confidence-aggregation.md` — `RuntimeCompatProbe.confidence` feeds `aggregate_migration_confidence`. The aggregator is S17-01; this story only emits a well-laddered `confidence`.
  - `../ADRs/0027-migration-observability-bundle.md` — the grouped findings render in the M3 `transformations_applied` / PR-description WARN bundle. The WARN surface is S18; this story emits the slice.
  - `../ADRs/0021-runtime-shell-invocation-probe.md` — the deterministic-refusal sibling (G4/G12). `RuntimeCompatProbe` is the *advisory* counterpart; the two are orthogonal.
- **Existing code / precedents:**
  - `src/codegenie/grammars/lock.py` — `language_for("javascript" | "typescript")` is the **only** way to obtain a tree-sitter `Language`; it raises `GrammarLoadRefused` on every failure path. `tree-sitter-bash` is forbidden (Amendment A §A.3).
  - `src/codegenie/probes/layer_b/node_reflection.py` — the canonical tree-sitter JS/TS probe; mirror its parser-construction and module-level `Final` query-catalog shape for the `filesystem` + `locale_tz` JS/TS pass.
  - `src/codegenie/probes/layer_c/dockerfile.py` + `src/codegenie/probes/layer_c/_dockerfile_parse.py` — the Phase 2 Dockerfile-parsing precedent; the `user_uid` family reuses `dockerfile-parse` (the Phase 7 parser, in-tree from S13-01's window) for `COPY`/`EXPOSE`/`WORKDIR`/`USER` instructions.
  - `src/codegenie/probes/base.py` — the frozen Probe ABC. Two-arg `run(self, repo, ctx)`.
  - `src/codegenie/probes/registry.py` — `@register_probe` defaults (`heaviness="light"`, `runs_last=False`).
  - `src/codegenie/types/identifiers.py` — newtype-identifier discipline. This story introduces `SourceLocation` as a frozen dataclass (`file: str`, `line: int | None`, `instruction_index: int | None` — one or the other populated depending on whether the finding came from the Dockerfile pass or the JS/TS pass) and uses a closed `HazardFamily` sum type.
  - `S7-01-base-image-probe.md` Implementation outline §2 — the `_BASE_IMAGE_KIND_RULES` open/closed marker-catalog pattern; `RuntimeCompatProbe`'s per-family rule catalogs mirror it.
- **Story-pipeline neighbors:**
  - `S13-03-amendment-a-schemas-and-fence.md` — **must land first.** Established the `schema/` directory, the `$ref`-wiring pattern, and the ADR-0029 allowlist amendment.
  - `S7-01-base-image-probe.md` — the structural template for any Amendment-era Phase 7 plugin probe. Mirror it.
  - `S15-01-runtime-shell-invocation-probe.md` + `S15-02-container-probe-compat-probe.md` — sibling Step-15 probes; same metadata-AC + purity-fence shape. Land independently.
  - `S17-01-migration-confidence-aggregator.md` — `aggregate_migration_confidence` consumes `RuntimeCompatProbe.confidence`. Downstream.
  - `S18-*` (observability bundle) — renders the grouped findings as WARNs in the PR description. Downstream.

## Goal

Land `RuntimeCompatProbe` under `plugins/distroless-migration--node--npm/probes/runtime_compat_probe.py` as a Probe-ABC-conformant, `@register_probe`-decorated, Layer-C, `task_specific`, `applies_to_tasks=["distroless-migration"]` probe that runs one `dockerfile-parse` pass (uid/user-delta hazards) and one tree-sitter JS/TS pass (filesystem + locale/TZ hazards) plus a JS/TS signal-handler scan (PID-1 hazard), classifies every finding under the closed `HazardFamily` sum type (`user_uid | pid1_signals | filesystem | locale_tz`), attaches a typed `SourceLocation` to each, and emits the deterministic `RuntimeCompatSlice` the migration PR-description bundle renders as advisory WARNs and the `MigrationConfidence` aggregator reads for probe health. Every finding is WARN — the probe never refuses. No subprocess, no network, no `tree-sitter-bash`.

## Acceptance criteria

**Probe ABC conformance (AC-1 through AC-3)**
- [ ] **AC-1** `plugins/distroless-migration--node--npm/probes/runtime_compat_probe.py` exists. `RuntimeCompatProbe(Probe)` is defined with class attributes `name = "runtime_compat"`, `layer = "C"`, `tier = "task_specific"`, `applies_to_tasks = ["distroless-migration"]`, `applies_to_languages = ["javascript", "typescript"]`, `requires = []`, `declared_inputs = ["**/Dockerfile", "**/Dockerfile.*", "**/Containerfile", "**/*.js", "**/*.mjs", "**/*.cjs", "**/*.ts", "**/*.mts", "**/*.cts", "**/*.tsx"]`, `cache_strategy = "content"`, `timeout_seconds = 60`. Verified by `tests/unit/plugins/distroless_migration_node_npm/probes/test_runtime_compat_metadata.py::test_probe_metadata_shape` (reads `__dict__`, asserts each field byte-equal).
- [ ] **AC-2** `RuntimeCompatProbe` is registered via `@register_probe` (defaults — `heaviness="light"`, `runs_last=False`). The decoration is at class scope. `test_runtime_compat_metadata.py::test_registry_entry_present` constructs a fresh `Registry`, imports the module, and asserts `entry.probe_cls is RuntimeCompatProbe AND entry.heaviness == "light" AND entry.runs_last is False`.
- [ ] **AC-3** `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` is the only abstract-method override; signature matches the frozen Phase 0 ABC byte-for-byte. `test_runtime_compat_metadata.py::test_run_signature_matches_abc` AST-asserts the parameter list is exactly `["self", "repo", "ctx"]`.

**Slice shape (AC-4 through AC-6)**
- [ ] **AC-4** Slice shape (returned in `ProbeOutput.schema_slice["runtime_compat"]`):
  ```python
  {
      "findings": [
          {
              "family": "user_uid|pid1_signals|filesystem|locale_tz",
              "rule_id": "<str matching ^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$>",  # e.g. 'user_uid.copy_without_chown'
              "detail": "<short human-readable description>",
              "source": {
                  "file": "<repo-relative-posix-path>",
                  "line": "<int | None>",                  # populated for JS/TS findings
                  "instruction_index": "<int | None>",     # populated for Dockerfile findings
              },
          }, ...
      ],
      "confidence": "high|medium|low",
  }
  ```
  `findings` is sorted deterministically by `(family, source.file, source.line or source.instruction_index or 0)`. Verified against `tests/golden/probes/runtime_compat/*.json`; the **field set + key order + sort order** is pinned by this story's AC.
- [ ] **AC-5** `family` is a **closed sum type** — `HazardFamily = Literal["user_uid", "pid1_signals", "filesystem", "locale_tz"]` (or a `StrEnum` with exactly those four members), never a free string. A module-level `_HAZARD_FAMILIES: Final[tuple[HazardFamily, ...]]` enumerates them. `test_findings_grouped_by_family.py::test_family_is_closed_sum_type` reads the slice and asserts every `family` value is a member of `_HAZARD_FAMILIES`, and `test_family_set_is_exactly_four` asserts `len(_HAZARD_FAMILIES) == 4` and the set equals `{"user_uid", "pid1_signals", "filesystem", "locale_tz"}` — adding a fifth family is an ADR amendment (ADR-0023 Reversibility), and this test is the tripwire.
- [ ] **AC-6** Each hazard family's detection rules live in a module-level open/closed catalog — `_USER_UID_RULES`, `_FILESYSTEM_RULES`, `_LOCALE_TZ_RULES` are each a `Final[tuple[...]]`, iterated, never an `if/elif` chain. The PID-1 detection is a single scan (a presence/absence check, not a rule list — see AC-9). `test_detection_uses_catalogs.py::test_no_if_chain_on_family` AST-walks the family dispatch and asserts no `if/elif` arm performs string equality against a family literal — the per-family analysers are selected by iterating a `Final` mapping of `family -> analyser`, not by branching.

**Behavior — one finding per family (AC-7 through AC-11)**
- [ ] **AC-7** `user_uid` family — fixture `tests/fixtures/portfolio/runtime-compat-uid/Dockerfile` containing `COPY ./app /app` (no `--chown`) **and** `EXPOSE 80` (privileged, < 1024) → slice has at least two `user_uid` findings: one `rule_id == "user_uid.copy_without_chown"` with `source.instruction_index` pointing at the `COPY` line, one `rule_id == "user_uid.privileged_expose"` with the `EXPOSE` line. `test_runtime_compat_behavior.py::test_user_uid_family` asserts both findings' `family == "user_uid"`, both `rule_id`s present, and that each `source.instruction_index` is an `int` while `source.line is None` (Dockerfile findings carry the instruction index, not a line).
- [ ] **AC-8** `filesystem` family — fixture `runtime-compat-fs/src/auth.ts` containing `import { readFileSync } from "fs"; const u = readFileSync("/etc/passwd", "utf8");` → slice has one `filesystem` finding, `rule_id == "filesystem.literal_system_path_read"`, `source.file == "src/auth.ts"`, `source.line` is the 1-based line of the call, `source.instruction_index is None`. `test_runtime_compat_behavior.py::test_filesystem_family` asserts the finding and that the `detail` names the literal path `/etc/passwd`. The rule fires for literal-path reads of `/etc/passwd`, `/etc/timezone`, `/etc/shadow`, and `/tmp`-rooted absolute paths (a `_FILESYSTEM_RULES` catalog of sensitive path prefixes).
- [ ] **AC-9** `pid1_signals` family — fixture `runtime-compat-pid1/src/server.js` that starts an HTTP server (`http.createServer(...).listen(...)`) and **never** registers a `SIGTERM` listener (`process.on('SIGTERM', ...)`) → slice has one `pid1_signals` finding, `rule_id == "pid1_signals.no_sigterm_handler"`, `source.file == "src/server.js"`. The detection is **absence-based**: the probe scans each entrypoint-shaped JS/TS file for a `process.on('SIGTERM', ...)` / `process.once('SIGTERM', ...)` call; a file that runs a long-lived server with no such call produces the finding. `test_runtime_compat_behavior.py::test_pid1_no_sigterm` asserts the finding fires for the no-handler fixture **and** that a paired fixture `runtime-compat-pid1-ok/src/server.js` — identical but with `process.on('SIGTERM', shutdown)` — produces **no** `pid1_signals` finding (the absence-detection must not false-positive on a compliant app).
- [ ] **AC-10** `locale_tz` family — fixture `runtime-compat-tz/src/clock.ts` containing `const tz = process.env.TZ;` → slice has one `locale_tz` finding, `rule_id == "locale_tz.process_env_tz_read"`, `source.file == "src/clock.ts"`, `source.line` set. `test_runtime_compat_behavior.py::test_locale_tz_family` asserts the finding. The `_LOCALE_TZ_RULES` catalog covers `process.env.TZ` reads and (best-effort) an ICU-dependent dependency named in `package.json` (`full-icu`, `moment-timezone`) — the `package.json` check is `applies_to`-gated and contributes a `locale_tz.icu_dependent_dependency` finding when present.
- [ ] **AC-11** Clean case — fixture `runtime-compat-clean/` with a `Dockerfile` that uses `COPY --chown=nonroot:nonroot`, `EXPOSE 3000`, a `USER nonroot`, and a `src/index.ts` with a `SIGTERM` handler, no literal system-path reads, and no `process.env.TZ` → slice has `findings == []`, `confidence == "high"`. `test_runtime_compat_behavior.py::test_clean_repo_no_findings` asserts the empty slice is well-formed (`findings` present as an empty list) and `confidence == "high"`.

**Disposition + degraded path + warning-ID discipline (AC-12 through AC-16)**
- [ ] **AC-12** **WARN disposition — the probe never refuses.** `test_disposition.py::test_no_refusal_outcome_emitted` AST-walks `runtime_compat_probe.py` and asserts the module **does not import `src/codegenie/transforms/outcomes.py`** and does not construct any `Refused*` / `RemediationOutcome` value — every finding is advisory data in the slice, never a refusal. (ADR-0023: the recipe never refuses on `RuntimeCompatSlice` findings; G7–G10 are non-deterministic to fix and a hard fail would block legitimate migrations.)
- [ ] **AC-13** Dockerfile-parse-failure path — fixture with a malformed `Dockerfile` (`COPY` with no destination; backslash-truncated line) → the probe appends `"runtime_compat.dockerfile_parse_failed"` to `warnings` (matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`), skips the `user_uid` pass for that file, still runs the JS/TS passes, and downgrades `confidence` to `"low"`. **No exception escapes `run()`.** `test_runtime_compat_degraded.py::test_dockerfile_parse_failed` asserts the warning ID is regex-valid, that JS/TS findings from valid sibling files are still emitted, and `pytest.raises(BaseException)` confirms nothing escapes.
- [ ] **AC-14** JS/TS-parse-failure path — fixture with a `.ts` file containing a syntax error → the probe appends `"runtime_compat.source_parse_failed"` to `warnings`, skips that file, continues, and downgrades `confidence` to `"low"`. A `GrammarLoadRefused` from the kernel and a tree-sitter `ERROR` node are both folded to the warning. `test_runtime_compat_degraded.py::test_source_parse_failed` covers it.
- [ ] **AC-15** Module-level `_WARNING_IDS: Final[frozenset[str]] = frozenset({"runtime_compat.dockerfile_parse_failed", "runtime_compat.source_parse_failed"})` exists; an import-time `raise AssertionError(...)` (NOT a bare `assert`) checks each ID against `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. Pattern mirrors S7-01's `_WARNING_IDS` block. Additionally, every `rule_id` the probe can emit is collected in a module-level `_RULE_IDS: Final[frozenset[str]]` and validated against the same regex at import time — a freeform `rule_id` is an import-time `AssertionError`.
- [ ] **AC-16** `confidence` ladder (load-bearing despite the advisory disposition — ADR-0023): `"high"` when every Dockerfile and every JS/TS source parsed cleanly; `"low"` when any file failed to parse; `"medium"` is reserved for the case where the JS/TS `locale_tz` `package.json` check could not run because `package.json` was absent or unparseable (partial coverage, no parse failure). `test_confidence_ladder.py::test_confidence_ladder` asserts `high` on the clean fixture, `low` on the parse-failure fixture, and `medium` on a fixture with valid sources but a missing `package.json`. `test_confidence_ladder.py::test_confidence_is_load_bearing_not_disposition` documents-via-assertion that the WARN disposition (findings) and the `confidence` value are independent — a probe with many `user_uid` findings but all-clean parses is still `confidence == "high"`.

**Fence + lint discipline (AC-17 through AC-20)**
- [ ] **AC-17** AST-walk purity fence: `tests/fence/test_runtime_compat_probe_purity.py` walks `runtime_compat_probe.py` and rejects `subprocess.run`, `subprocess.Popen`, `os.system`, `os.popen`, `shell=True`, `requests.*`, `urllib.request.urlopen`, `httpx.*`, any LLM-SDK import (`anthropic`, `openai`, `langchain`, `langgraph`, `transformers`), **and any import of `tree_sitter_bash` or a `language_for("bash")` call** (Amendment A §A.3 departure #3). Three planted-violation parametrized cases prove the walker fires. The fence file uses `raise AssertionError("...")` — bare `assert` is forbidden.
- [ ] **AC-18** `make lint-imports` green; the new file introduces no forbidden import path, and in particular **does not import `src/codegenie/transforms/outcomes.py`** (AC-12 — the probe is advisory-only). The S5-03 import-linter contract already covers `plugins/distroless-migration--*/` against LLM SDKs.
- [ ] **AC-19** `ruff check`, `ruff format --check`, `mypy --strict plugins/distroless-migration--node--npm/probes/runtime_compat_probe.py` all clean. **No `Any` in annotations** — the Phase 7 `test_no_any_in_plugin_surface` discipline applies. The `SourceLocation` dataclass is frozen; `match`/exhaustiveness over `HazardFamily` uses `assert_never` so a future fifth family is a `mypy` error at every consumer.
- [ ] **AC-20** Phase 7 ADR-0009 byte-edit allowlist fence (`tests/fence/test_phase7_no_byte_edits_to_locked_files.py`) green: this story adds files only under `plugins/distroless-migration--node--npm/` and `tests/`; the one envelope-schema `$ref` insertion is at an ADR-0029-allowlisted path (landed by S13-03). No Phase 0–6.5 file is touched.

## Implementation outline

1. **Net-new files only — no edits to Phase 0–6.5.** Create:
   - `plugins/distroless-migration--node--npm/probes/runtime_compat_probe.py` — the probe + private helpers + per-family catalogs.
   - `plugins/distroless-migration--node--npm/schema/runtime_compat.schema.json` — the sub-schema (`additionalProperties: false` at every node), wired into `repo_context.schema.json` with one additive `$ref` following S13-03's precedent.
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_runtime_compat_metadata.py`
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_runtime_compat_behavior.py`
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_runtime_compat_degraded.py`
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_findings_grouped_by_family.py`
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_detection_uses_catalogs.py`
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_disposition.py`
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_confidence_ladder.py`
   - `tests/fence/test_runtime_compat_probe_purity.py`
   - Fixture trees under `tests/fixtures/portfolio/runtime-compat-{uid,fs,pid1,pid1-ok,tz,clean,dockerfile-parse-failed,source-parse-failed,no-package-json}/`.

2. **Module-level data (closed sum type + Open/Closed catalogs) in `runtime_compat_probe.py`:**
   ```python
   from typing import Final, Literal
   from dataclasses import dataclass
   import re

   HazardFamily = Literal["user_uid", "pid1_signals", "filesystem", "locale_tz"]
   _HAZARD_FAMILIES: Final[tuple[HazardFamily, ...]] = (
       "user_uid", "pid1_signals", "filesystem", "locale_tz",
   )

   @dataclass(frozen=True)
   class SourceLocation:
       file: str
       line: int | None = None
       instruction_index: int | None = None

   @dataclass(frozen=True)
   class RuntimeCompatFinding:
       family: HazardFamily
       rule_id: str
       detail: str
       source: SourceLocation

   _SENSITIVE_FS_PREFIXES: Final[tuple[str, ...]] = (
       "/etc/passwd", "/etc/shadow", "/etc/timezone", "/tmp",
   )

   _WARNING_IDS: Final[frozenset[str]] = frozenset({
       "runtime_compat.dockerfile_parse_failed", "runtime_compat.source_parse_failed",
   })
   _RULE_IDS: Final[frozenset[str]] = frozenset({
       "user_uid.copy_without_chown", "user_uid.write_outside_home_tmp",
       "user_uid.privileged_expose", "pid1_signals.no_sigterm_handler",
       "filesystem.literal_system_path_read", "locale_tz.process_env_tz_read",
       "locale_tz.icu_dependent_dependency",
   })
   _ID_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
   for _id in (*_WARNING_IDS, *_RULE_IDS):
       if not _ID_RE.fullmatch(_id):
           raise AssertionError(f"id {_id!r} violates Phase 1 ADR-0007 regex")
   ```
   `_USER_UID_RULES`, `_FILESYSTEM_RULES`, `_LOCALE_TZ_RULES` are `Final` tuples of detector rules; a `Final` `_FAMILY_ANALYSERS: dict[HazardFamily, ...]` maps each family to its analyser so the dispatch iterates rather than branches (AC-6).

3. **`_analyse_dockerfile(path, parsed) -> list[RuntimeCompatFinding]` — the `user_uid` pass:**
   - Iterate `_USER_UID_RULES` over `dockerfile-parse` instructions: a `COPY`/`ADD` without a `--chown=` flag → `user_uid.copy_without_chown`; a `WORKDIR`/`RUN`-write to a path outside `$HOME`/`/tmp` → `user_uid.write_outside_home_tmp`; an `EXPOSE` with a numeric port < 1024 → `user_uid.privileged_expose`. Each finding carries `SourceLocation(file=path, instruction_index=<idx>)`.

4. **`_analyse_js_ts(path, tree, source_bytes) -> list[RuntimeCompatFinding]` — the `filesystem` + `locale_tz` JS/TS pass:**
   - Iterate `_FILESYSTEM_RULES`: a `readFile`/`readFileSync`/`fs.readFile` whose first argument is a string literal starting with any `_SENSITIVE_FS_PREFIXES` entry → `filesystem.literal_system_path_read`.
   - Iterate `_LOCALE_TZ_RULES`: a member access `process.env.TZ` (read) → `locale_tz.process_env_tz_read`.
   - Each finding carries `SourceLocation(file=path, line=<1-based start line>)`.

5. **`_analyse_pid1(entrypoint_files) -> list[RuntimeCompatFinding]` — the `pid1_signals` pass:**
   - Absence-based. For each entrypoint-shaped JS/TS file (heuristic: a file that calls `.listen(`, `http.createServer`, `app.listen`, or is named in `package.json` `main`/`bin`), scan for a `process.on('SIGTERM', ...)` / `process.once('SIGTERM', ...)` call. A long-lived-server file with no such call → one `pid1_signals.no_sigterm_handler` finding per file. The paired-fixture test (AC-9) guards against false positives on a compliant app.

6. **`package.json` ICU check (`locale_tz`):** if `package.json` exists and parses, scan its dependency maps for `full-icu` / `moment-timezone` → `locale_tz.icu_dependent_dependency`. If `package.json` is absent or unparseable, this sub-check is skipped and `confidence` drops to `medium` (AC-16) — no warning ID, because a missing `package.json` is not a *failure*, just partial coverage.

7. **`async def run(self, repo, ctx) -> ProbeOutput`:**
   - `t0 = time.perf_counter()`.
   - Discover Dockerfiles + JS/TS sources via `declared_inputs` globs (sorted, deterministic).
   - Dockerfile pass: parse each via `dockerfile-parse`; on parse failure append `"runtime_compat.dockerfile_parse_failed"`, skip the file, continue.
   - JS/TS pass: pick the grammar by extension, `language_for(...)`, parse; on `GrammarLoadRefused` or an `ERROR` root append `"runtime_compat.source_parse_failed"`, skip, continue.
   - PID-1 pass + `package.json` ICU check.
   - Concatenate all findings; sort by `(family, source.file, source.line or source.instruction_index or 0)`.
   - `confidence`: `low` if any parse failed; else `medium` if the ICU check could not run; else `high`.
   - Return `ProbeOutput(schema_slice={"runtime_compat": {...}}, raw_artifacts=[], confidence=..., duration_ms=..., warnings=warnings, errors=[])`.

8. **Fixtures:** each fixture is a minimal tree — see AC-7…AC-14 for exact contents. The clean fixture and the `pid1-ok` fixture are the load-bearing false-positive guards.

## TDD plan — red / green / refactor

**Red** — write `test_runtime_compat_metadata.py::test_probe_metadata_shape` first. It does `from plugins.distroless_migration_node_npm.probes.runtime_compat_probe import RuntimeCompatProbe` and asserts every metadata field. Run pytest — fails with `ModuleNotFoundError`.

**Green** — minimum code: create the module with the class skeleton (metadata attributes + the closed `HazardFamily` + `_HAZARD_FAMILIES`; `async def run` raising `NotImplementedError`). Re-run pytest — metadata test green; behavior tests still fail.

**Red+** — write `test_runtime_compat_behavior.py::test_user_uid_family` (AC-7). It builds the `runtime-compat-uid` fixture, runs the probe, and asserts both `user_uid` findings. Pytest fails on `NotImplementedError`.

**Green+** — implement `run()` + `_analyse_dockerfile` + the `_USER_UID_RULES` catalog. Then iterate the remaining family ACs (AC-8 `filesystem`, AC-9 `pid1_signals`, AC-10 `locale_tz`, AC-11 clean), adding one analyser + one catalog + one fixture at a time. Each new family turns its red behavior test green by extending `_FAMILY_ANALYSERS` (a new map entry), never by editing a dispatch `if` (proves AC-6).

**Red++** — write `test_detection_uses_catalogs.py::test_no_if_chain_on_family` with a planted-violation stub (`if family == "filesystem": ...`). The AST walker is not written → pytest fails.

**Green++** — implement the AST walker; the planted-violation case goes red-by-construction, the real family dispatch passes.

**Red+++** — write `test_disposition.py::test_no_refusal_outcome_emitted` (AC-12). With the module importing `outcomes.py` as a planted violation, the AST walker fails. Remove the planted import; the real module passes (it never imports `outcomes.py`).

**Red++++** — write `test_runtime_compat_probe_purity.py::test_no_tree_sitter_bash_import` with a planted `import tree_sitter_bash`. The purity walker is not written → fails.

**Green++++** — implement the purity AST walker; three planted-violation parametrize rows (`subprocess.run`, `import tree_sitter_bash`, `requests.get`) all show red-by-construction.

**Refactor** — extract `_analyse_dockerfile`, `_analyse_js_ts`, `_analyse_pid1`, the per-family catalogs, and the `_FAMILY_ANALYSERS` map into module-level pure functions/data; confirm `run()` is the only impure code (functional-core / imperative-shell). AST-assert the family dispatch has no chained `if/elif` on a family literal.

## Files to touch

**New files (no Phase 0–6.5 byte-edits except the one ADR-0029-allowlisted `$ref`):**

| Path | Purpose |
|---|---|
| `plugins/distroless-migration--node--npm/probes/runtime_compat_probe.py` | The probe + private helpers + per-family catalogs |
| `plugins/distroless-migration--node--npm/schema/runtime_compat.schema.json` | Per-probe sub-schema (`additionalProperties: false` at every node) |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_runtime_compat_metadata.py` | AC-1, AC-2, AC-3 |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_runtime_compat_behavior.py` | AC-7…AC-11 |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_runtime_compat_degraded.py` | AC-13, AC-14 |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_findings_grouped_by_family.py` | AC-4, AC-5 |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_detection_uses_catalogs.py` | AC-6 |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_disposition.py` | AC-12 |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_confidence_ladder.py` | AC-16 |
| `tests/fence/test_runtime_compat_probe_purity.py` | AC-17 |
| `tests/fixtures/portfolio/runtime-compat-*/...` | Nine fixture trees (AC-7…AC-14, AC-16) |

**Edited (ADR-0029-allowlisted, S13-03 established the precedent):**

| Path | Edit |
|---|---|
| `src/codegenie/schema/repo_context.schema.json` | One additive `$ref` for `runtime_compat` under `properties.probes` |

**Files NOT touched** (would fail Phase 7 ADR-0009 fence): `src/codegenie/probes/`, `src/codegenie/exec/`, `src/codegenie/grammars/lock.py`, `src/codegenie/transforms/outcomes.py` (the probe is advisory-only — AC-12), `pyproject.toml`, the plugin loader.

## Out of scope

- **Any refusal / `RemediationOutcome`** — `RuntimeCompatProbe` is advisory; ADR-0023 is explicit that G7–G10 are non-deterministic to auto-fix and the recipe never refuses on them. AC-12 enforces the probe does not even import `outcomes.py`. The deterministic-refusal sibling is `RuntimeShellInvocationProbe` (S15-01 / ADR-0021).
- **The `transformations_applied` WARN bundle / PR-description rendering** — S18 (`../ADRs/0027-migration-observability-bundle.md`) owns the WARN surface. This story emits the grouped `findings` the bundle reads.
- **`MigrationConfidence` aggregation** — S17-01 (`aggregate_migration_confidence`) consumes `RuntimeCompatProbe.confidence`. This story only emits a correctly-laddered `confidence`; the rollup is downstream.
- **A fifth hazard family** — the `HazardFamily` sum type is closed at four (G7–G10). Adding one is a Phase-7-ADR amendment + a new `family` variant + schema growth (ADR-0023 Reversibility); AC-5's `test_family_set_is_exactly_four` is the tripwire.
- **Auto-fixing any finding** — adding a `SIGTERM` handler, inserting `--chown`, parameterising a path are all code changes no recipe authors. The probe gathers evidence; the human merger decides.
- **`tree-sitter-bash` / parsing shell** — Amendment A §A.3 departure #3 forbids it. The `user_uid` pass uses `dockerfile-parse`; the JS/TS passes use the existing `javascript`/`typescript` grammars.
- **Plugin loader explicit-import wiring + `api.py` side-effect import** — S8-03 / the plugin's `api.py`.
- **Perf bench** — a `@pytest.mark.bench` body lands in S12-05.

## Notes for the implementer

- **Rule 2 — simplicity first.** ADR-0023 chose *one* probe over four deliberately — the findings are uniformly advisory, so four probes would 4× the registry/schema/`$ref`/fence cost for zero behavioural payoff. Resist the urge to split the four passes into four probes "for cleanliness"; the cohesion is the design. The four *passes* are separate pure functions inside one probe — that is the right granularity.
- **Rule 12 — fail loud, but advisory ≠ silent.** Every finding is WARN — it does not block — but it is *loud*: it lands in the slice, renders in the PR description (S18), and the human sees "literal `fs.readFile('/etc/passwd')` at `src/auth.ts:42`". WARN is not "swallow"; it is "surface and hand the judgment to the merger." A parse failure, by contrast, is a real warning ID + a `confidence` downgrade — `confidence` is load-bearing even though the findings are advisory (ADR-0023 Tradeoffs row 4; AC-16's `test_confidence_is_load_bearing_not_disposition` pins the distinction).
- **Rule 9 — tests verify intent.** The behavior tests assert business semantics: "a `COPY` without `--chown` is a `user_uid` hazard because the distroless target runs as uid 65532 and the copied files would be root-owned" — not "the function returns a list". AC-9's **paired fixture** (`runtime-compat-pid1` vs `runtime-compat-pid1-ok`) is the load-bearing intent test for the absence-based PID-1 detection — without the `-ok` fixture, a detector that *always* fires would pass AC-9's positive case. Absence-detection is the easiest family to get subtly wrong; the paired fixture is non-negotiable.
- **Closed `family` sum type (production ADR-0033).** `HazardFamily` is exactly four members; consumers `match` on it with `assert_never` for exhaustiveness. `AC-5`'s `test_family_set_is_exactly_four` is the tripwire that forces a fifth family to be an ADR amendment, not a casual addition — mirror the `_BASE_IMAGE_KIND_RULES` discipline from S7-01.
- **Open/Closed per-family catalogs.** `_USER_UID_RULES`, `_FILESYSTEM_RULES`, `_LOCALE_TZ_RULES` and the `_FAMILY_ANALYSERS` map are the open/closed seams — adding a new `user_uid` rule (e.g. a `VOLUME` outside `/tmp`) is one tuple row, not an edit to `_analyse_dockerfile`'s control flow. AC-6's AST fence enforces it.
- **Two parsers, one probe.** The `user_uid` pass uses `dockerfile-parse`; the `filesystem`/`locale_tz`/`pid1_signals` passes use the tree-sitter `javascript`/`typescript` grammars via `grammars.lock.language_for`. Both parsers already exist in-tree — the probe is a thin orchestrator over them (ADR-0023 Tradeoffs row 1). Mirror `node_reflection.py` for the JS/TS half and `layer_c/dockerfile.py` for the Dockerfile half; do not fork either.
- **A missing `package.json` is `medium`, not a warning.** The ICU sub-check needs `package.json`; if it is absent the check is skipped and `confidence` is `medium` (partial coverage). This is *not* a parse failure — no warning ID, no `low`. Keep the `medium` arm distinct from the `low` arm; AC-16 tests all three.
- **No async I/O.** `async def run` is required by the ABC, but the body is pure file reads + parsing. No `await`. `mypy --strict` permits it; `asyncio_mode = "auto"` handles test invocation.
- **Effort budget.** Probe body ≤ 200 LOC (it is the largest of the three Step-15 probes — four passes); tests ≈ 340 LOC; fence ≈ 60 LOC. If the body grows past 230 LOC, extract the four passes into `_runtime_compat_passes.py` (precedent: `src/codegenie/probes/layer_c/_dockerfile_parse.py`).
- **Token-budget guard (Rule 6).** This story is at the upper edge of single-session — four families, two parsers. If it approaches the 4k-token budget mid-implementation, checkpoint after the `user_uid` + `filesystem` families are GREEN and start a fresh session for `pid1_signals` + `locale_tz`. Surfacing the breach beats overrunning.
