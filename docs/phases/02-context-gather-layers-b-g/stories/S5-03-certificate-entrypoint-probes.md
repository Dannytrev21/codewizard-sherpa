# Story S5-03 — `CertificateProbe` + `EntrypointProbe` + sub-schemas

**Step:** Step 5 — Ship Layer C static probes (`DockerfileProbe`, `ShellUsageProbe`, `CertificateProbe`, `EntrypointProbe`, plus `RuntimeTraceProbe` class-only)
**Status:** Ready
**Effort:** S
**Depends on:** S5-01 (`DockerfileProbe` — peer-output source via standard `requires`)
**ADRs honored:** ADR-0002 (`RuntimeTraceProbe` deferral — both probes may emit `runtime_trace_pending: true` for cases that need runtime confirmation), production ADR-0001 (facts not judgments — emit certificate paths + entrypoint forms, no security or migration verdicts)

## Context

Two small sibling synthesizer probes that consume `DockerfileProbe`'s peer output via `requires = ["dockerfile"]`. **`CertificateProbe`** walks every stage's instructions and emits a list of certificate-related findings: `COPY *.crt`, `COPY *.pem`, `ADD *.crt`, `ADD *.pem` source paths, plus any `RUN apt-get install ... ca-certificates` directive. **`EntrypointProbe`** extracts each stage's `ENTRYPOINT` + `CMD` raw form and classifies the runtime stage's entrypoint as `exec` (e.g., `["node","app.js"]`) vs `shell` (e.g., `node app.js`).

Both probes are Tier-0 pure-Python synthesizers (no subprocess, no network, no parsing — `DockerfileProbe` already parsed everything). `CertificateProbe` matters for Phase 7's distroless migration: ca-certificate bundles need to be carried forward explicitly when moving to `gcr.io/distroless/*`. `EntrypointProbe`'s exec-vs-shell classification matters because shell-form entrypoints invoke `sh -c` implicitly — incompatible with distroless images that don't ship a shell. Both probes set `runtime_trace_pending: true` (per ADR-0002) for cases where the static evidence is incomplete: e.g., a `COPY ./bundle/ /etc/ssl/certs/` (does it contain `.crt` files? unknowable statically) → `certificate.runtime_trace_pending: true`; e.g., a multi-stage Dockerfile where the runtime stage's `CMD` is inherited from a base image (unknowable from THIS Dockerfile alone) → `entrypoint.runtime_trace_pending: true`.

These two probes are small enough to ship together in one story — combined LOC under ~150, combined test surface ~10 tests. Shipping them separately would create two PRs of the same shape, which violates Rule 2 (Simplicity First). The dispatch is structurally narrow (substring matching against a small fixed pattern list); coverage carve-out is NOT needed because the test surface is small and each branch has a real intent target.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #11 ShellUsageProbe (C5), CertificateProbe (C6), EntrypointProbe (C7)` — full interface contract for both probes.
  - `../phase-arch-design.md §"Data model" CertificateSlice + EntrypointSlice` — slice shapes.
  - `../phase-arch-design.md §"Edge cases"` — `COPY ./bundle/ /etc/ssl/certs/` (opaque bundle), runtime-stage entrypoint inherited from base image (unknowable statically).
- **Phase ADRs:**
  - `../ADRs/0002-c4-runtime-trace-class-only-phase-5-impl.md` — the `runtime_trace_pending` signal contract.
- **Production ADRs:**
  - `../../../production/adrs/0001-facts-not-judgments.md` (or the canonical name) — emit findings, never verdicts.
- **Source design:**
  - `../final-design.md §"Components" §4.5` — synthesis ledger row for C5/C6/C7.
  - `../localv2.md §5.3 C6, C7` — slice contracts.
- **Existing code (Step 1–5 output):**
  - `src/codegenie/probes/dockerfile.py` (S5-01) — emits per-stage instruction list with `cmd`, `raw`, `run_form`, and the parsed `COPY`/`ADD`/`ENTRYPOINT`/`CMD` source/dest fields.
  - `src/codegenie/probes/base.py` (Phase 0) — `Probe` ABC.
  - `src/codegenie/probes/__init__.py` — registry seam.

## Goal

Ship two deterministic, in-process, no-network synthesizer probes — `CertificateProbe` and `EntrypointProbe` — that consume `DockerfileProbe`'s peer output and emit strict `certificate` and `entrypoint` slices (`additionalProperties: false`, `schema_version: "v1"`) populated with certificate-related findings AND entrypoint exec-vs-shell classification respectively, both declaring `runtime_trace_pending: true` where the static evidence is incomplete.

