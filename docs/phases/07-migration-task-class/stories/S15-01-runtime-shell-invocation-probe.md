# Story S15-01 — `RuntimeShellInvocationProbe` + tree-sitter JS/TS shell-out detection + path-derived criticality

**Step:** Step 15 — Runtime-compatibility gather (G4, G6, G7–G10, G12)
**Status:** Ready
**Effort:** M
**Depends on:** S13-03 (`S13-03-amendment-a-schemas-and-fence.md` — the Amendment-A probe sub-schema directory `plugins/distroless-migration--node--npm/schema/` exists, the envelope `$ref`-wiring precedent is established, and `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` is already amended per ADR-0029 so this story's new files land inside an already-allowlisted tree)

**ADRs honored:** Phase 7 [ADR-0021](../ADRs/0021-runtime-shell-invocation-probe.md) (`RuntimeShellInvocationProbe` — static tree-sitter JS/TS detection; `src/**` hits block, `tests/**` hits are advisory); Phase 7 [ADR-0005](../ADRs/0005-probes-live-under-plugin-not-core-tree.md) (probes live under the plugin, NOT `src/codegenie/probes/`); Phase 7 [ADR-0009](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) + [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) (this story is **net-new-files-only** under the already-allowlisted plugin tree); Phase 7 [ADR-0025](../ADRs/0025-migration-refusal-taxonomy.md) (a `blocking` hit feeds the closed `RefusedRuntimeShellOutInProductionCode` refusal variant — defined in S16-01, consumed downstream, not this story); Phase 0 ADR-0007 / [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md) (frozen Probe ABC — two-arg `run(self, repo, ctx)`); Phase 1 ADR-0004 (per-probe sub-schema `additionalProperties: false`); Phase 1 ADR-0007 (warning-ID regex); 02-ADR-0011 (tree-sitter grammars via the `grammars.lock` kernel — the existing `javascript`/`typescript` grammars only, NO `tree-sitter-bash`).

## Context

`RuntimeShellInvocationProbe` is the **light, static, Layer C** probe that closes Amendment A gaps **G4** and **G12** (`../final-design.md §Amendment A §A.2`). A Chainguard distroless runtime image has **no `/bin/sh` and no shell utilities**. Application code that shells out at runtime — `child_process.exec`/`execSync`/`spawn`, `Bun.spawn`, `Deno.run` — builds clean, passes the `DockerfilePolicyGate`, merges, and then fails with `ENOENT` the first time that code path executes in production. The design-of-record's `ShellInvocationTraceProbe` (S7-02, [ADR-0002](../ADRs/0002-shell-invocation-trace-probe-runs-in-microvm.md)) observes shell invocations *during the image build* — it says nothing about what the app does *at runtime*. **G4 is that gap.**

**G12 is the inverse failure.** Test fixtures and test harnesses legitimately shell out (`execSync('git ...')` in a setup script, an integration test spawning a helper binary). A probe that treated every shell-out as blocking would refuse a perfectly valid production migration because of code that never runs in the shipped image. The probe must distinguish *production* shell-out from *test-infra* shell-out. ADR-0021 resolves both gaps to one plugin-internal probe that walks JS/TS sources and tags each hit with a **path-derived `criticality`**: `src/**` is `blocking`; `tests/**` and `*.test.*` / `*.spec.*` are `advisory`.

The probe walks JS/TS sources via the **existing** `grammars.lock.language_for("javascript" | "typescript")` grammars — **no `tree-sitter-bash`, no new grammar wheel** (Amendment A §A.3 departure #3 is explicit: G4 needs the JS/TS call graph, not bash parsing). A module-level `Final` query catalog enumerates the shell-out forms; detection is catalog-driven, never an `if/elif` chain on call shape.

Each hit emits a typed record carrying the file path, `argv[0]` (the literal first argument where statically resolvable, else the sentinel `dynamic`), and the `criticality`. Because distroless has no `/bin/sh`, any `blocking` hit whose `argv[0]` is outside the safe set `{node, npm, yarn}` — and any `blocking` hit with a `dynamic` `argv[0]` — feeds the typed refusal `RefusedRuntimeShellOutInProductionCode` ([ADR-0025](../ADRs/0025-migration-refusal-taxonomy.md)). **That refusal variant is defined in S16-01 and consumed by the recipe in S16-02 — this story ships the probe + slice only.** The `argv[0]` allowlist `{node, npm, yarn}` lets a self-invoking process (`spawn('node', ...)`) pass — distroless ships `node` — without a blanket refusal.

The probe lives under `plugins/distroless-migration--node--npm/probes/runtime_shell_invocation_probe.py` — **NOT** under `src/codegenie/probes/`. [ADR-0005](../ADRs/0005-probes-live-under-plugin-not-core-tree.md) is explicit; the fence test from S5-02 (`tests/fence/test_provenance_primitive_in_plugin_directory.py`) AST-asserts placement and would fail if the file lived in core.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — Amendment A §18 (RuntimeShellInvocationProbe)` — names the slice fields (`hits` with `path`, `argv0`, `criticality`), the static-tree-sitter approach, and the `{node, npm, yarn}` allowlist.
  - `../phase-arch-design.md §Component design — Amendment A` preamble — every Amendment-A probe obeys the frozen Probe ABC.
  - `../phase-arch-design.md §Amendment A gaps — G1–G17, M1–M3` — G4 (runtime shell-out) and G12 (`tests/**` advisory vs `src/**` blocking) are the two gaps this story closes.
- **Phase ADRs:**
  - `../ADRs/0021-runtime-shell-invocation-probe.md` — **the governing ADR.** Option B (static tree-sitter AST walk) was adopted; Option A (dynamic trace) and Option C (regex grep) were rejected. The query-catalog + `criticality` sum-type + `argv[0]`-sentinel discipline all come from here.
  - `../ADRs/0005-probes-live-under-plugin-not-core-tree.md` — `plugins/distroless-migration--node--npm/probes/runtime_shell_invocation_probe.py` is the canonical location.
  - `../ADRs/0009-phase-7-byte-edit-allowlist-fence.md` + `../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md` — ADR-0029 already enumerates `runtime_shell_invocation_probe.py` and its sub-schema in the allowlist; this story consumes those rows (landed by S13-03), it does not add them.
  - `../ADRs/0025-migration-refusal-taxonomy.md` — `RefusedRuntimeShellOutInProductionCode` is the closed refusal variant a `blocking` hit feeds. **Defined in S16-01; this story does not touch `outcomes.py`.**
- **Existing code / precedents:**
  - `src/codegenie/grammars/lock.py` — `language_for("javascript" | "typescript")` is the **only** way to obtain a tree-sitter `Language`. The kernel raises `GrammarLoadRefused` on every failure path (import failure, unknown name, grammar-load failure) — catch that single typed exception. `SupportedLanguage` is `Literal["typescript", "tsx", "javascript"]`; `tsx` is parsed by the `tsx` grammar but `.ts`/`.js` use `typescript`/`javascript` respectively.
  - `src/codegenie/probes/layer_b/node_reflection.py` — the **canonical precedent** for a tree-sitter JS/TS probe: it builds a `Parser`, walks the tree, and matches against a module-level `_REFLECTION_QUERIES: Final[...]` catalog. Mirror its catalog-iteration shape — `RuntimeShellInvocationProbe` is structurally the same probe with a different query set.
  - `src/codegenie/probes/layer_b/tree_sitter_import_graph.py` — second precedent for tree-sitter tree-walking + node-text extraction.
  - `src/codegenie/probes/base.py` — the frozen Probe ABC. Two-arg `run(self, repo, ctx)`; a one-arg `run` is a `TypeError` at dispatch.
  - `src/codegenie/probes/registry.py` — `@register_probe` (defaults — `heaviness="light"`, `runs_last=False`) is what this probe ships with.
  - `src/codegenie/types/identifiers.py` — newtype-identifier discipline. This story introduces `Argv0` (the resolved first-argument value) as a `NewType("Argv0", str)`; the `dynamic` sentinel is `Argv0("dynamic")` produced by a smart constructor, never a bare string.
- **Story-pipeline neighbors:**
  - `S13-03-amendment-a-schemas-and-fence.md` — **must land first.** It established the `plugins/distroless-migration--node--npm/schema/` directory, the envelope `$ref`-wiring pattern, and the ADR-0029 allowlist amendment. This story adds `schema/runtime_shell_invocation.schema.json` into that already-existing directory and adds one `$ref` following S13-03's precedent.
  - `S7-01-base-image-probe.md` — the structural template for any Amendment-era Phase 7 plugin probe (metadata-AC shape, purity fence, fixture layout). Mirror it.
  - `S16-01-refusal-taxonomy-outcomes.md` — defines `RefusedRuntimeShellOutInProductionCode`. Downstream of this story.
  - `S16-02-recipe-contract-amendment.md` — the recipe consumes `RuntimeShellInvocationSlice` and emits the refusal. Downstream consumer.
  - `S15-03-runtime-compat-probe.md` — sibling Step-15 probe; also uses the JS/TS grammars. Land independently.

## Goal

Land `RuntimeShellInvocationProbe` under `plugins/distroless-migration--node--npm/probes/runtime_shell_invocation_probe.py` as a Probe-ABC-conformant, `@register_probe`-decorated, Layer-C, `task_specific`, `applies_to_tasks=["distroless-migration"]`, `applies_to_languages=["javascript", "typescript"]` probe that walks every JS/TS source under the repo via `grammars.lock.language_for(...)`, detects every `child_process.exec`/`execSync`/`spawn`, `Bun.spawn`, and `Deno.run` call against a module-level `Final` query catalog, resolves each call's `argv[0]` to a literal or the `dynamic` sentinel, derives `criticality` from the file path (`src/**` → `blocking`, `tests/**`/`*.test.*`/`*.spec.*` → `advisory`), and emits the deterministic `RuntimeShellInvocationSlice` the migration recipe + `MigrationConfidence` aggregator consume. No subprocess, no network, no `tree-sitter-bash`.

## Acceptance criteria

**Probe ABC conformance (AC-1 through AC-3)**
- [ ] **AC-1** `plugins/distroless-migration--node--npm/probes/runtime_shell_invocation_probe.py` exists. `RuntimeShellInvocationProbe(Probe)` is defined with class attributes `name = "runtime_shell_invocation"`, `layer = "C"`, `tier = "task_specific"`, `applies_to_tasks = ["distroless-migration"]`, `applies_to_languages = ["javascript", "typescript"]`, `requires = []`, `declared_inputs = ["**/*.js", "**/*.mjs", "**/*.cjs", "**/*.ts", "**/*.mts", "**/*.cts", "**/*.tsx"]`, `cache_strategy = "content"`, `timeout_seconds = 60`. Verified by `tests/unit/plugins/distroless_migration_node_npm/probes/test_runtime_shell_invocation_metadata.py::test_probe_metadata_shape` (reads `RuntimeShellInvocationProbe.__dict__` and asserts each field byte-equal to the declared value).
- [ ] **AC-2** `RuntimeShellInvocationProbe` is registered via `@register_probe` (defaults — `heaviness="light"`, `runs_last=False`). The decoration is at class scope. Verified by `test_runtime_shell_invocation_metadata.py::test_registry_entry_present`, which constructs a fresh `Registry`, imports the module, and asserts `entry.probe_cls is RuntimeShellInvocationProbe AND entry.heaviness == "light" AND entry.runs_last is False`.
- [ ] **AC-3** `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` is the only abstract-method override; its signature matches the frozen Phase 0 ABC byte-for-byte. `test_runtime_shell_invocation_metadata.py::test_run_signature_matches_abc` AST-asserts the parameter list is exactly `["self", "repo", "ctx"]` — a one-arg `run` fails this AC.

**Slice shape (AC-4 through AC-6)**
- [ ] **AC-4** Slice shape (returned in `ProbeOutput.schema_slice["runtime_shell_invocation"]`):
  ```python
  {
      "hits": [
          {
              "path": "<repo-relative-posix-path>",
              "line": <int>,                       # 1-based start line of the call
              "call_form": "child_process.exec|child_process.execSync|child_process.spawn|child_process.execFile|bun.spawn|deno.run",
              "argv0": "<literal-string | 'dynamic'>",  # Argv0 newtype; 'dynamic' sentinel iff not statically resolvable
              "criticality": "blocking|advisory",
          }, ...
      ],
      "confidence": "high|medium|low",
  }
  ```
  `hits` is sorted deterministically by `(path, line)`. Verified against `tests/golden/probes/runtime_shell_invocation/*.json` (S13-03's `$ref`-wiring precedent governs the schema; the **field set + key order + sort order** is pinned by this story's AC). `test_runtime_shell_invocation_behavior.py::test_hits_sorted_by_path_then_line` constructs a fixture whose calls appear out of source order across two files and asserts the emitted `hits` list is `(path, line)`-sorted.
- [ ] **AC-5** `_SHELL_OUT_QUERIES: Final[tuple[ShellOutQuery, ...]]` is a module-level open/closed query catalog. Each `ShellOutQuery` is a frozen dataclass with fields `(call_form: CallForm, query_source: str)` where `query_source` is a tree-sitter S-expression query string and `CallForm` is a closed `StrEnum`/`Literal`. The catalog is iterated in `_collect_hits(tree, source_bytes) -> list[_RawHit]`, **never branched on with a chained `if/elif` on call shape**. Verified by `test_detection_uses_query_catalog.py::test_no_if_chain_on_call_form` — it AST-walks `_collect_hits` and asserts no `if/elif` arm performs string equality against a literal call name (`"exec"`, `"spawn"`, …); detection must come from catalog iteration. The catalog covers at minimum: `child_process.exec`, `child_process.execSync`, `child_process.spawn`, `child_process.execFile`, `Bun.spawn`, `Deno.run` — including the `require('child_process').exec(...)` and destructured-import (`const {exec} = require('child_process')`) call forms.
- [ ] **AC-6** `argv0` is always an `Argv0` newtype, never a bare `str`, and `criticality` is always a closed `Criticality` sum type (`Literal["blocking", "advisory"]` or `StrEnum`), never a free string. `test_typed_fields.py::test_argv0_and_criticality_are_typed` reads the slice from the `dynamic`-argv fixture and asserts (a) the `dynamic` value is exactly the sentinel produced by the `Argv0` smart constructor, and (b) every `criticality` value is a member of the `Criticality` enum/Literal set. A freeform `criticality` string fails this test.

**Behavior — detection + classification (AC-7 through AC-12)**
- [ ] **AC-7** `src/**` blocking — fixture `tests/fixtures/portfolio/runtime-shell-src-exec/src/jobs/runner.ts` containing `import { exec } from "child_process"; exec("curl -fsSL https://example.com | sh");` → slice has exactly one hit, `path == "src/jobs/runner.ts"`, `call_form == "child_process.exec"`, `argv0 == "curl"`, `criticality == "blocking"`. This is the case ADR-0021 names — a production shell-out distroless cannot satisfy.
- [ ] **AC-8** `tests/**` advisory — fixture `tests/fixtures/portfolio/runtime-shell-tests-exec/tests/setup.js` containing `const { execSync } = require("child_process"); execSync("git rev-parse HEAD");` → slice has exactly one hit, `path == "tests/setup.js"`, `call_form == "child_process.execSync"`, `argv0 == "git"`, `criticality == "advisory"`. The G12 case: test-infra shell-out is detected but never blocks. `test_runtime_shell_invocation_behavior.py::test_tests_path_is_advisory_not_blocking` asserts `criticality == "advisory"` AND that the same `execSync('git ...')` call placed under `src/` would be `blocking` (a paired-fixture assertion proving the classification is path-derived, not call-derived).
- [ ] **AC-9** `*.test.*` / `*.spec.*` advisory — a `child_process.spawn(...)` inside `src/api/handler.test.ts` is classified `advisory` even though it lives under `src/`. `test_runtime_shell_invocation_behavior.py::test_test_suffix_overrides_src_prefix` asserts the filename-suffix rule (`*.test.*`, `*.spec.*`) takes precedence — a file is `advisory` if it is *either* under `tests/**` *or* matches the test-suffix glob.
- [ ] **AC-10** `dynamic` argv[0] — fixture containing `exec(buildCommand(userInput))` (the first argument is a call expression / template literal with interpolation, not a string literal) under `src/` → the hit's `argv0` is exactly the `dynamic` sentinel and `criticality == "blocking"`. ADR-0021: an unresolvable invocation target cannot be cleared statically. `test_runtime_shell_invocation_behavior.py::test_dynamic_argv0_when_not_literal` covers both the call-expression form and the interpolated-template-literal form.
- [ ] **AC-11** `argv[0]` of `node` not flagged blocking-in-the-refusal-sense — fixture `src/worker.js` containing `spawn("node", ["./child.js"])` → the hit is still emitted (`call_form == "child_process.spawn"`, `argv0 == "node"`, `criticality == "blocking"` because it is under `src/`), **but** a module-level helper `_argv0_in_safe_set(argv0) -> bool` returns `True` for `node` (and for `npm`, `yarn`). `test_runtime_shell_invocation_behavior.py::test_node_argv0_in_safe_set` asserts `_argv0_in_safe_set(Argv0("node")) is True` and `_argv0_in_safe_set(Argv0("curl")) is False`. **Clarification for the implementer:** `criticality` is *path-derived only* — a `src/**` hit is always `criticality="blocking"`. The `{node, npm, yarn}` allowlist is a *separate* concern consumed downstream by S16-02 to decide whether a `blocking` hit actually triggers `RefusedRuntimeShellOutInProductionCode`. This story exposes `_argv0_in_safe_set` and pins `_SAFE_ARGV0` so S16-02 can import it; it does **not** itself produce a refusal.
- [ ] **AC-12** Empty case — fixture `tests/fixtures/portfolio/runtime-shell-clean/src/index.ts` with no shell-out calls (only `fetch(...)` and plain function calls) → slice has `hits == []`, `confidence == "high"`. `test_runtime_shell_invocation_behavior.py::test_empty_when_no_shell_out` asserts the empty slice is still well-formed (`hits` present as an empty list, not absent) and that `confidence == "high"` — a clean repo is high-confidence, not low.

**Degraded path + warning-ID discipline (AC-13 through AC-15)**
- [ ] **AC-13** Parse-failure path — fixture with a JS file containing a deliberate syntax error (`function () { exec(`) → the probe appends `"runtime_shell_invocation.source_parse_failed"` to `warnings` (matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` per Phase 1 ADR-0007), skips that file, continues to the rest, and downgrades `confidence` to `"low"`. **No exception escapes `run()`** — a `GrammarLoadRefused` from the kernel and a tree-sitter `ERROR` node are both folded to the warning. `test_runtime_shell_invocation_degraded.py::test_parse_failure_warns_and_continues` asserts (a) the warning ID is present and regex-valid, (b) a *valid* sibling file in the same fixture still contributes its hits, and (c) `pytest.raises(BaseException)` confirms nothing escapes.
- [ ] **AC-14** Module-level `_WARNING_IDS: Final[frozenset[str]] = frozenset({"runtime_shell_invocation.source_parse_failed"})` exists; an import-time `raise AssertionError(...)` (NOT a bare `assert` — the `forbidden-patterns` pre-commit hook rejects bare `assert`) checks each ID against `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. Pattern mirrors S7-01's `_WARNING_IDS` block.
- [ ] **AC-15** `confidence` ladder: `"high"` when every discovered source file parsed cleanly; `"low"` when any file failed to parse. There is no `"medium"` arm for this probe (it has no resolver-style optional capability) — `test_confidence_ladder.py::test_confidence_high_iff_all_parsed` asserts `high` on the clean fixture and `low` on the parse-failure fixture, and that no fixture produces `medium`.

**Fence + lint discipline (AC-16 through AC-19)**
- [ ] **AC-16** AST-walk purity fence: `tests/fence/test_runtime_shell_invocation_probe_purity.py` walks `runtime_shell_invocation_probe.py` and rejects `subprocess.run`, `subprocess.Popen`, `os.system`, `os.popen`, `shell=True`, `requests.*`, `urllib.request.urlopen`, `httpx.*`, any LLM-SDK import (`anthropic`, `openai`, `langchain`, `langgraph`, `transformers`), **and any import of `tree_sitter_bash` or a `language_for("bash")` call** (Amendment A §A.3 departure #3 — `tree-sitter-bash` is deliberately not added). Three planted-violation parametrized cases (red-by-construction inside the test) prove the walker fires. The fence file uses `raise AssertionError("...")` — bare `assert` is forbidden.
- [ ] **AC-17** `make lint-imports` green; the new file introduces no forbidden import path. The S5-03 import-linter contract already covers `plugins/distroless-migration--*/` against LLM SDKs.
- [ ] **AC-18** `ruff check`, `ruff format --check`, `mypy --strict plugins/distroless-migration--node--npm/probes/runtime_shell_invocation_probe.py` all clean. **No `Any` in annotations** — the Phase 7 `test_no_any_in_plugin_surface` discipline applies to the migration plugin tree.
- [ ] **AC-19** Phase 7 ADR-0009 byte-edit allowlist fence (`tests/fence/test_phase7_no_byte_edits_to_locked_files.py`) green: this story adds files only under `plugins/distroless-migration--node--npm/` and `tests/`; the one envelope-schema `$ref` insertion is at a path ADR-0029 already allowlisted (landed by S13-03). No Phase 0–6.5 file is touched.

## Implementation outline

1. **Net-new files only — no edits to Phase 0–6.5.** Create:
   - `plugins/distroless-migration--node--npm/probes/runtime_shell_invocation_probe.py` — the probe + private helpers.
   - `plugins/distroless-migration--node--npm/schema/runtime_shell_invocation.schema.json` — the sub-schema (`additionalProperties: false` at every node), wired into `repo_context.schema.json` with one additive `$ref` following S13-03's precedent.
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_runtime_shell_invocation_metadata.py`
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_runtime_shell_invocation_behavior.py`
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_runtime_shell_invocation_degraded.py`
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_detection_uses_query_catalog.py`
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_typed_fields.py`
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_confidence_ladder.py`
   - `tests/fence/test_runtime_shell_invocation_probe_purity.py`
   - Fixture source trees under `tests/fixtures/portfolio/{runtime-shell-src-exec,runtime-shell-tests-exec,runtime-shell-test-suffix,runtime-shell-dynamic,runtime-shell-node-spawn,runtime-shell-clean,runtime-shell-parse-failed}/`.

2. **Module-level data (Open/Closed query catalog) in `runtime_shell_invocation_probe.py`:**
   ```python
   from typing import Final, Literal
   from dataclasses import dataclass
   from enum import StrEnum
   import re

   CallForm = Literal[
       "child_process.exec", "child_process.execSync", "child_process.spawn",
       "child_process.execFile", "bun.spawn", "deno.run",
   ]
   Criticality = Literal["blocking", "advisory"]

   @dataclass(frozen=True)
   class ShellOutQuery:
       call_form: CallForm
       query_source: str          # tree-sitter S-expression

   _SHELL_OUT_QUERIES: Final[tuple[ShellOutQuery, ...]] = (
       ShellOutQuery("child_process.exec", _Q_EXEC),
       ShellOutQuery("child_process.execSync", _Q_EXECSYNC),
       ShellOutQuery("child_process.spawn", _Q_SPAWN),
       ShellOutQuery("child_process.execFile", _Q_EXECFILE),
       ShellOutQuery("bun.spawn", _Q_BUN_SPAWN),
       ShellOutQuery("deno.run", _Q_DENO_RUN),
   )

   _SAFE_ARGV0: Final[frozenset[str]] = frozenset({"node", "npm", "yarn"})
   _DYNAMIC_ARGV0: Final[str] = "dynamic"   # the Argv0 sentinel value

   _WARNING_IDS: Final[frozenset[str]] = frozenset({"runtime_shell_invocation.source_parse_failed"})
   _WARNING_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
   for _id in _WARNING_IDS:
       if not _WARNING_ID_RE.fullmatch(_id):
           raise AssertionError(f"warning id {_id!r} violates Phase 1 ADR-0007 regex")
   ```
   `Argv0` is `NewType("Argv0", str)`; a smart constructor `_argv0(value: str | None) -> Argv0` maps `None`/non-literal to `Argv0(_DYNAMIC_ARGV0)`.

3. **`_criticality_for(path: str) -> Criticality`:**
   - Pure path classifier. `advisory` if the posix path is under a `tests/` segment **or** the filename matches `*.test.*` / `*.spec.*`; otherwise `blocking`. The test-suffix rule wins over the `src/` prefix (AC-9). Implemented as iteration over a small `Final` tuple of advisory predicates — no chained `if`.

4. **`_resolve_argv0(call_node, source_bytes) -> Argv0`:**
   - Extract the first argument node of the call. If it is a `string` literal → `Argv0(<text without quotes, first whitespace-split token>)` (a literal `"curl -fsSL ..."` resolves to `curl`). For `spawn`/`execFile` the first arg is the command itself; for `exec`/`execSync` it is a full command string — split on whitespace and take token 0.
   - Anything else (call expression, template literal with `${...}` interpolation, identifier, member expression) → `Argv0(_DYNAMIC_ARGV0)`.

5. **`_collect_hits(tree, source_bytes) -> list[_RawHit]`:**
   - Iterate `_SHELL_OUT_QUERIES`; run each `query_source` against the tree via `tree_sitter.Query`. For each capture, build a `_RawHit(call_form, line, argv0)` from the matched call node. Catalog-driven — no `if/elif` on call shape (AC-5).

6. **`async def run(self, repo, ctx) -> ProbeOutput`:**
   - `t0 = time.perf_counter()`.
   - Discover JS/TS sources via the `declared_inputs` globs (sorted, deterministic).
   - For each file: pick the grammar — `.tsx` → `tsx`, `.ts`/`.mts`/`.cts` → `typescript`, `.js`/`.mjs`/`.cjs` → `javascript` — call `grammars.lock.language_for(...)`, build a `Parser`, parse the bytes. If `language_for` raises `GrammarLoadRefused`, or the parsed tree's root has an `ERROR` node, append `"runtime_shell_invocation.source_parse_failed"` once for that file and continue.
   - `_collect_hits` → for each raw hit build the final record with `criticality = _criticality_for(path)`.
   - Sort `hits` by `(path, line)`.
   - `confidence`: `"high"` if no file failed to parse, else `"low"`.
   - Return `ProbeOutput(schema_slice={"runtime_shell_invocation": {...}}, raw_artifacts=[], confidence=..., duration_ms=..., warnings=warnings, errors=[])`.

7. **Fixtures:** each fixture is a minimal source tree (one or two files) — see AC-7…AC-13 for the exact contents. The clean fixture must contain *non-shell* calls (`fetch`, plain functions) so it proves the catalog does not over-match.

## TDD plan — red / green / refactor

**Red** — write `test_runtime_shell_invocation_metadata.py::test_probe_metadata_shape` first. It does `from plugins.distroless_migration_node_npm.probes.runtime_shell_invocation_probe import RuntimeShellInvocationProbe` and asserts every metadata field. Run pytest — it fails with `ModuleNotFoundError`.

**Green** — minimum code for the metadata test: create the module with the class skeleton (metadata attributes only; `async def run` raising `NotImplementedError`). Re-run pytest — metadata test green; behavior tests still fail.

**Red+** — write `test_runtime_shell_invocation_behavior.py::test_src_exec_is_blocking` (AC-7). It builds the `runtime-shell-src-exec` fixture, runs the probe, and asserts the single hit's `path`/`call_form`/`argv0`/`criticality`. Pytest fails on `NotImplementedError`.

**Green+** — implement `run()`, `_collect_hits`, `_resolve_argv0`, `_criticality_for` for the `child_process.exec` query. Iterate over the remaining behavior ACs (AC-8…AC-12), adding one `ShellOutQuery` row at a time and one fixture at a time. Each new row turns its red behavior test green without editing `_collect_hits`'s control flow (proves AC-5's catalog design).

**Red++** — write `test_detection_uses_query_catalog.py::test_no_if_chain_on_call_form` with a planted-violation case (a stub `_collect_hits` containing `if call == "exec"`). The AST walker is not yet written → pytest fails.

**Green++** — implement the AST walker; the planted-violation case goes red-by-construction, the real `_collect_hits` passes.

**Red+++** — write `test_runtime_shell_invocation_probe_purity.py::test_no_tree_sitter_bash_import` with a planted `import tree_sitter_bash`. The purity walker is not written → fails.

**Green+++** — implement the purity AST walker; three planted-violation parametrize rows (`subprocess.run`, `import tree_sitter_bash`, `urllib.request.urlopen`) all show red-by-construction.

**Refactor** — extract `_resolve_argv0`, `_criticality_for`, the query catalog, and the source-discovery helper into module-level pure functions; confirm `run()` is the only impure code (the functional-core / imperative-shell discipline). AST-assert `_collect_hits` and `_criticality_for` have no chained `if/elif` on call name / path literal.

## Files to touch

**New files (no Phase 0–6.5 byte-edits except the one ADR-0029-allowlisted `$ref`):**

| Path | Purpose |
|---|---|
| `plugins/distroless-migration--node--npm/probes/runtime_shell_invocation_probe.py` | The probe + private helpers + module-level query catalog |
| `plugins/distroless-migration--node--npm/schema/runtime_shell_invocation.schema.json` | Per-probe sub-schema (`additionalProperties: false` at every node) |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_runtime_shell_invocation_metadata.py` | AC-1, AC-2, AC-3 |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_runtime_shell_invocation_behavior.py` | AC-7…AC-12 |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_runtime_shell_invocation_degraded.py` | AC-13 |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_detection_uses_query_catalog.py` | AC-5 |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_typed_fields.py` | AC-4, AC-6 |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_confidence_ladder.py` | AC-15 |
| `tests/fence/test_runtime_shell_invocation_probe_purity.py` | AC-16 |
| `tests/fixtures/portfolio/runtime-shell-*/...` | Seven fixture source trees (AC-7…AC-13) |

**Edited (ADR-0029-allowlisted, S13-03 established the precedent):**

| Path | Edit |
|---|---|
| `src/codegenie/schema/repo_context.schema.json` | One additive `$ref` for `runtime_shell_invocation` under `properties.probes` |

**Files NOT touched** (would fail Phase 7 ADR-0009 fence): `src/codegenie/probes/`, `src/codegenie/exec/`, `src/codegenie/grammars/lock.py`, `src/codegenie/transforms/outcomes.py`, `pyproject.toml`, the plugin loader.

## Out of scope

- **The `RefusedRuntimeShellOutInProductionCode` refusal variant** — defined in S16-01 (`src/codegenie/transforms/outcomes.py` additive variants). This story ships the slice + the `_argv0_in_safe_set` helper + `_SAFE_ARGV0`; S16-02's recipe consumes them to *decide* the refusal. This story never imports `outcomes.py` and never produces a `RemediationOutcome`.
- **The build-time `ShellInvocationTraceProbe`** — S7-02 owns the heavy, sandboxed, build-trace probe. This probe is the *static, runtime-code* complement; the two are orthogonal (ADR-0021 Context names the distinction explicitly).
- **`tree-sitter-bash` / parsing the shelled-out command** — Amendment A §A.3 departure #3 forbids it. This probe records *that* code shells out and *what `argv[0]` is*; it never parses the shell command itself.
- **Plugin loader explicit-import wiring + `api.py` side-effect import** — S8-03 owns `src/codegenie/plugins/loader.py`; the `from .probes import runtime_shell_invocation_probe  # noqa: F401` side-effect import lives in the plugin's `api.py` (ADR-0029 allowlisted, owned by the loader-wiring story).
- **`MigrationConfidence` aggregation** — S17-01 (`aggregate_migration_confidence`) consumes `RuntimeShellInvocationSlice.confidence`; it is downstream.
- **Perf bench** — a `@pytest.mark.bench` body lands in S12-05; this story does not write the perf test.

## Notes for the implementer

- **Rule 11 — match the existing convention.** `src/codegenie/probes/layer_b/node_reflection.py` is the canonical tree-sitter JS/TS probe. It builds a `Parser`, walks the tree, and matches a module-level `Final` query catalog. `RuntimeShellInvocationProbe` is structurally the *same probe* with a different query set — mirror its parser-construction, its `language_for` call, and its catalog-iteration shape. Do not fork a new tree-walking style.
- **Rule 12 — fail loud.** A `GrammarLoadRefused` from the kernel and a tree-sitter `ERROR` node are *typed warnings*, not swallowed errors — the file is skipped, `confidence` drops to `low`, and the warning ID is emitted. A `blocking` hit the recipe later cannot clear becomes a *typed refusal* (S16-02), never a silent pass. Catch the **specific** `GrammarLoadRefused` exception class — a bare `except Exception` is forbidden by `mypy --strict` config and breaks Rule 12.
- **Rule 9 — tests verify intent.** The behavior tests assert business semantics: "an `exec('curl ...')` under `src/` is `blocking` because distroless has no shell to run `curl`" — not "the function returns a dict with a `hits` key". The paired-fixture test (AC-8: same `execSync('git ...')` call, once under `tests/`, once under `src/`) is the load-bearing intent test — it proves `criticality` is path-derived, the exact property G12 needs.
- **Criticality is path-derived, full stop.** A `src/**` hit is *always* `criticality="blocking"`, regardless of `argv[0]`. The `{node, npm, yarn}` allowlist does *not* change `criticality` — it is a separate signal (`_argv0_in_safe_set`) that S16-02 reads to decide whether a `blocking` hit actually refuses. Keep these two concerns separate in the code; conflating them (e.g. setting `criticality="advisory"` for `node`) would corrupt the slice for any consumer that is not the refusal path.
- **Open/Closed query catalog (toolkit pattern).** `_SHELL_OUT_QUERIES` is the open/closed seam — adding a new shell-out form (a future `node:child_process` import alias, a `process.binding` form) is **one new `ShellOutQuery` row + one S-expression**, not an edit to `_collect_hits`. The AST fence (AC-5) is the load-bearing enforcer; without it a future engineer adds `if "spawn" in text: ...` and the catalog rots.
- **`dynamic` is a real value, not a `None`.** The slice's `argv0` field is never absent and never `null` — an unresolvable target is the string sentinel `"dynamic"`, produced by the `Argv0` smart constructor. Downstream `match` code in S16-02 keys on it directly; a `None` would force every consumer to handle two absent-shapes.
- **No async I/O.** `async def run` is required by the ABC, but the body is pure file reads + tree-sitter parsing. No `await`. `mypy --strict` permits this; `asyncio_mode = "auto"` handles test invocation.
- **`.tsx` files.** The `declared_inputs` glob includes `**/*.tsx` and the grammar dispatch routes `.tsx` → `language_for("tsx")`. A `child_process` call inside a `.tsx` React component is rare but real (a build script written as `.tsx`); do not silently skip the extension.
- **Effort budget.** Probe body ≤ 140 LOC; tests ≈ 280 LOC; fence ≈ 60 LOC. If the body grows past 170 LOC, extract the tree-sitter query layer into `_shell_out_queries.py` (precedent: `src/codegenie/probes/layer_c/_dockerfile_parse.py`).
- **Token-budget guard (Rule 6).** Single-session-implementable at ~4k tokens. If tree-sitter query syntax for a destructured-import call form (`const {exec} = require(...)`) proves awkward, STOP and surface — a two-pass approach (resolve the import alias first, then match calls on the alias) is acceptable and matches `tree_sitter_import_graph.py`'s precedent.
