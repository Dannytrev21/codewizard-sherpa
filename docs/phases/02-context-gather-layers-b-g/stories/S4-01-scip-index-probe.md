# Story S4-01 — `SCIPIndexProbe` + `.codegenie/index/` namespace + grammar re-validation

**Step:** Step 4 — Ship Layer B remainder (`SCIPIndexProbe`, `NodeReflectionProbe`, `GeneratedCodeProbe`)
**Status:** Ready
**Effort:** L
**Depends on:** S1-06 (`tools.scip_typescript` wrapper), S2-07 (`SCHEMA-EVOLUTION-POLICY.md`), S3-01 (`IndexHealthProbe` declares `requires=["scip_index", …]`)
**ADRs honored:** ADR-0013 (conditional `node_modules` read-only mount; never `npm install`), ADR-0004 (`tools/digests.yaml` cache-key inclusion), ADR-0003 (sandbox profile extension; `network="none"`), ADR-0006 (sanitizer Pass 4/5 idempotence on the slice), ADR-0011 (advisory budget — irrelevant here but consumer reads `scip` domain), ADR-0007 (`--ignore-scripts` precedent extended to "no `npm install`")

## Context

`SCIPIndexProbe` (B1) is the load-bearing Layer B probe — the SCIP index it writes is what `TestCoverageMappingProbe` (S7-05), `NodeReflectionProbe` (S4-02), `IndexHealthProbe`'s `scip` domain, and Stage 3 Planning's symbol-resolution all read. The synthesis on `node_modules` policy (`final-design.md "Conflict-resolution table" D3`) is the load-bearing security/evidence tradeoff: mount `node_modules/` read-only **if present**; **never** invoke `npm install` (the same postinstall-RCE surface `BuildGraphProbe` closes via `--ignore-scripts`). When `node_modules` is absent, the probe walks lockfiles and emits `confidence: medium` — honest evidence, not a degraded fallback.

Two artifacts make this story Phase-2-distinct from a normal probe: (1) the SCIP output is a **per-repo binary** at `.codegenie/index/scip-index.scip`, rewritten in place on every cache-miss, **never** auto-deleted by `cache gc` (S4-04 enforces the distinction); (2) the parent process **re-validates** the `.scip` bytes against the SCIP protobuf grammar before merging the slice — corruption (truncated, byte-flipped, hostile compiler-plugin output) → `confidence: low` and the cache entry is not stored.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #7 SCIPIndexProbe (B1) — conditional node_modules mount` — full interface contract, mount policy, cache-key composition, re-validation, performance envelope, failure behavior.
  - `../phase-arch-design.md §"Component design" #17 Per-file findings cache + .codegenie/index/` — on-disk namespace (`.codegenie/index/scip-index.scip` is per-repo; `cache gc` extended in S4-04).
  - `../phase-arch-design.md §"Logical view"` — sibling relation to `IndexHealthProbe`, `NodeReflectionProbe`, `TestCoverageMappingProbe`.
  - `../phase-arch-design.md §"Physical view"` — `.codegenie/index/scip-index.scip` lives outside `cache/`.
- **Phase ADRs:**
  - `../ADRs/0013-scip-node-modules-conditional-mount.md` — the mount-if-present-but-never-install decision; confidence ladder (`high`/`medium`/`low`); per-repo binary lifecycle; grammar re-validation.
  - `../ADRs/0004-tools-digests-yaml-pin-manifest.md` — `scip-typescript` digest participates in this probe's cache key.
  - `../ADRs/0003-subprocess-sandbox-profile-extension.md` — `network="none"`, env-strip, `ro_bind` for `node_modules`.
  - `../ADRs/0011-index-health-advisory-budget-and-strict-flag.md` — the consumer side (B2) reads `scip.last_indexed_commit`, `coverage_pct`, `confidence`.
- **Production ADRs:**
  - `../../../production/adrs/0005-no-llm-in-gather-pipeline.md` — re-validation result records facts; no judgment.
- **Source design:**
  - `../final-design.md §"Synthesis ledger" row D3` — `node_modules` policy resolution.
  - `../final-design.md §"Components" §3.1 SCIPIndexProbe` — provenance and risks.
  - `../final-design.md §"Failure modes"` — `scip-typescript not on PATH` → `confidence: low`; SCIP corruption → re-validation → `confidence: low`.
