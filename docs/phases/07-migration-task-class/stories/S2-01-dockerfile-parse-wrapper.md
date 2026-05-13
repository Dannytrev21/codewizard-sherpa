# Story S2-01 — `tools/dockerfile_parse.py` strict wrapper

**Step:** Step 2 — Tool wrappers and the pre-rendered base catalog hot view
**Status:** Ready
**Effort:** M
**Depends on:** S1-01, S1-05
**ADRs honored:** ADR-P7-001 (gate_registry isolation — wrapper must not import coordinator), ADR-P7-006 (`Recipe.engine="dockerfile"` — engine relies on this wrapper), ADR-0009 (contract-surface snapshot — `DockerfileInventory` schema is captured)

## Context

This story lands the **first** of the four deterministic tool wrappers Step 2 owns. Every later Phase 7 component that touches a Dockerfile (`BaseImageProbe` in S3-01, `DockerfileRecipeEngine` in S4-01, the adversarial corpus property tests in S6-02) goes through *this* wrapper — never through raw `subprocess.run("dockerfile-parse")`. That means *strict mode* (BOM/CR/`ONBUILD`/>1 MB rejected), a 10 s wall-clock cap, and a Pydantic `DockerfileInventory` model with the honest-confidence surface `parser_skipped_lines: int`. If this wrapper is permissive, every downstream consumer silently inherits the bug.

The wrapper is also the seam where `phase-arch-design.md §Edge cases #1` ("Hostile Dockerfile") fires: BOM, UTF-16, CR, `ONBUILD`, 2 MB files, parse-bombs all raise `DockerfileRejected` here, not three layers up.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — 1. BaseImageProbe` (lines ~503–529) — names this wrapper as a dependency; describes `parser_skipped_lines` honest-confidence surface and rejection codes.
  - `../phase-arch-design.md §Component design — 4. DockerfileRecipeEngine` (lines ~585–605) — round-trip safety property `parse(serialize(parse(x))) == parse(x)` requires this wrapper.
  - `../phase-arch-design.md §Data model ›Internal` (`DockerfileInventoryRaw`) — in-memory shape.
  - `../phase-arch-design.md §Data model ›Contracts` (`DockerfileInventory` Pydantic — `schema_version: Literal["v0.7.0"]`, `parser_skipped_lines: int`, `confidence`, `confidence_reasons`).
  - `../phase-arch-design.md §Edge cases #1` — BOM/UTF-16/CR/`ONBUILD`/2 MB/parse-bomb behavior table.
- **Phase ADRs:**
  - `../ADRs/0002-register-gate-probe-new-registry.md` — ADR-P7-001 — wrapper must not import Phase 2 coordinator.
  - `../ADRs/0007-recipe-engine-literal-extended-with-dockerfile.md` — ADR-P7-006 — engine `"dockerfile"` is the consumer.
  - `../ADRs/0009-contract-surface-snapshot-canary.md` — `DockerfileInventory.model_json_schema()` enters the snapshot via S2-06 round-trip; freeze the field set deliberately.
- **High-level impl:**
  - `../High-level-impl.md §Step 2` (lines 54–82) — features delivered + done criteria for this wrapper.
- **External docs (only if directly relevant):**
  - `dockerfile-parse` PyPI page — for the version pin and known brittle edge cases (BuildKit heredocs especially; Step 4 risk note).

## Goal

`from codegenie.tools.dockerfile_parse import parse_dockerfile` returns a Pydantic-typed `DockerfileInventory` on every legal UTF-8 LF-only Dockerfile, and raises `DockerfileRejected(reason=<code>)` on every input outside the strict envelope.

## Acceptance criteria

