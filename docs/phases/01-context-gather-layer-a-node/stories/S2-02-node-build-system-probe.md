# Story S2-02 — `NodeBuildSystemProbe`

**Step:** Step 2 — Extend `LanguageDetectionProbe` and ship `NodeBuildSystemProbe`
**Status:** Ready
**Effort:** L
**Depends on:** S1-04 (`jsonc` parser — required by the `tsconfig.json#extends` walker), S1-10 (`node` in `ALLOWED_BINARIES` + sub-schema convention + structlog event constants)
**ADRs honored:** ADR-0001 (`node` in `ALLOWED_BINARIES`), ADR-0002 (consumes `ctx.parsed_manifest`), ADR-0004 (`additionalProperties: false` at sub-schema root), ADR-0007 (warning-ID pattern), ADR-0010 (slice optional at envelope), ADR-0008 (no per-probe sandbox; in-process caps are the defense)

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

- [ ] `src/codegenie/probes/node_build_system.py` defines `class NodeBuildSystemProbe(Probe)` with class attributes per `../phase-arch-design.md §"Component design" #2`: `name="node_build_system"`, `version="0.1.0"`, `tier="base"`, `applies_to_languages=("javascript","typescript")`, `applies_to_tasks=("*",)`, `requires=("language_detection",)`, `timeout_seconds=30`, `declared_inputs` matching the 14-entry list in §"Component design" #2 verbatim.
- [ ] Lockfile-precedence existence check (no parse) selects `package_manager` from `bun.lockb > pnpm-lock.yaml > yarn.lock > package-lock.json`. Multiple lockfiles present → `confidence="low"`, `warnings` contains `"package_manager.multi_lockfile"`, slice's `additional_lockfiles: list[str]` lists the runners-up sorted by precedence.
- [ ] `package.json` is read via `ctx.parsed_manifest(...)` when available; falls back to `safe_json.load(...)` when the memo is `None` (edge case 12). `package.json#scripts` is recorded verbatim into `commands: dict[str, str]`; values are **never** evaluated, executed, or interpolated.
- [ ] `tsconfig.json` is parsed via `parsers.jsonc.load(...)`. `extends` chain is followed at most 4 levels under `repo_root` containment. Depth > 4 → `confidence="medium"`, `warnings` contains `"tsconfig.extends_depth_exceeded"`; cycle detected → `warnings` contains `"tsconfig.extends_cycle"`. The deepest-reached config is recorded in `typescript.resolved_compiler_options`.
- [ ] Node version precedence: `engines.node` → `.nvmrc` → `.node-version` → `.tool-versions`. `engines.node` lands in `node_version_constraint`; the first hit of the latter three lands in `node_version_pinned`. Each source recorded as a literal string; no semver expansion.
- [ ] Optional `node --version` cross-check via `exec.run_allowlisted(["node", "--version"], cwd=repo_root, timeout_s=5)`. Output parsed by regex `^v\d+\.\d+\.\d+`; match → `node_version_resolved_locally: str`; non-match (hostile-shim case, edge case 6) → `node_version_resolved_locally: null`, `warnings` contains `"node.version_unparseable"`, `confidence` **stays high**; binary absent / timeout / `FileNotFoundError` → `node_version_resolved_locally: null`, `confidence` unaffected (no warning required — the binary is optional).
- [ ] `disagreement` warning: if `node_version_pinned` is parseable as semver and `node_version_resolved_locally` is set and they disagree → `warnings` contains `"node.version_declared_resolved_disagree"`; `confidence` stays high (cross-check is informational).
- [ ] Bundler detection by dict-lookup against `dependencies + devDependencies` for `{"webpack","rollup","esbuild","vite","parcel","turbopack"}`; first hit (deterministic-sorted) → `bundler: str`; none → `null`.
- [ ] `packageManager` field handling per Open Implementation Question #3: if `package.json#packageManager` (e.g., `"pnpm@8.6.0"`) disagrees with the lockfile-precedence pick, emit `warnings: ["package_manager.declaration_lockfile_disagree"]`; the **lockfile wins** for `package_manager`. Document the outcome in this file's "Notes for the implementer".
- [ ] `src/codegenie/schema/probes/node_build_system.schema.json` exists; `additionalProperties: false` at root + every nested block (`TypeScriptInfo`); declares the slice **optional** at envelope level (ADR-0010); `warnings[]` uses ADR-0007 pattern constraint.
- [ ] `src/codegenie/probes/__init__.py` imports `NodeBuildSystemProbe` via an explicit additive line; `default_registry.all_probes()` includes it; `for_task("*", frozenset({"typescript"}))` returns a tuple containing it.
- [ ] ADR-0004 extra-field rejection test: synthetic envelope with `{"probes": {"node_build_system": {"extra_field": 1, ...}}}` is rejected with `SchemaValidationError` at JSON Pointer `/probes/node_build_system/extra_field`.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/probes/node_build_system.py`, `pytest tests/unit/probes/test_node_build_system.py` all pass.

## Implementation outline

1. Create `src/codegenie/probes/node_build_system.py`. Subclass `Probe` from `probes/base.py`; declare the class attributes in acceptance criteria.
2. Implement `async def run(self, snapshot, ctx) -> ProbeOutput`:
   - **Lockfile precedence.** Existence check in order; record `package_manager`, `additional_lockfiles`, multi-lockfile warning. No parse.
   - **`package.json` read.** Via memo with fallback. Catch `SizeCapExceeded`, `MalformedJSONError`, `SymlinkRefusedError` → `confidence="low"`, `errors=["package_json.size_cap_exceeded" | …]`, return early with a minimal slice.
   - **TypeScript block.** If `tsconfig.json` exists, call `jsonc.load(tsconfig_path, max_bytes=5*1024*1024)`. Follow `extends` via a small recursive function with a `visited: set[Path]` + `depth: int` parameter; cap at 4. Resolve paths under `repo_root` (`Path.resolve()` + `is_relative_to`). Build `TypeScriptInfo` dict.
   - **Node version.** Read `engines.node` from parsed package.json. Walk `.nvmrc` → `.node-version` → `.tool-versions` for `node` line; first hit wins. Both fields are literal strings.
   - **`node --version` cross-check.** Try `exec.run_allowlisted(["node", "--version"], cwd=snapshot.root, timeout_s=5)`. On success, regex `^v\d+\.\d+\.\d+`. Wrap in `try/except` for `FileNotFoundError`, `TimeoutExpired`, `ExecError`.
   - **Bundler.** Dict-lookup; first hit wins (deterministic sort).
   - **`packageManager` field.** If present in package.json and inconsistent with lockfile-precedence pick → warning.
   - **`output_artifacts`.** Phase 1 leaves empty `[]` — populated by later phase (or by reading `package.json#files`; if cheap, populate from that field). Per `../phase-arch-design.md §"Data model"` it's `list[str]`.
