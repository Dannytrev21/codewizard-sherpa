# Story S5-01 — `DockerfileProbe` + `dockerfile` pip dep + sub-schema

**Step:** Step 5 — Ship Layer C static probes (`DockerfileProbe`, `ShellUsageProbe`, `CertificateProbe`, `EntrypointProbe`, plus `RuntimeTraceProbe` class-only)
**Status:** Ready
**Effort:** M
**Depends on:** S2-07 (`SCHEMA-EVOLUTION-POLICY.md` + `schema_version: "v1"` discipline), S1-08 (`tools/digests.yaml` + verifier CI — for the new wheel pin)
**ADRs honored:** ADR-0004 (`tools/digests.yaml` pin manifest), ADR-0006 (sanitizer Pass 4 + Pass 5 round-trip on emitted slice), production ADR-0005 (no LLM in gather), production ADR-0001 (facts not judgments — emits parsed instructions, no migration verdict)

## Context

`DockerfileProbe` is the **Layer C anchor**. It is the only probe in Step 5 that reads bytes off disk; the three sibling Layer C static probes (`ShellUsageProbe`, `CertificateProbe`, `EntrypointProbe`) all consume its parsed output via the standard `requires = ["dockerfile"]` peer-output mechanism (NOT `consumes_peer_outputs` — these are plain dependents per `phase-arch-design.md §"Component design" #11`, not frozen-snapshot consumers like `IndexHealthProbe`). Two design tensions concentrate here. First, **parser choice**: `final-design.md §4.1` and ADR-0006 (production side) commit to the pure-Python `dockerfile` library — no `buildctl debug dump-llb` fallback (would require BuildKit running and expand the sandbox attack surface for marginal gain on a small minority of complex Dockerfiles). Second, **honest confidence**: unresolvable variable interpolation in `RUN` directives (`RUN ${WHATEVER}`) does NOT crash the probe — it emits `confidence: medium` with the unresolved directive recorded verbatim (facts, not judgments).

