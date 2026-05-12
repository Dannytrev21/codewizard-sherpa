# Story S2-03 — Fixture `node_typescript_helm/`

**Step:** Step 2 — Extend `LanguageDetectionProbe` and ship `NodeBuildSystemProbe`
**Status:** Ready
**Effort:** S
**Depends on:** S2-01 (`LanguageDetectionProbe` extension consumes the fixture's `package.json` + `turbo.json`/workspaces if present), S2-02 (`NodeBuildSystemProbe` consumes the fixture's `package.json`, `pnpm-lock.yaml`, `.nvmrc`, `tsconfig.json`)
**ADRs honored:** ADR-0010 (sub-schema slice optionality irrelevant here — the fixture is Node; relevant for ensuring nothing in this fixture forces non-optional probes)

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

- [ ] `tests/fixtures/node_typescript_helm/` directory exists.
- [ ] `package.json` declares `"name": "node-typescript-helm"`, `"version": "0.0.1"`, `"dependencies": {"express": "^4.18.2"}`, `"devDependencies": {"typescript": "^5.3.0", "vitest": "^1.0.0"}`, `"engines": {"node": ">=20.0.0"}`, `"scripts": {"build": "tsc -p .", "test": "vitest run", "start": "node dist/index.js"}`. No `packageManager` field (avoids triggering the disagreement warning that would dirty the golden).
- [ ] `pnpm-lock.yaml` exists with a minimal valid pnpm v6 lockfile header (`lockfileVersion: '6.0'`) — enough that the precedence check picks pnpm and the YAML parses with `safe_yaml.load`. Contents minimal; not required to resolve `express` (S3-05 native-module catalog cross-reference uses a different fixture).
- [ ] `tsconfig.json` exists, valid JSONC (one block comment + one line comment to exercise `parsers/jsonc.py`), declares `compilerOptions.target: "ES2022"`, `compilerOptions.module: "ESNext"`, `compilerOptions.strict: true`, no `extends`.
- [ ] `.nvmrc` exists with content `v20.11.0\n`.
- [ ] `src/index.ts` exists with a trivial valid TS body (one `import express from "express"` + a 3-line server stub) — purely to make `LanguageDetectionProbe`'s extension walk count one `.ts` file.
- [ ] `.github/workflows/ci.yml` exists with a single `build` job + a `run: pnpm install && pnpm test` step — populates `CIProbe`'s slice in S5-05.
- [ ] `deploy/chart/Chart.yaml` exists with `name`, `version`, `apiVersion: v2`.
- [ ] `deploy/chart/values.yaml` exists with `image.repository: ghcr.io/example/node-typescript-helm`, `image.tag: "0.0.1"`.
- [ ] `deploy/chart/values-prod.yaml` exists with an `image.tag: "prod-0.0.1"` override (one alternate environment — exercises the multi-env path in `DeploymentProbe`).
- [ ] `tests/fixtures/node_typescript_helm/README.md` lists every file in the tree and the probe that consumes it; references `../../docs/phases/01-context-gather-layer-a-node/phase-arch-design.md` for the canonical slice descriptions.
- [ ] No file in the fixture is byte-identical to a checked-in production source file (i.e., copying `src/codegenie/...` into the fixture is forbidden — fixtures must be self-contained).
- [ ] A trivial unit test exists at `tests/unit/test_fixture_node_typescript_helm_shape.py` asserting the file tree has the expected paths — fails loud if a future edit deletes a load-bearing file.

## Implementation outline

