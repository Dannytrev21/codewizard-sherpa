# Story S1-08 — `tools/digests.yaml` pin manifest + install-time verifier CI job

**Step:** Step 1 — Plant sandbox extension, tool wrappers, tool-digest pin manifest, and the four Phase-0/1 in-place edits
**Status:** Ready
**Effort:** M
**Depends on:** S1-04
**ADRs honored:** ADR-0004

## Context

Phase 2 introduces six external CLIs and tree-sitter grammar wheels. Each is a code-loading interpreter on attacker-controlled bytes; silent tool drift on a CI runner (or hostile binary swap mid-install) changes probe output without invalidating any cache. `IndexHealthProbe` (B2) catches drift *after* the gather — pre-gather, the install gate must reject a runner whose tools don't match pinned digests.

ADR-0004 chose `tools/digests.yaml` as a single SHA-256 pin manifest with install-time verification and per-probe cache-key inclusion. The manifest is loaded at module import via Phase 1's `safe_yaml.load`, `MappingProxyType`-wrapped, and exposes a `tools.digests.get(name) -> str` lookup helper that every wrapper from S1-05/06/07 will eventually call to populate `ToolResult.tool_digest`.

This story is the smallest unit that ships **both** the catalog file and the CI gate that enforces it. Without the gate, the catalog is shelfware; without the catalog, the wrappers' `tool_digest` fields are stub strings.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #2 (tools/ wrappers)` — `tool_digest` field on every `ToolResult` is populated from this catalog.
  - `../phase-arch-design.md §"Goals" #7` — tool-digest pinning statement.
  - `../phase-arch-design.md §"Components" §10 AuditWriter` — digest auditing reads from this catalog.
- **Phase ADRs:**
  - `../ADRs/0004-tools-digests-yaml-pin-manifest.md` — ADR-0004 — full decision; `catalog_version: int` field at root; per-probe cache-key inclusion; install-gate verification.
  - `../ADRs/0005-allowed-binaries-additions.md` — every new binary's "digest cache-key contribution: Yes" subsection refers to this catalog.
- **Production ADRs:**
  - `../../../production/adrs/0006-deterministic-gather-no-llm.md` — the deterministic-gather invariant this catalog defends.
- **Source design:**
  - `../final-design.md §"Goals (concrete, measurable)"` Tool-digest-pinning bullet.
  - `../final-design.md §"Components" #8 Cache layer extension` — digest-in-cache-key spec.