- [ ] `src/codegenie/tools/dockerfile_parse.py` exports `parse_dockerfile(path: Path) -> DockerfileInventory` (or `bytes` overload for in-memory bytes); both honor the same 10 s wall-clock and 1 MB size cap.
- [ ] `DockerfileInventory` Pydantic model matches `phase-arch-design.md §Data model ›Contracts` exactly: `schema_version: Literal["v0.7.0"]`, `dockerfile_paths`, `stages: list[DockerfileStage]`, `is_multistage`, `final_stage_index`, `parser_skipped_lines: int`, `resolved_pre_image_digest`, `resolved_at`, `confidence: Literal["high","medium","low"]`, `confidence_reasons`. `model_config = ConfigDict(extra="forbid", frozen=True)`.
- [ ] `DockerfileRejected` is raised with a documented machine-readable `reason` code from the closed set `{"bom","cr_line_endings","onbuild_directive","size_cap_exceeded","subprocess_timeout","non_utf8","parse_bomb","embedded_null"}`. Reason set lives as a `Literal` so the contract-surface snapshot tracks it.
- [ ] BuildKit heredoc / `ARG`-indirect `FROM` / similar partial-parse inputs do **not** raise; they return `confidence="medium"` with `parser_skipped_lines > 0` and `confidence_reasons` populated (honest-confidence surface, not silent under-coverage).
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/tools/test_dockerfile_parse.py` all pass on the touched files.
- [ ] Fence-CI confirms the new module imports neither `anthropic`, `chromadb`, nor `sentence-transformers` (G18).

## Implementation outline

1. Add `dockerfile-parse` to `pyproject.toml` (pinned — see Risk #4 in High-level-impl). Add the version pin to `tools/digests.yaml` alongside its install source.
2. Write the failing test in `tests/unit/tools/test_dockerfile_parse.py` (see TDD plan below). Commit as the red marker.
3. Implement `DockerfileInventory` + `DockerfileStage` Pydantic models in `src/codegenie/tools/dockerfile_parse.py`. Mirror the schemas in `phase-arch-design.md §Data model ›Contracts`. `extra="forbid"`, `frozen=True`.
4. Implement `parse_dockerfile`: read file as bytes; reject BOM (any UTF BOM), CR-only line endings, `\x00` embedded null, size > 1 MB before invoking the parser. Then run `dockerfile-parse` in a subprocess (or via its Python API guarded by `signal.alarm` / threading timeout) with a 10 s wall-clock; rejects `ONBUILD` directive on parsed AST.
5. Map parse output into `DockerfileInventory`; surface `parser_skipped_lines` honestly. Compute `is_multistage`, `final_stage_index`.
6. Add the `DockerfileRejected` exception with a `reason: Literal[...]` field; export both from the module's `__all__`.
7. Run all five layers of the acceptance test matrix until green; refactor for clarity.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/tools/test_dockerfile_parse.py`

What the test asserts:

```python
# tests/unit/tools/test_dockerfile_parse.py
from pathlib import Path
import pytest
from codegenie.tools.dockerfile_parse import (
    parse_dockerfile,
    DockerfileInventory,
    DockerfileRejected,
)


def test_parse_dockerfile_happy_single_stage(tmp_path: Path) -> None:
    # arrange: minimal legal Dockerfile, UTF-8, LF
    df = tmp_path / "Dockerfile"
    df.write_bytes(b"FROM node:20-bullseye-slim\nCMD [\"node\",\"index.js\"]\n")
    # act
    inv = parse_dockerfile(df)
    # assert: typed Pydantic, single stage, high confidence, no skipped lines
    assert isinstance(inv, DockerfileInventory)
    assert inv.is_multistage is False
    assert inv.final_stage_index == 0
    assert inv.parser_skipped_lines == 0
    assert inv.confidence == "high"
    assert inv.stages[0].from_ref == "node:20-bullseye-slim"


@pytest.mark.parametrize(
    "evil_bytes,reason",
    [
        (b"\xef\xbb\xbfFROM node:20\n", "bom"),                  # UTF-8 BOM
        (b"FROM node:20\r", "cr_line_endings"),                  # CR-only
        (b"FROM node:20\nONBUILD RUN echo\n", "onbuild_directive"),
        (b"FROM node:20\n" + b"# pad\n" * 200_000, "size_cap_exceeded"),
        (b"FROM node:20\n\x00", "embedded_null"),
    ],
)
def test_parse_dockerfile_strict_rejection(tmp_path, evil_bytes, reason):
    df = tmp_path / "Dockerfile"
    df.write_bytes(evil_bytes)
    with pytest.raises(DockerfileRejected) as exc:
        parse_dockerfile(df)
    assert exc.value.reason == reason


def test_parse_dockerfile_heredoc_partial_parse_honest(tmp_path: Path) -> None:
    # arrange: BuildKit heredoc — dockerfile-parse won't fully parse it
    df = tmp_path / "Dockerfile"
    df.write_bytes(
        b"FROM node:20-bullseye-slim\n"
        b"RUN <<EOF\n"
        b"  echo hello\n"
        b"EOF\n"
    )
    inv = parse_dockerfile(df)
    # assert: NOT rejected; instead reports honest medium confidence
    assert inv.confidence == "medium"
    assert inv.parser_skipped_lines > 0
    assert any("heredoc" in r.lower() for r in inv.confidence_reasons)
```

