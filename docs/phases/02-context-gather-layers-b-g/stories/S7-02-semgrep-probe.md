# Story S7-02 — `SemgrepProbe` + rule-pack pinning + per-file cache + `--paranoid` cross-file

**Step:** Step 7 — Ship Layer D, Layer E (real + stubs), Layer G; plant per-file findings sub-caches
**Status:** Ready
**Effort:** M
**Depends on:** S7-01, S1-05, S2-03
**ADRs honored:** ADR-0004 (rule-pack digests pinned), `final-design.md` D12 (semgrep rule-pack network policy)

## Context

`SemgrepProbe` (G1) is one of Phase 2's two load-bearing SAST scanners (the other is gitleaks, S7-03). It runs semgrep with rule packs pinned by SHA-256 digest, against the changed-files set, with `--network=none`, populating the per-file findings sub-cache so incremental gathers skip unchanged files. Cross-file taint mode is **opt-in only** via `--paranoid`; in that mode the per-file cache is bypassed. Findings are normalized to the `SemgrepFinding` model with `message_content_hash` (Pass 4 fingerprint of the raw message — raw never stored). The probe consumes `tools.semgrep.run` from Step 1; the rule pack catalog from Step 2; the per-file cache module from S7-01.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #13` — interface, `declared_inputs` globs, `requires=["language_detection"]`, 360 s timeout, rule-pack pinning, per-file cache key, custom-rules location, `--paranoid` semantics.
  - `../phase-arch-design.md §"Data model" → SemgrepFinding` — `message_content_hash` is Pass 4 fingerprint; raw message not stored.
  - `../phase-arch-design.md §"Process view"` — Wave 5 (Layer G) dispatch; per-file cache consulted before invocation.
  - `../phase-arch-design.md §"Edge cases"` — pathological regex → `ToolTimeout`; rule pack network → refused (sandbox `--network=none`).
- **Phase ADRs:**
  - `../ADRs/0004-tools-digests-yaml-pin-manifest.md` — rule-pack digests live in `tools/digests.yaml`.
- **Source design:**
  - `../final-design.md §"Components" §7 Layer G — SAST + behavioral hints`.
  - `../final-design.md §"Conflict-resolution table" D12` — winner `[S]` "sandbox `--network=none`; rule packs pre-warmed from pinned digests".
- **Existing code:**
  - `src/codegenie/tools/semgrep.py` (S1-05) — `async run(...) -> SemgrepResult` wrapper.
  - `src/codegenie/catalogs/semgrep_rule_packs.yaml` (S2-03) — declares which packs apply per task; closed enum on `task_types`.
  - `src/codegenie/coordinator/per_file_cache.py` (S7-01) — sub-cache module.
  - `src/codegenie/output_sanitizer.py` (S1-09) — Pass 4 BLAKE3 fingerprinter rewrites `message`-keyed fields.

## Goal

Ship `src/codegenie/probes/semgrep.py` and `src/codegenie/schema/probes/semgrep.schema.json` — invokes `tools.semgrep.run` with pinned rule packs + `--network=none`; consults `PerFileCache` keyed on `(file_content_blake3, rule_pack_version, tool_digest)` to skip unchanged files; emits `SemgrepFinding[]` post-sanitization; `--paranoid` flag (config knob) enables cross-file taint and bypasses the per-file cache.

## Acceptance criteria

