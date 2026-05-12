# Story S3-03 — `tools/digests.yaml` extension for `npm` + `ncu`

**Step:** Step 3 — Ship the `NcuRecipeEngine` vertical: `tools/npm` + `tools/ncu` wrappers, `LockfileResolver`, `LockfileCanonicalizer`, recipe catalog + selector
**Status:** Ready
**Effort:** S
**Depends on:** S3-01, S3-02
**ADRs honored:** ADR-0011, ADR-0014

## Context

Phase 2 landed `src/codegenie/catalogs/tools/digests.yaml` as the binary pin manifest plus the `tool_digests_verify` CI gate. Phase 3 adds two binaries that must satisfy the same discipline: `npm` (pinned at **minor-version precision** per ADR-0011 — patch-version drift is tolerated, minor-version drift invalidates the portfolio cache) and `ncu` (the npm-check-updates CLI; pinned at full SHA-256). The minor-version-precision choice for `npm` is load-bearing: `LockfileResolver`'s four-component cache key uses `npm_minor_digest`, **not** `npm_patch_digest`, to avoid portfolio-wide stampedes on every patch release (`final-design.md §Goals #8`).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #5 (LockfileResolver)` — cache key uses `npm_minor_digest`.
  - `../phase-arch-design.md §"Cross-cutting concerns" pin-manifest discipline` — two manifests in Phase 3.
- **Phase ADRs:**
  - `../ADRs/0011-lockfile-canonicalization-and-npm-digest-pin-for-deterministic-diffs.md` — `npm` minor-version pin rationale.
  - `../ADRs/0014-allowed-binaries-additions-npm-ncu-java.md` — `npm`/`ncu` allowlisted.
- **Existing code:**
  - `src/codegenie/catalogs/tools/digests.yaml` — Phase-2 manifest (extended in-place).
  - `scripts/check_tool_digests.py` (or equivalent from Phase 2 S1-08) — install-time verifier (extended).
  - `.github/workflows/` — `tool_digests_verify` job.

## Goal

Extend `tools/digests.yaml` with SHA-256 pins for `npm` (minor-version precision) and `ncu`; extend the digest verification script to enforce the new entries; wire the CI job; pin drift-adversarial behavior.

## Acceptance criteria

- [ ] `src/codegenie/catalogs/tools/digests.yaml` adds two entries:
  - `npm` → `{minor_version: "10.8", sha256: "<full-hash>", binary_path_pattern: "npm-cli.js"}` (or whichever shape Phase-2 established for cross-platform binaries).
  - `ncu` → `{version: "<exact>", sha256: "<full-hash>"}`.
- [ ] `scripts/check_tool_digests.py` (or equivalent) is extended to verify `npm` matches the **minor-version digest** (computed by hashing the published `npm` tarball restricted to the minor) and `ncu` matches the **full digest**; documented in the script's docstring.
- [ ] `npm_minor_digest` is exposed via a Python helper (`from codegenie.catalogs.tools import npm_minor_digest`) used by `LockfileResolver` in S3-08.
- [ ] `.github/workflows/` `tool_digests_verify` job extension covers `npm` + `ncu` at install time.
- [ ] `tests/adv/test_tools_digests_yaml_drift_breaks_install.py` — drift the `npm` digest in a fixture copy; the verifier exits non-zero; the wrapper's `tools.npm.run(...)` smoke test fails.
- [ ] `tests/unit/catalogs/test_tools_digests_extension.py` — happy-path load; `npm_minor_digest` helper returns expected shape; missing entry raises `ToolDigestMissing`.
- [ ] `ruff check`, `mypy --strict`, `pytest` pass.

## Implementation outline

1. Land `tests/adv/test_tools_digests_yaml_drift_breaks_install.py` first (red).
2. Compute the two digests locally:
   - `npm` minor-version digest: pull npm 10.8.x as the pinned-minor (or whichever range matches the project's Node version); document the source URL + retrieval method in `docs/phases/03-vuln-deterministic-recipe/runbook.md` placeholder (filled in S7-07).
   - `ncu` full digest: `sha256sum $(which ncu)` after pinned install.
3. Append entries to `src/codegenie/catalogs/tools/digests.yaml`.
4. Extend `scripts/check_tool_digests.py` to read both entries + add a Python helper `npm_minor_digest()` returning the pinned hash string (consumed by S3-08).
5. Extend `.github/workflows/<file>.yml` `tool_digests_verify` step to fail when either entry mismatches.
6. Land the unit test + the drift adversarial test.

## TDD plan — red / green / refactor

### Red
Path: `tests/adv/test_tools_digests_yaml_drift_breaks_install.py`
```python
import shutil
from pathlib import Path

import pytest
import yaml


def test_drifted_npm_digest_breaks_verifier(tmp_path: Path, monkeypatch):
    src_yaml = Path("src/codegenie/catalogs/tools/digests.yaml")
    drifted = tmp_path / "digests.yaml"
    data = yaml.safe_load(src_yaml.read_text())
    data["npm"]["sha256"] = "0" * 64               # corrupt
    drifted.write_text(yaml.safe_dump(data))

    from scripts import check_tool_digests
    rc = check_tool_digests.verify(manifest_path=drifted)
    assert rc != 0, "drifted manifest must fail verification"
```

### Green
Smallest impl: append two YAML entries, add the helper, extend the verifier to fail on mismatch.

### Refactor
- Move the `npm_minor_digest` helper into a small `catalogs/tools/__init__.py` if/when a third consumer needs it; resist now.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/catalogs/tools/digests.yaml` | Append `npm` + `ncu` entries |
| `scripts/check_tool_digests.py` | Verify the new entries |
| `src/codegenie/catalogs/tools/__init__.py` | New helper `npm_minor_digest()` (if absent) |
| `.github/workflows/<phase-2-ci-file>.yml` | Extend `tool_digests_verify` job |
| `tests/adv/test_tools_digests_yaml_drift_breaks_install.py` | New — drift pin |
| `tests/unit/catalogs/test_tools_digests_extension.py` | New — happy load + helper shape |

## Out of scope

- **`openrewrite-jar` digest pin** — handled by S6-01 (extends this same manifest then).
- **`recipes/digests.yaml`** — new manifest landed in S3-04 (separate concern: recipe YAML pinning, not binary pinning).
- **The `LockfileResolver` cache key that consumes `npm_minor_digest`** — handled by S3-08.

## Notes for the implementer
- The minor-version-precision choice for `npm` is deliberately weaker than the patch-precision for `ncu`. `ncu`'s output is fully consumed and audited; `npm`'s output (the lockfile bytes) is canonicalized downstream by S3-09, so minor-version determinism is sufficient.
- Document the retrieval/verification path for both digests in a sibling `digests.README.md` next to the YAML; the verification recipe must be reproducible by a future contributor.
- When the npm minor version is bumped (e.g., 10.8 → 10.9), the portfolio-wide lockfile cache invalidates; document this in the runbook stub (Gap 5; filled in S7-07).
- The drift adversarial test must use a **copy** of the manifest in `tmp_path`, never mutate the in-repo file.
- The `npm_minor_digest()` helper is what S3-08's cache key calls — keep the return type a plain `str` (full hex) for easy `blake3` mixing.
- Per Rule 12 (Fail loud): the CI gate's failure message must name the binary + observed hash + expected hash, not just "digest mismatch".