1. `mkdir -p tests/fixtures/node_typescript_helm/{src,deploy/chart,.github/workflows}`.
2. Write each file per acceptance criteria. Keep contents minimal — every byte ends up in the golden.
3. Run `pnpm install` on a scratch directory with the same `package.json` to obtain a real pnpm-v6 lockfile header **only if necessary** — otherwise, copy the minimal `lockfileVersion: '6.0'` shape from a reference pnpm lockfile and verify it parses via `safe_yaml.load`. Strip irrelevant metadata to keep the byte count small.
4. Write `tests/fixtures/node_typescript_helm/README.md` documenting every file + the consuming probe (table form).
5. Write `tests/unit/test_fixture_node_typescript_helm_shape.py` — a single test enumerating expected paths and asserting `Path.is_file()` on each.
6. Run `codegenie gather` against the fixture locally **before** committing to verify no probe crashes on this fixture. (This is a smoke check, not a test — the real assertion lives in S2-04 / S2-05 / S5-05.)

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_fixture_node_typescript_helm_shape.py`

```python
# tests/unit/test_fixture_node_typescript_helm_shape.py

from pathlib import Path
import pytest

FIXTURE = Path(__file__).parent.parent / "fixtures" / "node_typescript_helm"

REQUIRED_FILES = (
    "package.json",
    "pnpm-lock.yaml",
    "tsconfig.json",
    ".nvmrc",
    "src/index.ts",
    ".github/workflows/ci.yml",
    "deploy/chart/Chart.yaml",
    "deploy/chart/values.yaml",
    "deploy/chart/values-prod.yaml",
    "README.md",
)

@pytest.mark.parametrize("relpath", REQUIRED_FILES)
def test_fixture_has_required_file(relpath: str) -> None:
    assert (FIXTURE / relpath).is_file(), f"missing: {relpath}"


def test_package_json_declares_express() -> None:
    import json
    pkg = json.loads((FIXTURE / "package.json").read_text())
    assert "express" in pkg["dependencies"]
```

The first parametrized test must fail with `AssertionError: missing: package.json` (and similarly for the rest). Confirm red on at least one file, commit, then Green.

### Green — make it pass

Create the directory tree + each file per acceptance criteria. Verify the test goes green.

### Refactor — clean up

- Review every file byte for incidental non-determinism (trailing whitespace, line-ending). Files committed must round-trip through `git diff` cleanly (LF endings, final newline).
- `tests/fixtures/node_typescript_helm/README.md` is curated — the file-by-file table is for the *next implementer* who debugs a golden-file mismatch.
- `mypy --strict` clean (the fixture is data; only the shape test needs typing).

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

- **The fixture's bytes are part of the contract.** Adding or removing a file changes the S6-01 golden. Resist the urge to "round out" the fixture with extra files for completeness — every file forces a golden regen.
- **No `packageManager` field in `package.json`.** Setting it would trip the `package_manager.declaration_lockfile_disagree` warning (from S2-02) if it disagreed with the lockfile, or be silently consistent and pollute the slice. Either way, the golden becomes more complex than necessary. The disagreement path is tested via S2-02's unit tests, not via this fixture.
- **`tsconfig.json` deliberately includes both a `//` line comment and a `/* */` block comment** to exercise `parsers/jsonc.py`'s comment-stripper on the warm path. Without comments, the file would parse via plain JSON and the `jsonc.py` code path stays untested in integration.
- **`pnpm-lock.yaml` content minimality matters for the depth-cap test in S5-01** (billion-laughs adversarial). If you put a deeply nested fixture lockfile here, the cap-exceeded fixture in S5-01 has to be even deeper. Keep this one shallow.
- **`src/index.ts` body matters only for the counts.** A trivial `console.log("hi")` would suffice, but a one-line `import express from "express"` is more illustrative for the fixture README; either is acceptable.
- **`.github/workflows/ci.yml` should declare one job + one step.** A multi-job workflow adds bytes to the golden without exercising new code paths in Phase 1 (`CIProbe` records jobs as a list; one entry suffices).
- **`Chart.yaml` apiVersion = v2** — this is the modern Helm chart shape; matches what `DeploymentProbe` parses in Step 4.
- **No `.gitignore` inside the fixture.** Phase 0's gather adds `.codegenie/` to a target repo's `.gitignore`; we want this fixture's `.codegenie/` writes (from the integration tests) to be cleaned by `pytest` teardown, not silently swallowed by an in-fixture `.gitignore`.
