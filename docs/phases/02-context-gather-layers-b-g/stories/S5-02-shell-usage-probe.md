# Story S5-02 — `ShellUsageProbe` + `shell_replacements/node.yaml` consumer + `runtime_trace_pending`

**Step:** Step 5 — Ship Layer C static probes (`DockerfileProbe`, `ShellUsageProbe`, `CertificateProbe`, `EntrypointProbe`, plus `RuntimeTraceProbe` class-only)
**Status:** Ready
**Effort:** M
**Depends on:** S5-01 (`DockerfileProbe` — peer-output source via standard `requires`), S2-03 (`shell_replacements/node.yaml` catalog + schema)
**ADRs honored:** ADR-0002 (`RuntimeTraceProbe` deferral — this probe declares `runtime_trace_pending: true` where static evidence is incomplete), ADR-0008 (closed-enum dispatch pattern via catalog), production ADR-0001 (facts not judgments — emits replacement candidates, never asserts migration safety)

## Context

`ShellUsageProbe` walks the `RUN` directives in the `dockerfile` peer output AND consumes the `shell_replacements/node.yaml` catalog (planted by S2-03) to emit a list of **replacement candidates** for Phase 7's Chainguard distroless migration. The probe is a **synthesizer** — it does not parse Dockerfiles itself; it reads `DockerfileProbe`'s parsed instructions via the standard `requires = ["dockerfile"]` peer-output mechanism (NOT `consumes_peer_outputs` per `phase-arch-design.md §"Component design" #11` — these are plain dependents, not frozen-snapshot consumers like `IndexHealthProbe`).

The load-bearing piece is the `runtime_trace_pending` field. ADR-0002 defers `RuntimeTraceProbe` (C4) to Phase 5 — Phase 2's static evidence is incomplete by design for cases that need runtime confirmation (e.g., "is this `RUN sh -c '...'` invocation actually exercised at container start?"). This probe declares `runtime_trace_pending: true` in its slice whenever the static evidence is incomplete; consumers (Phase 7's distroless planner) read it as "static finding; dynamic confirmation owed by Phase 5." **Not setting this field correctly is a silent-staleness failure** — same shape as the `IndexHealthProbe`-style honesty discipline that runs through Phase 2.

Closed-enum dispatch over the catalog's `replacement_type` field (per ADR-0008's pattern for `ConventionProbe`, applied here at a smaller scale) means a catalog edit that adds a new replacement type without updating the probe's `match/case` is caught at CI. The Step 5 catalog has a few entries (`sh`, `bash`, `curl_pipe_sh`, `apt_get`, `apk_add`); the parity-lint pattern from S2-04 doesn't apply at the probe level here, but the closed-enum schema validation does.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #11 ShellUsageProbe (C5), CertificateProbe (C6), EntrypointProbe (C7)` — full interface contract; the three siblings share the `requires = ["dockerfile"]` shape.
  - `../phase-arch-design.md §"Data model" ShellUsageSlice` — replacement-candidate list shape, `runtime_trace_pending` field semantics.
  - `../phase-arch-design.md §"Edge cases"` — `RUN curl ... | sh` (the boundary case for `runtime_trace_pending: true`), multi-stage with shell usage only in build stage (the runtime-stage emits `runtime_trace_pending: false` if no shell usage; `true` otherwise).
- **Phase ADRs:**
  - `../ADRs/0002-c4-runtime-trace-class-only-phase-5-impl.md` — the `runtime_trace_pending` signal contract.
  - `../ADRs/0008-conventions-catalog-closed-enum-ci-lint.md` — the closed-enum dispatch pattern (this probe applies the same pattern to `replacement_type`).
- **Production ADRs:**
  - `../../../production/adrs/0001-facts-not-judgments.md` (or the canonical name) — emit candidates with confidence, never migration verdicts.
- **Source design:**
  - `../final-design.md §"Components" §4.5` — synthesis ledger row for C5/C6/C7.
  - `../localv2.md §5.3 C5` — slice contract.
- **Existing code (Step 1–5 output):**
  - `src/codegenie/probes/dockerfile.py` (S5-01) — emits per-stage instruction list with `RUN` form classification (`exec | shell | unparsable`).
  - `src/codegenie/catalogs/shell_replacements/node.yaml` (S2-03) — replacement entries keyed by `pattern` (regex or substring) with `replacement_type` (closed enum), `recommended_action` (string), `severity` (closed enum).
  - `src/codegenie/catalogs/shell_replacements/_schema.json` (S2-03) — schema with closed-enum `replacement_type`.
  - `src/codegenie/probes/base.py` (Phase 0) — `Probe` ABC; `requires` mechanism returns peer outputs from coordinator.