## Acceptance criteria

- [ ] `src/codegenie/probes/certificate.py` exists, defines `class CertificateProbe(Probe)`, sets `name = "certificate"`, `layer = "C"`, `applies_to_languages = ["*"]`, `applies_to_tasks = ["*"]`, `requires = ["dockerfile"]`, `timeout_seconds = 5`, `declared_inputs = []` (consumes peer output only). Does NOT declare `consumes_peer_outputs`. `applies()` returns `True` only when `dockerfile` peer is present with at least one stage.
- [ ] `src/codegenie/probes/entrypoint.py` exists, defines `class EntrypointProbe(Probe)`, sets `name = "entrypoint"`, `layer = "C"`, `applies_to_languages = ["*"]`, `applies_to_tasks = ["*"]`, `requires = ["dockerfile"]`, `timeout_seconds = 5`, `declared_inputs = []`. Does NOT declare `consumes_peer_outputs`. `applies()` returns `True` only when `dockerfile` peer is present with at least one stage.
- [ ] `src/codegenie/schema/probes/certificate.schema.json` exists, Draft 2020-12, `schema_version: "v1"` at root, `additionalProperties: false` at every nesting level, declares `runtime_trace_pending: boolean` (required), `findings: array` (required) where each item has `{type: string (closed enum: "cert_file_copied", "cert_file_added", "ca_certificates_installed", "opaque_bundle_copied"), source_path: string (nullable), dest_path: string (nullable), stage_index: int, instruction_index: int}`, plus `warnings: array` with the `WarningId` pattern.
- [ ] `src/codegenie/schema/probes/entrypoint.schema.json` exists, Draft 2020-12, `schema_version: "v1"` at root, `additionalProperties: false` at every nesting level, declares `runtime_trace_pending: boolean` (required), `stages: array` (required) where each item has `{stage_index: int, stage_name: string (nullable), entrypoint_raw: string (nullable), entrypoint_form: string (closed enum: "exec", "shell", "inherited", "absent"), cmd_raw: string (nullable), cmd_form: string (closed enum), runtime_stage: boolean}` — the **last non-empty entrypoint/cmd stage** is the runtime stage (`runtime_stage: true`); all earlier stages have `runtime_stage: false`. Plus `warnings: array`.
- [ ] Red tests exist and were committed failing; green tests pass.
  - `tests/unit/probes/test_certificate.py` covers (a) `COPY ./certs/foo.crt /etc/ssl/certs/foo.crt` → finding with `type: "cert_file_copied"`, source + dest paths populated; (b) `RUN apt-get install -y ca-certificates` → finding with `type: "ca_certificates_installed"`, `runtime_trace_pending: false` (this is a positive signal, not pending); (c) `COPY ./bundle/ /etc/ssl/certs/` (directory copy with no `.crt` extension visible) → finding with `type: "opaque_bundle_copied"`, `runtime_trace_pending: true` (edge-case table row); (d) Dockerfile with NO certificate-related instructions → `findings: []`, `runtime_trace_pending: false`; (e) `ADD https://x/ca.crt /etc/ssl/certs/` → finding with `type: "cert_file_added"` AND warning `certificate.network_add_directive` (URL-form `ADD` is a supply-chain smell — record as fact).
  - `tests/unit/probes/test_entrypoint.py` covers (a) single-stage Dockerfile `CMD ["node","app.js"]` → `entrypoint_form: "absent"`, `cmd_form: "exec"`, `runtime_stage: true`; (b) single-stage `CMD node app.js` → `cmd_form: "shell"`, `runtime_stage: true`; (c) `ENTRYPOINT ["node"] / CMD ["app.js"]` → both forms `exec`; (d) multi-stage with `CMD` only in `runtime` stage → that stage is `runtime_stage: true`, build stages `runtime_stage: false`; (e) multi-stage with NO `ENTRYPOINT` and NO `CMD` in any stage → last stage `entrypoint_form: "inherited"`, `runtime_trace_pending: true` (inherited from base image — unknowable statically); (f) `dockerfile` peer with `run_form: "unparsable"` instructions does NOT propagate to entrypoint classification (this probe reads `ENTRYPOINT`/`CMD`, not `RUN`); (g) `dockerfile` peer missing → `applies()` returns `False`.
- [ ] `tests/unit/probes/test_certificate_schema.py` and `tests/unit/probes/test_entrypoint_schema.py` each ship an `additionalProperties: false` rejection test at root AND at the first nested array element level (so two tests per file, one assertion target each).
- [ ] `src/codegenie/probes/__init__.py` gains two additive import lines (one for each probe).
- [ ] PR body documents per-probe local coverage at 90/80 floor for both files (neither is on the 85/75 carve-out list).

