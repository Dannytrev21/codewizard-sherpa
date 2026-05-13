# Story S3-01 — `BaseImageProbe` Layer-C gather-time probe

**Step:** Step 3 — Land `BaseImageProbe`, `ShellInvocationTraceProbe`, and the four signal collectors
**Status:** Ready
**Effort:** M
**Depends on:** S2-01, S1-02
**ADRs honored:** ADR-P7-002 (`ObjectiveSignals` widening + allowlists), ADR-P7-007 (advisory-only / facts-not-judgments lineage), ADR-P7-001 (gate registry — this probe does **not** use it; it's gather-time), ADR-0008 (production: trust score uses objective signals only)

## Context

This is the gather-time probe that captures Dockerfile evidence — `FROM` refs, multi-stage shape, parsed users / entrypoints, pre-image manifest digest — for both `distroless_migration` and `vuln_remediation` task classes (the slice is shared because base-image CVEs apply to both). It is the first probe Phase 7 contributes to the existing Phase 2 `@register_probe` registry; the Phase 2 coordinator picks it up at discovery time with **no coordinator edit** (the discipline ADR-P7-001 protects).

This story is foundational for Step 3: every other Step 3 story consumes this probe's output (`DockerfileInventory`) either directly (S3-04's dive signal reads the pre-image digest carried here; S3-06's `BaseImageSignal` projects it gate-time) or indirectly (S3-05's strict-AND signals lean on inventory shape to know when to fire). It also exercises ADR-P7-002's `ObjectiveSignals` widening from S1-02 — the four optional fields land here as their first real producers.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design ›1. BaseImageProbe` — full purpose, ABC shape, internal structure, performance envelope, failure behavior.
  - `../phase-arch-design.md §Data model ›Contracts` — `DockerfileInventory` + `DockerfileStage` Pydantic shape with `parser_skipped_lines`, `confidence`, `confidence_reasons`.
  - `../phase-arch-design.md §Edge cases` — rows 1, 4, 10, 12 (BOM/CR/ONBUILD reject; `--platform=linux/amd64` cache key; BuildKit heredoc `parser_skipped_lines > 0`; catalog row staleness).
  - `../phase-arch-design.md §Testing strategy ›Unit tests` — first bullet enumerates the ≥14 test classes (single/multi-stage, `ARG`-indirect FROMs, `FROM scratch`, heredoc, malformed → typed reject, `applies_to_tasks` matrix, `declared_inputs` glob, cache_key invalidation, intent test).
  - `../phase-arch-design.md §Agentic best practices ›Confidence handling` — `confidence=high|medium|low` with `confidence_reasons` enumerated.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0003-objective-signals-widening-and-allowlists.md` — ADR-P7-002 — the four-field widening this probe's output ultimately reaches via the `BaseImageSignal` collector (S3-06).
  - `../ADRs/0008-dive-efficiency-advisory-only.md` — ADR-P7-007 — facts-not-judgments lineage; informs the intent test.
  - `../ADRs/0001-six-named-additive-seams-and-adr-0028-amendment.md` — ADR-P7-001 — the "extension by addition" amendment; this probe is a *pure-addition new file* under `probes/`.
- **Production ADRs:**
  - `../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md` — `Probe` ABC byte-stable; this story imports `Probe` verbatim from `codegenie.probes.base`.
  - `../../../production/adrs/0008-objective-signal-trust-score.md` — facts, not judgments.
- **Existing code:**
  - `src/codegenie/probes/base.py` — Phase 2 `Probe` ABC + `@register_probe` decorator (read; do not edit).
  - `src/codegenie/tools/dockerfile_parse.py` — strict-mode wrapper landed in S2-01; this probe's only Dockerfile-parse pathway.
  - `src/codegenie/tools/buildkit.py` — `imagetools inspect --raw --platform=linux/amd64` for manifest-digest resolution (S2-02).
  - `src/codegenie/sandbox/signals/models.py` — `ObjectiveSignals` widened in S1-02; `BaseImageSignal` model lives here.

## Goal

`@register_probe class BaseImageProbe(Probe)` lives at `src/codegenie/probes/base_image.py`, registers at import time on the Phase 2 `@register_probe` registry, produces a Pydantic `DockerfileInventory` carrying base-image evidence (FROM refs, multi-stage shape, manifest digest, `parser_skipped_lines`, `confidence` + `confidence_reasons`), and emits **facts only** — no field name contains `is_*|safe_*|recommended_*`.

## Acceptance criteria

- [ ] `src/codegenie/probes/base_image.py` exists; `BaseImageProbe` decorated with `@register_probe` (Phase 2's, **not** `@register_gate_probe`); `name = "base_image"`, `layer = "C"`, `applies_to_tasks = ["distroless_migration", "vuln_remediation"]`, `applies_to_languages = ["*"]`, `timeout_seconds = 30`, `cache_strategy = "content"`.
- [ ] `declared_inputs` includes `"**/Dockerfile"`, `"**/Dockerfile.*"`, `"**/*.dockerfile"`, and the fingerprint glob `"fingerprint:~/.docker/config.json#auths"` — verified by a unit test that asserts the exact tuple.
- [ ] `DockerfileInventory` + `DockerfileStage` Pydantic models live in this module (or imported from `probes/base_image.py`'s schema submodule) with `extra="forbid"`, `frozen=True`, `schema_version: Literal["v0.7.0"]`, and the field set from `phase-arch-design.md §Data model ›Contracts`.
- [ ] **Intent test** `test_base_image_emits_facts_not_judgments` asserts that no field name on `DockerfileInventory` or `DockerfileStage` matches the regex `^(is_|safe_|recommended_).*` — runs via `DockerfileInventory.model_fields.keys()` recursion into nested models. Test commits as red, passes after impl.
- [ ] ≥14 unit tests in `tests/unit/probes/test_base_image.py` covering: single-stage; multi-stage (final stage by `--from` ref); textually-last `FROM`; `ARG`-indirect `FROM` → `confidence=medium`; `FROM scratch`; BuildKit heredoc → `parser_skipped_lines > 0`; BOM-prefixed Dockerfile → `DockerfileRejected`; CR line endings → `DockerfileRejected`; `ONBUILD` → `DockerfileRejected`; > 1 MB → `DockerfileRejected`; `applies_to_tasks` matrix (both task classes return `True`, any third returns `False`); `declared_inputs` exact tuple; cache key includes `--platform=linux/amd64` (different platform → different cache key); the intent test above.
- [ ] `mypy --strict src/codegenie/probes/base_image.py` and `ruff check`/`ruff format --check` clean.
- [ ] Fence-CI denies `anthropic|chromadb|sentence-transformers` imports under `src/codegenie/probes/` — exercised by S1-08; this story does not import any of those.
- [ ] The probe re-registers idempotently: importing the module twice does not duplicate the class in `all_probes()` (unit-asserted).

## Implementation outline

1. Scaffold `src/codegenie/probes/base_image.py` with `from .base import Probe, register_probe`, `DockerfileInventory`/`DockerfileStage` Pydantic models (`extra="forbid"`, `frozen=True`), and the `BaseImageProbe` class shell.
2. Implement `applies(view: RepoView) -> bool` — `True` iff any `declared_inputs` glob matches; trivial.
3. Implement `run(view) -> DockerfileInventory`:
   - Call `tools.dockerfile_parse.parse(path, strict=True)` for each matched Dockerfile.
   - Identify final stage by `--from` ref backwards walk; fall back to textually-last `FROM`.
   - Detect `ARG`-indirect FROMs → push reason into `confidence_reasons`, downgrade to `medium`.
   - Call `tools.buildkit.imagetools_inspect_raw(image_ref, platform="linux/amd64")`; cache to `.codegenie/cache/imagetools/<sha>.json` (24h TTL). Cache key derived from `(image_ref, "linux/amd64")` — platform is part of the key.
   - Materialize `DockerfileInventory(schema_version="v0.7.0", ..., parser_skipped_lines=…, resolved_pre_image_digest=…, confidence=…, confidence_reasons=…)`.
4. Failure modes: raise `DockerfileRejected` from the parse wrapper on BOM/CR/`ONBUILD`/size>1MB; on `imagetools` non-200 → `confidence=low, resolved_at=None`; never raise silently.
5. Register via `@register_probe` at module bottom (or class-decorator).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/probes/test_base_image.py`