The test must fail because `codegenie.tools.dockerfile_parse` does not exist yet — `ImportError`. Run it, confirm it fails, commit the failing test as a marker.

### Green — make it pass

Smallest implementation:

- Add `src/codegenie/tools/__init__.py` (if missing) and `src/codegenie/tools/dockerfile_parse.py`.
- Define `DockerfileStage` and `DockerfileInventory` Pydantic models with the exact field set from §Data model ›Contracts.
- Define `DockerfileRejected(Exception)` with a `reason: Literal[...]` attribute.
- Implement `parse_dockerfile(path)`:
  - Pre-flight byte checks (BOM, CR-only, null byte, size).
  - Subprocess or thread-wrapped invocation with a 10 s timeout → catches and re-raises as `DockerfileRejected("subprocess_timeout")`.
  - Walk parsed AST; detect `ONBUILD`; raise.
  - Compute `parser_skipped_lines` from `dockerfile-parse`'s structured output (it tracks unparseable lines).
- Resist over-implementing: no caching layer, no `imagetools` integration — those belong to `BaseImageProbe` (S3-01) and `tools/buildkit.py` (S2-02).

### Refactor — clean up

- Type hints (PEP 604 `X | None`); docstring on every public symbol.
- Honor `phase-arch-design.md §Edge cases #1` row by row: confirm each rejection code has at least one test.
- Add a module docstring explaining the strict envelope and why it is enforced *here* (so a future reader doesn't loosen it three calls down).
- Log a single `structlog` event `dockerfile.parse_rejected` with the reason code (per §Harness engineering — "No raw subprocess output goes to logger"); raw `dockerfile-parse` stderr does NOT go to the logger.
- Ensure no `random`, no `time.time()` for control flow inside the module (fence-CI).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/tools/dockerfile_parse.py` | New — strict wrapper + Pydantic models + `DockerfileRejected`. |
| `src/codegenie/tools/__init__.py` | New if absent — package marker; export `parse_dockerfile`, `DockerfileInventory`, `DockerfileRejected`. |
| `tests/unit/tools/test_dockerfile_parse.py` | New — anchors the red phase + the strict-rejection parametrized matrix. |
| `tests/unit/tools/__init__.py` | New if absent. |
| `pyproject.toml` | Add `dockerfile-parse` (pinned version) under `[project.dependencies]` or a `tools` extra. |
| `tools/digests.yaml` | Record the pinned `dockerfile-parse` version for parity with §Risks #4. |

## Out of scope

- **`imagetools inspect` + `confidence` resolution from registry** — that's `BaseImageProbe`'s job (S3-01) and `tools/buildkit.py`'s wrapper (S2-02).
- **Cache layer** (`.codegenie/cache/dockerfile-parse/<sha>.json`) — `BaseImageProbe` owns content-addressed caching; this wrapper is stateless.
- **Round-trip safety property `parse(serialize(parse(x))) == parse(x)`** — `DockerfileRecipeEngine` enforces that (S4-01); this wrapper only does parse.
- **`cache_lock`-coordinated cache writes** — S2-05.
- **Adversarial corpus over the wrapper** — S6-01/S6-02 lights it up over the full ≥30-fixture set.

## Notes for the implementer

- `phase-arch-design.md §Edge cases #1` is your acceptance test inventory. Every reason code in the `Literal` must have at least one fixture in the parametrized test; the reason set is a closed contract — adding new codes is an additive ADR (the snapshot will catch a sloppy widening).
- The 10 s wall-clock matters: `dockerfile-parse` has known degenerate cases on heredocs and very-long `RUN` lines. A test that *times out the runner* is a bug, not a flake — keep the subprocess truly bounded (preferably `subprocess.run(timeout=10)` with a separate process, not `signal.alarm`, since the wrapper may be called from worker threads).
- `parser_skipped_lines` is **load-bearing** — `BaseImageProbe` (S3-01) flips `confidence="medium"` on any nonzero value. Do not collapse this to a bool. Do not hide it inside `confidence_reasons` strings.
- `dockerfile-parse` is single-maintained and brittle (Risk #4 in High-level-impl). Pin the version in `pyproject.toml`; bumping it is a separate PR with the adversarial corpus rerun.
- `extra="forbid"` on the Pydantic models is what makes Step 6's adversarial corpus + Hypothesis tests catch silent shape drift. Do not relax it for "convenience."
- This module **must not** import `codegenie.coordinator`, `codegenie.probes.coordinator`, or any Phase 2 internal — ADR-P7-001 (gate_registry seam) keeps the Phase 2 coordinator byte-stable. Fence-CI enforces; verify your imports.
