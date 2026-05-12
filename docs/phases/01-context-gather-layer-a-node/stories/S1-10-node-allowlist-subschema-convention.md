# Story S1-10 — `node` in `ALLOWED_BINARIES` + per-probe sub-schema convention + event constants

**Step:** Step 1 — Plant shared primitives, sub-schema convention, and the three Phase-0 in-place edits
**Status:** Ready
**Effort:** S
**Depends on:** S1-09
**ADRs honored:** ADR-0001, ADR-0004, ADR-0010

## Context

The final Step 1 story bundles three small ADR-gated landings: (a) the **`node` in `ALLOWED_BINARIES`** edit — the third and last Phase-0 in-place edit Phase 1 makes, gated by ADR-0001; (b) the **per-probe sub-schema convention** markdown — the in-tree documentation that ADR-0004 + ADR-0010 demand (every Phase 1 sub-schema sets `additionalProperties: false` at its own root; slices declared optional at envelope level); (c) **event-name constants** in `codegenie/logging.py` so the literals scattered across S1-02 through S1-09 collapse to `Final[str]` references.

After this story lands, every primitive Step 1 plants has its event names lifted to constants, its convention rule documented, and its allowlist entry plumbed — Step 2 onward consumes them.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #2` — `NodeBuildSystemProbe`'s optional `node --version` call via `exec.run_allowlisted` (consumed in S2-02, not this story).
  - `../phase-arch-design.md §"Component design" #11` — per-probe sub-schemas at `src/codegenie/schema/probes/`, each strict at own root.
  - `../phase-arch-design.md §"Harness engineering" → "Logging strategy"` — names every Phase-1 event: `probe.parser.cap_exceeded`, `probe.memo.hit`, `probe.memo.miss`, `probe.catalog.load`, `probe.raw_artifact.truncated`, `parser_kind` tracing field.
  - `../phase-arch-design.md §"Edge cases"` row 6 — hostile `node` shim path; this story enables the allowlist; S2-02 uses it; S5-02 adversarial tests it.
- **Phase ADRs:**
  - `../ADRs/0001-add-node-to-allowed-binaries.md` — ADR-0001 — the allowlist edit; env-strip + `shell=False` unchanged.
  - `../ADRs/0004-per-probe-subschema-additional-properties-false.md` — ADR-0004 — the convention `_subschema_convention.md` documents.
  - `../ADRs/0010-layer-a-slices-optional-at-envelope.md` — ADR-0010 — slices declared optional at envelope; non-Node repos validate.
- **Production ADRs:**
  - `../../../production/adrs/0005-no-llm-in-gather-pipeline.md` — `fence` job continues to assert.
- **Existing code:**
  - `src/codegenie/exec.py` (Phase 0) — `ALLOWED_BINARIES: frozenset[str] = frozenset({"git"})` per Phase 0 ADR-0012; this story extends to `frozenset({"git", "node"})`.
  - `src/codegenie/logging.py` (Phase 0 S2-01) — exports six `EVENT_PROBE_*` constants; this story appends five more.
  - `src/codegenie/schema/probes/` — directory exists from Phase 0 (Phase 0 ships `language_detection.schema.json`); this story adds `_subschema_convention.md` alongside.

## Goal

Three surgical landings: (a) add `"node"` to `ALLOWED_BINARIES`; (b) ship `_subschema_convention.md` documenting ADR-0004 + ADR-0010; (c) register five new event-name `Final[str]` constants in `codegenie/logging.py`.

## Acceptance criteria

