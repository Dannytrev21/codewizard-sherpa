# Story S2-02 — `NodeBuildSystemProbe`

**Step:** Step 2 — Extend `LanguageDetectionProbe` and ship `NodeBuildSystemProbe`
**Status:** Done (GREEN 2026-05-14 — see `_attempts/S2-02.md`)
**Effort:** L
**Depends on:** S1-04 (`jsonc` parser — `tsconfig.json#extends` walker), S1-07 (`ParsedManifestMemo` — consumed via `ctx.parsed_manifest`), S1-08 (`input_snapshot` adapter — wires the memo with content-hash key), S1-10 (`node` in `ALLOWED_BINARIES` + sub-schema convention + structlog event constants)
**ADRs honored:** Phase-1 ADR-0001 (`node` in `ALLOWED_BINARIES` + env-strip + display-only output parse), Phase-1 ADR-0002 (consumes `ctx.parsed_manifest`; no further `ProbeContext` extensions), Phase-1 ADR-0004 (`additionalProperties: false` at sub-schema root), Phase-1 ADR-0007 (warning-ID pattern `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`; typed-exception IDs land in `ProbeOutput.errors`), Phase-1 ADR-0008 (no per-probe sandbox; in-process caps are the defense), Phase-1 ADR-0010 (slice optional at envelope), Phase-0 ADR-0007 (probe contract frozen — preserved here by subclassing the frozen ABC without contract edits)

## Validation notes (added 2026-05-14)

Hardened by the `phase-story-validator` skill (scheduled task: story-validation-corrector). Verdict: **HARDENED**. The full audit is at [`_validation/S2-02-node-build-system-probe.md`](_validation/S2-02-node-build-system-probe.md); load-bearing fixes recorded here so an implementer reading only this story sees them:

- **Tuple class attributes were a frozen-ABC violation.** The original AC-1 used tuples (`("javascript","typescript")`); the frozen `Probe` ABC at `src/codegenie/probes/base.py:70-73` declares `list[str]`. All class attributes are now `list[str]` matching the ABC.
- **ADR-0001 env-strip is now an explicit AC** (AC-12) — `node --version` admissible **only** via `exec.run_allowlisted`. A new test (T-15) installs a sentinel on `codegenie.exec.run_allowlisted` and asserts the probe routes through it. Import discipline is pinned: `from codegenie import exec as _exec` (Notes-for-implementer).
- **Three precedence chains are now data, not branching code.** `_LOCKFILE_PRECEDENCE`, `_BUNDLERS_SORTED`, `_NODE_VERSION_PINNED_SOURCES` — module-level tuples. Adding a new lockfile/bundler/version-source is a one-line tuple insertion + schema enum bump + fixture test; **zero** edits to selection logic. Mirrors S2-01's `_MONOREPO_PRECEDENCE` precedent.
- **Typed-exception IDs land in `ProbeOutput.errors[]`, not `warnings[]`** (AC-14) — matches ADR-0007 line 50 and the S1-08/S2-01 hardening pattern.
- **Memo-consumption invariant** (AC-13): when `ctx.parsed_manifest` is not None, the probe consults it exactly once for `package.json`. T-17 anchors via a counting wrapper.
- **AC-4 (extends) split** into AC-4a (depth>4) + AC-4b (cycle); **AC-6 (node version) split** into AC-6a/6b/6c (success / unparseable / absent — distinct outcomes per edge case 6 and Component-design line 490).
- **Test helpers preamble added** at the head of the TDD plan. Monkeypatch target for the exec stub is unambiguous.
- **`output_artifacts` rule pinned** (AC-15) — was previously contradictory between Green ("leave `[]`") and Refactor ("populate if cheap"). Now: `package.json#files` verbatim when present as a list of strings; else `[]`.
- **`packageManager` vs lockfile** ("lockfile wins") rule is an Open Question (#3) in the arch elevated to a *recommendation* — this story takes the resolution, but a Phase-1.5/Phase-2 ADR upgrade is flagged in Notes-for-implementer.
- **Departures from arch surfaced (Rule 7).** Bundler sort order: arch says "deterministic-sorted"; Design-Patterns critic proposed intentional priority (e.g., vite-before-esbuild). This story interprets the arch as **alpha-sorted** (simplest reading); the intentional-priority alternative is recorded in Notes-for-implementer as a deferred Phase-2 consideration.

## Context

`NodeBuildSystemProbe` is the **first new probe** of Phase 1 — the proof point that the Phase 0 spine + Step 1's shared primitives (parsers, memo, sub-schema convention, `node` allowlist entry) compose into a working probe without editing the frozen Phase 0 chokepoints. It is also the only Phase 1 probe that invokes an external binary (`node --version`, optional, ADR-0001-gated). The hostile-shim adversarial fixture lands in S5-02; this story must make the env-strip path real and defensible.

The probe's internal surface is the largest in Phase 1 outside `DeploymentProbe`: lockfile-precedence existence check (no parse — `NodeManifestProbe` in S3-05 owns lockfile parsing), `package.json` via memo, `tsconfig.json` via `jsonc.load` with a depth-4 `extends` walker + cycle detection, a four-source Node version precedence chain, optional `node --version` cross-check, bundler dict-lookup, scripts verbatim. The phase budget for cold execution is ~250 ms p50 (dominated by `node --version` + tsconfig parse); warm via memo is ~5 ms.

This story does not parse any lockfile — it only checks existence in the precedence order `bun.lockb > pnpm-lock.yaml > yarn.lock > package-lock.json`. S3-05 (`NodeManifestProbe`) is the lockfile-parsing probe.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #2` (this probe; full internal structure, perf envelope, failure behavior).
  - `../phase-arch-design.md §"Data model"` — `BuildSystemSlice` Pydantic-style shape; `TypeScriptInfo` block.
  - `../phase-arch-design.md §"Control flow" → "Decision points"` — lockfile precedence; `node --version` invocation; per-probe sub-schema strictness.
  - `../phase-arch-design.md §"Edge cases"` rows 5 (`tsconfig.extends` cycle), 6 (`node --version` returns garbage from a hostile shim), 7 (multi-lockfile), 16 (`package.json` mtime change mid-gather).
  - `../phase-arch-design.md §"Harness engineering"` — `parser_kind` tracing field; `probe.parser.cap_exceeded` event.
- **Phase ADRs:**
  - `../ADRs/0001-add-node-to-allowed-binaries.md` — env-strip + `shell=False` + display-only output parse; this probe is the consumer.
  - `../ADRs/0002-parsed-manifest-memo-on-probe-context.md` — `package.json` reads go through the memo.
  - `../ADRs/0004-per-probe-subschema-additional-properties-false.md` — `node_build_system.schema.json` sets it at root.
  - `../ADRs/0007-warnings-id-pattern.md` — every warning matches the pattern.
- **Source design:**
  - `../../../localv2.md §5.1 A2` — `BuildSystem` probe inventory entry.
- **Existing code:**
  - `src/codegenie/probes/base.py` (frozen — subclass; do not edit).
  - `src/codegenie/probes/__init__.py` — explicit additive import.
  - `src/codegenie/parsers/jsonc.py` (from S1-04) — used for `tsconfig.json`.
  - `src/codegenie/parsers/safe_json.py` (from S1-02) — fallback for memo-absent path.
  - `src/codegenie/exec.py` (extended in S1-10) — `run_allowlisted(["node", "--version"], ...)`.
  - `src/codegenie/coordinator/parsed_manifest_memo.py` (from S1-07) — consumed via `ctx.parsed_manifest`.
- **External docs:**
  - Node.js docs on `engines.node` semver string — not parsed beyond regex `^v\d+\.\d+\.\d+` for the locally-resolved version.

## Goal

Running `codegenie gather` against a TypeScript + pnpm fixture (S2-03's `node_typescript_helm/`) populates a `build_system` slice with `package_manager == "pnpm"`, `commands` containing the verbatim `package.json#scripts`, `typescript.compiler_options_path == "tsconfig.json"`, `node_version_pinned` from `.nvmrc`, and — if `node` is on `$PATH` and ADR-0001 is honored — `node_version_resolved_locally` matching `^v\d+\.\d+\.\d+`.

## Acceptance criteria

- [x] **AC-1 — Probe contract attributes.** `src/codegenie/probes/node_build_system.py` defines `class NodeBuildSystemProbe(Probe)` with class attributes matching the frozen `Probe` ABC at `src/codegenie/probes/base.py:70-73` (`list[str]` annotations, **not** tuples — tuples fail `mypy --strict` against the override and break `Registry.for_task`'s `set(cls.applies_to_languages)`): `name="node_build_system"`, `version="0.1.0"`, `layer="A"`, `tier="base"`, `applies_to_languages=["javascript","typescript"]`, `applies_to_tasks=["*"]`, `requires=["language_detection"]`, `timeout_seconds=30`, and a verbatim 14-entry `declared_inputs: list[str]` matching `../phase-arch-design.md §"Component design" #2` line 478 in the same order.

- [x] **AC-2 — Lockfile precedence as data, not branching.** Lockfile precedence is encoded as a single module-level precedence-ordered tuple `_LOCKFILE_PRECEDENCE: tuple[tuple[str, str], ...] = (("bun.lockb", "bun"), ("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("package-lock.json", "npm"))`. Selection is a single linear scan: first present filename → `package_manager: str`; remaining present filenames → `additional_lockfiles: list[str]` sorted **by precedence** (not by alpha). Multiple lockfiles present → `confidence="low"`, `warnings` contains `"package_manager.multi_lockfile"`. **Open/Closed observable:** adding a new package-manager kind (e.g., Deno) requires (a) one tuple-entry insertion in `_LOCKFILE_PRECEDENCE`, (b) one `Literal` addition in the schema's `package_manager` enum, (c) one fixture test — with **zero** edits to the selection function's body.

- [x] **AC-3 — `package.json` read path + scripts verbatim.** `package.json` is read via `ctx.parsed_manifest(repo_root / "package.json")` when `ctx.parsed_manifest is not None`; otherwise falls back to `safe_json.load(repo_root / "package.json", max_bytes=5*1024*1024, max_depth=64)` (cap values match `ParsedManifestMemo._MAX_BYTES` and the arch §"Control flow" 5 MB / depth 64 convention; `max_bytes` is a required keyword on `safe_json.load` — silence here would crash). `package.json#scripts` is recorded verbatim into `commands: dict[str, str]`; values are **never** evaluated, executed, interpolated, or shell-quoted.

- [x] **AC-4a — `tsconfig.json#extends` depth cap (no cycle).** `tsconfig.json` is parsed via `parsers.jsonc.load(tsconfig_path, max_bytes=5*1024*1024, max_depth=64)`. `extends` chain followed at most 4 levels under `repo_root` containment (`Path.resolve()` + `is_relative_to(repo_root)`). Linear chain at depth > 4 (no cycle) → `confidence="medium"`, `warnings` contains `"tsconfig.extends_depth_exceeded"` (NOT the cycle ID); the deepest-reached config is recorded in `typescript.resolved_compiler_options`.

- [x] **AC-4b — `tsconfig.json#extends` cycle detection.** Cycle detected at any depth (e.g., `A → A`, `A → B → A`, `A → B → C → A`) → `confidence="medium"`, `warnings` contains `"tsconfig.extends_cycle"` (NOT the depth ID); the deepest-reached non-cyclic config is recorded. Cycle detection uses a `set[Path]` of **resolved-absolute** paths (so `./a.json` and `a.json` resolve to the same path), not strings.

- [x] **AC-5 — Node version precedence (sources).** Precedence chain: `engines.node` (from parsed `package.json`) → `.nvmrc` → `.node-version` → `.tool-versions` (grep the `node ` line). Sources are encoded as a module-level tuple `_NODE_VERSION_PINNED_SOURCES: tuple[tuple[str, Callable[[Path], str | None]], ...]` of `(source_name, pure_extractor)` for the latter three; first non-`None` hit wins. Each source recorded as a literal string; no semver expansion. **Open/Closed observable:** adding a future source (e.g., Volta — `package.json#volta.node`) is one tuple-entry insertion.

- [x] **AC-6a — `node --version` success path.** When `exec.run_allowlisted(["node", "--version"], cwd=snapshot.root, timeout_s=5)` returns successfully and stdout matches `^v\d+\.\d+\.\d+`, the matched substring lands in `node_version_resolved_locally: str` and `confidence` is unaffected.

- [x] **AC-6b — `node --version` unparseable output (hostile-shim case, edge case 6).** When `exec.run_allowlisted` returns successfully but stdout does **not** match `^v\d+\.\d+\.\d+` (e.g., garbage bytes from a hostile shim, ANSI colors, BOM prefix), `node_version_resolved_locally: null`, `warnings` contains `"node.version_unparseable"`, and `confidence` **stays `"high"`** (the cross-check is informational; the constraint is load-bearing for `production/design.md`'s "Honest confidence" — failure here is *not* a degraded signal).

- [x] **AC-6c — `node --version` absent / timeout / exec-error path.** When `exec.run_allowlisted` raises `FileNotFoundError`, `TimeoutExpired`, or `ExecError` (non-zero exit), `node_version_resolved_locally: null`, **no warning is emitted**, `out.errors == []` (absent binary is optional, not an error), and `confidence` is unaffected.

- [x] **AC-7 — Version disagreement warning.** If both `node_version_pinned` and `node_version_resolved_locally` are non-`None` AND both match `^v?\d+\.\d+\.\d+` after stripping a leading `v` from each (the "parseable as semver" rule — strict-semver libraries are not used; this is the pragmatic comparison) AND they differ, `warnings` contains `"node.version_declared_resolved_disagree"` and `confidence` stays `"high"` (informational). If either side fails the regex (e.g., `.nvmrc` content `lts/hydrogen`), the comparison is **silently skipped** — no false-positive warning.

- [x] **AC-8 — `packageManager` field handling (Open Question #3 resolution).** If `package.json#packageManager` is present (e.g., `"pnpm@8.6.0"`):
    - **Agreement case:** the prefix before `@` matches `package_manager` (lockfile pick) → no warning, no degraded confidence.
    - **Disagreement case:** the prefix before `@` does NOT match `package_manager` → `warnings` contains `"package_manager.declaration_lockfile_disagree"`; the **lockfile wins** for `package_manager`. This decision is currently a story-level resolution of an arch Open Question (not yet ADR-ratified) — see Notes-for-implementer for the Phase-1.5/Phase-2 ADR upgrade TODO.

- [x] **AC-9 — Bundler detection via alpha-sorted tuple.** Bundler detection consumes a module-level alpha-sorted tuple `_BUNDLERS_SORTED: tuple[str, ...] = ("esbuild", "parcel", "rollup", "turbopack", "vite", "webpack")` (interpretation of the arch's "deterministic-sorted" prescription — see Notes-for-implementer for the intentional-priority alternative deferred to Phase 2). First member of the tuple present in `dependencies ∪ devDependencies` → `bundler: str`; none → `null`. Adding a bundler is a one-line tuple insertion (the schema's `bundler` `Literal` enum must be updated in the same PR).

- [x] **AC-10 — Sub-schema constraints.** `src/codegenie/schema/probes/node_build_system.schema.json` exists; `additionalProperties: false` at root and at every nested block (notably `TypeScriptInfo`); declares the slice **optional** at envelope level (no entry in the envelope's `properties.probes.required` array — ADR-0010); the sub-schema constrains **both** `warnings[]` and `errors[]` against the ADR-0007 pattern `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`.

- [x] **AC-11 — Warning + error ID frozenset + import-time assertion.** All warning IDs (`package_manager.multi_lockfile`, `package_manager.declaration_lockfile_disagree`, `tsconfig.extends_cycle`, `tsconfig.extends_depth_exceeded`, `node.version_unparseable`, `node.version_declared_resolved_disagree`) AND all error IDs (`package_json.size_cap_exceeded`, `package_json.malformed`, `package_json.symlink_refused`, `tsconfig.depth_cap_exceeded`) are declared in a module-level `frozenset[str]` (one per category). An import-time `assert` verifies every member matches the ADR-0007 regex; if any drifts, the module fails to import.

- [x] **AC-12 — ADR-0001 env-strip path (load-bearing).** The probe invokes `node --version` **only** via `exec.run_allowlisted(["node", "--version"], cwd=snapshot.root, timeout_s=5)`. No direct `subprocess.run`, `subprocess.Popen`, `os.system`, or `os.popen` call appears anywhere in the module. The probe imports as `from codegenie import exec as _exec` and calls `_exec.run_allowlisted(...)` so that unit tests can monkeypatch `codegenie.exec.run_allowlisted` and verify the seam from the outside (a `_exec.run_allowlisted` stub installed on the module IS what the probe calls — no import-aliasing around the seam).

- [x] **AC-13 — Memo-consumption invariant.** When `ctx.parsed_manifest is not None`, the probe calls `ctx.parsed_manifest(repo_root / "package.json")` **exactly once** during a single `run(...)` invocation. A counting-wrapper test (T-17) asserts `call_count == 1`. When `ctx.parsed_manifest is None`, the probe calls `safe_json.load(...)` exactly once on the `package.json` path. Mid-gather `package.json` content changes (edge case 16) are owned by the coordinator/memo (S1-07/S1-08), not by this probe.

- [x] **AC-14 — Typed-exception → `errors[]`.** `SizeCapExceeded`, `MalformedJSONError`, `SymlinkRefusedError`, `DepthCapExceeded` raised by `safe_json.load` / `jsonc.load` are caught into `ProbeOutput.errors` with IDs `package_json.size_cap_exceeded`, `package_json.malformed`, `package_json.symlink_refused`, `tsconfig.depth_cap_exceeded` respectively. Each ID matches the ADR-0007 pattern. On these, `confidence="low"` and the probe returns a minimal slice (no further parse work — the typed exception is the contract).

- [x] **AC-15 — `output_artifacts` rule.** `build_system.output_artifacts` is `package.json#files` verbatim (literal list copy) when that key is present **and** is a `list` of `str`; otherwise `[]`. Non-list values (`{}`, raw string, missing key, `null`) → `[]`. Entries are treated as glob patterns as authored, never resolved to filesystem paths at this layer.

- [x] **AC-16 — `package_manager_version` field in Phase 1.** `build_system.package_manager_version` is `null` unconditionally in Phase 1; the field is populated by S3-05 (`NodeManifestProbe`) from the lockfile, not by this probe. The sub-schema permits `null`.

- [x] **AC-17 — Version routing rule.** `engines.node` (parsed range string, e.g., `">=20.0.0"`) lands in `node_version_constraint`; the **first non-`None`** result from the `_NODE_VERSION_PINNED_SOURCES` chain lands in `node_version_pinned`. Routing is fixed by `BuildSystemSlice` field semantics (`node_version_constraint` = declared range; `node_version_pinned` = exact dev-environment pin), **not** by the precedence-chain order. `engines.node` cannot leak into `node_version_pinned` by chain reordering.

- [x] **AC-18 — `scripts` edge cases.** Missing `scripts` key, `scripts: null`, or `scripts: {}` → `commands: {}` (empty dict, **never** `null`). Non-string values within `scripts` (e.g., `{"x": 42}`, `{"y": ["array", "value"]}`) are **silently skipped** — the probe is not a `package.json` linter; schema-violating `package.json` is upstream's problem. No warning emitted for non-string values.

- [x] **AC-19 — Single-lockfile sanity (no spurious multi-lockfile warning).** Single lockfile present → `package_manager` matches the lockfile, `additional_lockfiles == []`, `warnings` does NOT contain `"package_manager.multi_lockfile"`, `confidence == "high"`. (Test catches the "always emit multi-lockfile warning" mutation.)

- [x] **AC-20 — Registry membership + filter.** `src/codegenie/probes/__init__.py` imports `NodeBuildSystemProbe` via an explicit additive line; `default_registry.all_probes()` includes it. `for_task("*", frozenset({"javascript"}))`, `for_task("*", frozenset({"typescript"}))`, and `for_task("*", frozenset({"javascript","typescript"}))` each return a tuple containing the probe; `for_task("*", frozenset({"go"}))` does NOT (skip case — non-Node repo path).

- [x] **AC-21 — ADR-0004 extra-field rejection.** A synthetic envelope with `{"probes": {"node_build_system": {"extra_field": 1, ...}}}` is rejected by the envelope+sub-schema validator with `SchemaValidationError` at JSON Pointer `/probes/node_build_system/extra_field`.

- [x] **AC-22 — Tooling green.** `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/probes/node_build_system.py`, `pytest tests/unit/probes/test_node_build_system.py` all pass. Per-module coverage for `node_build_system.py` is pasted into the PR body (per cross-cutting concern #6); the floor is 90/80 line/branch (S6-02's ratchet cannot recover if this probe lands below).

## Implementation outline

The shape is **functional core, imperative shell** (Rule 2 / Rule 11 — keep `run(...)` thin; pure helpers are testable in isolation). Module-level constants encode the three precedence chains as **data**, not branching code.

1. **Create `src/codegenie/probes/node_build_system.py`.** Subclass `Probe` from `probes/base.py`. Import `from codegenie import exec as _exec` (the env-strip seam — see AC-12 + Notes-for-implementer). Declare class attributes per AC-1 (all `list[str]`, not tuples — frozen ABC).

2. **Module-level constants (the file-boundary Open/Closed seams).**

    ```python
    _LOCKFILE_PRECEDENCE: Final[tuple[tuple[str, str], ...]] = (
        ("bun.lockb", "bun"),
        ("pnpm-lock.yaml", "pnpm"),
        ("yarn.lock", "yarn"),
        ("package-lock.json", "npm"),
    )

    _BUNDLERS_SORTED: Final[tuple[str, ...]] = (
        "esbuild", "parcel", "rollup", "turbopack", "vite", "webpack",
    )

    _NODE_VERSION_PINNED_SOURCES: Final[tuple[tuple[str, Callable[[Path], str | None]], ...]] = (
        (".nvmrc",         _read_nvmrc),
        (".node-version",  _read_node_version),
        (".tool-versions", _read_tool_versions_node),
    )

    _WARNING_IDS: Final[frozenset[str]] = frozenset({
        "package_manager.multi_lockfile",
        "package_manager.declaration_lockfile_disagree",
        "tsconfig.extends_cycle",
        "tsconfig.extends_depth_exceeded",
        "node.version_unparseable",
        "node.version_declared_resolved_disagree",
    })

    _ERROR_IDS: Final[frozenset[str]] = frozenset({
        "package_json.size_cap_exceeded",
        "package_json.malformed",
        "package_json.symlink_refused",
        "tsconfig.depth_cap_exceeded",
    })

    # Import-time invariant: every emitted ID conforms to ADR-0007.
    _ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    for _id in (*_WARNING_IDS, *_ERROR_IDS):
        assert _ID_PATTERN.match(_id), f"ADR-0007 violation: {_id!r}"
    ```

3. **Pure helpers (functional core — testable in isolation, no I/O).**

    - `_select_package_manager(present: Sequence[str]) -> tuple[str | None, list[str]]` — single linear scan over `_LOCKFILE_PRECEDENCE`; returns `(picked, runners_up_in_precedence_order)`.
    - `_parse_node_version_output(stdout: str) -> str | None` — single regex `^v\d+\.\d+\.\d+`; pure `str → str | None`.
    - `_read_nvmrc(root: Path) -> str | None`, `_read_node_version(root: Path) -> str | None`, `_read_tool_versions_node(root: Path) -> str | None` — each reads at most one file with a small size cap (1 KB); returns the trimmed first matching line or `None`.
    - `_walk_extends(tsconfig_path: Path, repo_root: Path, *, max_depth: int = 4) -> tuple[Mapping[str, Any], list[str]]` — returns `(deepest_compiler_options_dict, warnings_emitted)`. Cycle detection via `set[Path]` of **resolved-absolute** paths (gotcha: `./a.json` vs `a.json` resolve identically — string-set is wrong; Path-set is right). Style preference: iterative-with-explicit-stack matching `language_detection._walk`; recursive-with-frozenset-rebuild is admissible if simpler at depth-4.

4. **Implement `async def run(self, snapshot, ctx) -> ProbeOutput`.** Order:

    1. **Lockfile precedence.** `present = [name for name, _ in _LOCKFILE_PRECEDENCE if (snapshot.root / name).is_file()]`; pass to `_select_package_manager`; if `len(present) > 1` → add `package_manager.multi_lockfile` warning + `confidence = "low"`.
    2. **`package.json` read.** `if ctx.parsed_manifest is not None: pkg = ctx.parsed_manifest(snapshot.root / "package.json")` else `pkg = safe_json.load(snapshot.root / "package.json", max_bytes=5*1024*1024, max_depth=64)`. Wrap in `try / except (SizeCapExceeded, MalformedJSONError, SymlinkRefusedError) as exc:` → map to `_ERROR_IDS` entry, `confidence = "low"`, return minimal slice immediately.
    3. **TypeScript block.** If `(snapshot.root / "tsconfig.json").is_file()`, call `jsonc.load(tsconfig_path, max_bytes=5*1024*1024, max_depth=64)` and `_walk_extends(...)`. Catch `DepthCapExceeded` → `tsconfig.depth_cap_exceeded` in `errors`.
    4. **Node version.** Read `engines.node` → `node_version_constraint`. Walk `_NODE_VERSION_PINNED_SOURCES` for first non-`None` hit → `node_version_pinned` (literal string, no semver expansion).
    5. **`node --version` cross-check.** `try: result = _exec.run_allowlisted(["node", "--version"], cwd=snapshot.root, timeout_s=5)` then `_parse_node_version_output(result.stdout.decode("utf-8", errors="replace"))`. On `None` → add `node.version_unparseable` warning. `except (FileNotFoundError, TimeoutExpired, ExecError):` → silent (no warning).
    6. **Disagreement check.** Apply AC-7's strip-leading-`v` + regex-both-sides rule. Silent skip on either side's regex miss.
    7. **Bundler.** `deps = set((pkg.get("dependencies") or {}).keys()) | set((pkg.get("devDependencies") or {}).keys())`; `bundler = next((b for b in _BUNDLERS_SORTED if b in deps), None)`.
    8. **`packageManager` field.** If `pkg.get("packageManager")` and its `^([a-z]+)@` prefix ≠ `package_manager` → add `package_manager.declaration_lockfile_disagree` warning.
    9. **`output_artifacts`.** `files = pkg.get("files"); output_artifacts = files if isinstance(files, list) and all(isinstance(f, str) for f in files) else []`.
    10. **`commands`.** `scripts = pkg.get("scripts") or {}; commands = {k: v for k, v in scripts.items() if isinstance(v, str)}`.

5. **Logging.** Emit `EVENT_PROBE_START` / `EVENT_PROBE_SUCCESS` / `EVENT_PROBE_FAILURE` (the Phase 0 constants from `codegenie.logging`). Emit `probe.parser.cap_exceeded` (with `cap_kind ∈ {"size", "depth"}`, `path`, `parser`) when a `safe_json` / `jsonc` cap fires. Every parse-related log line includes the `parser_kind` field (`"jsonc"` or `"safe_json"`). `probe.memo.{hit,miss}` is the memo's responsibility (S1-07 instrumentation), not this probe's.

6. **Write `src/codegenie/schema/probes/node_build_system.schema.json`** per `../phase-arch-design.md §"Data model"` `BuildSystemSlice`. `additionalProperties: false` at root + every nested block. ADR-0007 `pattern` constraint on **both** `warnings[]` and `errors[]` array items.

7. **Register the probe** via an additive import in `src/codegenie/probes/__init__.py` (one line: `from codegenie.probes import node_build_system`; the `@register_probe` decorator runs on module load and adds the class to `default_registry`).

## TDD plan — red / green / refactor

### Test helpers preamble (define inline at the top of the test file — do NOT depend on `conftest.py` for these; following the S2-01 precedent)

```python
# tests/unit/probes/test_node_build_system.py
from __future__ import annotations
import asyncio, json, os, re, types
import pytest
from pathlib import Path
from subprocess import TimeoutExpired

# The probe under test imports `from codegenie import exec as _exec` and calls
# `_exec.run_allowlisted(...)`. Tests MUST monkeypatch the canonical seam at
# `codegenie.exec.run_allowlisted` (NOT `subprocess.run` — that would bypass
# the ADR-0001 env-strip wrapper and render S5-02 the only line of defense).
def _stub_exec_returning(monkeypatch, stdout: bytes, returncode: int = 0) -> None:
    import codegenie.exec
    monkeypatch.setattr(
        codegenie.exec, "run_allowlisted",
        lambda argv, **kw: types.SimpleNamespace(stdout=stdout, returncode=returncode),
    )

def _stub_exec_raising(monkeypatch, exc: BaseException) -> None:
    import codegenie.exec
    def _raise(*a, **kw): raise exc
    monkeypatch.setattr(codegenie.exec, "run_allowlisted", _raise)

def _snapshot(root: Path):
    from codegenie.probes.base import RepoSnapshot
    return RepoSnapshot(root=root, git_commit=None, detected_languages={"typescript": 1}, config={})

def _ctx(root: Path, parsed_manifest=None):
    import logging
    from codegenie.probes.base import ProbeContext
    return ProbeContext(
        cache_dir=root / ".cache",
        output_dir=root / ".out",
        workspace=root,
        logger=logging.getLogger("test"),
        config={},
        parsed_manifest=parsed_manifest,
    )

def _run_probe(root: Path, parsed_manifest=None):
    from codegenie.probes.node_build_system import NodeBuildSystemProbe
    return asyncio.run(NodeBuildSystemProbe().run(_snapshot(root), _ctx(root, parsed_manifest)))

ADR_0007 = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
```

### Red — write the failing tests first

Eighteen tests, ten parametrized. Drive Green with the first four (T-9, T-1, T-2, T-15 — the contract + lockfile + scripts + env-strip-seam quartet); the remainder lands during Refactor as the implementation widens.

```python
# --- AC-1: probe contract attributes ---
def test_probe_contract_attributes_match_arch_design():
    """T-9. AC-1. Drift in any class attribute breaks Wave-1 ordering or cache keys."""
    from codegenie.probes.node_build_system import NodeBuildSystemProbe as P
    assert P.name == "node_build_system"
    assert P.version == "0.1.0"
    assert P.layer == "A"
    assert P.tier == "base"
    assert P.applies_to_languages == ["javascript", "typescript"]  # list, not tuple
    assert P.applies_to_tasks == ["*"]
    assert P.requires == ["language_detection"]                    # Wave-2 dep
    assert P.timeout_seconds == 30
    # 14-entry declared_inputs in the arch's published order
    assert len(P.declared_inputs) == 14
    for expected in ("package.json", "pnpm-workspace.yaml", "lerna.json", "nx.json",
                     "turbo.json", ".nvmrc", ".node-version", ".tool-versions",
                     "tsconfig.json", "tsconfig.*.json",
                     "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb"):
        assert expected in P.declared_inputs, f"missing: {expected}"


# --- AC-2: lockfile precedence as TOTAL ORDERING ---
@pytest.mark.parametrize("present,expected_pm,expected_runners,expect_warn", [
    ({"bun.lockb","pnpm-lock.yaml","yarn.lock","package-lock.json"},
     "bun", ["pnpm-lock.yaml","yarn.lock","package-lock.json"], True),
    ({"pnpm-lock.yaml","yarn.lock","package-lock.json"},
     "pnpm", ["yarn.lock","package-lock.json"], True),
    ({"yarn.lock","package-lock.json"}, "yarn", ["package-lock.json"], True),
    ({"package-lock.json"}, "npm", [], False),                       # AC-19 sanity
    ({"bun.lockb","package-lock.json"}, "bun", ["package-lock.json"], True),
])
def test_lockfile_precedence_total_ordering(tmp_path, present, expected_pm, expected_runners, expect_warn):
    """T-1. AC-2 + AC-19. Runners-up ordering is by PRECEDENCE, not alpha."""
    (tmp_path / "package.json").write_text("{}")
    for f in present: (tmp_path / f).write_text("x")
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == expected_pm
    assert s["additional_lockfiles"] == expected_runners
    assert ("package_manager.multi_lockfile" in s["warnings"]) is expect_warn


def test_lockfile_precedence_tuple_order_locked():
    """T-1b. AC-2 ordering invariant: the module constant must not drift."""
    from codegenie.probes.node_build_system import _LOCKFILE_PRECEDENCE
    assert _LOCKFILE_PRECEDENCE == (
        ("bun.lockb", "bun"),
        ("pnpm-lock.yaml", "pnpm"),
        ("yarn.lock", "yarn"),
        ("package-lock.json", "npm"),
    )


# --- AC-3: scripts verbatim, never evaluated ---
def test_scripts_recorded_verbatim_and_never_evaluated(tmp_path):
    """T-2. AC-3. The `rm -rf dist && tsc` script body would be a smoking gun
    if any shell interpolation or expansion crept in."""
    (tmp_path / "package.json").write_text(json.dumps({
        "scripts": {"test": "vitest", "build": "rm -rf dist && tsc"}}))
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '6.0'")
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["commands"] == {"test": "vitest", "build": "rm -rf dist && tsc"}


# --- AC-18: scripts edge cases ---
@pytest.mark.parametrize("pkg_body,expected", [
    ({}, {}),                                          # missing key
    ({"scripts": None}, {}),                           # null
    ({"scripts": {}}, {}),                             # empty
    ({"scripts": {"x": "ok", "y": 42}}, {"x": "ok"}),  # non-string silently skipped
    ({"scripts": {"x": "ok", "y": ["array"]}}, {"x": "ok"}),
])
def test_scripts_edge_cases(tmp_path, pkg_body, expected):
    """T-11. AC-18."""
    (tmp_path / "package.json").write_text(json.dumps(pkg_body))
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["commands"] == expected


# --- AC-4a: tsconfig depth boundary (no cycle) ---
def test_extends_depth_4_ok_depth_5_warns(tmp_path):
    """T-10. AC-4a. Off-by-one mutation (`if depth > 5`) passes original cycle
    test but fails this one."""
    (tmp_path / "package.json").write_text("{}")
    # depth 4 OK: tsconfig → a → b → c → d
    (tmp_path / "tsconfig.json").write_text('{"extends":"./a.json"}')
    (tmp_path / "a.json").write_text('{"extends":"./b.json"}')
    (tmp_path / "b.json").write_text('{"extends":"./c.json"}')
    (tmp_path / "c.json").write_text('{"extends":"./d.json"}')
    (tmp_path / "d.json").write_text('{"compilerOptions":{"strict":true}}')
    s_ok = _run_probe(tmp_path).schema_slice["build_system"]
    assert "tsconfig.extends_depth_exceeded" not in s_ok["warnings"]
    # extend by one — depth 5 must warn
    (tmp_path / "d.json").write_text('{"extends":"./e.json"}')
    (tmp_path / "e.json").write_text("{}")
    s_bad = _run_probe(tmp_path).schema_slice["build_system"]
    assert "tsconfig.extends_depth_exceeded" in s_bad["warnings"]
    assert "tsconfig.extends_cycle" not in s_bad["warnings"]


# --- AC-4b: tsconfig cycles (path-based, not string-based) ---
@pytest.mark.parametrize("files", [
    {"tsconfig.json": '{"extends":"./tsconfig.json"}'},                            # self-cycle
    {"tsconfig.json": '{"extends":"./a.json"}',                                    # 2-hop with
     "a.json":        '{"extends":"tsconfig.json"}'},                              #   relative-path alias
    {"tsconfig.json": '{"extends":"./a.json"}',                                    # 3-hop
     "a.json":        '{"extends":"./b.json"}',
     "b.json":        '{"extends":"./tsconfig.json"}'},
])
def test_tsconfig_extends_cycles_detected(tmp_path, files):
    """T-3. AC-4b. `./a.json` and `a.json` MUST resolve to the same absolute
    path — string-set cycle detection is the wrong implementation."""
    (tmp_path / "package.json").write_text("{}")
    for n, b in files.items(): (tmp_path / n).write_text(b)
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert "tsconfig.extends_cycle" in s["warnings"]
    assert "tsconfig.extends_depth_exceeded" not in s["warnings"]


# --- AC-5/AC-17: node version precedence ---
@pytest.mark.parametrize("files,pinned,constraint", [
    ({".nvmrc": "v18.17.0", ".node-version": "v20.0.0", ".tool-versions": "node 21.0.0\n"},
     "v18.17.0", None),                                       # .nvmrc wins
    ({".node-version": "v20.0.0", ".tool-versions": "node 21.0.0\n"},
     "v20.0.0", None),                                        # .node-version wins absent .nvmrc
    ({".tool-versions": "python 3.11\nnode 21.0.0\n"},
     "21.0.0", None),                                         # only .tool-versions; line-parse correct
    ({}, None, None),                                         # no source
    ({".nvmrc": "v18.17.0"}, "v18.17.0", ">=20.0.0"),         # constraint independent
])
def test_node_version_precedence(tmp_path, files, pinned, constraint):
    """T-4. AC-5 + AC-17. engines.node ROUTING goes to `node_version_constraint`,
    NOT into the chain — a chain-reorder mutation that lets engines.node fall into
    `node_version_pinned` would fail T-4."""
    pkg = {"engines": {"node": constraint}} if constraint else {}
    (tmp_path / "package.json").write_text(json.dumps(pkg))
    for n, b in files.items(): (tmp_path / n).write_text(b)
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["node_version_pinned"] == pinned
    assert s["node_version_constraint"] == constraint


# --- AC-6b: hostile-shim path warns; AC-11 pattern-conformance ---
def test_node_version_hostile_shim_warns_but_stays_high(monkeypatch, tmp_path):
    """T-5. AC-6b + AC-11. Every emitted ID matches ADR-0007."""
    _stub_exec_returning(monkeypatch, b"x\x00")
    (tmp_path / "package.json").write_text("{}")
    out = _run_probe(tmp_path)
    s = out.schema_slice["build_system"]
    assert s["node_version_resolved_locally"] is None
    assert "node.version_unparseable" in s["warnings"]
    for w in s["warnings"]:
        assert ADR_0007.match(w), f"warning ID violates ADR-0007: {w!r}"
    assert out.confidence == "high"
    assert out.errors == []


# --- AC-6c: absent/timeout/exec-error — silent ---
@pytest.mark.parametrize("exc", [
    FileNotFoundError(),
    TimeoutExpired("node", 5),
    # ExecError is imported lazily — the test asserts coverage of "non-zero exit".
])
def test_node_version_exceptions_all_silently_skipped(monkeypatch, tmp_path, exc):
    """T-6. AC-6c. NO warning emitted; confidence unaffected; errors empty."""
    _stub_exec_raising(monkeypatch, exc)
    (tmp_path / "package.json").write_text("{}")
    out = _run_probe(tmp_path)
    s = out.schema_slice["build_system"]
    assert s["node_version_resolved_locally"] is None
    assert all(not w.startswith("node.") for w in s["warnings"])
    assert out.errors == []
    assert out.confidence == "high"


# --- AC-7: declared-vs-resolved disagree (both directions) ---
def test_version_declared_resolved_disagree_warns_high_confidence(monkeypatch, tmp_path):
    """T-13. AC-7 disagree case."""
    _stub_exec_returning(monkeypatch, b"v20.10.0\n")
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / ".nvmrc").write_text("v18.17.0")
    out = _run_probe(tmp_path)
    s = out.schema_slice["build_system"]
    assert s["node_version_resolved_locally"] == "v20.10.0"
    assert s["node_version_pinned"] == "v18.17.0"
    assert "node.version_declared_resolved_disagree" in s["warnings"]
    assert out.confidence == "high"


def test_version_declared_resolved_agree_emits_no_warning(monkeypatch, tmp_path):
    """T-14a. AC-7 agreement case (positive AND negative — no false alarm)."""
    _stub_exec_returning(monkeypatch, b"v20.10.0\n")
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / ".nvmrc").write_text("v20.10.0")
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert "node.version_declared_resolved_disagree" not in s["warnings"]


def test_version_disagree_silently_skipped_when_unparseable(monkeypatch, tmp_path):
    """T-14b. AC-7 silent-skip case: `.nvmrc` content is `lts/hydrogen` — not
    parseable as semver — comparison MUST NOT fire a false-positive warning."""
    _stub_exec_returning(monkeypatch, b"v20.10.0\n")
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / ".nvmrc").write_text("lts/hydrogen")
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert "node.version_declared_resolved_disagree" not in s["warnings"]


# --- AC-8: packageManager (disagree AND agree) ---
def test_package_manager_declaration_disagreement(tmp_path):
    """T-7a. AC-8 disagree case (lockfile wins)."""
    (tmp_path / "package.json").write_text('{"packageManager": "yarn@3.0.0"}')
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '6.0'")
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == "pnpm"
    assert "package_manager.declaration_lockfile_disagree" in s["warnings"]


def test_package_manager_declaration_agreement(tmp_path):
    """T-7b. AC-8 agreement case — no warning."""
    (tmp_path / "package.json").write_text('{"packageManager": "pnpm@8.6.0"}')
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '6.0'")
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == "pnpm"
    assert "package_manager.declaration_lockfile_disagree" not in s["warnings"]


# --- AC-9: bundler determinism ---
@pytest.mark.parametrize("deps_order", [
    ["webpack", "rollup"], ["rollup", "webpack"],   # shuffled — dict-insertion-order trap
    ["vite", "esbuild", "webpack"],                 # 3-way
])
def test_bundler_deterministic_alpha_first_hit(tmp_path, deps_order):
    """T-12. AC-9. Alpha-sorted via `_BUNDLERS_SORTED` — esbuild < parcel < rollup
    < turbopack < vite < webpack. A dict.items()-first mutation passes the
    single-bundler test but fails this parametrize."""
    deps = {n: "^1.0.0" for n in deps_order}
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": deps}))
    bundler = _run_probe(tmp_path).schema_slice["build_system"]["bundler"]
    candidates = {"esbuild","parcel","rollup","turbopack","vite","webpack"}
    expected = sorted(d for d in deps_order if d in candidates)[0]
    assert bundler == expected


def test_bundler_none_when_no_bundler_dep(tmp_path):
    """T-12b. AC-9 null case."""
    (tmp_path / "package.json").write_text('{"dependencies":{"lodash":"^4"}}')
    assert _run_probe(tmp_path).schema_slice["build_system"]["bundler"] is None


# --- AC-12: env-strip seam (load-bearing) ---
def test_env_strip_seam_routes_through_run_allowlisted(monkeypatch, tmp_path):
    """T-15. AC-12. The probe MUST go through `codegenie.exec.run_allowlisted`.
    If the implementer imports as a module-attribute alias and later refactors
    to `subprocess.run`, this test breaks. The S5-02 adversarial $PATH-shim test
    is intentionally orthogonal; this unit test pins the import discipline."""
    import codegenie.exec
    sentinel_was_called = []
    def sentinel(argv, **kw):
        sentinel_was_called.append(argv)
        return types.SimpleNamespace(stdout=b"v20.10.0\n", returncode=0)
    monkeypatch.setattr(codegenie.exec, "run_allowlisted", sentinel)
    (tmp_path / "package.json").write_text("{}")
    out = _run_probe(tmp_path)
    assert sentinel_was_called, "probe bypassed codegenie.exec.run_allowlisted"
    assert sentinel_was_called[0][:2] == ["node", "--version"]


# --- AC-13: memo branch ---
def test_package_json_read_via_memo_when_present(tmp_path):
    """T-17. AC-13 memo branch. Counting wrapper proves call_count == 1."""
    calls = []
    def memo(path):
        calls.append(path); return {"scripts": {"test": "vitest"}}
    (tmp_path / "package.json").write_text("garbage-but-memo-wins")
    out = _run_probe(tmp_path, parsed_manifest=memo)
    assert len(calls) == 1
    assert calls[0].name == "package.json"
    assert out.schema_slice["build_system"]["commands"] == {"test": "vitest"}


def test_package_json_read_via_safe_json_when_memo_none(tmp_path):
    """T-18. AC-13 fallback branch (`ctx.parsed_manifest is None`)."""
    (tmp_path / "package.json").write_text('{"scripts":{"test":"vitest"}}')
    out = _run_probe(tmp_path)  # default ctx → parsed_manifest=None
    assert out.schema_slice["build_system"]["commands"] == {"test": "vitest"}


# --- AC-14: typed-exception → errors[] (NOT warnings[]) ---
def test_package_json_size_cap_lands_in_errors(tmp_path):
    """T-16a. AC-14. `SizeCapExceeded` → `errors`, not `warnings`."""
    big = "x" * (5 * 1024 * 1024 + 16)
    (tmp_path / "package.json").write_text(big)
    out = _run_probe(tmp_path)
    assert "package_json.size_cap_exceeded" in out.errors
    assert out.confidence == "low"
    assert "build_system" in out.schema_slice  # minimal slice still emitted


def test_package_json_malformed_lands_in_errors(tmp_path):
    """T-16b. AC-14. `MalformedJSONError` → `errors`."""
    (tmp_path / "package.json").write_text('{"scripts":{"test":"vitest"')  # truncated
    out = _run_probe(tmp_path)
    assert "package_json.malformed" in out.errors
    assert out.confidence == "low"


def test_package_json_symlink_refused_lands_in_errors(tmp_path):
    """T-16c. AC-14. `SymlinkRefusedError` (O_NOFOLLOW) → `errors`."""
    outside = tmp_path.parent / "evil.json"
    outside.write_text('{"scripts": {"test": "rm -rf /"}}')
    (tmp_path / "package.json").symlink_to(outside)
    out = _run_probe(tmp_path)
    assert "package_json.symlink_refused" in out.errors
    assert out.confidence == "low"
    # Critically: the symlink target's content must NOT leak into commands.
    assert out.schema_slice["build_system"].get("commands", {}) == {}


# --- AC-15: output_artifacts ---
@pytest.mark.parametrize("pkg_body,expected", [
    ({"files": ["dist/**", "README.md"]}, ["dist/**", "README.md"]),
    ({}, []),                                   # missing
    ({"files": None}, []),                      # null
    ({"files": {}}, []),                        # wrong type
    ({"files": [1, "ok"]}, []),                 # any non-str → []
])
def test_output_artifacts_from_package_json_files(tmp_path, pkg_body, expected):
    """T-21. AC-15. The 'if cheap' hedge is gone — rule is explicit."""
    (tmp_path / "package.json").write_text(json.dumps(pkg_body))
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["output_artifacts"] == expected


# --- AC-16: package_manager_version is null in Phase 1 ---
def test_package_manager_version_is_null_in_phase_1(tmp_path):
    """T-22. AC-16. S3-05 populates this from the lockfile; this story does not."""
    (tmp_path / "package.json").write_text('{"packageManager": "pnpm@8.6.0"}')
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '6.0'")
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager_version"] is None


# --- AC-19: single-lockfile sanity ---
# Covered by the AC-2 parametrize's `{"package-lock.json"}` case (expect_warn=False).

# --- AC-20: registry membership + filter ---
def test_registry_membership_and_for_task_filter():
    """T-23. AC-20."""
    from codegenie.probes import default_registry
    from codegenie.probes.node_build_system import NodeBuildSystemProbe
    assert NodeBuildSystemProbe in default_registry.all_probes()
    for langs in [frozenset({"javascript"}), frozenset({"typescript"}),
                  frozenset({"javascript", "typescript"})]:
        assert NodeBuildSystemProbe in default_registry.for_task("*", langs)
    # Non-Node repo path — skip cleanly (ADR-0010 envelope-optional)
    assert NodeBuildSystemProbe not in default_registry.for_task("*", frozenset({"go"}))


# --- AC-21: sub-schema extra-field rejection ---
def test_sub_schema_rejects_extra_field_under_node_build_system():
    """T-24. AC-21."""
    from codegenie.schema import load_envelope_validator
    envelope = _minimal_envelope_with_node_build_system(extra={"rogue": True})
    with _expect_schema_violation_at("/probes/node_build_system/rogue"):
        load_envelope_validator().validate(envelope)


# --- AC-11: ID frozenset import-time invariant ---
def test_warning_and_error_ids_match_adr_0007():
    """T-25. AC-11. If the module imports, the assert ran. This test pins that
    the frozensets are non-empty AND every member matches the pattern."""
    from codegenie.probes import node_build_system as nbs
    assert nbs._WARNING_IDS, "module-level warning IDs frozenset missing"
    assert nbs._ERROR_IDS, "module-level error IDs frozenset missing"
    for i in (*nbs._WARNING_IDS, *nbs._ERROR_IDS):
        assert ADR_0007.match(i), f"violates ADR-0007: {i!r}"


# --- cross-cutting: determinism ---
def test_two_runs_byte_equal(tmp_path):
    """T-26. Reproducibility (`production/design.md` 'deterministic end-to-end').
    Catches insertion-order-dependent behavior in bundler/lockfile/scripts dict
    iteration; any mutation that returns a set() somewhere would fail this."""
    (tmp_path / "package.json").write_text(json.dumps(
        {"scripts": {"test": "vitest", "build": "tsc"},
         "dependencies": {"vite": "^5", "rollup": "^4", "express": "^4"}}))
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '6.0'")
    (tmp_path / "package-lock.json").write_text("{}")
    a = _run_probe(tmp_path).schema_slice
    b = _run_probe(tmp_path).schema_slice
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# --- structlog parser_kind field (nit) ---
def test_parser_kind_field_emitted_on_tsconfig_parse(tmp_path):
    """T-20. observability anchor: `parser_kind` field present on parse events."""
    from structlog.testing import capture_logs
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "tsconfig.json").write_text('{"compilerOptions":{"strict":true}}')
    with capture_logs() as logs: _run_probe(tmp_path)
    assert any(e.get("parser_kind") == "jsonc" for e in logs)
```

Run all eighteen; all should be red (`ModuleNotFoundError: codegenie.probes.node_build_system` for everything except T-25 / T-24 which fail differently). Confirm red, commit, then Green.

### Green — make it pass

Add `src/codegenie/probes/node_build_system.py`:

- Class attributes per AC-1 (all `list[str]` — frozen ABC).
- Module-level `_LOCKFILE_PRECEDENCE`, `_BUNDLERS_SORTED`, `_NODE_VERSION_PINNED_SOURCES`, `_WARNING_IDS`, `_ERROR_IDS` constants + import-time ADR-0007 assert.
- Pure helpers: `_select_package_manager`, `_parse_node_version_output`, `_walk_extends`, `_read_nvmrc`, `_read_node_version`, `_read_tool_versions_node`.
- `async def run(self, snapshot, ctx) -> ProbeOutput` orchestrates them per the Implementation outline §4.

Write `src/codegenie/schema/probes/node_build_system.schema.json` per `BuildSystemSlice` (ADR-0007 pattern on both `warnings[]` and `errors[]`; `additionalProperties: false` at root + every nested block). Add the additive import line in `src/codegenie/probes/__init__.py`.

Drive Green with the **first four** tests (T-9 contract, T-1 lockfile precedence, T-2 scripts verbatim, T-15 env-strip seam). The remaining 14 land progressively during Refactor — each Red→Green cycle should not require touching code green-ed by an earlier cycle (functional-core helpers are pure → orthogonal).

### Refactor — clean up

- Ensure `_walk_extends`, `_select_package_manager`, `_parse_node_version_output`, and the three `_read_*` extractors are independently importable + unit-test-callable (the test file references them implicitly via integration; an optional `tests/unit/probes/test_node_build_system_pure.py` can table-drive `_parse_node_version_output` for compactness).
- Module docstring explaining the four version sources + the ADR-0001 env-strip implication + the three Open/Closed precedence tuples.
- `mypy --strict` clean; `ruff check` + `ruff format --check`; coverage local report for `node_build_system.py` pasted into the PR body (per cross-cutting concern #6 — floor is 90/80).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/node_build_system.py` | New file — the probe itself. |
| `src/codegenie/schema/probes/node_build_system.schema.json` | New file — `BuildSystemSlice` sub-schema with `additionalProperties: false` at root. |
| `src/codegenie/probes/__init__.py` | Additive import — registers the probe. |
| `tests/unit/probes/test_node_build_system.py` | New test file — eight unit tests. |

## Out of scope

- **Lockfile parsing.** This story does **existence checks only** in the precedence order. S3-05 (`NodeManifestProbe`) parses lockfiles via the three lockfile siblings (S3-01/02/03).
- **Workspaces traversal (per-workspace `tsconfig.json` walks).** Deferred to Phase 2.
- **Fixture `node_typescript_helm/`.** Built in S2-03.
- **Warm-path memo + cache-hit integration tests.** S2-04 and S2-05.
- **`node` adversarial hostile-shim integration test.** Lives in `tests/adv/test_planted_node_on_path_ignored.py` (S5-02). This story tests the env-strip path via a `monkeypatch`-stubbed `run_allowlisted`; the real `$PATH` shim test is S5-02.
- **`node_modules/` walks.** Phase-1 non-goal #4 (`../phase-arch-design.md §"Non-goals"`).
- **Bun-specific quirks** beyond lockfile-precedence priority. The probe knows `"bun"` as a possible `package_manager` value; deeper Bun handling is Phase 2.

## Notes for the implementer

- **Frozen `Probe` ABC — class attributes are `list[str]`, not tuples.** `src/codegenie/probes/base.py:70-73` declares `applies_to_languages: list[str]`, `applies_to_tasks: list[str]`, `requires: list[str]`. The Phase 0 `LanguageDetectionProbe` uses `list[str] = ["*"]`. Tuples will fail `mypy --strict` against the override (LSP-bound) and `tests/unit/test_probe_contract.py` will flag the drift.
- **Import `exec` as `_exec` and call `_exec.run_allowlisted(...)`.** This pins the seam: tests monkeypatch `codegenie.exec.run_allowlisted` and the probe routes through it (AC-12 / T-15). Do **not** `from codegenie.exec import run_allowlisted` — that binds the function at import time and decouples the monkeypatch from the call site. Do **not** call `subprocess.run` / `subprocess.Popen` / `os.system` / `os.popen` directly — `exec.run_allowlisted` is the env-strip seam (ADR-0001).
- **`exec.run_allowlisted` env-strip is the load-bearing defense for ADR-0001.** Do not pass `env=os.environ` anywhere. The S5-02 adversarial test will assert with a sentinel-writing `$PATH` shim that the env-strip holds — if you break it here, S5-02 fails. T-15 in this story unit-tests the import-level seam; S5-02 integration-tests the actual env-strip against a hostile binary.
- **Three module-level precedence tuples are the file-boundary Open/Closed seams.** `_LOCKFILE_PRECEDENCE`, `_BUNDLERS_SORTED`, `_NODE_VERSION_PINNED_SOURCES`. Adding a new lockfile / bundler / version-source is **always** a one-line tuple insertion (+ schema enum bump for `package_manager` / `bundler`); never an edit to selection logic. This mirrors S2-01's `_MONOREPO_PRECEDENCE` pattern.
- **Bundler sort order — alpha, not intentional priority (deferred Phase-2 consideration).** The arch's "deterministic-sorted" prescription is interpreted here as **alpha-sorted** (`esbuild < parcel < rollup < turbopack < vite < webpack`). A Phase-2 case for intentional priority (e.g., `vite` before `esbuild` because vite uses esbuild internally; `next` before `webpack` etc.) is plausible — but encoding it requires a deliberate decision per bundler and is out of scope here. If a future ADR opts in, change `_BUNDLERS_SORTED` to a priority-ordered tuple with an inline rationale comment; the seam is unchanged.
- **The `packageManager` vs lockfile "lockfile wins" rule** (AC-8) is currently a story-level resolution of an arch Open Question (#3 — *recommendation*, not ratified). The reasoning is empirical: the lockfile is the bound contract; `packageManager` is a hint the developer may have set and forgotten. **TODO:** Phase 1.5 or Phase 2 should land an ADR explicitly ratifying this (or flipping it). Downstream consumers (Phase 7 distroless migration) inherit the rule via the warning ID; flipping later would require a Phase 7 migration plan.
- **Phase 1's open-question #9 (probe-version constants) is established by this probe.** Set `version: str = "0.1.0"` as a class attribute. Bump on any future code-change PR to this probe. The convention seeds S3-05 / S4-01 / S4-02 / S4-03.
- **`tsconfig.json#extends` cycle detection uses a `set[Path]` of resolved-absolute paths**, not strings. `"./a.json"` and `"a.json"` resolve to the same absolute path; cycle detection must catch that. T-3's 2-hop parameter case anchors this gotcha.
- **Walker shape — iterative-with-explicit-stack preferred (Rule 11).** `language_detection._walk` is the established walker shape in this codebase. The `_walk_extends` helper can follow the same pattern. A recursive form with `visited: set[Path]` + `depth: int` parameter is admissible at depth-4 cap, but if kept recursive, prefer rebuilding `visited` as a frozenset at each call site rather than mutating one (closes the entire "someone adds a branch that doesn't update visited" regression class).
- **`ParsedManifestMemo` is wired by the coordinator via the S1-08 `content_hash`-keyed adapter.** This probe consumes `ctx.parsed_manifest` as the public seam; do **not** call the memo's `get(...)` directly, and do **not** read `ctx.input_snapshot` here. Edge case 16 (mid-gather mtime change) is owned by the coordinator + memo tests (S1-07 / S1-08), not this probe.
- **`raw/<probe>.json` budget.** This probe has small output; the default 5 MB budget from S1-09 applies and is fine.
- **`os.scandir` is not used here** (S2-05's monkeypatch target is `language_detection.os.scandir`, not this module). Reading lockfile precedence is `Path.is_file()` only — no walks.
- **`mypy --strict` and the `Mapping[str, JSONValue]` types from `parsed_manifest`.** Treat the parsed dict as `Mapping[str, object]` and narrow with `isinstance(..., dict)` / `isinstance(..., str)` / `isinstance(..., list)` checks before using values. A typed shim for `package.json` is overkill in Phase 1; defer to a `TypedDict` only if `mypy --strict` complains in a way you cannot quiet with an `assert isinstance(...)`.
- **`output_artifacts` entries are glob patterns as authored in `package.json#files`, not resolved filesystem paths** (AC-15). Do not glob-expand at this layer — that resolution belongs to a future consumer.
- **Deferred patterns (rule-of-three guard).** Within-file rule-of-three is met by the three precedence tuples; that justifies the in-file extraction. Cross-file rule-of-three is **not** yet met — do **not** extract a shared `probes/_precedence.py` kernel (`first_match(root, precedence) -> (picked, runners_up)`). S3-05's lockfile precedence list is different (no bun for `NodeManifestProbe`); sharing would force a parameterized callable for a 5-line scan in each module. Re-evaluate when a fourth file replicates the shape. Similarly, `LockfileSelection` / `NodeVersionOutcome` tagged unions and a `ParserKind` `Literal` alias are all deferred — each is sound when there is a second consumer.
- **Probe coverage local report.** Per cross-cutting concern #6 in the manifest, paste the per-module coverage percentage for `node_build_system.py` into the PR body. S6-02's ratchet to 90/80 cannot recover if this probe lands below 90 line / 80 branch.