- **Existing code (Steps 1–3 output):**
  - `src/codegenie/tools/scip_typescript.py` (S1-06) — `async run(repo_root: Path, *, raw_output_path: Path, node_modules_path: Path | None, timeout_s: float = 600) -> SCIPTypescriptResult` with `tool_digest` field surfaced from `tools/digests.yaml`.
  - `src/codegenie/exec.py` (S1-02, S1-03) — `run_in_sandbox(..., network="none", ro_bind=(...))` keyword-only args.
  - `src/codegenie/catalogs/tools/digests.yaml` (S1-08) — pinned SHA-256 for `scip-typescript`; cache-key participation per ADR-0004.
  - `src/codegenie/errors.py` (S1-01) — `ToolNotFound`, `ToolOutputMalformed`, `ToolNonZeroExit`, `ToolTimeout`.
  - `src/codegenie/probes/base.py` (Phase 0, ADR-0001-bumped) — `Probe` ABC.
  - `src/codegenie/probes/__init__.py` — additive import registration.
  - `src/codegenie/coordinator/cache_key.py` (S2-06) — `sub_schema_version` participation; this probe's cache key extends by adding `tool_digest`.
- **External references:**
  - SCIP protobuf grammar: `https://github.com/sourcegraph/scip/blob/main/scip.proto` — used for parent-side re-validation.

## Goal

Ship a deterministic, sandbox-isolated `SCIPIndexProbe` that produces a re-validated `.codegenie/index/scip-index.scip` per-repo binary, honors a committed/pre-warmed `node_modules/` via read-only mount, **never** invokes `npm install`, and emits an `additionalProperties: false` `scip_index` slice whose `confidence` ladder honestly reflects the three resolution outcomes (`high` / `medium` / `low`).

## Acceptance criteria