- [ ] `src/codegenie/probes/semgrep.py` exports `SemgrepProbe(Probe)` with `name="semgrep"`, `declared_inputs = ["src/**/*.{ts,tsx,mts,cts,js,mjs,cjs}", "Dockerfile", "Dockerfile.*", ".codegenie/semgrep-rules/**/*.yaml"]`, `requires=["language_detection"]`, `applies_to_languages=["*"]`, `timeout_seconds=360`.
- [ ] On `run`, resolves rule-pack set from `catalogs/semgrep_rule_packs.yaml` filtered by detected language(s) + task type from `ctx.task_type`. Loads pinned digests from `catalogs/tools/digests.yaml`. Invokes `tools.semgrep.run(rules=<resolved>, paths=<dirty>, env={"SEMGREP_RULES_CACHE": <pinned_dir>}, extra_args=["--disable-version-check", "--disable-metrics"], network="none", timeout=self.timeout_seconds)`.
- [ ] Per-file cache: for each candidate file, compute `content_hash` (already on `ctx.input_snapshot`); key = `(content_hash, rule_pack_version_hash, semgrep_digest)`; on hit, append cached findings to result; on miss, include file in the actual semgrep invocation. After invocation, write per-file findings back to cache.
- [ ] `--paranoid` mode (config flag `semgrep.paranoid: bool` in `ProbeContext.config`): when `True`, **bypasses the per-file cache entirely**; invokes semgrep with `--config p/taint-mode` added to the rule set; runs over the full file set, not just changed files; emits `paranoid_mode: true` in the slice metadata.
- [ ] `SemgrepFinding` Pydantic model with `extra="forbid"` and fields exactly `{rule_id, file, line_start, line_end, severity ∈ {"info","warn","error"}, rule_pack, rule_pack_version, message_content_hash}`. No `message` / `raw` / `extra` fields permitted.
- [ ] `src/codegenie/schema/probes/semgrep.schema.json` declares `additionalProperties: false` at root and every nested block; `schema_version: "v1"`; matches the Pydantic model exactly.
- [ ] Pathological regex → `ToolTimeout` (raised by wrapper) → probe emits `confidence: "low"` + `errors=["semgrep.timeout: rule_id=<id>"]`; gather continues.
- [ ] `tests/unit/probes/test_semgrep.py` covers: happy path on recorded fixture (`tests/fixtures/tool_outputs/semgrep_happy.json`); per-file cache hit on second invocation (assert `tools.semgrep.run` called with empty `paths` or not called at all on full hit); `--paranoid` bypasses cache + emits `paranoid_mode: true`; `ToolTimeout` → `confidence: "low"`; rule-pack-version change invalidates per-file cache (different `version_key`).
- [ ] `tests/adv/test_semgrep_redos.py` — pathological regex rule (`(a+)+b` on a long input) → `ToolTimeout` fires within `timeout_seconds + ε`; sandbox kill verified via `tools.semgrep.run` mock; `confidence: low`.
- [ ] `tests/adv/test_malformed_semgrep_output.py` — invalid JSON stdout → `ToolOutputMalformed` raised; `confidence: low`; probe does not crash.
- [ ] `tests/golden/semgrep/<fixture>/expected.json` — one golden per probe (Step 8 ratchets all goldens; this story plants the canonical one).
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Create `src/codegenie/probes/semgrep.py`:
   - `SemgrepProbe(Probe)` with class attributes per acceptance criteria.
   - `async run(self, snapshot, ctx) -> ProbeOutput`:
     1. Resolve rule-pack set from `semgrep_rule_packs.yaml` × `ctx.task_type` × detected languages.
     2. Compute `rule_pack_version_hash` (BLAKE3 over the sorted list of `(pack_name, pack_digest)` tuples — deterministic).
     3. If `ctx.config.get("semgrep", {}).get("paranoid", False)`:
        - Cross-file mode; skip per-file cache; invoke semgrep over the full set; collect findings.
     4. Else:
        - Iterate candidate files from `snapshot.changed_files`; for each, consult `PerFileCache(self._cache_root, tool="semgrep").get(content_hash, rule_pack_version_hash, semgrep_digest)`.
        - Bucket files into `cache_hits` (findings appended directly) and `cache_misses` (need semgrep invocation).
        - One semgrep invocation over `cache_misses`; partition results by file; write each file's findings back to cache.
     5. Normalize all findings to `SemgrepFinding` (replace `message` with `message_content_hash` here — Pass 4 also runs at envelope time, this is belt-and-suspenders).
     6. Build `ProbeOutput` with `slice={"findings": [...], "rule_packs_in_use": [...], "rule_pack_version": ..., "paranoid_mode": ...}`.
2. Create `src/codegenie/schema/probes/semgrep.schema.json` — match the Pydantic model 1:1; `schema_version: "v1"`; `additionalProperties: false`.
3. Register probe in `src/codegenie/probes/__init__.py` (one import + `@register_probe` decorator on the class).
4. Plant `tests/fixtures/tool_outputs/semgrep_happy.json` + 1-2 ReDoS rule fixtures.

## TDD plan — red / green / refactor

### Red

Path: `tests/unit/probes/test_semgrep.py`.

```python
import pytest
from codegenie.probes.semgrep import SemgrepProbe
from codegenie.coordinator.per_file_cache import PerFileCache

async def test_happy_path_emits_findings(tmp_repo, ctx, semgrep_recorded_fixture):
    probe = SemgrepProbe()
    out = await probe.run(tmp_repo.snapshot, ctx)
    assert out.confidence == "high"
    assert all(f.message_content_hash for f in out.slice["findings"])
    # No raw message field anywhere.
    assert "message" not in {k for f in out.slice["findings"] for k in f.model_dump()}

async def test_per_file_cache_hit_skips_invocation(tmp_repo, ctx, mocker):
    spy = mocker.spy("codegenie.tools.semgrep", "run")
    probe = SemgrepProbe()
    await probe.run(tmp_repo.snapshot, ctx)  # populate cache
    spy.reset_mock()
    await probe.run(tmp_repo.snapshot, ctx)  # second run — all hits
    assert spy.call_count == 0 or spy.call_args.kwargs.get("paths") == []

async def test_paranoid_bypasses_cache(tmp_repo, ctx_paranoid, mocker):
    spy = mocker.spy("codegenie.tools.semgrep", "run")
    probe = SemgrepProbe()
    out = await probe.run(tmp_repo.snapshot, ctx_paranoid)
    assert out.slice["paranoid_mode"] is True
    assert spy.call_count == 1  # invoked even on second run

async def test_timeout_lowers_confidence(tmp_repo, ctx, monkeypatch):
    async def raise_timeout(*a, **kw):
        from codegenie.errors import ToolTimeout
        raise ToolTimeout("rule_id=test.redos")
    monkeypatch.setattr("codegenie.tools.semgrep.run", raise_timeout)
    out = await SemgrepProbe().run(tmp_repo.snapshot, ctx)
    assert out.confidence == "low"
    assert any("semgrep.timeout" in e for e in out.errors)
```