This is a Tier-0 pure-Python probe with `sandbox: network="none"` (inherited; the `dockerfile` library is in-process). The new pip dep is the load-bearing piece: it gets pinned in `pyproject.toml` AND gets a wheel-hash entry in `tools/digests.yaml` (S1-08's manifest) AND lands in the `security` job's `pip-audit`/`osv-scanner` closure (S8-06 wires that — this story declares the obligation in PR notes).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #12 DockerfileProbe (C1)` — full interface contract (`declared_inputs`, internal structure, performance envelope, failure behavior).
  - `../phase-arch-design.md §"Data model"` — `DockerfileSlice` shape (parsed instructions, multi-stage detection, RUN shape, ports, entrypoint form).
  - `../phase-arch-design.md §"Edge cases"` — multi-stage with `FROM ... AS <name>`, malformed Dockerfile, `RUN` with unresolvable variable, `.dockerignore` parsing.
- **Phase ADRs:**
  - `../ADRs/0004-tools-digests-yaml-pin-manifest.md` — the `dockerfile` wheel-hash entry pattern.
  - `../ADRs/0006-output-sanitizer-passes-4-5.md` — emitted slice must round-trip through Pass 4 + Pass 5 unmutated (no secret-like fields, no marker patterns).
- **Production ADRs:**
  - `../../../production/adrs/0005-no-llm-in-gather-pipeline.md` — no LLM call for `RUN` directive resolution; unresolved → `confidence: medium`.
- **Source design:**
  - `../final-design.md §"Components" §4.1 DockerfileProbe (C1)` — synthesis ledger row.
  - `../localv2.md §5.3 C1` — slice contract.
- **Existing code (Step 1 + 2 + 4 output):**
  - `src/codegenie/probes/base.py` (Phase 0) — `Probe` ABC contract.
  - `src/codegenie/probes/__init__.py` — explicit additive import seam.
  - `src/codegenie/errors.py` (S1-01) — `ToolNonZeroExit`, `SizeCapExceeded`, schema-evolution errors.
  - `src/codegenie/output_sanitizer.py` (S1-09) — Pass 4 + Pass 5 (consumes slice).
  - `src/codegenie/coordinator.py` (Phase 0 + S1-11) — standard two-arg dispatch path (this probe does NOT declare `consumes_peer_outputs`).
  - `src/codegenie/catalogs/tools/digests.yaml` (S1-08) — the digest manifest the new wheel hash lands in.
- **External docs:**
  - `dockerfile` Python library (PyPI) — pinned to a specific version + wheel digest.

## Goal

Ship a deterministic, in-process, no-network `DockerfileProbe` that pure-Python-parses every `Dockerfile*` under the repo root, emits a strict `dockerfile` slice (`additionalProperties: false` at every nesting level, `schema_version: "v1"`) with parsed instructions / multi-stage info / `RUN` shape / exposed ports / entrypoint form, downgrades confidence on unresolvable interpolation rather than crashing, and lands the `dockerfile` library wheel hash in `tools/digests.yaml`.

## Acceptance criteria

- [ ] `src/codegenie/probes/dockerfile.py` exists, defines `class DockerfileProbe(Probe)`, sets `name = "dockerfile"`, `layer = "C"`, `applies_to_languages = ["*"]`, `applies_to_tasks = ["*"]`, `requires = []`, `timeout_seconds = 15`, `declared_inputs = ["Dockerfile", "Dockerfile.*", ".dockerignore"]`, and does NOT declare `consumes_peer_outputs` (defaults to `False`).
- [ ] `applies()` returns `True` if at least one Dockerfile (case-insensitive, root + any path matching the glob) exists; returns `False` otherwise.
- [ ] `src/codegenie/schema/probes/dockerfile.schema.json` exists, Draft 2020-12, declares `schema_version: "v1"` at root, `additionalProperties: false` at every nesting level, validates `DockerfileSlice` per `phase-arch-design.md §"Data model"` (stages list, instructions per stage, `RUN` shape with form classification `exec | shell | unparsable`, `EXPOSE` ports, base images, `ENTRYPOINT` + `CMD` raw form).
- [ ] `pyproject.toml` adds `dockerfile==<pinned-version>` to `[project.dependencies]`; `src/codegenie/catalogs/tools/digests.yaml` adds a wheel-hash entry under a new `pip_wheels:` section (or extends the existing wheel-pin section per S1-08's manifest shape); the `tool_digests_verify` CI script (S1-08) refuses to start the gather if the resolved wheel hash differs.
- [ ] Red test exists and was committed failing; green tests pass: `tests/unit/probes/test_dockerfile.py` covers (a) single-stage Dockerfile → all instructions parsed, `confidence: high`; (b) multi-stage with `FROM <img> AS <name>` → stages list populated with named stages preserved; (c) `RUN apt-get update && apt-get install -y curl` → form classified as `shell`; (d) `RUN ["node", "app.js"]` → form classified as `exec`; (e) `RUN ${UNRESOLVED_VAR} --flag` → recorded verbatim, `confidence: medium`, slice does NOT crash; (f) `EXPOSE 8080/tcp 9090/udp` → ports recorded with protocol; (g) malformed Dockerfile (truncated mid-instruction) → `confidence: low` with structured warning; (h) no Dockerfile present → `applies()` returns `False`.
- [ ] `tests/unit/probes/test_dockerfile_schema.py` ships an explicit `additionalProperties: false` rejection test at every nesting level (root, per-stage, per-instruction) — a synthetic envelope with `probes.dockerfile.unknown_field: 1` and one with `probes.dockerfile.stages[0].unknown_field: 1` both fail `SchemaValidationError` with JSON Pointers identifying the unknown field. Each variant is a separate test (one assertion target per test).
- [ ] `tests/unit/probes/test_dockerfile_sanitizer_roundtrip.py` ships a Hypothesis-style round-trip test: emitted `ProbeOutput.schema_slice` passes through `OutputSanitizer.scrub` and the **post-scrub dict equals the pre-scrub dict byte-for-byte** (no secret-like field names; no `<|im_start|>` / `[INST]` markers in the parsed instruction strings of fixtures used). This pins ADR-0006's idempotence-on-clean-data property for the new slice.
- [ ] `src/codegenie/probes/__init__.py` gains one additive import line registering `DockerfileProbe` (no rewrite of registry list).
- [ ] PR body notes: (1) the new `dockerfile` pip dep + wheel hash + the obligation that S8-06 add it to `pip-audit`/`osv-scanner` closure; (2) per-probe local coverage report at 90/80 floor (per cross-cutting concern; this probe is NOT on the 85/75 carve-out list).

## Implementation outline

1. **Write `dockerfile.schema.json` first** — mirror `phase-arch-design.md §"Data model" DockerfileSlice`. `additionalProperties: false` at root AND at every nested object (stages list elements, instructions, `EXPOSE` entries). `schema_version: "v1"` at root. Each `run_form` field constrained to the closed enum `["exec", "shell", "unparsable"]`. Each `warnings[]` entry matches the Phase 1 `WarningId` pattern `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`.
2. **Pin the `dockerfile` library:**
   - Resolve the latest stable version on PyPI.
   - Add `dockerfile==<version>` to `pyproject.toml`'s `[project.dependencies]`.
   - Compute the wheel SHA-256 and add it to `tools/digests.yaml` under the manifest's existing pip-wheel section (S1-08 manifest shape); if S1-08 did not stand up a pip-wheel section, add one as a minimal additive change and document in `tools/digests.yaml`'s header comment.
3. **Implement `DockerfileProbe.run(ctx, snapshot)`:**
   - Walk `snapshot.root` for `Dockerfile`, `Dockerfile.*` (per glob; respect Phase 1 exclusion set); read each file as bytes (10 MB cap via Phase 1's `safe_bytes` reader, if present; otherwise hard-cap inline).
   - Parse each via `dockerfile.parse_string(content)`; wrap in try/except — parser raise → record `warnings: ["dockerfile.parse_error"]` + `confidence: low` for that file; continue with the next file.
   - For each parsed Dockerfile, build a per-stage list. For each instruction:
     - Record `cmd` (instruction name, e.g., `RUN`, `COPY`, `EXPOSE`, `ENTRYPOINT`, `CMD`, `FROM`, `WORKDIR`, `USER`, `ARG`, `ENV`).
     - For `RUN`: classify form — JSON-array literal at the AST level → `exec`; shell string → `shell`; if the value contains an unresolved `${VAR}` AND the parser surfaced it as unresolved → `unparsable` + `confidence: medium` accumulated.
     - For `EXPOSE`: parse each token; default protocol `tcp` if unspecified.
     - For `FROM`: capture base image ref AND optional `AS <stage_name>`.
     - For `ENTRYPOINT` / `CMD`: capture raw form (exec vs shell) for `EntrypointProbe` to read via `requires`.
   - Aggregate: `confidence` is `high` if every file parsed cleanly and zero `unparsable` `RUN`s; `medium` if any `unparsable` directive; `low` if any file failed to parse at all.
4. **Failure handling:** every parser exception is caught into a typed warning ID (`dockerfile.parse_error`, `dockerfile.size_cap_exceeded`, `dockerfile.expose_malformed`). `WarningId` pattern enforced by the sub-schema.
5. **Register** in `src/codegenie/probes/__init__.py` with one additive import line.
6. **Wire the sub-schema** into the envelope via `$ref` composition under `probes.dockerfile`.

## TDD plan — red / green / refactor

### Red — write failing tests first

Path: `tests/unit/probes/test_dockerfile.py`

```python
# tests/unit/probes/test_dockerfile.py
"""Pins: DockerfileProbe parses single+multi-stage; classifies RUN form;
records unresolvable interpolation as confidence:medium, not crash.
Traces to: phase-arch-design.md §Component design #12; ADR-0006."""
import pytest
from codegenie.probes.dockerfile import DockerfileProbe

@pytest.mark.asyncio
async def test_single_stage_high_confidence(tmp_path):
    (tmp_path / "Dockerfile").write_text(
        "FROM node:20-alpine\nWORKDIR /app\nCOPY . .\nRUN npm ci --ignore-scripts\nCMD [\"node\",\"app.js\"]\n"
    )
    out = await DockerfileProbe().run(_ctx(tmp_path), _snapshot(tmp_path))
    assert out.schema_slice["stages"][0]["base_image"] == "node:20-alpine"
    assert any(i["cmd"] == "RUN" and i["run_form"] == "shell" for i in out.schema_slice["stages"][0]["instructions"])
    assert out.confidence == "high"

@pytest.mark.asyncio
async def test_multi_stage_named_stages_preserved(tmp_path):
    (tmp_path / "Dockerfile").write_text(
        "FROM node:20 AS build\nRUN npm run build\n"
        "FROM gcr.io/distroless/nodejs20 AS runtime\nCOPY --from=build /app /app\n"
    )
    out = await DockerfileProbe().run(_ctx(tmp_path), _snapshot(tmp_path))
    names = [s.get("stage_name") for s in out.schema_slice["stages"]]
    assert names == ["build", "runtime"]

@pytest.mark.asyncio
async def test_run_exec_form_classified(tmp_path):
    (tmp_path / "Dockerfile").write_text('FROM scratch\nRUN ["node", "app.js"]\n')
    out = await DockerfileProbe().run(_ctx(tmp_path), _snapshot(tmp_path))
    run_insn = next(i for i in out.schema_slice["stages"][0]["instructions"] if i["cmd"] == "RUN")
    assert run_insn["run_form"] == "exec"

@pytest.mark.asyncio
async def test_unresolvable_interpolation_medium_not_crash(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM alpine\nRUN ${UNRESOLVED_VAR} --flag\n")
    out = await DockerfileProbe().run(_ctx(tmp_path), _snapshot(tmp_path))
    assert out.confidence == "medium"
    run_insn = next(i for i in out.schema_slice["stages"][0]["instructions"] if i["cmd"] == "RUN")
    # facts, not judgments: verbatim record, no resolution
    assert "${UNRESOLVED_VAR}" in run_insn["raw"]

@pytest.mark.asyncio
async def test_expose_ports_with_protocol(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM alpine\nEXPOSE 8080/tcp 9090/udp\n")
    out = await DockerfileProbe().run(_ctx(tmp_path), _snapshot(tmp_path))
    ports = out.schema_slice["stages"][0]["expose"]
    assert {"port": 8080, "protocol": "tcp"} in ports
    assert {"port": 9090, "protocol": "udp"} in ports

@pytest.mark.asyncio
async def test_malformed_dockerfile_low_confidence(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM alpine\nRUN \\\n")  # truncated mid-continuation
    out = await DockerfileProbe().run(_ctx(tmp_path), _snapshot(tmp_path))
    assert out.confidence == "low"
    assert "dockerfile.parse_error" in out.schema_slice["warnings"]

def test_subschema_rejects_unknown_field_at_root():
    from codegenie.coordinator.schema_validator import SchemaValidator
    envelope = {"probes": {"dockerfile": {"stages": [], "unknown_field": 1}}}
    with pytest.raises(Exception) as ei:
        SchemaValidator().validate(envelope)
    assert "unknown_field" in str(ei.value)

def test_subschema_rejects_unknown_field_in_stage():
    from codegenie.coordinator.schema_validator import SchemaValidator
    envelope = {"probes": {"dockerfile": {"stages": [{"base_image": "alpine", "unknown_field": 1, "instructions": []}]}}}
    with pytest.raises(Exception) as ei:
        SchemaValidator().validate(envelope)
    assert "unknown_field" in str(ei.value)
```

Sanitizer round-trip lives in `tests/unit/probes/test_dockerfile_sanitizer_roundtrip.py`:

```python
def test_dockerfile_slice_sanitizer_idempotent_on_clean_data(tmp_path):
    # build a known-clean slice, push through Pass 1-5, assert byte-for-byte equality.
    ...
```

Run `pytest tests/unit/probes/test_dockerfile.py tests/unit/probes/test_dockerfile_schema.py tests/unit/probes/test_dockerfile_sanitizer_roundtrip.py -q`. All red.

### Green — make it pass

1. Land `src/codegenie/schema/probes/dockerfile.schema.json` first (the contract).
2. Add `dockerfile==<version>` to `pyproject.toml` + wheel hash to `tools/digests.yaml`. Run `pip install -e .` locally; verify the digest verifier (S1-08) passes.
3. Implement `src/codegenie/probes/dockerfile.py` per **Implementation outline**.
4. Register in `src/codegenie/probes/__init__.py`.
5. Compose sub-schema into envelope.
6. Run tests; iterate.

### Refactor — clean up

- Extract per-stage parsing into a private `_parse_stage(parsed_stage) -> dict` helper if `run()` body exceeds ~40 lines.
- Move the `WarningId` constants to module-level (`_WARN_PARSE_ERROR = "dockerfile.parse_error"`, etc.).
- Confirm no `import requests` / `import httpx` / `import socket` in the file (import-linter rule from Phase 0 enforces).
- `ruff format` + `ruff check`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/dockerfile.py` | New — `DockerfileProbe` implementation |
| `src/codegenie/schema/probes/dockerfile.schema.json` | New — strict slice schema |
| `src/codegenie/probes/__init__.py` | Edit — one additive import line registering `DockerfileProbe` |
| `src/codegenie/schema/repo_context.schema.json` | Edit — `$ref` compose `dockerfile.schema.json` under `probes.dockerfile` |
| `pyproject.toml` | Edit — pin `dockerfile==<version>` |
| `src/codegenie/catalogs/tools/digests.yaml` | Edit — add `dockerfile` wheel SHA-256 |
| `tests/unit/probes/test_dockerfile.py` | New — unit tests |
| `tests/unit/probes/test_dockerfile_schema.py` | New — sub-schema rejection tests |
| `tests/unit/probes/test_dockerfile_sanitizer_roundtrip.py` | New — Pass 4 + Pass 5 idempotence on clean slice |

## Out of scope

- **`buildctl debug dump-llb` fallback** — explicitly rejected per `final-design.md §4.1`. No BuildKit dependency.
- **Resolving `${VAR}` against `ARG` declarations** — would require multi-pass variable resolution; Phase 2 records verbatim with `confidence: medium`. A future phase may layer a Tier-1 resolution pass; that is NOT this story.
- **Helm chart parsing** — Helm values are read by `ShellUsageProbe` (S5-02) for the `runtime_trace_pending` heuristic; this probe stays strictly on Dockerfiles.
- **Hostile-Dockerfile adversarial fixture** (`RUN curl ... | sh` boundary defense) — handled by S6-03 against `SyftSBOMProbe`, not here. The DockerfileProbe parses the bytes; the sandbox boundary is exercised by C2.
- **`pip-audit` / `osv-scanner` integration** for the new wheel — declared as obligation in PR body; wired by S8-06.
- **Bench canary** for parse time — advisory only; S8-05 covers the cold e2e canary that includes this probe.

## Notes for the implementer

- The `dockerfile` Python library is a new external dep; once you pin the version, **verify the wheel SHA-256 against PyPI's published hash before adding to `tools/digests.yaml`**. A spoofed hash makes S1-08's verifier useless. Document the hash source (PyPI JSON API URL or `pip download --no-deps` + `sha256sum`) in the `tools/digests.yaml` comment block.
- `applies()` only checks for Dockerfile presence — do NOT pre-parse here. The dispatch path is: `applies()` → cheap; `run()` → does the work. Pre-parsing in `applies()` defeats the per-probe timeout.
- `RUN` form classification matters for `EntrypointProbe` AND for `ShellUsageProbe`: both read this field. If the classifier is ambiguous, prefer `unparsable` over a guess — downstream consumers will treat `unparsable` as "static evidence incomplete" and emit `runtime_trace_pending: true`.
- The `dockerfile` library may surface its own `unresolved_var` flag depending on version; rely on the AST node type / field rather than a string match on `${`. Bind the test to the AST shape, not the library version.
- The `WarningId` pattern is enforced by the sub-schema's regex constraint — if a future warning ID lacks the dot (e.g., `parse_error` instead of `dockerfile.parse_error`), schema validation fails. Encode this discipline directly; don't let it drift.
- Per cross-cutting concern, this probe's local coverage is reported in the PR body; the **S8-06 ratchet cannot recover** if `dockerfile.py` lands below 90/80. Don't merge below floor.
- A grep for `import requests` / `import httpx` / `import urllib3` / `import socket` / `subprocess` in this file should return empty. Pure-Python in-process parsing only.