3. Emit `probe.start` / `probe.success` / `probe.parser.cap_exceeded` / `probe.memo.{hit,miss}` (the latter through `ctx.parsed_manifest`'s instrumentation, not this probe directly) — the structlog `parser_kind` field on every parse-related log line.
4. Write `node_build_system.schema.json` per `../phase-arch-design.md §"Data model"` `BuildSystemSlice`. Test the extra-field rejection at the right JSON Pointer.
5. Register the probe via an additive import in `src/codegenie/probes/__init__.py`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/probes/test_node_build_system.py`

Write **eight** red tests, one per behavior contour. Drive Green with the first three; the rest land during Refactor.

```python
# tests/unit/probes/test_node_build_system.py

import asyncio, json
from pathlib import Path

def test_pnpm_lockfile_wins_precedence(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"scripts": {"test": "vitest"}}')
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '6.0'")
    (tmp_path / "package-lock.json").write_text('{"lockfileVersion": 3}')
    out = _run_probe(tmp_path)
    slice_ = out.schema_slice["build_system"]
    assert slice_["package_manager"] == "pnpm"
    assert slice_["additional_lockfiles"] == ["package-lock.json"]
    assert "package_manager.multi_lockfile" in slice_["warnings"]
    assert out.confidence == "low"


def test_scripts_recorded_verbatim_and_never_evaluated(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(json.dumps({
        "scripts": {"test": "vitest", "build": "rm -rf dist && tsc"}
    }))
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '6.0'")
    out = _run_probe(tmp_path)
    assert out.schema_slice["build_system"]["commands"] == {
        "test": "vitest", "build": "rm -rf dist && tsc",
    }


def test_tsconfig_extends_cycle_detected_and_warned(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '6.0'")
    (tmp_path / "tsconfig.json").write_text('{"extends": "./a.json"}')
    (tmp_path / "a.json").write_text('{"extends": "./tsconfig.json"}')
    out = _run_probe(tmp_path)
    assert "tsconfig.extends_cycle" in out.schema_slice["build_system"]["warnings"]


def test_node_version_precedence_engines_beats_nvmrc(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(json.dumps({
        "engines": {"node": ">=20.0.0"},
    }))
    (tmp_path / ".nvmrc").write_text("v18.17.0\n")
    out = _run_probe(tmp_path)
    slice_ = out.schema_slice["build_system"]
    assert slice_["node_version_constraint"] == ">=20.0.0"
    assert slice_["node_version_pinned"] == "v18.17.0"


def test_node_version_hostile_shim_warns_but_stays_high(monkeypatch, tmp_path: Path) -> None:
    # Edge case 6 — output regex fails; confidence stays high.
    _stub_exec_returning(monkeypatch, b"x\x00")
    (tmp_path / "package.json").write_text("{}")
    out = _run_probe(tmp_path)
    slice_ = out.schema_slice["build_system"]
    assert slice_["node_version_resolved_locally"] is None
    assert "node.version_unparseable" in slice_["warnings"]
    assert out.confidence == "high"


def test_node_binary_absent_silently_skipped(monkeypatch, tmp_path: Path) -> None:
    _stub_exec_raising(monkeypatch, FileNotFoundError())
    (tmp_path / "package.json").write_text("{}")
    out = _run_probe(tmp_path)
    assert out.schema_slice["build_system"]["node_version_resolved_locally"] is None
    # Optional — no warning required when binary is just absent
    assert "node.version_unparseable" not in out.schema_slice["build_system"]["warnings"]


def test_package_manager_declaration_disagreement(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"packageManager": "yarn@3.0.0"}')
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '6.0'")
    out = _run_probe(tmp_path)
    slice_ = out.schema_slice["build_system"]
    assert slice_["package_manager"] == "pnpm"  # lockfile wins
    assert "package_manager.declaration_lockfile_disagree" in slice_["warnings"]


def test_sub_schema_rejects_extra_field_under_node_build_system() -> None:
    from codegenie.schema import load_envelope_validator
    envelope = _minimal_envelope_with_node_build_system(extra={"rogue": True})
    with _expect_schema_violation_at("/probes/node_build_system/rogue"):
        load_envelope_validator().validate(envelope)
```

Run all eight; all should be red (`ModuleNotFoundError: codegenie.probes.node_build_system` for the first seven, schema-missing for the eighth). Confirm red, commit, then Green.

### Green — make it pass

Add `src/codegenie/probes/node_build_system.py`:

- Class attributes per §"Component design" #2.
- `run()` implementation in this order: lockfile precedence → package.json read (memo path) → tsconfig walk → node-version chain → `node --version` subprocess (try/except) → bundler dict-lookup → packageManager disagreement.
- Lift the warning IDs into a module-level frozenset; assert at import-time they match the ADR-0007 pattern.

Write `src/codegenie/schema/probes/node_build_system.schema.json` per `BuildSystemSlice`. Add an explicit additive import line in `src/codegenie/probes/__init__.py`.

Just enough to green the eight tests; no docstring, no `output_artifacts` polish.

### Refactor — clean up

- Extract `_walk_extends(tsconfig_path, repo_root) -> (resolved, warnings)` into a private function; mypy-strict-clean.
- Module docstring explaining the four version sources + the ADR-0001 env-strip implication.
- Populate `output_artifacts` from `package.json#files` if present (cheap; falls out of the parsed dict).
- Confirm `mypy --strict` clean; `ruff check`; coverage local report for `node_build_system.py` reported in the PR body (per cross-cutting concern #6).

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

- **The Open Implementation Question #3 outcome — recorded here per the manifest:** when `package.json#packageManager` disagrees with the lockfile, **the lockfile wins** for `package_manager`. The `packageManager` value is recorded only via the warning `package_manager.declaration_lockfile_disagree`. The reasoning is empirical — the lockfile is the bound contract; `packageManager` is a hint the developer may have set and forgotten. This is the rule consumers downstream (Phase 7 distroless migration) inherit; do not flip it later without a Phase 2+ ADR.
- **Phase 1's open-question #9 (probe-version constants) is established by this probe.** Set `version: str = "0.1.0"` as a class attribute. Bump on any future code-change PR to this probe. The convention seeds S3-05 / S4-01 / S4-02 / S4-03.
- **`exec.run_allowlisted` env-strip is the load-bearing defense for ADR-0001.** Do not pass `env=os.environ` anywhere; do not subprocess.Popen `node` directly; always go through `exec.run_allowlisted`. The S5-02 adversarial test will assert with a sentinel-writing shim that the env-strip holds — if you break it here, S5-02 fails.
- **`tsconfig.json#extends` cycle detection uses a `set[Path]` of resolved-absolute paths**, not strings. `"./a.json"` and `"a.json"` resolve to the same path; cycle detection must catch that.
- **`raw/<probe>.json` budget.** This probe has small output; the default 5 MB budget from S1-09 applies and is fine.
- **`os.scandir` is not used here** (S2-05's monkeypatch target is `language_detection.os.scandir`, not this module). Reading lockfile-precedence is `Path.exists()` only — no walks.
- **`mypy --strict` and the `Mapping[str, JSONValue]` types from `parsed_manifest`.** Treat the parsed dict as `Mapping[str, object]` and narrow with `isinstance(..., dict)` / `isinstance(..., str)` checks before using values. A typed shim for `package.json` is overkill in Phase 1; defer to a `TypedDict` only if `mypy --strict` complains in a way you cannot quiet with an `assert isinstance(...)`.
- **Probe coverage local report.** Per cross-cutting concern #6 in the manifest, paste the per-module coverage percentage for `node_build_system.py` into the PR body. S6-02's ratchet to 90/80 cannot recover if this probe lands below 90 line / 80 branch.