Adversarial: `tests/adv/test_semgrep_redos.py` + `tests/adv/test_malformed_semgrep_output.py` — see acceptance criteria for shape.

### Green

Minimal impl per outline. Use the `ProbeOutput` constructor from Phase 0; the slice is a plain dict; Pass 4 in `OutputSanitizer` will rewrite `message` fields at envelope time as belt-and-suspenders, but the probe itself normalizes to `message_content_hash` *before* returning, so the unsanitized `ProbeOutput` already conforms.

### Refactor

- Pull rule-pack resolution into a `_resolve_rule_packs(catalog, task_type, languages)` private helper — testable in isolation.
- Helper `_compute_version_key(rule_packs) -> str` — BLAKE3 over sorted tuples.
- Module docstring naming `phase-arch-design.md §"Component design" #13`, `final-design.md` D12.
- Constants for the SEMGREP env vars at module scope.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/semgrep.py` | New — `SemgrepProbe` class. |
| `src/codegenie/schema/probes/semgrep.schema.json` | New — sub-schema. |
| `src/codegenie/probes/__init__.py` | Register `SemgrepProbe`. |
| `tests/unit/probes/test_semgrep.py` | New — 5 unit tests. |
| `tests/adv/test_semgrep_redos.py` | New — ReDoS rule timeout. |
| `tests/adv/test_malformed_semgrep_output.py` | New — invalid JSON handling. |
| `tests/fixtures/tool_outputs/semgrep_happy.json` | New — recorded happy-path output. |
| `tests/golden/semgrep/happy/expected.json` | New — golden file. |

## Out of scope

- **Cross-file taint default-on** — refused (`final-design.md` D12); `--paranoid` is opt-in.
- **Rule pack auto-update** — refused (`final-design.md` D12); rule packs are pinned via digest; updating is an ADR-gated bump.
- **Custom rule authoring tooling** — Phase 2 reads from `.codegenie/semgrep-rules/`; tooling to author rules is out of scope.
- **Cross-language taint** — semgrep's polyglot mode not exercised in Phase 2.
- **History scan** — semgrep over `git log` is not invoked; gitleaks (S7-03) has the history-scan opt-in.

## Notes for the implementer

- **The `rule_pack_version_hash` is the load-bearing cache-key component.** If you compute it over the unsorted list, cache hits flake when YAML key order changes. Sort by `(pack_name, pack_digest)` lexicographically before hashing; document the sort discipline in the helper's docstring.
- **`SEMGREP_RULES_CACHE` must point inside the pre-warmed pin directory** that ADR-0004's install hook produces. The probe never writes to this directory at gather time. If the directory is missing, the wrapper raises `ToolInvariantViolation` from S1-05 — surface that as `confidence: low`, don't crash.
- **`--paranoid` is a config flag, not a CLI flag.** Users opt in via `.codegenie/config.yaml`'s `semgrep.paranoid: true`. The probe reads `ctx.config`; if the key is missing, default `False`. Don't introduce a `gather` CLI flag for this — keep the CLI surface stable.
- **Per-file cache write happens *after* normalization, not before.** Cache the `SemgrepFinding`-shaped objects, not the raw semgrep JSON. The cache key is stable across rule-pack-version changes (changing version invalidates), so the cached shape can evolve with sub-schema version bumps.
- **Pass 4 will rewrite anything Pass 4 finds.** If you leave `message` as a string in the slice for any reason, Pass 4 turns it into `{content_hash, entropy_band, length}` at envelope time — which then fails the sub-schema's `additionalProperties: false`. Normalize to `message_content_hash` in the probe; never emit `message` from the slice.
- **`paranoid_mode` in the slice is for downstream visibility.** Phase 3 / Phase 8 consumers need to know if a given `repo-context.yaml`'s semgrep slice reflects cross-file taint or per-file. The field is required, not optional.
- **`additionalProperties: false` at root + nested blocks** is the ADR-0004 envelope from Phase 1 — preserve it. Adding a stray `extra` field will fail schema validation downstream.