- [ ] `src/codegenie/exec.py` — `ALLOWED_BINARIES` extends from `frozenset({"git"})` to `frozenset({"git", "node"})`. No other change to the file.
- [ ] `tests/unit/exec/test_allowed_binaries.py` (Phase 0) — extended to assert `"node"` is in the set; extended to assert the env-strip still drops `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `AWS_*`, `SSH_AUTH_SOCK` (the Phase 0 test already covers `git`; this story adds the `node` matrix).
- [ ] `src/codegenie/schema/probes/_subschema_convention.md` exists and documents: every Phase 1 sub-schema sets `additionalProperties: false` at its own root; slices declared optional at envelope `probes.*` level; `WarningId` pattern `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` applies to `warnings[]` and structured `errors[]`; references ADR-0004 + ADR-0007 + ADR-0010 by path.
- [ ] `src/codegenie/logging.py` exports five new `Final[str]` constants:
  - `EVENT_PROBE_PARSER_CAP_EXCEEDED: Final[str] = "probe.parser.cap_exceeded"`
  - `EVENT_PROBE_MEMO_HIT: Final[str] = "probe.memo.hit"`
  - `EVENT_PROBE_MEMO_MISS: Final[str] = "probe.memo.miss"`
  - `EVENT_PROBE_CATALOG_LOAD: Final[str] = "probe.catalog.load"`
  - `EVENT_PROBE_RAW_ARTIFACT_TRUNCATED: Final[str] = "probe.raw_artifact.truncated"`
- [ ] `tests/unit/test_logging.py` extended to assert each new constant exists and resolves to the documented string value.
- [ ] **Optional follow-up cleanup:** S1-02, S1-03, S1-04, S1-05, S1-07, S1-09 emit literal event strings. This story may also flip those literals to the new constants for consistency — if the story author chooses, do it surgically. Otherwise leave them as literals and flag for a Phase 1 follow-up. (Choose one; document the choice in the PR body.)
- [ ] TDD red tests exist, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Edit `src/codegenie/exec.py` — one-line addition to `ALLOWED_BINARIES`.
2. Extend `tests/unit/exec/test_allowed_binaries.py` with the `node`-membership assertion and the env-strip matrix.
3. Create `src/codegenie/schema/probes/_subschema_convention.md` — ≤ 80-line in-tree note covering the three rules (root-strict, envelope-optional, WarningId pattern) with code-blocks showing the canonical JSON Schema fragment.
4. Append five `Final[str]` constants to `src/codegenie/logging.py` in the same block-style as the Phase 0 six constants.
5. Extend `tests/unit/test_logging.py` with the new-constant assertions.
6. (Optional sweep) Replace literal event strings in `safe_json.py`, `safe_yaml.py`, `jsonc.py`, `catalogs/__init__.py`, `parsed_manifest_memo.py`, and the raw-artifact-budget writer with the new constants.

## TDD plan — red / green / refactor

### Red — failing test first

```python
# tests/unit/exec/test_allowed_binaries.py — extension
from codegenie.exec import ALLOWED_BINARIES, run_allowlisted

def test_node_in_allowed_binaries():
    # ADR-0001: phase 1 extends from {"git"} to {"git", "node"}
    assert "node" in ALLOWED_BINARIES
    assert ALLOWED_BINARIES == frozenset({"git", "node"})

def test_env_strip_drops_secrets_for_node_invocation(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "leak")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "leak")
    monkeypatch.setenv("GITHUB_TOKEN", "leak")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "leak")
    monkeypatch.setenv("SSH_AUTH_SOCK", "/leak/sock")
    # mock subprocess to record the env passed
    import subprocess
    captured = {}
    def _fake_run(cmd, **kw):
        captured["env"] = kw.get("env", {})
        class R: returncode = 0; stdout = b"v20.0.0\n"; stderr = b""
        return R()
    monkeypatch.setattr(subprocess, "run", _fake_run)
    run_allowlisted(["node", "--version"], cwd=".", timeout_s=5)
    assert "OPENAI_API_KEY" not in captured["env"]
    assert "GITHUB_TOKEN" not in captured["env"]
    assert "SSH_AUTH_SOCK" not in captured["env"]
```

```python
# tests/unit/test_logging.py — extension
import codegenie.logging as cgl

def test_phase1_event_constants():
    assert cgl.EVENT_PROBE_PARSER_CAP_EXCEEDED == "probe.parser.cap_exceeded"
    assert cgl.EVENT_PROBE_MEMO_HIT == "probe.memo.hit"
    assert cgl.EVENT_PROBE_MEMO_MISS == "probe.memo.miss"
    assert cgl.EVENT_PROBE_CATALOG_LOAD == "probe.catalog.load"
    assert cgl.EVENT_PROBE_RAW_ARTIFACT_TRUNCATED == "probe.raw_artifact.truncated"
```

```python
# tests/unit/schema/test_subschema_convention_doc.py
from pathlib import Path

def test_subschema_convention_doc_exists_and_links_adrs():
    doc = Path("src/codegenie/schema/probes/_subschema_convention.md")
    assert doc.exists()
    text = doc.read_text()
    # the doc must reference the three load-bearing ADRs by filename
    assert "0004-per-probe-subschema-additional-properties-false" in text
    assert "0007-warnings-id-pattern" in text
    assert "0010-layer-a-slices-optional-at-envelope" in text
    # the pattern shape must be quoted verbatim
    assert "^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$" in text