## Goal

Ship a deterministic, in-process, no-network `ShellUsageProbe` that consumes `dockerfile` peer output and the `shell_replacements/node.yaml` catalog, emits a strict `shell_usage` slice (`additionalProperties: false`, `schema_version: "v1"`) with a list of replacement candidates per Dockerfile stage, declares `runtime_trace_pending: true` whenever static evidence is incomplete, and dispatches over `replacement_type` via `match/case` on a closed enum.

## Acceptance criteria

- [ ] `src/codegenie/probes/shell_usage.py` exists, defines `class ShellUsageProbe(Probe)`, sets `name = "shell_usage"`, `layer = "C"`, `applies_to_languages = ["*"]`, `applies_to_tasks = ["*"]`, `requires = ["dockerfile"]`, `timeout_seconds = 5`, `declared_inputs = ["src/codegenie/catalogs/shell_replacements/node.yaml"]` (so a catalog edit invalidates cache entries; same ADR-0006 invalidation pattern as Phase 1's `node_manifest` consuming `ci_providers.yaml`). Does NOT declare `consumes_peer_outputs`.
- [ ] `applies()` returns `True` only when the `dockerfile` peer output exists and has at least one stage with at least one `RUN` instruction; returns `False` otherwise (no Dockerfile → no shell to analyze).
- [ ] `src/codegenie/schema/probes/shell_usage.schema.json` exists, Draft 2020-12, `schema_version: "v1"` at root, `additionalProperties: false` at every nesting level, declares `runtime_trace_pending: boolean` (required), `replacement_candidates: array` (required) where each item has `{pattern_matched: string, replacement_type: string (closed enum), recommended_action: string, severity: string (closed enum), stage_index: int, instruction_index: int, source_run_form: string (closed enum from S5-01)}`, and a `warnings: array` with the standard `WarningId` pattern.
- [ ] The probe's internal dispatch over `replacement_type` uses **Python `match/case`** on a closed enum literal set (drawn from the catalog `_schema.json`); a `case _:` default raises an internal `ProbeAssertion` so a catalog edit that adds a new `replacement_type` without updating this probe's dispatch is caught at runtime AND by a coverage test (the dispatch-coverage test below). This mirrors ADR-0008's pattern at the probe scale.
- [ ] Red tests exist and were committed failing; green tests pass: `tests/unit/probes/test_shell_usage.py` covers (a) `RUN curl ... | sh` directive → at least one candidate emitted with `replacement_type: "curl_pipe_sh"`, `runtime_trace_pending: true` (boundary case from edge-case table); (b) `RUN apt-get install -y ca-certificates` → candidate with `replacement_type: "apt_get"`; (c) `RUN ["node", "app.js"]` (exec form, no shell builtin invoked) → empty `replacement_candidates`, `runtime_trace_pending: false`; (d) `RUN sh -c 'echo hi'` → candidate with `replacement_type: "sh"`, `runtime_trace_pending: true`; (e) multi-stage Dockerfile with shell usage only in `build` stage and an `exec`-form `CMD` in `runtime` stage → candidates carry `stage_index`, `runtime_trace_pending: true` (because the build-stage shell usage is `pending` confirmation); (f) `RUN` instruction with `run_form: "unparsable"` (from S5-01's medium-confidence path) → `runtime_trace_pending: true` + warning `shell_usage.unparsable_run_directive`; (g) `dockerfile` peer-output missing → `applies()` returns `False`, no warning; (h) `dockerfile` peer with empty stages → `applies()` returns `False`.
- [ ] `tests/unit/probes/test_shell_usage_dispatch_coverage.py` ships a dispatch-coverage test that parametrizes over every `replacement_type` value declared in `catalogs/shell_replacements/_schema.json`'s enum and asserts each is reached by at least one fixture; missing case → test fails (this is the probe-scale equivalent of ADR-0008's parity lint).
- [ ] `tests/unit/probes/test_shell_usage_schema.py` ships an `additionalProperties: false` rejection test at root AND at the `replacement_candidates[*]` nesting level (two separate tests, one assertion target each).
- [ ] `src/codegenie/probes/__init__.py` gains one additive import line registering `ShellUsageProbe`.
- [ ] PR body documents (1) per-probe local coverage at 90/80 floor (not on the 85/75 carve-out list); (2) `runtime_trace_pending` semantics — one paragraph in the PR description explicitly noting the field is the Phase 5 promotion path.

## Implementation outline

1. **Write `shell_usage.schema.json` first.** Mirror `phase-arch-design.md §"Data model" ShellUsageSlice`. `runtime_trace_pending: boolean` required at root. `replacement_candidates: array` required (may be empty). `replacement_type` and `severity` are closed-enum strings drawn verbatim from `catalogs/shell_replacements/_schema.json`. `source_run_form` is the closed enum from S5-01's `dockerfile.schema.json` (`["exec", "shell", "unparsable"]`).
2. **Implement `ShellUsageProbe.run(ctx, snapshot)`:**
   - Pull `dockerfile_slice = ctx.peer_outputs["dockerfile"].schema_slice` via the Phase 0 `requires` mechanism. If absent → return early with `applies()`-style guard already-handled.
   - Load the `shell_replacements/node.yaml` catalog from the import-time-built `catalogs.SHELL_REPLACEMENTS_NODE` mapping (S2-03 lands this). Each entry has `{pattern, replacement_type, recommended_action, severity}`.
   - For each stage (with `stage_index`), for each `RUN` instruction (with `instruction_index`):
     - If `run_form == "unparsable"` → emit warning `shell_usage.unparsable_run_directive`; set `runtime_trace_pending = True`; continue.
     - Walk catalog entries; for each entry whose `pattern` matches the `RUN` directive's raw text (substring or anchored regex per the catalog entry's declared mode — S2-03 catalog `_schema.json` should declare match-mode; if not, default to substring), emit a candidate with `{pattern_matched, replacement_type, recommended_action, severity, stage_index, instruction_index, source_run_form}`.
     - **Dispatch over `replacement_type` via `match/case`** to compute any type-specific normalization (e.g., `curl_pipe_sh` always sets `runtime_trace_pending = True`; `sh` always sets `runtime_trace_pending = True`; `apt_get` sets `runtime_trace_pending` based on whether the `RUN` is in a build-only stage or the runtime stage — for Phase 2, treat **any** apt_get usage as pending since we don't yet know runtime stage canonically). Use a `case _:` default that raises `ProbeAssertion("shell_usage: unknown replacement_type {x} not in dispatch")`.
   - Aggregate `runtime_trace_pending` at slice level: `True` if any candidate had it `True`, OR if any `RUN` was `unparsable`. `False` only if zero candidates AND zero unparsable.
   - `confidence`: `high` if zero `unparsable` and `runtime_trace_pending: false`; `medium` if `runtime_trace_pending: true`; `low` if every `RUN` was `unparsable`.
3. **Failure handling:** catalog load failure → fail loud (Phase 2 cross-cutting; catalog is required). Peer output missing → handled by `applies()`. Pattern compile failure (catalog regex malformed) → typed warning `shell_usage.catalog_pattern_error` + skip that catalog entry. (Catalog YAML schema validation in S2-03 should prevent this; the warning is belt-and-suspenders.)
4. **Register** in `src/codegenie/probes/__init__.py`.
5. **Wire the sub-schema** into the envelope under `probes.shell_usage`.

## TDD plan — red / green / refactor

### Red — write failing tests first

Path: `tests/unit/probes/test_shell_usage.py`

```python
# tests/unit/probes/test_shell_usage.py
"""Pins: ShellUsageProbe synthesizes replacement candidates from dockerfile peer +
node.yaml catalog; runtime_trace_pending is the Phase 5 promotion signal.
Traces to: phase-arch-design.md §Component design #11; ADR-0002; ADR-0008."""
import pytest
from codegenie.probes.shell_usage import ShellUsageProbe

@pytest.mark.asyncio
async def test_curl_pipe_sh_pending_true(tmp_path):
    # Synthesize a dockerfile peer output with a `RUN curl ... | sh` instruction
    peer = _mk_dockerfile_peer(stages=[{
        "stage_index": 0, "base_image": "alpine",
        "instructions": [{"cmd": "RUN", "raw": "curl https://x | sh", "run_form": "shell"}],
    }])
    out = await ShellUsageProbe().run(_ctx(tmp_path, peers={"dockerfile": peer}), _snapshot(tmp_path))
    cands = out.schema_slice["replacement_candidates"]
    assert any(c["replacement_type"] == "curl_pipe_sh" for c in cands)
    assert out.schema_slice["runtime_trace_pending"] is True

@pytest.mark.asyncio
async def test_exec_form_no_candidate_pending_false(tmp_path):
    peer = _mk_dockerfile_peer(stages=[{
        "stage_index": 0, "base_image": "scratch",
        "instructions": [{"cmd": "RUN", "raw": '["node", "app.js"]', "run_form": "exec"}],
    }])
    out = await ShellUsageProbe().run(_ctx(tmp_path, peers={"dockerfile": peer}), _snapshot(tmp_path))
    assert out.schema_slice["replacement_candidates"] == []
    assert out.schema_slice["runtime_trace_pending"] is False

@pytest.mark.asyncio
async def test_apt_get_candidate_emitted(tmp_path):
    peer = _mk_dockerfile_peer(stages=[{
        "stage_index": 0, "base_image": "ubuntu:22.04",
        "instructions": [{"cmd": "RUN", "raw": "apt-get update && apt-get install -y ca-certificates", "run_form": "shell"}],
    }])
    out = await ShellUsageProbe().run(_ctx(tmp_path, peers={"dockerfile": peer}), _snapshot(tmp_path))
    assert any(c["replacement_type"] == "apt_get" for c in out.schema_slice["replacement_candidates"])

@pytest.mark.asyncio
async def test_unparsable_run_emits_warning_and_pending(tmp_path):
    peer = _mk_dockerfile_peer(stages=[{
        "stage_index": 0, "base_image": "alpine",
        "instructions": [{"cmd": "RUN", "raw": "${UNRESOLVED} --flag", "run_form": "unparsable"}],
    }])
    out = await ShellUsageProbe().run(_ctx(tmp_path, peers={"dockerfile": peer}), _snapshot(tmp_path))
    assert out.schema_slice["runtime_trace_pending"] is True
    assert "shell_usage.unparsable_run_directive" in out.schema_slice["warnings"]

@pytest.mark.asyncio
async def test_no_dockerfile_peer_applies_false(tmp_path):
    probe = ShellUsageProbe()
    assert probe.applies(_snapshot(tmp_path, dockerfile_peer_present=False)) is False

@pytest.mark.asyncio
async def test_multi_stage_carries_stage_index(tmp_path):
    peer = _mk_dockerfile_peer(stages=[
        {"stage_index": 0, "base_image": "node:20", "instructions": [
            {"cmd": "RUN", "raw": "sh -c 'npm run build'", "run_form": "shell"}]},
        {"stage_index": 1, "base_image": "gcr.io/distroless/nodejs20", "instructions": [
            {"cmd": "CMD", "raw": '["node", "app.js"]', "run_form": "exec"}]},
    ])
    out = await ShellUsageProbe().run(_ctx(tmp_path, peers={"dockerfile": peer}), _snapshot(tmp_path))
    cands = out.schema_slice["replacement_candidates"]
    assert any(c["stage_index"] == 0 for c in cands)
    assert all(c["stage_index"] != 1 for c in cands)  # runtime stage is clean
```

Dispatch coverage test at `tests/unit/probes/test_shell_usage_dispatch_coverage.py`:

```python
def test_every_replacement_type_in_schema_is_reached(catalog_schema_enum, fixture_per_type):
    """Pin ADR-0008-style discipline at probe scale: a new replacement_type in the
    catalog schema without a fixture exercising it fails CI before merge."""
    ...
```

Schema rejection tests at `tests/unit/probes/test_shell_usage_schema.py`:

```python
def test_subschema_rejects_unknown_root_field(): ...
def test_subschema_rejects_unknown_candidate_field(): ...
```

Run `pytest tests/unit/probes/test_shell_usage.py tests/unit/probes/test_shell_usage_dispatch_coverage.py tests/unit/probes/test_shell_usage_schema.py -q`. All red.

### Green — make it pass

1. Land `src/codegenie/schema/probes/shell_usage.schema.json` first.
2. Implement `src/codegenie/probes/shell_usage.py` per **Implementation outline**.
3. Register in `src/codegenie/probes/__init__.py`.
4. Compose sub-schema into envelope.
5. Run tests; iterate.

### Refactor — clean up

- Extract `_emit_candidate(raw, stage_idx, instr_idx, catalog_entry) -> dict` if the body grows past ~40 lines.
- Module-level constants for warning IDs (`_WARN_UNPARSABLE = "shell_usage.unparsable_run_directive"`, `_WARN_CATALOG_PATTERN = "shell_usage.catalog_pattern_error"`).
- Confirm the `match/case` has a `case _:` raising `ProbeAssertion`; document inline why this is load-bearing (closed-enum invariant).
- `ruff format` + `ruff check`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/shell_usage.py` | New — `ShellUsageProbe` implementation |
| `src/codegenie/schema/probes/shell_usage.schema.json` | New — strict slice schema |
| `src/codegenie/probes/__init__.py` | Edit — one additive import line registering `ShellUsageProbe` |
| `src/codegenie/schema/repo_context.schema.json` | Edit — `$ref` compose `shell_usage.schema.json` under `probes.shell_usage` |
| `tests/unit/probes/test_shell_usage.py` | New — unit tests |
| `tests/unit/probes/test_shell_usage_dispatch_coverage.py` | New — dispatch coverage over closed-enum `replacement_type` |
| `tests/unit/probes/test_shell_usage_schema.py` | New — `additionalProperties: false` rejection tests |

## Out of scope

- **`CertificateProbe` + `EntrypointProbe`** — siblings shipped by S5-03; share the `requires = ["dockerfile"]` shape but read different fields.
- **`RuntimeTraceProbe` itself** — class-only, `applies()=False`, shipped by S5-04. This probe just sets `runtime_trace_pending: true`; the Phase 5 implementation will read those slices to know what to dynamically confirm.
- **Adversarial fixture for hostile shell-replacement patterns** (e.g., a catalog entry with a ReDoS regex) — handled by S8-01's adversarial corpus completion (`shell_usage.catalog_pattern_error` is the warning to assert on).
- **Helm values walking** — `final-design.md §4.5` mentions Helm values + `package.json#engines` as additional inputs; in Phase 2 we restrict to the Dockerfile `RUN` set per the simpler scope (`phase-arch-design.md §"Component design" #11` says "walks Dockerfile `RUN` directives + `shell_replacements/node.yaml` catalog"). Helm/`engines` are a Phase 7 extension; this story does NOT preempt the scope.
- **Catalog parity lint at probe level** — ADR-0008's `conventions_catalog_parity` CI script lints `ConventionProbe`'s `match/case`; we apply the discipline here via the dispatch-coverage TEST rather than a separate CI script. If a future probe also needs this pattern, generalize the script then; not now (Rule 2 — Simplicity First).

## Notes for the implementer

- `runtime_trace_pending` is the load-bearing field. Read ADR-0002 carefully: this is the **Phase 5 promotion signal**. Misclassifying `runtime_trace_pending: false` when the static evidence is actually incomplete is a silent-staleness failure — exactly the kind of dishonesty that the whole gather pipeline is structured to prevent. When in doubt, set `true`.
- The catalog patterns are **declared in YAML, never inlined** in the probe. If you find yourself writing `if "curl" in run_directive and "| sh" in run_directive`, stop — move it to `node.yaml` as a new entry. The catalog is the extension point. (S2-03 lands the catalog with its initial entries; if a pattern is missing, this story may extend it — note the extension in PR body.)
- Catalog regex patterns are the one place attacker-controllable bytes meet a regex engine in this probe. Patterns in `node.yaml` should be bounded (no nested `*`/`+`); the catalog `_schema.json` should constrain pattern length (~256 char cap is reasonable). If a pattern looks like it could ReDoS, flag it in PR review and tighten before merging.
- The closed-enum `match/case` dispatch with `case _:` raising `ProbeAssertion` is what catches future drift. Do NOT replace `case _:` with a soft fallthrough — that would silently swallow a new `replacement_type`, breaking the discipline at the seam where it matters.
- A grep for `import subprocess` / `import requests` / `import httpx` / `import urllib3` / `import socket` in this file should return empty. Synthesis-only probe, in-process.
- Per cross-cutting concern, per-probe local coverage in the PR body; this probe is at the 90/80 floor (NOT on the 85/75 carve-out list). The S8-06 ratchet cannot recover.
- The `stage_index` field on each candidate is what Phase 7's distroless planner uses to distinguish build-stage shell usage (acceptable) from runtime-stage shell usage (must be eliminated). Don't conflate; keep `stage_index` faithful.