- **Existing code:**
  - `src/codegenie/parsers/safe_yaml.py` (Phase 1 S1-03) — used at module import.
  - `src/codegenie/catalogs/` (Phase 1 S1-05) — same package shape; same authoring discipline.
  - `src/codegenie/errors.py` — `CatalogLoadError` (Phase 1 S1-01); this story adds `ToolDigestMismatch` (additive — not in S1-01's nine; it lands here alongside the verifier).

## Goal

Ship `src/codegenie/catalogs/tools/digests.yaml` with SHA-256 pins for the five external CLI binaries plus the tree-sitter grammar wheel hashes plus rule-pack version digests; ship `scripts/check_tool_digests.py` that verifies installed binaries against the pins; wire a new `tool_digests_verify` CI job; expose a `tools.digests.get(name)` helper consumed by every wrapper.

## Acceptance criteria

- [ ] `src/codegenie/catalogs/tools/digests.yaml` exists with `catalog_version: 1` at root and SHA-256 pins for `scip-typescript`, `semgrep`, `syft`, `grype`, `gitleaks` (Linux x86_64 + macOS arm64 digests under per-platform keys) plus `grammars: {tree_sitter, tree_sitter_typescript, tree_sitter_javascript}` wheel SHA-256 entries plus `rule_packs: {p_ci, p_typescript}` (or whichever packs Phase 2 ships) with their version digests.
- [ ] `src/codegenie/catalogs/tools/_schema.json` is a Draft 2020-12 schema validating the manifest; `additionalProperties: false` at every nesting level; `catalog_version: int` required at root.
- [ ] `src/codegenie/catalogs/tools/__init__.py` (or `src/codegenie/tools/digests.py`) loads the YAML at module import via `safe_yaml.load(..., max_bytes=1_000_000)`, validates against the schema, wraps in `MappingProxyType`, and exposes `def get(name: str) -> str` returning the platform-appropriate digest. Malformed YAML / schema mismatch raises `CatalogLoadError` (existing typed exception).
- [ ] `src/codegenie/errors.py` extends additively with `ToolDigestMismatch(CodegenieError)` carrying `tool_name: str`, `expected: str`, `actual: str`; the verifier script raises it on mismatch.
- [ ] `scripts/check_tool_digests.py` walks the five binaries on `$PATH`, computes their SHA-256, looks up the expected digest from `tools.digests.get(...)`, and exits 0 on full match or 1 on any mismatch. The script handles the "binary not on $PATH" case by exiting 0 with a structured warning (the binary's wrapper raises `ToolNotFound` at probe time; install-time absence is a CI-runner config issue, not a digest issue).
- [ ] A new CI job `tool_digests_verify` in `.github/workflows/<ci>.yml` runs `scripts/check_tool_digests.py` before any unit tests; failure red-gates the CI run.
- [ ] `tests/unit/catalogs/tools/test_digests_loader.py` ships ≥ 5 tests — happy load, malformed YAML → `CatalogLoadError`, schema mismatch → `CatalogLoadError`, `MappingProxyType` immutability, `get("unknown")` raises `KeyError`.
- [ ] `tests/unit/scripts/test_check_tool_digests.py` ships ≥ 3 tests — happy path (binary digest matches), mismatch (raises `ToolDigestMismatch`-shaped exit), binary-not-on-$PATH (exits 0 with warning).
- [ ] The TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Write `tests/unit/catalogs/tools/test_digests_loader.py` first (red).
2. Write `tests/unit/scripts/test_check_tool_digests.py` (red); patch `subprocess`/`shutil.which`/`hashlib` seams.
3. Create `src/codegenie/catalogs/tools/digests.yaml` with seed entries. For initial values, use placeholder SHA-256 hashes that match the CI runner's installed binaries; the install-gate is the source of truth for any later corrections. Document that per-platform keys are required: `linux_amd64: sha256:...`, `darwin_arm64: sha256:...`.
4. Create `src/codegenie/catalogs/tools/_schema.json` (Draft 2020-12). Top-level requires `catalog_version: int`, `binaries: object`, `grammars: object`, `rule_packs: object`. Under `binaries`, each entry requires `linux_amd64: string (regex sha256:[0-9a-f]{64})` and `darwin_arm64: string (same)`.
5. Implement the loader (`src/codegenie/tools/digests.py` or `catalogs/tools/__init__.py` — pick one location and document it): `_DIGESTS = _load(...)` at module scope; `get(name: str) -> str` returns the platform-appropriate value via `platform.machine()` + `sys.platform` lookup.
6. Extend `src/codegenie/errors.py` with `ToolDigestMismatch` and add to `__all__`.
7. Implement `scripts/check_tool_digests.py`:
   - Loads `tools.digests` module.
   - For each binary in `BINARIES = ["scip-typescript", "semgrep", "syft", "grype", "gitleaks"]`, calls `shutil.which(binary)`; if `None`, emit a `tool.absent` warning and continue.
   - For each present binary, read bytes with `Path(path).read_bytes()` and compute `hashlib.sha256(...).hexdigest()`.
   - Compare to `tools.digests.get(binary)`; on mismatch, print `binary: expected=<x> actual=<y>` and accumulate failures.
   - At end: if any failure, exit 1; else exit 0.
8. Wire the new CI job. Add a job entry to the existing CI workflow (do not create a new workflow): runs on `ubuntu-latest`, installs tools per the documented procedure, runs `python scripts/check_tool_digests.py`, marks required.
9. Update `pyproject.toml` if the verifier needs any new deps (it shouldn't — `hashlib`, `shutil` are stdlib).
10. Run pytest, ruff, mypy.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/catalogs/tools/test_digests_loader.py`.

```python
from types import MappingProxyType
import pytest

import codegenie.errors as e


def test_digests_module_loads_and_exposes_get():
    from codegenie.tools import digests
    val = digests.get("semgrep")
    assert val.startswith("sha256:")
    # the underlying mapping is immutable
    assert isinstance(digests._DIGESTS, MappingProxyType)


def test_digests_get_unknown_raises_key_error():
    from codegenie.tools import digests
    with pytest.raises(KeyError):
        digests.get("never-heard-of-it")


def test_malformed_yaml_hard_fails(tmp_path, monkeypatch):
    bad = tmp_path / "digests.yaml"
    bad.write_text(":\n:\n: invalid")
    from codegenie.catalogs.tools import _load_digests  # internal test seam
    with pytest.raises(e.CatalogLoadError):
        _load_digests(bad)


def test_schema_mismatch_hard_fails(tmp_path):
    bad = tmp_path / "digests.yaml"
    bad.write_text("catalog_version: 1\nbinaries:\n  semgrep:\n    bogus_platform: sha256:abc\n")
    from codegenie.catalogs.tools import _load_digests
    with pytest.raises(e.CatalogLoadError):
        _load_digests(bad)
```

```python
# tests/unit/scripts/test_check_tool_digests.py
import subprocess
import sys
from pathlib import Path


def test_check_passes_when_no_binaries_on_path(monkeypatch):
    # Force shutil.which to always return None — verifier should exit 0 with warning
    monkeypatch.setenv("PATH", "")
    res = subprocess.run(
        [sys.executable, "scripts/check_tool_digests.py"], capture_output=True, text=True,
    )
    assert res.returncode == 0
    assert "absent" in res.stdout.lower()


def test_check_fails_on_digest_mismatch(tmp_path, monkeypatch):
    # Create a fake "semgrep" binary in tmp_path with known bad content
    fake = tmp_path / "semgrep"
    fake.write_bytes(b"not the real semgrep")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    res = subprocess.run(
        [sys.executable, "scripts/check_tool_digests.py"], capture_output=True, text=True,
    )
    assert res.returncode == 1
    assert "expected" in res.stdout.lower()
```

Run; confirm `ModuleNotFoundError` / failures. Commit as red marker.

### Green — make it pass

Land the catalog, schema, loader module, exception extension, and verifier script.

### Refactor — clean up

- The loader uses a `_load_digests(path)` internal seam exposed to tests. Document it as such.
- The verifier script's binary list is `Final[tuple[str, ...]]` at module top — no magic strings.
- Catalog YAML comments at top reference `phase-arch-design.md §"Goals" #7` and ADR-0004.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/catalogs/tools/digests.yaml` | New — pin manifest |
| `src/codegenie/catalogs/tools/_schema.json` | New — Draft 2020-12 schema |
| `src/codegenie/catalogs/tools/__init__.py` | New — `_load_digests` seam |
| `src/codegenie/tools/digests.py` | New — `_DIGESTS` + `get()` helper |
| `src/codegenie/errors.py` | Append `ToolDigestMismatch`; extend `__all__` |
| `scripts/check_tool_digests.py` | New — install-gate verifier |
| `.github/workflows/<ci>.yml` | Add `tool_digests_verify` job to existing workflow |
| `tests/unit/catalogs/tools/test_digests_loader.py` | New — ≥ 5 loader tests |
| `tests/unit/scripts/test_check_tool_digests.py` | New — ≥ 3 verifier tests |

## Out of scope

- **Wrappers consuming `tools.digests.get(...)` for `tool_digest` population** — handled in S1-05, S1-06, S1-07 (each wrapper reads its tool's digest at result-construction time). This story exposes the API; the wrappers consume it.
- **Per-probe cache-key inclusion of `tool_digest`** — handled in S3-01 onward (`IndexHealthProbe`'s cache key includes upstream tool digests; per-probe cache keys are extended as probes land). ADR-0004 documents the discipline; this story provides the catalog the keys read from.
- **`grype-db-listing.signed.json` signed listing for the grype vuln DB** — handled by S6-02.
- **Sub-schema `sub_schema_version` cache-key participation** — handled by S2-06.

## Notes for the implementer

- **Per-platform digests are mandatory.** Linux and macOS binaries have different SHA-256s for the same upstream release. The schema enforces `linux_amd64` and `darwin_arm64` keys; future Phase 7 may add `linux_arm64`. Per Rule 12 (Fail loud), if a CI runner runs on an unrecognized platform, `get(...)` should `raise CatalogLoadError(detail="unsupported platform: ...")` rather than silently returning the wrong digest.
- The initial digest values are **placeholders until first CI run**. The expected workflow: implementer lands this story with the SHA-256s of their local-machine binaries → CI runs on `ubuntu-latest`, the install-gate fails on Linux runner digest mismatch → implementer reads the actual digests from CI output → commits the corrected values → CI green. Document this bootstrap procedure in the catalog's leading comment.
- `shutil.which(binary)` returns `None` when the binary is absent. The verifier's "absent → exit 0 with warning" decision is intentional: at install time, the CI runner may legitimately not have all six binaries (e.g., `docker` may be unavailable in a constrained job). The wrapper raises `ToolNotFound` at probe time, which is the correct surface for the probe-side concern. Per Rule 7 (surface conflicts, don't average them), don't try to enforce "all six binaries must be present" — that's a separate concern handled by the deployment recipe.
- `tools.digests.get(name)` is the single-call surface every wrapper uses. Keep the signature `get(name: str) -> str` — no overloads, no per-platform args. Platform detection is internal. If a wrapper needs both Linux and macOS digests (rare), it can read `_DIGESTS` directly with documented justification.
- The `catalog_version: int` field follows Phase 1 ADR-0006's pattern. A digest bump is a **minor** version increment; adding a new binary entry is also **minor**; removing a binary is **major** and requires a Phase-level ADR amendment. Document the policy in the catalog's leading comment.
- The CI job ordering matters: `tool_digests_verify` must run **before** any test job, so a digest mismatch fails fast and doesn't waste CI minutes on flaky probe tests. Wire it as a prerequisite (GitHub Actions `needs:` keyword).
- `ToolDigestMismatch` is added to `errors.py` in this story (not in S1-01) because it ships with the verifier that raises it. Phase 0/1 convention: typed exceptions land with their first raise site. Adding it to `__all__` is the load-bearing piece for re-export.
- Do **not** make the verifier compute the *expected* digests from upstream URLs. The catalog is the source of truth; recomputation defeats the pin. The catalog's update procedure is human-mediated: bump tool → compute new SHA-256 manually → commit catalog change → CI verifies on the next runner install.
- The `rule_packs` block is provisional in Phase 2 — semgrep rule pack digests will be consumed by S2-03 (catalog) and S7-02 (`SemgrepProbe`). Seed the structure even if only one pack is named; future packs slot in by addition.