```

Run; confirm failures. Commit as red.

### Green — minimal impl

- `src/codegenie/exec.py`: change `ALLOWED_BINARIES = frozenset({"git"})` → `ALLOWED_BINARIES = frozenset({"git", "node"})`. **Nothing else.**
- `src/codegenie/logging.py`: append five `Final[str]` constants below the existing six. Order: parser, memo.hit, memo.miss, catalog.load, raw_artifact.truncated.
- `src/codegenie/schema/probes/_subschema_convention.md`: write the convention doc. Suggested structure:
  - Heading + one-line summary.
  - Rule 1: `additionalProperties: false` at root (link to ADR-0004).
  - Rule 2: Slices optional at envelope `probes.*` (link to ADR-0010).
  - Rule 3: `warnings[]` and structured `errors[]` use `WarningId` pattern (link to ADR-0007), quote the regex.
  - Canonical example: a 15-line JSON Schema fragment for a fictional probe demonstrating root-strict + pattern-constrained warnings.

### Refactor — clean up

- Module docstring in `exec.py` already names ADR-0012 from Phase 0 — append a one-line note that Phase 1 extends with `node` per ADR-0001.
- `logging.py` constants block: confirm `ruff format` does not reflow (Phase 0 S2-01 already handled this).
- The convention doc: keep concise (≤ 80 lines). It is reference, not tutorial.
- If pursuing the optional sweep: do it as a separate commit within the PR so it can be reverted if it grows beyond surgical.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/exec.py` | Add `"node"` to `ALLOWED_BINARIES` |
| `src/codegenie/logging.py` | Add five `Final[str]` Phase-1 event-name constants |
| `src/codegenie/schema/probes/_subschema_convention.md` | Document ADR-0004 + ADR-0010 + ADR-0007 conventions |
| `tests/unit/exec/test_allowed_binaries.py` | Extend with `node`-membership + env-strip matrix |
| `tests/unit/test_logging.py` | Extend with new-constant assertions |
| `tests/unit/schema/test_subschema_convention_doc.py` | New — convention-doc smoke test |
| (Optional sweep) | `src/codegenie/parsers/safe_json.py`, `safe_yaml.py`, `jsonc.py`, `catalogs/__init__.py`, `coordinator/parsed_manifest_memo.py`, `coordinator/coordinator.py` — replace event literals with the new constants |

## Out of scope

- **Consuming the `node` allowlist entry** — S2-02 (`NodeBuildSystemProbe.run` calls `exec.run_allowlisted(["node", "--version"], ...)`).
- **Adversarial test for the hostile `node` shim** — S5-02 (`test_planted_node_on_path_ignored.py`).
- **Per-probe sub-schema files themselves** — S2-01 (extension), S2-02, S3-05, S4-01, S4-02, S4-03 ship the actual sub-schema JSONs. This story only documents the convention they all follow.
- **Tool-readiness check in the CLI for `node`** — Phase 0's tool-readiness check (S4-02) walks `ALLOWED_BINARIES`. Once `"node"` is in the set, the CLI's `WARN` on absent `node` follows automatically. No additional code in this story.

## Notes for the implementer

- **All three edits are surgical.** Total LOC: roughly 1 (exec.py) + 5 (logging.py) + 60 (convention doc) + 30 (tests). Well under any review-blast-radius threshold.
- **`ALLOWED_BINARIES` is `frozenset`.** Adding an element produces a new frozenset literal — there is no `.add()`. This is the Phase 0 contract and intentionally so.
- **The convention doc is in `src/`, not in `docs/`.** Phase 0 placed schema sources under `src/codegenie/schema/`; this convention note lives alongside. `mkdocs build --strict` ignores `src/`. The doc is for engineer eyes, navigable inside the source tree.
- **Per Rule 11 (Match conventions):** the existing event-name constants in `logging.py` use `EVENT_PROBE_<UPPERCASE_UNDERSCORE>` naming. Follow exactly:
  - `EVENT_PROBE_PARSER_CAP_EXCEEDED` (not `EVENT_PROBE_CAP_EXCEEDED` — the `parser` segment is structural and reflects the event-string namespace).
  - `EVENT_PROBE_MEMO_HIT` / `EVENT_PROBE_MEMO_MISS` (two separate constants — they're separate event strings).
- **`shell=False` is the Phase 0 contract.** Don't touch it. Don't add new env-strip rules — Phase 0's strip is intentional and already covers the secrets adversarial test (S5-02) needs.
- **Per Rule 12:** the `test_env_strip_drops_secrets_for_node_invocation` test is the **load-bearing regression**. If a future PR adds a new "convenience" env var to passthrough, this test must fail. Make the assertion explicit — `assert "OPENAI_API_KEY" not in env` is more durable than asserting `env == {}` (the latter would also fail on benign passthroughs like `PATH`).
- **Optional sweep advisory:** if you flip literals to constants, do it in one focused commit; otherwise leave a single-line `TODO(S1-10-sweep)` comment in each file or in the PR body so a follow-up story can be filed.
- **This story closes Step 1.** After it merges, Step 2 (`LanguageDetectionProbe` extension + `NodeBuildSystemProbe`) starts from a complete primitives surface: parsers, memo, snapshot pass, raw-artifact budget, catalogs, allowlist entry, convention doc, event constants — all on disk.
