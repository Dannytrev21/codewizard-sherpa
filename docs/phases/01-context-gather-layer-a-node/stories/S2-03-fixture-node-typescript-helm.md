# Story S2-03 — Fixture `node_typescript_helm/`

**Step:** Step 2 — Extend `LanguageDetectionProbe` and ship `NodeBuildSystemProbe`
**Status:** Done (GREEN 2026-05-14 — see `_attempts/S2-03.md`)
**Effort:** S
**Depends on:** S2-01 (`LanguageDetectionProbe` extension consumes the fixture's `package.json` + `turbo.json`/workspaces if present), S2-02 (`NodeBuildSystemProbe` consumes the fixture's `package.json`, `pnpm-lock.yaml`, `.nvmrc`, `tsconfig.json`)
**ADRs honored:** ADR-0004 (per-probe sub-schema strictness — the fixture's `deploy/chart/` triad must produce a `deployment` slice that respects `additionalProperties: false`), ADR-0010 (Layer A slices optional at envelope — nothing in this fixture forces non-optional probes), ADR-0012 (multi-environment Helm as `environments: list` with nullable primary `image_reference` — `values-prod.yaml` is the canonical second environment that exercises the list shape).

## Validation notes (2026-05-14)

Hardened by phase-story-validator (scheduled task: `story-validation-corrector`). Verdict: **HARDENED**.

Summary of changes:

- **Plus 12 ACs / -1 ACs** (12 → 23). Original ACs preserved when verifiable; thin ones split (e.g., AC-2 fanned into AC-2a–c for `package.json` shape + the *absence* of `packageManager`); 8 entirely new ACs added for parseability invariants, closed-set complement, forbidden subpaths, and the README-references-every-file rule.
- **Test-Quality.** Replaced the loose `REQUIRED_FILES: tuple[str, ...]` pattern with a typed `_FileSpec` NamedTuple + `_FILE_SPECS: tuple[_FileSpec, ...]` module-level constant in the shape test — same Open/Closed-at-file-boundary precedent S2-01 set with `_MONOREPO_PRECEDENCE` and S2-02 set with `_LOCKFILE_PRECEDENCE`. Adding a fixture file = one tuple entry insertion + zero edits to the parametrized test body. Each `_FileSpec` carries a typed `consumers` tuple (`Literal[<six Phase-1 probe names>]`, `mypy --strict` catches typos) and an optional `content_checks` tuple of pure predicates, each independently unit-testable.
- **Coverage.** Added ACs that (a) every parseable fixture file *actually parses* through the parser its consuming probe will use (`safe_json` / `safe_yaml` / `jsonc`) — without these, malformed bytes pass the original existence-only shape test and fail opaquely in S2-04 / S5-05; (b) the fixture tree is **closed-set** (REQUIRED files plus nothing else under tracked paths) — without this, a stray file silently dirties the S6-01 golden; (c) forbidden subpaths (`node_modules/`, `.codegenie/`, `.gitignore`) are absent (the original story had this in Notes-for-implementer only); (d) `package.json` has no `packageManager` field (lifted from Notes to a positive observable); (e) `tsconfig.json` actually contains both a `//` line comment AND a `/* */` block comment (the load-bearing reason the file exists — exercises `parsers/jsonc.py`'s state machine on the warm path; the original story had this in Notes only).
- **Design-Pattern lifts (per CLAUDE.md "Extension by addition" load-bearing commitment).** `_FILE_SPECS` is the **single source of truth** for the shape test, the README cross-reference test, and (in Phase 2) the per-fixture golden manifest. The `consumers` field uses a `Literal` closed set over the six Phase-1 probe names, which makes the README mapping mechanically verifiable rather than prose-only.
- **Consistency.** Added ADR-0012 to "ADRs honored" (`values-prod.yaml` is the load-bearing multi-env exemplar; the original story referenced the ADR's *effect* in AC-10 but did not cite the ADR). Flagged the `engines.node = ">=20.0.0"` vs. `.nvmrc = "v20.11.0"` vs. runtime-`node --version` interaction as a S6-01 golden-determinism concern (the cross-check is ADR-0001-gated and golden regen runs with it disabled per phase-arch-design.md §"Golden files"; recorded in Notes-for-implementer, NOT an AC for this story because the deterministic-golden invariant lives at S6-01).
- **Deferred (rule-of-three guard, per Rule 2).** A generic `tests/fixtures/_shape_test_kernel.py` that parametrizes over `_FILE_SPECS` from any fixture is **not** introduced here — only one fixture in Phase 1 has a shape test (`node_typescript_helm/`). Re-evaluate at the third fixture (S5-04 lands `node_monorepo_turbo/` + `non_node_go/` shape tests — that *is* the third+fourth consumer; the kernel lifts then). Documented in Notes-for-implementer.

Full audit log: see [`_validation/S2-03-fixture-node-typescript-helm.md`](_validation/S2-03-fixture-node-typescript-helm.md).

## Context

`node_typescript_helm/` is the **canonical Phase-1 fixture**. It is reused by:

- The warm-path memo integration test (S2-04) — asserts `framework_hints == ["express"]` and exactly one memo hit + one memo miss across the two probes in Step 2.
- The cache-hit-on-real-repo integration test (S2-05, extended in S5-05) — load-bearing Phase 1 exit criterion #2.
- The layer-A end-to-end integration test (S5-05, `test_layer_a_end_to_end.py`) — load-bearing Phase 1 exit criterion #1.
- The golden file anchor (S6-01) — `tests/golden/node_typescript_helm.repo-context.yaml`.

Because the fixture flows into the golden, **its contents are part of the contract**. Adding a file to it later changes the golden bytes and forces a regen-script run. Keep the fixture minimal: only the files Step 2 + Step 5 + Step 6 collectively need.

The fixture's name — `node_typescript_helm` — telegraphs the four dimensions it exercises: Node, TypeScript, pnpm, Helm. Step 2 cares about Node + TS + pnpm; the Helm chart is added so S5-05's `test_layer_a_end_to_end.py` can populate the `deployment` slice without inventing a second fixture. CI workflow + Helm chart contents are minimal — enough for `CIProbe` and `DeploymentProbe` (Step 4) to produce a populated slice in Step 5.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Testing strategy" → "Fixture portfolio"` — the five-fixture list this fixture anchors.
  - `../phase-arch-design.md §"Component design" #1` (frameworks dict, monorepo markers — `express` is the seed entry exercised here).
  - `../phase-arch-design.md §"Component design" #2` (lockfile-precedence + `.nvmrc` + `tsconfig.json`).
  - `../phase-arch-design.md §"Component design" #6` (Helm chart shape — `Chart.yaml` + `values*.yaml`).
- **Phase ADRs:** none directly. The fixture is data, not behavior.
- **Source design:**
  - `../../../localv2.md §5.1 A1–A6` — every Layer A slice this fixture eventually populates.
- **Existing code:**
  - `tests/fixtures/` (Phase 0 fixtures: `js_only/`, `polyglot/`, `empty_repo/`) for the directory-style precedent.
  - The Phase 0 `js_only/` fixture's README, for the documentation convention.

## Goal

`tests/fixtures/node_typescript_helm/` exists with the minimal viable file tree: `package.json` (with `express` in `dependencies` and a TS-flavored scripts block), `pnpm-lock.yaml`, `tsconfig.json`, `.nvmrc`, a single `src/index.ts`, a single `.github/workflows/ci.yml`, and a `deploy/chart/{Chart.yaml,values.yaml,values-prod.yaml}` triad. The fixture's `README.md` documents what each file is for and which probe consumes it.

## Acceptance criteria

**Fixture tree shape**

- [x] **AC-1.** `tests/fixtures/node_typescript_helm/` directory exists.
- [x] **AC-2a — `package.json` shape.** Declares `"name": "node-typescript-helm"`, `"version": "0.0.1"`, `"dependencies": {"express": "^4.18.2"}`, `"devDependencies": {"typescript": "^5.3.0", "vitest": "^1.0.0"}`, `"engines": {"node": ">=20.0.0"}`, `"scripts": {"build": "tsc -p .", "test": "vitest run", "start": "node dist/index.js"}`.
- [x] **AC-2b — `package.json` parseability.** `parsers.safe_json.load(pkg_path, max_bytes=50 * 1024 * 1024)` returns the mapping above with no exception. The `ParsedManifestMemo` (Component 3) consumes this byte-for-byte; a malformed `package.json` here cascades opaquely through every Phase-1 Node probe.
- [x] **AC-2c — no `packageManager` field.** `"packageManager"` is **absent** (not `null`) from `package.json`. Setting it would trip the S2-02 `package_manager.declaration_lockfile_disagree` warning path (or, in the agreement case, pollute the slice for the golden). The S2-02 unit tests cover both paths; this fixture must stay in the silent-agree-by-absence regime.
- [x] **AC-3 — `pnpm-lock.yaml`.** Exists with a minimal valid pnpm v6 lockfile header (`lockfileVersion: '6.0'`). `parsers.safe_yaml.load(lock_path, max_bytes=50 * 1024 * 1024)` returns a mapping with no exception (this is the load-bearing invariant — S2-04's warm-path memo and S5-05's e2e BOTH parse this file). Contents minimal; not required to resolve `express` (S3-05 native-module catalog cross-reference uses a different fixture).
- [x] **AC-4a — `tsconfig.json` shape.** Valid JSONC; declares `compilerOptions.target: "ES2022"`, `compilerOptions.module: "ESNext"`, `compilerOptions.strict: true`, no `extends`.
- [x] **AC-4b — `tsconfig.json` comments load-bearing.** The file contains **at least one `//` line comment AND at least one `/* */` block comment**. This is the load-bearing reason the file exists in this shape: it exercises `parsers/jsonc.py`'s state-machine comment stripper on the warm integration path. Without comments, `tsconfig.json` parses via plain JSON and the `jsonc.py` code path stays untested in S5-05.
- [x] **AC-4c — `tsconfig.json` parseability.** `parsers.jsonc.load(ts_path, max_bytes=10 * 1024 * 1024)` returns the mapping above with no exception.
- [x] **AC-5 — `.nvmrc`.** Exists with content `v20.11.0\n` (exact: one line, trailing LF). Exercises the `engines.node` → `.nvmrc` precedence step in S2-02's `_NODE_VERSION_PINNED_SOURCES` chain.
- [x] **AC-6 — `src/index.ts`.** Exists with a trivial valid TS body (one `import express from "express"` + a 3-line server stub) — bumps `LanguageDetectionProbe`'s extension walk's `.ts` count to exactly 1.
- [x] **AC-7 — `.github/workflows/ci.yml`.** Exists with a single `build` job + a `run: pnpm install && pnpm test` step. `parsers.safe_yaml.load(workflow_path, max_bytes=10 * 1024 * 1024)` returns a mapping with no exception (populates `CIProbe`'s slice in S5-05).
- [x] **AC-8 — `deploy/chart/Chart.yaml`.** Declares `name: node-typescript-helm`, `version: "0.0.1"`, `apiVersion: v2` (the modern Helm chart shape; matches what `DeploymentProbe` parses in Step 4). `parsers.safe_yaml.load(chart_path, max_bytes=10 * 1024 * 1024)` returns a mapping with no exception.
- [x] **AC-9 — `deploy/chart/values.yaml`.** Declares `image.repository: ghcr.io/example/node-typescript-helm`, `image.tag: "0.0.1"`. `parsers.safe_yaml.load(values_path, max_bytes=10 * 1024 * 1024)` returns a mapping with no exception.
- [x] **AC-10 — `deploy/chart/values-prod.yaml` (ADR-0012).** Declares `image.tag: "prod-0.0.1"` override (one alternate environment). Exercises the `environments: list[EnvironmentEntry]` path in `DeploymentProbe` per ADR-0012; the filename stem `prod` becomes the `EnvironmentEntry.name`. `parsers.safe_yaml.load(values_prod_path, max_bytes=10 * 1024 * 1024)` returns a mapping with no exception.
- [x] **AC-11 — `README.md`.** Lists every file in `_FILE_SPECS` (AC-15) by its `relpath` and names every probe in its `consumers` tuple. References `../../docs/phases/01-context-gather-layer-a-node/phase-arch-design.md` for the canonical slice descriptions.

**Closed-set invariants (extension-by-addition gate)**

- [x] **AC-12 — no fixture byte equals a production source.** No file in `tests/fixtures/node_typescript_helm/` is byte-identical to a checked-in production source file under `src/codegenie/`. Copying `src/codegenie/...` content into the fixture is forbidden — fixtures must be self-contained.
- [x] **AC-13 — forbidden subpaths.** None of `node_modules/`, `.codegenie/`, `.gitignore`, `dist/`, `coverage/` exist inside the fixture tree (these would either pollute the golden, swallow the integration test's `.codegenie/` writes, or break the test-isolation invariant).
- [x] **AC-14 — closed-set complement.** Walking `tests/fixtures/node_typescript_helm/` (excluding `__pycache__/`, `.pytest_cache/`, and dotfiles created by editors) yields **exactly** the set `{spec.relpath for spec in _FILE_SPECS}`. A stray file added by mistake (or a missed deletion) fails this test before it can dirty the S6-01 golden silently.

**`_FILE_SPECS` SSoT (Design-Pattern: closed-set typed manifest)**

- [x] **AC-15 — `_FILE_SPECS` module-level typed manifest in the shape test.** `tests/unit/test_fixture_node_typescript_helm_shape.py` declares a module-level `_FILE_SPECS: tuple[_FileSpec, ...]` where:
  - `_FileSpec` is a `typing.NamedTuple` with fields `(relpath: str, consumers: tuple[_ProbeName, ...], parser: _ParserKind | None, content_checks: tuple[Callable[[Any], None], ...])`.
  - `_ProbeName = Literal["language_detection", "node_build_system", "node_manifest", "ci", "deployment", "test_inventory"]` — closed set of the six Phase-1 probe names. `mypy --strict` catches typos.
  - `_ParserKind = Literal["safe_json", "safe_yaml", "jsonc", "text"]` — closed set matching `parsers/` modules + a `"text"` sentinel for non-parseable files (`.nvmrc`, `src/index.ts`, `README.md`).
  - `parser=None` for files whose contents are inert (none in Phase 1; reserved for future fixtures that ship opaque blobs).
  - `content_checks` is a tuple of pure predicate functions; each takes the parsed structure (or the raw text, for `_ParserKind == "text"`) and raises `AssertionError` with a clear message.
  - The tuple's length is exactly the number of files in REQUIRED_FILES; adding a fixture file = one tuple entry insertion + zero edits to the parametrized shape-test body.
- [x] **AC-16 — `_FILE_SPECS` drives the parametrized shape test.** The shape test is parametrized over `_FILE_SPECS` (`@pytest.mark.parametrize("spec", _FILE_SPECS, ids=lambda s: s.relpath)`) and asserts, for each spec: (a) the file exists; (b) if `spec.parser` is not None, the file parses cleanly via the named parser (`safe_json` / `safe_yaml` / `jsonc`); (c) every `content_check` passes. An off-by-one mutation that drops a single content check from one file fails exactly one test case, with the failing path in the `pytest -v` output.
- [x] **AC-17 — README references every `_FILE_SPECS.relpath`.** A separate test reads `README.md` and asserts every `spec.relpath` appears literally in the text **and** every probe name in `spec.consumers` appears in the README's prose. README drift fails the test before the next implementer reads stale docs.
- [x] **AC-18 — `_ProbeName` is the Phase-1 closed set.** A test asserts `set(get_args(_ProbeName)) == {"language_detection", "node_build_system", "node_manifest", "ci", "deployment", "test_inventory"}`. Phase 2 adds layers B–G — extending this set is a deliberate edit. The `Literal` is the contract.

**Determinism and audit hygiene**

- [x] **AC-19 — LF line endings + final newline.** Every text file in the fixture round-trips through `git diff` cleanly: UTF-8, LF endings (no CRLF), trailing newline. The shape test asserts each text file's bytes end with `b"\n"` and contain no `b"\r"`.
- [x] **AC-20 — `mypy --strict` clean.** The shape test file and `_FileSpec` / `_ProbeName` / `_ParserKind` definitions pass `mypy --strict`. No `Any`, no untyped helpers.
- [x] **AC-21 — `tests/unit/test_fixture_node_typescript_helm_shape.py` exists** with the four parametrized / static tests above.
- [x] **AC-22 — gather smoke (manual).** `codegenie gather tests/fixtures/node_typescript_helm/` (after S2-01 + S2-02 land) completes with exit 0 and produces no probe-crash errors in the audit log. **This is a developer-side smoke check, not a CI test** — the real load-bearing assertions live in S2-04 / S2-05 / S5-05.
- [x] **AC-23 — Notes-for-implementer guidance respected.** The fixture intentionally contains *no* extra files for "completeness." Every byte of every file is justified by exactly one downstream consumer (named in `_FILE_SPECS[i].consumers`).

## Implementation outline

1. `mkdir -p tests/fixtures/node_typescript_helm/{src,deploy/chart,.github/workflows}`.
2. Write `tests/unit/test_fixture_node_typescript_helm_shape.py` first (TDD red). Land the `_FileSpec` / `_ProbeName` / `_ParserKind` typed manifest module-level. The tuple `_FILE_SPECS` lists every fixture file the story prescribes; each entry's `content_checks` enumerate the AC-2a / AC-4a / AC-4b / AC-7 / AC-8 / AC-9 / AC-10 content invariants as pure predicate functions defined module-level. All tests fail red because the fixture tree does not yet exist.
3. Write each fixture file per `_FILE_SPECS` content checks. Keep contents minimal — every byte ends up in the golden.
4. Run `pnpm install` on a scratch directory with the same `package.json` to obtain a real pnpm-v6 lockfile header **only if necessary** — otherwise, copy the minimal `lockfileVersion: '6.0'` shape from a reference pnpm lockfile and verify it parses via `safe_yaml.load`. Strip irrelevant metadata to keep the byte count small.
5. Write `tests/fixtures/node_typescript_helm/README.md` — table of `relpath` → consuming probe(s); references the arch design doc. The README itself is tested (AC-17), so drafts that drift fail loud.
6. Run the shape test (`pytest tests/unit/test_fixture_node_typescript_helm_shape.py -v`). All cases pass green.
7. Run `codegenie gather` against the fixture locally **before** committing to verify no probe crashes on this fixture. (This is a smoke check, not a test — the real assertion lives in S2-04 / S2-05 / S5-05.)

## TDD plan — red / green / refactor

### Test helpers preamble (preamble lives at module top of the shape test)

```python
# tests/unit/test_fixture_node_typescript_helm_shape.py
"""Shape test for tests/fixtures/node_typescript_helm/ — the Phase-1 canonical fixture.

`_FILE_SPECS` is the single source of truth for which files the fixture contains,
which probes consume each, and which content invariants each file must satisfy.
Adding a fixture file: one `_FileSpec` entry insertion + zero edits to the parametrized
test bodies. The same `Literal[...] _ProbeName` closed set is enforced both at
`mypy --strict` (typo-resistance) AND at runtime (AC-18).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Literal, NamedTuple, get_args

import pytest

from codegenie.parsers import jsonc, safe_json, safe_yaml

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "node_typescript_helm"

_ProbeName = Literal[
    "language_detection",
    "node_build_system",
    "node_manifest",
    "ci",
    "deployment",
    "test_inventory",
]

_ParserKind = Literal["safe_json", "safe_yaml", "jsonc", "text"]


class _FileSpec(NamedTuple):
    relpath: str
    consumers: tuple[_ProbeName, ...]
    parser: _ParserKind | None
    content_checks: tuple[Callable[[Any], None], ...]


# --- Pure content predicates (each independently unit-testable) -----------------

def _pkg_declares_express(pkg: dict[str, Any]) -> None:
    assert pkg.get("name") == "node-typescript-helm"
    assert pkg.get("version") == "0.0.1"
    assert pkg.get("dependencies", {}).get("express") == "^4.18.2"
    assert pkg.get("devDependencies", {}).get("typescript") == "^5.3.0"
    assert pkg.get("devDependencies", {}).get("vitest") == "^1.0.0"
    assert pkg.get("engines", {}).get("node") == ">=20.0.0"
    assert pkg.get("scripts", {}).get("build") == "tsc -p ."

def _pkg_omits_package_manager(pkg: dict[str, Any]) -> None:
    # AC-2c — must be absent, not None
    assert "packageManager" not in pkg, (
        "`packageManager` field would trip the S2-02 package_manager.declaration_lockfile_disagree path "
        "and dirty the S6-01 golden; this fixture must stay in the silent-agree-by-absence regime"
    )

def _pnpm_lock_header(lock: dict[str, Any]) -> None:
    assert lock.get("lockfileVersion") == "6.0"

def _tsconfig_shape(ts: dict[str, Any]) -> None:
    co = ts.get("compilerOptions", {})
    assert co.get("target") == "ES2022"
    assert co.get("module") == "ESNext"
    assert co.get("strict") is True
    assert "extends" not in ts

def _tsconfig_has_both_comment_styles(raw_bytes: bytes) -> None:
    # AC-4b — exercises jsonc.py's state machine on the warm path
    text = raw_bytes.decode("utf-8")
    assert "//" in text, "tsconfig.json must contain at least one // line comment"
    assert "/*" in text and "*/" in text, "tsconfig.json must contain at least one /* */ block comment"

def _nvmrc_exact(raw_bytes: bytes) -> None:
    assert raw_bytes == b"v20.11.0\n", f".nvmrc must be exactly b'v20.11.0\\n', got {raw_bytes!r}"

def _index_ts_imports_express(raw_bytes: bytes) -> None:
    text = raw_bytes.decode("utf-8")
    assert 'import express from "express"' in text

def _ci_single_build_job(workflow: dict[str, Any]) -> None:
    jobs = workflow.get("jobs", {})
    assert set(jobs.keys()) == {"build"}, f"expected exactly one job named 'build', got {set(jobs.keys())}"
    steps = jobs["build"].get("steps", [])
    runs = [s.get("run") for s in steps if "run" in s]
    assert "pnpm install && pnpm test" in runs

def _chart_apiversion_v2(chart: dict[str, Any]) -> None:
    assert chart.get("apiVersion") == "v2"
    assert chart.get("name") == "node-typescript-helm"
    assert chart.get("version") == "0.0.1"

def _values_image(values: dict[str, Any]) -> None:
    img = values.get("image", {})
    assert img.get("repository") == "ghcr.io/example/node-typescript-helm"
    assert img.get("tag") == "0.0.1"

def _values_prod_image_override(values: dict[str, Any]) -> None:
    assert values.get("image", {}).get("tag") == "prod-0.0.1"


# --- The single source of truth -------------------------------------------------

_FILE_SPECS: tuple[_FileSpec, ...] = (
    _FileSpec("package.json", ("language_detection", "node_build_system", "node_manifest", "test_inventory"),
              "safe_json", (_pkg_declares_express, _pkg_omits_package_manager)),
    _FileSpec("pnpm-lock.yaml", ("node_build_system", "node_manifest"),
              "safe_yaml", (_pnpm_lock_header,)),
    _FileSpec("tsconfig.json", ("node_build_system",),
              "jsonc", (_tsconfig_shape,)),
    _FileSpec(".nvmrc", ("node_build_system",), "text", (_nvmrc_exact,)),
    _FileSpec("src/index.ts", ("language_detection",), "text", (_index_ts_imports_express,)),
    _FileSpec(".github/workflows/ci.yml", ("ci",), "safe_yaml", (_ci_single_build_job,)),
    _FileSpec("deploy/chart/Chart.yaml", ("deployment",), "safe_yaml", (_chart_apiversion_v2,)),
    _FileSpec("deploy/chart/values.yaml", ("deployment",), "safe_yaml", (_values_image,)),
    _FileSpec("deploy/chart/values-prod.yaml", ("deployment",), "safe_yaml", (_values_prod_image_override,)),
    _FileSpec("README.md", (), "text", ()),  # consumers tuple intentionally empty — README documents others
)

# tsconfig.json gets an extra raw-bytes check (AC-4b) separately because content_checks
# is parameterized over the parsed structure; raw-bytes checks live in their own test.
```

### Red — write the failing test first

The five parametrized tests + AC-18 contract test + AC-13 forbidden-subpath test + AC-14 closed-set test all fail red because the fixture tree does not yet exist (each parametrized case raises `FileNotFoundError` or `AssertionError`). Confirm red, commit a marker, then Green.

### Green — make it pass

Create the directory tree + each file per `_FILE_SPECS` content checks. Verify every test goes green.

The full test surface:

```python
# --- Tests parametrized over _FILE_SPECS ----------------------------------------

@pytest.mark.parametrize("spec", _FILE_SPECS, ids=lambda s: s.relpath)
def test_fixture_file_exists(spec: _FileSpec) -> None:
    """AC-1, AC-16(a) — every spec'd file is present."""
    assert (_FIXTURE / spec.relpath).is_file(), f"missing: {spec.relpath}"

@pytest.mark.parametrize("spec", _FILE_SPECS, ids=lambda s: s.relpath)
def test_fixture_file_parses(spec: _FileSpec) -> None:
    """AC-2b/AC-3/AC-4c/AC-7/AC-8/AC-9/AC-10, AC-16(b) — file parses cleanly."""
    if spec.parser is None or spec.parser == "text":
        return
    path = _FIXTURE / spec.relpath
    parsers = {"safe_json": safe_json.load, "safe_yaml": safe_yaml.load, "jsonc": jsonc.load}
    parsers[spec.parser](path, max_bytes=50 * 1024 * 1024)  # raises on malformed

@pytest.mark.parametrize("spec", _FILE_SPECS, ids=lambda s: s.relpath)
def test_fixture_file_content_invariants(spec: _FileSpec) -> None:
    """AC-2a/AC-4a/AC-5/AC-6/AC-7/AC-8/AC-9/AC-10, AC-16(c) — every content_check passes."""
    if not spec.content_checks:
        return
    path = _FIXTURE / spec.relpath
    if spec.parser == "text" or spec.parser is None:
        payload: Any = path.read_bytes()
    elif spec.parser == "safe_json":
        payload = safe_json.load(path, max_bytes=50 * 1024 * 1024)
    elif spec.parser == "safe_yaml":
        payload = safe_yaml.load(path, max_bytes=50 * 1024 * 1024)
    elif spec.parser == "jsonc":
        payload = jsonc.load(path, max_bytes=10 * 1024 * 1024)
    for check in spec.content_checks:
        check(payload)

@pytest.mark.parametrize("spec", _FILE_SPECS, ids=lambda s: s.relpath)
def test_fixture_file_line_endings(spec: _FileSpec) -> None:
    """AC-19 — LF endings, no CRLF, trailing newline on text-like files."""
    raw = (_FIXTURE / spec.relpath).read_bytes()
    assert b"\r" not in raw, f"{spec.relpath} contains CR — must be LF-only"
    if spec.parser in ("safe_json", "safe_yaml", "jsonc", "text"):
        assert raw.endswith(b"\n"), f"{spec.relpath} must end with LF"


# --- AC-4b: tsconfig.json has both comment styles --------------------------------

def test_tsconfig_has_both_comment_styles() -> None:
    _tsconfig_has_both_comment_styles((_FIXTURE / "tsconfig.json").read_bytes())


# --- AC-13: forbidden subpaths absent -------------------------------------------

@pytest.mark.parametrize("forbidden", [
    "node_modules", ".codegenie", ".gitignore", "dist", "coverage",
])
def test_no_forbidden_subpaths(forbidden: str) -> None:
    assert not (_FIXTURE / forbidden).exists(), (
        f"{forbidden!r} must not exist in this fixture — would either pollute the golden "
        f"or break test isolation"
    )


# --- AC-14: closed-set complement ------------------------------------------------

_FIXTURE_NOISE_NAMES = frozenset({"__pycache__", ".pytest_cache", ".DS_Store"})

def _enumerate_tracked(root: Path) -> set[str]:
    out: set[str] = set()
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        if any(part in _FIXTURE_NOISE_NAMES or part.startswith(".pytest") for part in p.relative_to(root).parts):
            continue
        out.add(str(p.relative_to(root)))
    return out

def test_fixture_tree_is_closed_set() -> None:
    """AC-14 — REQUIRED_FILES is exhaustive. A stray file fails before it can dirty the S6-01 golden."""
    expected = {spec.relpath for spec in _FILE_SPECS}
    actual = _enumerate_tracked(_FIXTURE)
    extra = actual - expected
    missing = expected - actual
    assert not extra and not missing, f"extra files: {sorted(extra)}; missing files: {sorted(missing)}"


# --- AC-17: README references every spec.relpath + every consumer ----------------

def test_readme_references_every_spec() -> None:
    readme_text = (_FIXTURE / "README.md").read_text()
    for spec in _FILE_SPECS:
        if spec.relpath == "README.md":
            continue
        assert spec.relpath in readme_text, f"README missing reference to {spec.relpath}"
        for consumer in spec.consumers:
            assert consumer in readme_text, (
                f"README missing consumer {consumer!r} for {spec.relpath}"
            )


# --- AC-18: _ProbeName Literal is the Phase-1 closed set -------------------------

def test_probe_name_literal_matches_phase_1_closed_set() -> None:
    assert set(get_args(_ProbeName)) == {
        "language_detection", "node_build_system", "node_manifest",
        "ci", "deployment", "test_inventory",
    }


# --- AC-12: no fixture file byte-identical to a production source -----------------

def test_fixture_bytes_not_copied_from_production_sources() -> None:
    """AC-12 — defensive: a fixture file must not duplicate src/codegenie/* bytes."""
    src_root = Path(__file__).parent.parent.parent / "src" / "codegenie"
    production_hashes: dict[bytes, Path] = {}
    if src_root.exists():
        for p in src_root.rglob("*.py"):
            production_hashes[p.read_bytes()] = p
    for spec in _FILE_SPECS:
        fixture_bytes = (_FIXTURE / spec.relpath).read_bytes()
        assert fixture_bytes not in production_hashes, (
            f"{spec.relpath} is byte-identical to {production_hashes.get(fixture_bytes)} — "
            f"fixtures must be self-contained"
        )
```

### Mutation-resistance witness table

Each AC has at least one TDD test that *fails* if a wrong implementation is swapped in. Worked mutations:

| Mutation | Test that catches it |
|---|---|
| Drop `express` from `package.json#dependencies` | `test_fixture_file_content_invariants[package.json]` via `_pkg_declares_express` |
| Add `"packageManager": "pnpm@8.6.0"` to `package.json` | `test_fixture_file_content_invariants[package.json]` via `_pkg_omits_package_manager` |
| Set `pnpm-lock.yaml` `lockfileVersion: '5.0'` | `test_fixture_file_content_invariants[pnpm-lock.yaml]` via `_pnpm_lock_header` |
| Remove the `/* */` block comment from `tsconfig.json` (regression — would silently skip `jsonc.py`'s state machine in S5-05) | `test_tsconfig_has_both_comment_styles` |
| Add a stray `notes.md` to the fixture (would dirty S6-01 golden silently) | `test_fixture_tree_is_closed_set` |
| Add `node_modules/lodash/package.json` (or similar — common autocomplete mistake) | `test_no_forbidden_subpaths[node_modules]` |
| README drops the `deployment` consumer reference | `test_readme_references_every_spec` |
| CRLF line endings sneak in via Windows editor | `test_fixture_file_line_endings[*]` |
| Implementer adds a 7th Phase-1 probe name to `_ProbeName` (Phase-2 sneak-in) | `test_probe_name_literal_matches_phase_1_closed_set` |
| `values-prod.yaml` gets `image.tag: "0.0.1"` (no override — would silently nullify the multi-env test in S5-05) | `test_fixture_file_content_invariants[deploy/chart/values-prod.yaml]` via `_values_prod_image_override` |

### Refactor — clean up

- Review every file byte for incidental non-determinism (trailing whitespace, BOM, CRLF). AC-19 enforces LF + final newline.
- The `_FILE_SPECS` tuple is the **single source of truth**. Future fixture-shape additions: insert a new `_FileSpec` entry, write the content_check predicate, done. **No edits to the parametrized test bodies.**
- `tests/fixtures/node_typescript_helm/README.md` is curated and **mechanically verified by AC-17** — the file-by-file table is for the *next implementer* who debugs a golden-file mismatch.
- `mypy --strict` clean over the whole shape-test file (AC-20). No `Any` outside the explicit `payload: Any` parser-dispatch line; no untyped helpers.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/node_typescript_helm/package.json` | Canonical Phase-1 fixture: declares `express`, scripts, `engines.node`. |
| `tests/fixtures/node_typescript_helm/pnpm-lock.yaml` | Lockfile-precedence pick → `pnpm`. |
| `tests/fixtures/node_typescript_helm/tsconfig.json` | Exercises `jsonc.py` parsing path. |
| `tests/fixtures/node_typescript_helm/.nvmrc` | Exercises Node-version precedence (`.nvmrc` second). |
| `tests/fixtures/node_typescript_helm/src/index.ts` | Bumps `language_detection.counts.typescript` to ≥ 1. |
| `tests/fixtures/node_typescript_helm/.github/workflows/ci.yml` | Populates `CIProbe` in S5-05. |
| `tests/fixtures/node_typescript_helm/deploy/chart/Chart.yaml` | Populates `DeploymentProbe.type == "helm"` in S5-05. |
| `tests/fixtures/node_typescript_helm/deploy/chart/values.yaml` | Primary `image_reference`. |
| `tests/fixtures/node_typescript_helm/deploy/chart/values-prod.yaml` | Multi-env entry — exercises ADR-0012 list shape. |
| `tests/fixtures/node_typescript_helm/README.md` | Per-file probe-consumer documentation. |
| `tests/unit/test_fixture_node_typescript_helm_shape.py` | Shape test — fails loud on accidental deletions. |

## Out of scope

- **`node_pnpm_native/` and `node_yarn_legacy/` fixtures** — S3-06.
- **`node_monorepo_turbo/` and `non_node_go/` fixtures** — S5-04.
- **Adversarial fixtures (under `tests/adv/`)** — S5-01 / S5-02 / S5-03.
- **Golden file regeneration** — S6-01.
- **Realistic pnpm-lock content (full dependency graph)** — Phase 2 / Phase 3 may extend. Phase 1 needs only the parseable header.

## Notes for the implementer

- **The fixture's bytes are part of the contract.** Adding or removing a file changes the S6-01 golden. Resist the urge to "round out" the fixture with extra files for completeness — every file forces a golden regen. AC-14 enforces this mechanically.
- **`pnpm-lock.yaml` content minimality matters for the depth-cap test in S5-01** (billion-laughs adversarial). If you put a deeply nested fixture lockfile here, the cap-exceeded fixture in S5-01 has to be even deeper. Keep this one shallow.
- **`src/index.ts` body — the `import express from "express"` line is load-bearing**: AC-6's `_index_ts_imports_express` predicate pins it. A trivial `console.log("hi")` would not satisfy AC-6.
- **`.github/workflows/ci.yml` should declare one job + one step.** A multi-job workflow adds bytes to the golden without exercising new code paths in Phase 1 (`CIProbe` records jobs as a list; one entry suffices). AC-7's `_ci_single_build_job` predicate pins it.
- **Engine-version vs. `.nvmrc` vs. runtime `node --version` interaction (S6-01 concern, not this story).** `engines.node = ">=20.0.0"` is a range; `.nvmrc = "v20.11.0"` is a pin; the CI machine's installed Node could be e.g. v22 (which satisfies `>=20.0.0` but does not equal `v20.11.0`). The S2-02 `node.version_declared_resolved_disagree` warning may fire depending on the runtime. **This is not this story's problem** — the S6-01 golden-regen script (`scripts/regen_golden.py`) is expected to disable the ADR-0001-gated `node --version` cross-check (or to pin the regen environment's Node version) to keep the golden deterministic. Recorded here for the S6-01 implementer.

### Design-pattern lifts (rationale — informational for the implementer)

Three design-pattern decisions were lifted from this story's shape:

1. **`_FILE_SPECS: tuple[_FileSpec, ...]` module-level closed-set typed manifest** (AC-15) follows the same Open/Closed-at-file-boundary precedent that S2-01 set with `_MONOREPO_PRECEDENCE` and S2-02 set with `_LOCKFILE_PRECEDENCE` / `_BUNDLERS_SORTED`. Adding a fixture file is a pure additive — one tuple entry insertion, the parametrized test bodies stay frozen.

2. **`_ProbeName = Literal[...]` closed set over the six Phase-1 probe names** (AC-15, AC-18) makes the `_FILE_SPECS[i].consumers` field type-safe AND runtime-checked. Phase 2 adds Layers B–G probes; extending `_ProbeName` is a deliberate edit per AC-18's runtime assertion.

3. **`content_checks` as a tuple of pure predicates over the parsed structure** (AC-15) separates "the data this file must contain" from "how to read the data" (the `parser` field). Each predicate is independently unit-testable — `_pkg_omits_package_manager(pkg)` is a 3-line pure function; testing it in isolation against a synthetic dict is trivial.

### Patterns DELIBERATELY deferred (premature-abstraction guard, per Rule 2)

- **Generic `tests/fixtures/_shape_test_kernel.py`.** A reusable kernel that takes a `_FILE_SPECS` tuple and produces the parametrized shape test would be the natural extraction. **Defer**: only one Phase-1 fixture (this one) has a shape test. The within-codebase rule of three is not met. Re-evaluate at S5-04 when `node_monorepo_turbo/` and `non_node_go/` ship — those would be the third and fourth consumers; the kernel lifts then.
- **YAML-based `MANIFEST.yaml` inside the fixture tree as SSoT (instead of `_FILE_SPECS` in the shape test).** Slightly cleaner separation, but introduces an extra parser step + extra file in the fixture (which AC-14 then has to allowlist). Python-as-SSoT keeps it simple. Re-evaluate when the manifest is consumed by ≥ 3 distinct tests / scripts.
- **`FixtureConsumer` sum type / tagged union over probe + consumer-test.** Each `_FileSpec` could carry a more structured "consumed by S2-04's warm-path memo test" annotation. But the probe name is the load-bearing identity; the consumer test is an editorial cross-reference best left in the README. Defer until a fourth consumer dimension appears.
- **Newtype `RelPath = NewType("RelPath", str)` for the `relpath` field.** The string is path-shaped but never crosses a module boundary, so the newtype is overhead for no payoff in Phase 1. Re-evaluate when a `RelPath` is passed to a non-test module.