## Implementation outline

1. **Write both sub-schemas first.** Mirror the data-model section. Closed-enum fields drawn from `phase-arch-design.md §"Data model"`.
2. **`CertificateProbe.run(ctx, snapshot)`:**
   - Pull `dockerfile_slice = ctx.peer_outputs["dockerfile"].schema_slice`.
   - For each stage (with `stage_index`), for each instruction (with `instruction_index`):
     - `COPY` with source ending in `.crt` or `.pem` (case-insensitive) → `type: "cert_file_copied"`.
     - `ADD` with source ending in `.crt` or `.pem` → `type: "cert_file_added"`.
     - `ADD` with source matching `^https?://` → warning `certificate.network_add_directive` (in addition to the cert-file finding if extension matches).
     - `RUN` whose raw text contains the literal substring `ca-certificates` (after splitting on whitespace, exact token match — not substring, to avoid false positives on things like `my-ca-certificates-tool`) AND the raw text contains `apt-get install` OR `apk add` → `type: "ca_certificates_installed"`.
     - `COPY` / `ADD` with source ending in `/` (directory copy) AND dest matching `^/etc/ssl/` OR `^/etc/pki/` OR `^/usr/local/share/ca-certificates/` → `type: "opaque_bundle_copied"`, sets `runtime_trace_pending = True`.
   - Aggregate `runtime_trace_pending`: `True` if any `opaque_bundle_copied` finding exists; `False` otherwise (other types are deterministic from static evidence).
   - `confidence`: `high` if zero opaque-bundle findings AND zero network-`ADD` warnings; `medium` if `runtime_trace_pending: true` or network-`ADD` warning present; `low` only on internal error (shouldn't happen — no parsing).
3. **`EntrypointProbe.run(ctx, snapshot)`:**
   - Pull `dockerfile_slice`.
   - For each stage, extract `ENTRYPOINT` raw + form, `CMD` raw + form. Form classification — `exec` if the parsed instruction was a JSON array; `shell` if a bare string; `absent` if no such instruction in this stage; `inherited` ONLY at slice-aggregation time for the last stage when both `ENTRYPOINT` and `CMD` are `absent`.
   - Determine `runtime_stage`: the **last stage** in the Dockerfile that has at least one of `{ENTRYPOINT, CMD}` non-absent, OR — if every stage is absent — the last stage with `entrypoint_form: "inherited"`.
   - Aggregate `runtime_trace_pending`: `True` if the runtime stage has `entrypoint_form: "inherited"` AND `cmd_form: "inherited"` (entirely unknowable statically); `False` otherwise.
   - `confidence`: `high` if runtime stage has at least one `exec`-form non-`inherited`; `medium` if shell-form; `low` if fully inherited.
4. **Failure handling:** peer output missing → handled by `applies()`. No other failure paths (pure synthesizers).
5. **Register** both probes in `src/codegenie/probes/__init__.py` (two additive lines).
6. **Wire** both sub-schemas into the envelope.

## TDD plan — red / green / refactor

### Red — write failing tests first

Path: `tests/unit/probes/test_certificate.py`

```python
# tests/unit/probes/test_certificate.py
"""Pins: CertificateProbe surfaces cert-related findings as facts; opaque
directory COPYs and network ADDs are honest about static-evidence limits.
Traces to: phase-arch-design.md §Component design #11; ADR-0002."""
import pytest
from codegenie.probes.certificate import CertificateProbe

@pytest.mark.asyncio
async def test_copy_crt_file_recorded(tmp_path):
    peer = _mk_dockerfile_peer(stages=[{
        "stage_index": 0, "base_image": "alpine",
        "instructions": [{
            "cmd": "COPY", "raw": "COPY ./certs/foo.crt /etc/ssl/certs/foo.crt",
            "copy_src": "./certs/foo.crt", "copy_dest": "/etc/ssl/certs/foo.crt"}],
    }])
    out = await CertificateProbe().run(_ctx(tmp_path, peers={"dockerfile": peer}), _snapshot(tmp_path))
    f = out.schema_slice["findings"][0]
    assert f["type"] == "cert_file_copied"
    assert f["source_path"] == "./certs/foo.crt"

@pytest.mark.asyncio
async def test_ca_certificates_install_recorded(tmp_path):
    peer = _mk_dockerfile_peer(stages=[{
        "stage_index": 0, "base_image": "ubuntu:22.04",
        "instructions": [{"cmd": "RUN", "raw": "apt-get update && apt-get install -y ca-certificates", "run_form": "shell"}],
    }])
    out = await CertificateProbe().run(_ctx(tmp_path, peers={"dockerfile": peer}), _snapshot(tmp_path))
    assert any(f["type"] == "ca_certificates_installed" for f in out.schema_slice["findings"])
    assert out.schema_slice["runtime_trace_pending"] is False  # positive signal, not pending

@pytest.mark.asyncio
async def test_opaque_bundle_copy_pending_true(tmp_path):
    peer = _mk_dockerfile_peer(stages=[{
        "stage_index": 0, "base_image": "alpine",
        "instructions": [{"cmd": "COPY", "raw": "COPY ./bundle/ /etc/ssl/certs/",
                          "copy_src": "./bundle/", "copy_dest": "/etc/ssl/certs/"}],
    }])
    out = await CertificateProbe().run(_ctx(tmp_path, peers={"dockerfile": peer}), _snapshot(tmp_path))
    assert out.schema_slice["findings"][0]["type"] == "opaque_bundle_copied"
    assert out.schema_slice["runtime_trace_pending"] is True

@pytest.mark.asyncio
async def test_network_add_directive_warning(tmp_path):
    peer = _mk_dockerfile_peer(stages=[{
        "stage_index": 0, "base_image": "alpine",
        "instructions": [{"cmd": "ADD", "raw": "ADD https://x/ca.crt /etc/ssl/certs/",
                          "add_src": "https://x/ca.crt", "add_dest": "/etc/ssl/certs/"}],
    }])
    out = await CertificateProbe().run(_ctx(tmp_path, peers={"dockerfile": peer}), _snapshot(tmp_path))
    assert "certificate.network_add_directive" in out.schema_slice["warnings"]
```

Path: `tests/unit/probes/test_entrypoint.py`

```python
@pytest.mark.asyncio
async def test_exec_cmd_runtime_stage_high(tmp_path):
    peer = _mk_dockerfile_peer(stages=[{
        "stage_index": 0, "base_image": "scratch",
        "instructions": [{"cmd": "CMD", "raw": '["node", "app.js"]', "cmd_form": "exec"}],
    }])
    out = await EntrypointProbe().run(_ctx(tmp_path, peers={"dockerfile": peer}), _snapshot(tmp_path))
    s0 = out.schema_slice["stages"][0]
    assert s0["cmd_form"] == "exec"
    assert s0["runtime_stage"] is True
    assert out.confidence == "high"

@pytest.mark.asyncio
async def test_multi_stage_runtime_stage_last_with_cmd(tmp_path):
    peer = _mk_dockerfile_peer(stages=[
        {"stage_index": 0, "stage_name": "build", "base_image": "node:20",
         "instructions": [{"cmd": "RUN", "raw": "npm run build", "run_form": "shell"}]},
        {"stage_index": 1, "stage_name": "runtime", "base_image": "gcr.io/distroless/nodejs20",
         "instructions": [{"cmd": "CMD", "raw": '["node","app.js"]', "cmd_form": "exec"}]},
    ])
    out = await EntrypointProbe().run(_ctx(tmp_path, peers={"dockerfile": peer}), _snapshot(tmp_path))
    stages = {s["stage_index"]: s for s in out.schema_slice["stages"]}
    assert stages[0]["runtime_stage"] is False
    assert stages[1]["runtime_stage"] is True

@pytest.mark.asyncio
async def test_no_entrypoint_no_cmd_inherited_pending(tmp_path):
    peer = _mk_dockerfile_peer(stages=[{
        "stage_index": 0, "base_image": "node:20-alpine",
        "instructions": [{"cmd": "WORKDIR", "raw": "WORKDIR /app"}],
    }])
    out = await EntrypointProbe().run(_ctx(tmp_path, peers={"dockerfile": peer}), _snapshot(tmp_path))
    s0 = out.schema_slice["stages"][0]
    assert s0["entrypoint_form"] == "inherited"
    assert s0["cmd_form"] == "inherited"
    assert out.schema_slice["runtime_trace_pending"] is True
```

Schema rejection tests at `tests/unit/probes/test_certificate_schema.py` and `tests/unit/probes/test_entrypoint_schema.py`: two each, one for root unknown field, one for nested array element unknown field. One assertion target per test.

Run `pytest tests/unit/probes/test_certificate.py tests/unit/probes/test_entrypoint.py tests/unit/probes/test_certificate_schema.py tests/unit/probes/test_entrypoint_schema.py -q`. All red.

### Green — make it pass

1. Land both sub-schemas first.
2. Implement `src/codegenie/probes/certificate.py` per **Implementation outline**.
3. Implement `src/codegenie/probes/entrypoint.py`.
4. Register both in `src/codegenie/probes/__init__.py`.
5. Compose both sub-schemas into envelope.
6. Run tests; iterate.

### Refactor — clean up

- Extract `_is_cert_path(p: str) -> bool` as a module-level helper if used > 1 place in `certificate.py`.
- Extract `_classify_form(instruction) -> str` as a module-level helper in `entrypoint.py`.
- Module-level constants for `_CERT_EXTENSIONS = (".crt", ".pem")`, `_CERT_DEST_PREFIXES = ("/etc/ssl/", "/etc/pki/", "/usr/local/share/ca-certificates/")`, warning IDs.
- Confirm both probe files are < 100 LOC each (per `High-level-impl.md` Step 5 effort line — "five probes of small surface area (each < 100 LOC)").
- `ruff format` + `ruff check`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/certificate.py` | New — `CertificateProbe` implementation |
| `src/codegenie/probes/entrypoint.py` | New — `EntrypointProbe` implementation |
| `src/codegenie/schema/probes/certificate.schema.json` | New — strict slice schema |
| `src/codegenie/schema/probes/entrypoint.schema.json` | New — strict slice schema |
| `src/codegenie/probes/__init__.py` | Edit — two additive import lines |
| `src/codegenie/schema/repo_context.schema.json` | Edit — `$ref` compose both sub-schemas under `probes.certificate` and `probes.entrypoint` |
| `tests/unit/probes/test_certificate.py` | New — unit tests |
| `tests/unit/probes/test_entrypoint.py` | New — unit tests |
| `tests/unit/probes/test_certificate_schema.py` | New — `additionalProperties: false` rejection tests |
| `tests/unit/probes/test_entrypoint_schema.py` | New — `additionalProperties: false` rejection tests |

## Out of scope

- **Certificate trust-chain validation** — Phase 14 work; this probe records paths, never opens the file.
- **Reading the actual `.crt` byte contents** — explicit non-goal. Paths only.
- **Resolving inherited entrypoints by inspecting base-image manifests** (`docker manifest inspect <base>`) — this requires the `tools.docker` wrapper from S1-06 AND a sandbox-bound subprocess, which would inflate this story from S to M. Phase 2's `EntrypointProbe` is pure-Python; `entrypoint_form: "inherited"` is recorded as fact with `runtime_trace_pending: true`. A Phase 5/7 follow-up may layer base-image inspection.
- **`ShellUsageProbe`** — sibling shipped by S5-02.
- **`RuntimeTraceProbe`** — class-only, shipped by S5-04.
- **Adversarial fixture for hostile `ADD` URLs** — handled by S8-01's adversarial corpus completion.

## Notes for the implementer

- Both probes are pure synthesizers. There should be **zero** imports of `subprocess`, `requests`, `httpx`, `socket`, or any file-reading module. They read `ctx.peer_outputs["dockerfile"]` and emit dicts.
- `runtime_trace_pending` semantics for `CertificateProbe` are stricter than for `ShellUsageProbe`: only the opaque-bundle case sets it `true`. A `cert_file_copied` finding is fully deterministic from the static evidence — set it `false` confidently. Misclassifying a deterministic case as pending creates noise that drowns the real signal (the same anti-pattern ADR-0002 calls out for `IndexHealthProbe`'s `not_applicable` vs `not_run`).
- `EntrypointProbe`'s `runtime_stage: true/false` flag is what Phase 7's distroless planner reads to know which stage matters. The runtime stage is **the last stage that has an `ENTRYPOINT` or `CMD` (after `entrypoint_form` resolution)**, OR — if every stage is fully inherited — the last stage. Test the "every stage absent" path explicitly; it's easy to write a probe that crashes on a Dockerfile with no entrypoint/cmd at all.
- For the `ADD https://...` detection, match anchored regex `^https?://` against the parsed `add_src` field — do NOT parse the raw line. `DockerfileProbe` already structured this.
- The `ca-certificates` token match: split on whitespace, check `"ca-certificates" in tokens`. Do NOT use substring (`"ca-certificates" in raw`) — that matches `my-ca-certificates-tool` and creates a false positive. The PR review should catch this.
- Per cross-cutting concern, per-probe local coverage in PR body for BOTH files; both at 90/80 floor.
- Both files together should land under ~150 LOC. If you find yourself writing helper classes or threading, stop and simplify — these are pure synthesizers.