The load-bearing red test is the intent test (the rest follow):

```python
# tests/unit/probes/test_base_image.py
import re
from codegenie.probes.base_image import DockerfileInventory, DockerfileStage

JUDGMENT_RE = re.compile(r"^(is_|safe_|recommended_).*")

def _all_field_names(model_cls) -> list[str]:
    names: list[str] = []
    for name, field in model_cls.model_fields.items():
        names.append(name)
        ann = field.annotation
        # recurse into nested BaseModel annotations
        inner = getattr(ann, "__args__", ())
        for a in (ann, *inner):
            if hasattr(a, "model_fields"):
                names.extend(_all_field_names(a))
    return names

def test_base_image_emits_facts_not_judgments():
    # arrange: enumerate every field on DockerfileInventory + nested models
    fields = _all_field_names(DockerfileInventory)
    fields += _all_field_names(DockerfileStage)
    # act + assert: no field name expresses a judgment
    offenders = [f for f in fields if JUDGMENT_RE.match(f)]
    assert offenders == [], (
        f"BaseImageProbe outputs must be facts not judgments (ADR-0008 / Rule 9); "
        f"forbidden field names: {offenders}"
    )
```

This fails with `ImportError` initially (module doesn't exist), then `AttributeError` once the module exists but the models don't. Commit the failing test as the red marker.

Additional red tests (one per behavior, not one per line) — at least these 13 plus the intent test = ≥14:

```python
def test_base_image_probe_is_registered_on_phase2_registry(): ...
def test_base_image_probe_not_on_gate_registry(): ...   # gate_registry.all_gate_probes() must NOT contain it
def test_applies_to_tasks_includes_both_task_classes(): ...
def test_declared_inputs_exact_tuple(): ...
def test_single_stage_dockerfile_parses(tmp_path): ...
def test_multistage_dockerfile_final_stage_identified(tmp_path): ...
def test_arg_indirect_from_downgrades_confidence_to_medium(tmp_path): ...
def test_from_scratch_handled(tmp_path): ...
def test_buildkit_heredoc_sets_parser_skipped_lines_positive(tmp_path): ...
def test_bom_dockerfile_raises_dockerfile_rejected(tmp_path): ...
def test_cr_line_endings_raises_dockerfile_rejected(tmp_path): ...
def test_onbuild_raises_dockerfile_rejected(tmp_path): ...
def test_oversize_dockerfile_raises_dockerfile_rejected(tmp_path): ...
def test_cache_key_includes_platform_linux_amd64(): ...
def test_module_double_import_does_not_duplicate_registration(): ...
```

### Green — make it pass

Smallest implementation: define `DockerfileInventory` and `DockerfileStage` Pydantic models with the field set from the data-model section (no `is_*`/`safe_*`/`recommended_*` names — the intent test then passes), then implement `BaseImageProbe.run` over `tools.dockerfile_parse` and `tools.buildkit`. Use fakes / `unittest.mock` to feed the `imagetools` call deterministic fixtures.

### Refactor — clean up

- Type hints on every public method (`mypy --strict` clean).
- Docstrings on `BaseImageProbe.run` documenting confidence rules.
- Move `DockerfileRejected` to a sibling exceptions module if shared with S3-02.
- Wire structured-log entries per `phase-arch-design.md §Harness engineering ›Logging strategy` (one event per Dockerfile parsed; no raw bytes).
- Ensure cache key derivation lives in a small `_cache_key(image_ref, platform)` helper so the unit test asserting platform inclusion is one-line.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/base_image.py` | New — implements `BaseImageProbe` + `DockerfileInventory` + `DockerfileStage` per Component 1 + Data model. |
| `tests/unit/probes/test_base_image.py` | New — ≥14 unit tests including the intent test. |
| `src/codegenie/probes/__init__.py` | Add `from . import base_image` so import-side registration fires (additive line). |

## Out of scope

- **Gate-time shell-invocation tracing** — S3-02 (`ShellInvocationTraceProbe`).
- **`BaseImageSignal` collector** — S3-06; this story produces the probe output; the gate-time signal projection is a separate file.
- **`tools/dockerfile_parse.py` and `tools/buildkit.py`** — those wrappers are S2-01 / S2-02; this story consumes them.
- **`ObjectiveSignals` widening** — S1-02 lands the four optional fields; this story does not edit `models.py`.
- **Adversarial Dockerfile corpus (≥30 fixtures)** — S6-01; this story uses ≤6 hand-written fixtures.
- **Manifest-digest 24h TTL eviction job** — content-addressed cache; eviction can wait for Phase 14.

## Notes for the implementer

- The intent test is the load-bearing facts-vs-judgments check. If you add a "convenience" field like `is_distroless_candidate` because it'd make the planner's job easier — stop. Move the inference to the planner (S5-x). Probes emit evidence; the gate or planner writes verdicts.
- `phase-arch-design.md §Component 1` says `confidence=medium` on `ARG`-indirect FROMs; the reason string in `confidence_reasons` must be stable across runs (sort it). The contract-surface snapshot will check `model_json_schema()` byte-for-byte.
- `imagetools inspect` is networked. Mock it in unit tests; the integration coverage lives in S3-03 / S5-06. Unit tests must not require `docker` on `$PATH`.
- The cache key MUST include `--platform=linux/amd64` — see edge case #4 in `phase-arch-design.md §Edge cases`. A unit test that builds the key twice (once with `linux/amd64`, once with `linux/arm64`) and asserts they differ is the simplest enforcement.
- `phase-arch-design.md §Component 1 ›Failure behavior` says raise `DockerfileRejected`, never coerce to `False`. If `dockerfile-parse` returns an empty parse with no exception, raise — silent under-coverage is the worst failure mode (Rule 12 — Fail loud).
- Module double-import idempotence matters because `@register_probe` is module-level; if pytest reloads the module the test catches the duplication. Use `if cls not in _PROBES` inside Phase 2's decorator (it should already do this — verify) or guard at the call site.
- Do **not** import `codegenie.probes.gate_registry` here. The Phase 2 coordinator does not learn the word "lifecycle" (ADR-0002).