- [ ] `src/codegenie/probes/scip_index.py` exists, defines `class SCIPIndexProbe(Probe)`, sets `name = "scip_index"`, `layer = "B"`, `applies_to_languages = ["typescript", "javascript"]`, `applies_to_tasks = ["*"]`, `requires = ["language_detection", "node_build_system"]`, `timeout_seconds = 600`, `version: str = "1.0.0"`, `consumes_peer_outputs = False`, and `declared_inputs` matching `phase-arch-design.md §"Component design" #7` (tsconfig*, package.json, src/**, lockfiles) **plus** `"src/codegenie/catalogs/tools/digests.yaml"` so a digest catalog edit invalidates the `scip_index` cache.
- [ ] `src/codegenie/schema/probes/scip_index.schema.json` ships Draft 2020-12, declares `schema_version: "v1"`, `additionalProperties: false` at root **and** at every nested object, and validates the slice shape: `node_modules_present: bool`, `lockfiles_resolved: bool`, `coverage_pct: number (0..100)`, `last_indexed_commit: string`, `scip_index_path: string` (the relative path `.codegenie/index/scip-index.scip`), `tool_digest: string`, `confidence: enum("high","medium","low")`, `warnings: array(WarningId-pattern strings)`, `errors: array(string)`.
- [ ] `src/codegenie/probes/__init__.py` adds **one** additive import line registering `SCIPIndexProbe`. No rewrite of the registry list.
- [ ] Cache key for `SCIPIndexProbe` includes the `scip-typescript` `tool_digest` from `tools/digests.yaml`, the recursive `node_modules` content hash (if present), and lockfile hashes — different `tool_digest`, lockfile bytes, or `node_modules` contents → different cache key (per ADR-0004 + ADR-0013).
- [ ] The probe **never** invokes `npm install`, `pnpm install`, `yarn install`, or any package-manager subprocess. A grep test (`tests/unit/probes/test_scip_no_install_invocation.py`) asserts the source file does not call `tools.npm.*`/`tools.pnpm.*`/`tools.yarn.*` and that `subprocess.*` is not imported.
- [ ] `tests/unit/probes/test_scip_index.py` red test exists, was committed failing, and is now green. It covers (a) `node_modules` present → read-only mount; probe records `node_modules_present: true`, `confidence: high` (mocked wrapper returns >95% resolution); (b) `node_modules` absent + parseable lockfile → `node_modules_present: false, lockfiles_resolved: true, confidence: medium`; (c) neither present → `confidence: low`, slice still emitted; (d) wrapper raises `ToolNotFound` → `confidence: low`, structured warning `scip.tool_not_found`; (e) wrapper non-zero exit → `confidence: low`, warning `scip.indexer_nonzero_exit`; (f) cache-key changes when `tool_digest` changes; (g) cache-key changes when `node_modules` content hash changes.
- [ ] `tests/adv/test_truncated_scip_index.py` adversarial test exists: stub wrapper writes a 16-byte truncated `.scip` file; the probe's parent-side grammar re-validation rejects it; probe emits `confidence: low`, warning `scip.grammar_revalidation_failed`; cache entry **is not stored** (assert no `.codegenie/cache/blobs/scip_index/*` file appears); no OOM.
- [ ] `tests/adv/test_scip_compiler_plugin_attempt.py` adversarial test exists: a hostile `tsconfig.json` with a malicious `extends:` chain pointing at `../../../etc/passwd` is supplied; the sandboxed wrapper invocation contains it; no host file is read or modified; the probe emits a slice (the wrapper's failure surfaces honestly as `confidence: low` with `warnings: ["scip.tsconfig_extends_unresolved"]`).
- [ ] The probe's slice round-trips through `OutputSanitizer` Passes 1–5 idempotently (`pass4(pass4(slice)) == pass4(slice)`); verified by a single assertion in `test_scip_index.py`.
- [ ] Definition-of-done items hold: `ruff check`, `ruff format --check`, `mypy --strict` on `src/codegenie/probes/scip_index.py` and the new schema (jsonschema self-validation), `pytest tests/unit/probes/test_scip_index.py tests/adv/test_truncated_scip_index.py tests/adv/test_scip_compiler_plugin_attempt.py -q` all pass. Per-probe local coverage reported in the PR body (floor: 85 line / 75 branch per Definition-of-done in stories/README.md for `probes/scip_index.py`).
- [ ] `.codegenie/index/scip-index.scip` is written under the **analyzed repo**, **not** under `.codegenie/cache/`. The schema declares this path; the probe's `Path` construction is `snapshot.root / ".codegenie" / "index" / "scip-index.scip"`. The `cache gc` extension that preserves this binary lands in S4-04 — this story only asserts the write location.

## Implementation outline

1. **Write the sub-schema first.** `src/codegenie/schema/probes/scip_index.schema.json` per `phase-arch-design.md §"Component design" #7` and ADR-0013's enumerated fields. `additionalProperties: false` at every level. `schema_version: "v1"`. Cross-link the comment to `SCHEMA-EVOLUTION-POLICY.md`.
2. **Implement `SCIPIndexProbe.run(snapshot, ctx)`:**
   - **Resolve `node_modules` policy.** `nm = snapshot.root / "node_modules"`; `node_modules_present = nm.is_dir()`; if present, `ro_bind = (nm,)`; else `ro_bind = ()`.
   - **Resolve lockfile fallback.** If `node_modules_present is False`, walk `pnpm-lock.yaml` / `yarn.lock` / `package-lock.json` via `ParsedManifestMemo`-aware reads (Phase 1) → `lockfiles_resolved: bool`. Do **not** parse the full lockfile here; existence + Phase-1-cached parse is sufficient evidence.
   - **Compute the output path.** `scip_path = snapshot.root / ".codegenie" / "index" / "scip-index.scip"`. Create the parent dir with `mkdir(parents=True, exist_ok=True)`.
   - **Dispatch to the wrapper.** `result = await tools.scip_typescript.run(repo_root=snapshot.root, raw_output_path=scip_path, node_modules_path=nm if node_modules_present else None, timeout_s=600)`.
   - **Re-validate.** After the wrapper returns, open `scip_path` and parse against the SCIP protobuf grammar (vendored or pip-installed `scip` protobuf bindings; pure-Python; well-fuzzed). On `DecodeError` → `ToolOutputMalformed("scip.grammar_revalidation_failed", ...)`.
   - **Compute `coverage_pct`.** From `result.documents` / `result.symbols` — the wrapper surfaces resolution stats; if not, derive as `count(resolved_imports) / count(total_imports) * 100`. Document the formula in a module docstring.
   - **Map to confidence ladder** (ADR-0013):
     - `high` — `node_modules_present and coverage_pct > 95`.
     - `medium` — (`node_modules_present is False and lockfiles_resolved`) or (`node_modules_present and 70 <= coverage_pct <= 95`).
     - `low` — neither `node_modules` nor parseable lockfiles; or wrapper non-zero exit; or re-validation fails.
   - **Resolve `last_indexed_commit`.** Either via `gitpython` (default per ADR-0011 Open Question #7) or by reading `result.metadata`; record the commit SHA the index reflects.
   - **Emit the slice.** Return `ProbeOutput(name="scip_index", schema_slice={...}, confidence=<computed>, warnings=[...], errors=[...])`. **On `confidence == "low"` due to re-validation failure, `unlink()` `scip_path`** so the next gather doesn't see a corrupt file (the cache-blob non-storage is separate; this is the on-disk index sanity).
3. **Cache-key extension.** In whatever pattern S2-06 established, add `tool_digest` and the `node_modules` recursive content hash (if present) to the per-probe cache-key composition. **Skip subtrees the lockfile parsers already pin** to keep the hash cost bounded — document this in a module-level comment.
4. **Failure handling.** Every exception path emits a typed `WarningId`-pattern warning (`scip.tool_not_found`, `scip.indexer_nonzero_exit`, `scip.indexer_timeout`, `scip.grammar_revalidation_failed`, `scip.tsconfig_extends_unresolved`, `scip.no_lockfiles`). The pattern is enforced by the sub-schema; the probe emits strings matching it.
5. **Register** in `src/codegenie/probes/__init__.py` with one additive import. Add `scip_index` to the envelope's `probes.*` `$ref` composition under `repo_context.schema.json` (optional reference; the slice is optional at envelope level).
6. **No `npm install` discipline.** No `tools.npm.*` import; no `subprocess.run(["npm", ...])`; the grep test from acceptance criterion 5 enforces this mechanically.

## TDD plan — red / green / refactor

### Red — failing test first

Path: `tests/unit/probes/test_scip_index.py`

```python
"""Pins: SCIPIndexProbe honors node_modules read-only mount; never invokes npm install;
confidence ladder (high/medium/low) reflects ADR-0013; cache key includes tool_digest;
parent-side SCIP grammar re-validation rejects corruption.
Traces to: phase-arch-design.md §Component design #7; ADR-0013; ADR-0004."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock
from codegenie.probes.scip_index import SCIPIndexProbe

@pytest.mark.asyncio
async def test_node_modules_present_high_confidence(tmp_path, monkeypatch):
    (tmp_path / "node_modules" / "_pkg").mkdir(parents=True)
    (tmp_path / "tsconfig.json").write_text('{"compilerOptions":{}}')
    (tmp_path / "package.json").write_text('{"name":"x"}')
    # mock the wrapper to claim 99% resolution and produce a valid .scip
    _stub_wrapper(monkeypatch, coverage_pct=99.0, valid_scip=True)
    out = await SCIPIndexProbe().run(_snapshot(tmp_path), _ctx(tmp_path))
    assert out.schema_slice["node_modules_present"] is True
    assert out.confidence == "high"
    assert (tmp_path / ".codegenie" / "index" / "scip-index.scip").is_file()

@pytest.mark.asyncio
async def test_node_modules_absent_lockfile_resolvable_medium(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text('{"name":"x"}')
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n")
    _stub_wrapper(monkeypatch, coverage_pct=60.0, valid_scip=True)
    out = await SCIPIndexProbe().run(_snapshot(tmp_path), _ctx(tmp_path))
    assert out.schema_slice["node_modules_present"] is False
    assert out.schema_slice["lockfiles_resolved"] is True
    assert out.confidence == "medium"

@pytest.mark.asyncio
async def test_no_node_modules_no_lockfile_low(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text('{"name":"x"}')
    _stub_wrapper(monkeypatch, coverage_pct=10.0, valid_scip=True)
    out = await SCIPIndexProbe().run(_snapshot(tmp_path), _ctx(tmp_path))
    assert out.confidence == "low"
    assert "scip.no_lockfiles" in out.schema_slice["warnings"]

@pytest.mark.asyncio
async def test_wrapper_tool_not_found_low(tmp_path, monkeypatch):
    from codegenie.errors import ToolNotFound
    async def _raise(*a, **k): raise ToolNotFound("scip-typescript")
    monkeypatch.setattr("codegenie.tools.scip_typescript.run", _raise)
    out = await SCIPIndexProbe().run(_snapshot(tmp_path), _ctx(tmp_path))
    assert out.confidence == "low"
    assert "scip.tool_not_found" in out.schema_slice["warnings"]

@pytest.mark.asyncio
async def test_cache_key_changes_with_tool_digest(tmp_path, monkeypatch):
    # set the digest catalog to value A; capture key1.
    # set the digest catalog to value B; capture key2.
    # assert key1 != key2.
    ...

def test_source_imports_no_subprocess_and_no_install():
    src = Path("src/codegenie/probes/scip_index.py").read_text()
    assert "subprocess" not in src
    assert "npm install" not in src
    assert "pnpm install" not in src
```

Path: `tests/adv/test_truncated_scip_index.py`

```python
@pytest.mark.asyncio
async def test_truncated_scip_rejected(tmp_path, monkeypatch):
    """Pins: parent-side SCIP grammar re-validation rejects truncated bytes;
    confidence: low; cache blob NOT stored; no OOM."""
    # Stub the wrapper to write 16 bytes of garbage to raw_output_path.
    _stub_wrapper_writes_truncated(monkeypatch, byte_count=16)
    out = await SCIPIndexProbe().run(_snapshot(tmp_path), _ctx(tmp_path))
    assert out.confidence == "low"
    assert "scip.grammar_revalidation_failed" in out.schema_slice["warnings"]
    assert not list((tmp_path / ".codegenie" / "cache" / "blobs" / "scip_index").glob("*")) \
        if (tmp_path / ".codegenie" / "cache" / "blobs" / "scip_index").exists() else True
```

Path: `tests/adv/test_scip_compiler_plugin_attempt.py`

```python
@pytest.mark.asyncio
async def test_hostile_tsconfig_extends_contained(tmp_path):
    """Pins: hostile tsconfig.json extends: chain is sandbox-contained;
    no host file modified; probe emits confidence: low + warning."""
    (tmp_path / "tsconfig.json").write_text('{"extends":"../../../etc/passwd"}')
    (tmp_path / "package.json").write_text('{"name":"x"}')
    sentinel = Path("/tmp/codegenie_sentinel_should_not_exist_S4_01")
    if sentinel.exists(): sentinel.unlink()
    out = await SCIPIndexProbe().run(_snapshot(tmp_path), _ctx(tmp_path))
    assert not sentinel.exists()
    assert out.confidence == "low"
```

Run `pytest tests/unit/probes/test_scip_index.py tests/adv/test_truncated_scip_index.py tests/adv/test_scip_compiler_plugin_attempt.py -q`. Expect all red — the probe and schema don't exist yet.

### Green — smallest impl shape

1. Write `src/codegenie/schema/probes/scip_index.schema.json` with the shape from Acceptance criterion 2.
2. Write `src/codegenie/probes/scip_index.py` implementing the **Implementation outline**.
3. Register in `src/codegenie/probes/__init__.py`.
4. Extend `cache_key` derivation with `tool_digest` + `node_modules` content hash.
5. Wire schema $ref into `repo_context.schema.json` under `probes.scip_index` (optional).
6. Iterate until green.

### Refactor — bounded

- Extract `_compute_confidence(node_modules_present, lockfiles_resolved, coverage_pct, wrapper_ok, revalidation_ok) -> Confidence` to a private pure function with a property-based test (Hypothesis) covering the truth table. This is the one place "judgment as code" lives in the probe — keep it deterministic and tested.
- Extract `_revalidate_scip(scip_path: Path) -> None` to a private helper; raises `ToolOutputMalformed` on failure. Keeps `run()` readable.
- Module-level constants for warning IDs: `_W_TOOL_NOT_FOUND = "scip.tool_not_found"`, etc. — one source of truth.
- Run `ruff format`, `ruff check`, `mypy --strict`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/scip_index.py` | New — `SCIPIndexProbe` implementation |
| `src/codegenie/schema/probes/scip_index.schema.json` | New — `additionalProperties: false`, `schema_version: "v1"` |
| `src/codegenie/probes/__init__.py` | Edit — one additive import line |
| `src/codegenie/schema/repo_context.schema.json` | Edit — `$ref` compose `scip_index.schema.json` under `probes.scip_index` (optional) |
| `src/codegenie/coordinator/cache_key.py` (or wherever S2-06 lives) | Edit — additive: include `tool_digest` + `node_modules` content hash for `scip_index` |
| `tests/unit/probes/test_scip_index.py` | New — unit tests covering node_modules / lockfile / cache-key branches |
| `tests/unit/probes/test_scip_no_install_invocation.py` | New — grep test asserting no `npm install` / no `subprocess` import |
| `tests/adv/test_truncated_scip_index.py` | New — adversarial: truncated `.scip` rejection |
| `tests/adv/test_scip_compiler_plugin_attempt.py` | New — adversarial: hostile `tsconfig.json` extends: chain |

## Out of scope

- **`cache gc` preserve-index logic** — handled by S4-04. This story only asserts the write goes to `.codegenie/index/`, not `.codegenie/cache/`.
- **Per-file tree-sitter findings cache shape** — handled by S4-02. This probe writes a binary, not per-file findings.
- **`IndexHealthProbe` reads of `scip.last_indexed_commit`** — handled by S3-01. This story emits the field; the consumer is already implemented.
- **`TestCoverageMappingProbe` SCIP consumption** — handled by S7-05.
- **CI pre-warm `npm ci --ignore-scripts` orchestration** — that's the integration-test plumbing in S8-02; this probe never invokes it.
- **Phase 14 continuous-gather pre-gather step** — Phase 14 deliverable per ADR-0013.
- **Incremental SCIP indexing** — explicitly rejected in `final-design.md §"Components" §3.1`. Full re-index every cache-miss; ~25 s acceptable for the POC.

## Notes for the implementer

- **The single most important invariant is "never invoke `npm install`".** Read ADR-0013 before writing a line of probe code. The grep test in `test_scip_no_install_invocation.py` is a backstop; the discipline is on you. If a future PR proposes "let's just install on cache-miss" — that's a Phase 14 orchestration concern, not a probe concern.
- **`.codegenie/index/scip-index.scip` is a per-repo binary, not a cache blob.** It belongs *inside the analyzed repo*, alongside `.codegenie/cache/` but in a sibling directory. `cache gc` (S4-04) treats them differently. If you find yourself writing `ctx.cache_dir / "scip-index.scip"` — stop, re-read `phase-arch-design.md §"Component design" #17`.
- **The grammar re-validation is the load-bearing security mitigation** for "`scip-typescript` is a code-loading interpreter running on attacker-controlled bytes". Don't skip it because "the wrapper already returned successfully" — the wrapper is the producer; the probe is the consumer; the protobuf parse is the integrity check.
- **`coverage_pct` is honest evidence, not a gameable metric.** If the wrapper doesn't surface resolution stats, do not invent a number. Emit `coverage_pct: null` (the schema must permit) and degrade `confidence` to `medium` with `warnings: ["scip.coverage_unknown"]`. Better to be honest than guessing.
- **The `node_modules` content hash for cache-key is non-trivial cost.** Per ADR-0013, "skipping subtrees the lockfile parsers already pin" is the documented optimization. For Phase 2 just hash the top-level entry names + their `package.json` `version` fields; revisit if benches show this dominates incremental gather time.
- **The confidence ladder is a truth table, not a heuristic.** Keep `_compute_confidence` as a pure function with an exhaustive property test. The reviewer (and future readers) should be able to see at a glance which inputs produce which outcome. No floating-point comparisons against unstated thresholds.
- **Sanitizer Pass 4 + Pass 5 idempotence** is asserted at the slice level. The probe doesn't run the sanitizer itself (the coordinator does); but the slice shape must be Pass-4-stable (no fields that re-hash to different bytes on a second pass). The `tool_digest` field is already a content hash; re-fingerprinting a hash is a no-op. Keep it that way.
- A grep for `import requests`, `import httpx`, `import urllib3`, `import socket`, `subprocess` in `scip_index.py` should return empty. The `import-linter` rule (Phase 0) bans them; the probe must work via `tools.scip_typescript` only.
- **Hostile `tsconfig.json extends:` chain** is the adversarial fixture for the "compiler plugin attempt" attack class. The sandbox is the mitigation; the probe trusts the sandbox. Do not add file-existence checks before invoking the wrapper — that's defense in the wrong layer.
