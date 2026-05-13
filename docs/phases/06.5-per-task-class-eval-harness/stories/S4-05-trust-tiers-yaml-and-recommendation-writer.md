# Story S4-05 — `docs/trust-tiers.yaml` + recommendation writer

**Step:** Step 4 — Wire the CLI and the read-only promotion gate
**Status:** Ready
**Effort:** S
**Depends on:** S4-04 (`PromotionGate.evaluate` returns `PromotionVerdict`; `TierConfig` + `load_tier_config` exist)
**ADRs honored:** ADR-0003 (tier IDs as `str`, validated at startup against `docs/trust-tiers.yaml`; YAML is contract data, CODEOWNERS-gated, candidate numbers only), ADR-0009 (automatic-demotion is a recommendation-shift; the recommendation file is the only side effect), Production ADR-0009 (humans always merge; the recommendation file is advisory data, not a control signal), Production ADR-0015 (calibration deferred; `docs/trust-tiers.yaml` carries candidates, not commitments)

## Context

`docs/trust-tiers.yaml` is the **contract data** the rest of the harness reads to interpret tier names. ADR-0003 made tier identifiers `str` validated at startup against this file; the file's existence and minimal schema are load-bearing. Phase 6.5 ships it with **uncalibrated candidate numbers** for `bronze` only — production ADR-0015 (threshold calibration) stays deferred, and the YAML's README header says so loudly so future readers do not mistake the candidates for committed thresholds.

The recommendation writer is the second half of the read-only promotion contract. When `--with-verdict` is set on `eval run` (S4-02) or when an `evaluate` call flips `evidence_sufficient` from `False` to `True` for any registered task class, the writer persists the `PromotionVerdict` to `.codegenie/eval/recommendations/<utc-iso>.json`. Phase 11/12 will eventually read these files; Phase 6.5 just produces them. Per ADR-0009, the file is advisory — no Phase 6.5 code path consumes the `evidence_sufficient` field as a control signal. (The architecture explicitly notes this in `phase-arch-design.md §Failure modes`: "the system **never** branches on 'evidence sufficient' automatically.")

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design → src/codegenie/eval/promotion.py` — names `tier_config: TierConfig` with `thresholds: Mapping[str, float]` and `current_tiers: Mapping[str, str]`.
  - `../phase-arch-design.md §Component design → src/codegenie/eval/cli.py` — `--with-verdict` triggers the recommendation write.
  - `../phase-arch-design.md §Dynamic view → Sequence: 14-day silver-promotion candidate` — the day-15 verdict-flip writes a `PromotionVerdict` at `.codegenie/eval/recommendations/<utc-iso>.json`; `evidence_sufficient=True, target_tier="silver", reasons=("all conditions met",)`.
  - `../phase-arch-design.md §Open questions deferred to implementation` #5 — `docs/trust-tiers.yaml` schema details (versioning, per-task-class overrides, downgrade-threshold equality) all defer to ADR-0015 calibration; ship a minimal schema.
- **Phase ADRs:**
  - `../ADRs/0003-tier-identifiers-as-str-validated-at-startup.md` §Decision — `docs/trust-tiers.yaml` is CODEOWNERS-gated contract data; `TierConfig` is loaded from it; unknown tiers raise `TierConfigInvalid` at startup.
  - `../ADRs/0009-automatic-demotion-as-recommendation-shift.md` — the recommendation file is the *only* side effect; no automatic demotion.
- **Production ADRs:**
  - `../../../production/adrs/0009-humans-always-merge.md` — the recommendation file is data; humans act on it.
  - `../../../production/adrs/0015-trust-score-threshold-calibration.md` — the calibration ADR whose numbers this YAML eventually carries; in Phase 6.5 the YAML carries candidates with an "uncalibrated" header.
- **Source design:** `../High-level-impl.md §Step 4` — names the YAML schema (`thresholds`, `current_tiers`), the recommendation directory (`.codegenie/eval/recommendations/<utc-iso>.json`), and the "candidate numbers + uncalibrated header" discipline.

## Goal

Ship `docs/trust-tiers.yaml` (minimal schema, bronze candidate numbers, prominent uncalibrated header) and `src/codegenie/eval/recommendation.py` with `write_recommendation(verdict, out_dir) -> Path` invoked from S4-02's `--with-verdict` flag.

## Acceptance criteria

- [ ] `docs/trust-tiers.yaml` exists and parses to:
  ```yaml
  # SPDX-License-Identifier: Apache-2.0
  # codewizard-sherpa: tier-config-v1 (UNCALIBRATED — Phase 6.5 candidate numbers only)
  # See docs/production/adrs/0015-trust-score-threshold-calibration.md for calibration commitments.
  # CODEOWNERS-gated: every change requires an ADR amendment.
  schema_version: 1
  thresholds:
    bronze: 0.70    # CANDIDATE — pending ADR-0015 calibration
  current_tiers: {}  # empty until first task class promotes; updates require human PR
  ```
- [ ] The YAML's first non-blank line begins with `# codewizard-sherpa: tier-config-v1 (UNCALIBRATED` so a `head -3 docs/trust-tiers.yaml` reveals the disclaimer; a unit test asserts the first 200 bytes contain `"UNCALIBRATED"`.
- [ ] Only the `bronze` tier is declared; `silver` / `gold` / `platinum` are absent — Phase 7 / Phase 15 add them with their own ADR amendments per ADR-0003. (Test: `len(loaded.thresholds) == 1` and `"bronze" in loaded.thresholds`.)
- [ ] `current_tiers` is an empty mapping; no task class is registered as currently-tiered until a human-authored PR lands one.
- [ ] `load_tier_config(Path("docs/trust-tiers.yaml"))` (from S4-04) round-trips to a `TierConfig` whose fields match the YAML; `PromotionGate(load_tier_config(...))` constructs without raising.
- [ ] **Bench-registration tier slugs are validated against the YAML at startup.** A `TaskClass` registered with `min_cases_for_promotion={"bronze": 10, "platinum": 50}` against the Phase 6.5 YAML (which only declares `bronze`) raises `TierConfigInvalid` at `PromotionGate.__init__`. The integration test asserts this — adding silver/gold/platinum is a YAML-edit + ADR-amendment story for the consuming phase, not a code change.
- [ ] `src/codegenie/eval/recommendation.py` defines `write_recommendation(verdict: PromotionVerdict, out_dir: Path = Path(".codegenie/eval/recommendations")) -> Path`:
  - Creates `out_dir` (parents OK) if missing.
  - Filename: `<utc-iso>.json` where `<utc-iso>` is `datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")` (hyphens, not colons — same convention as S4-02 audit JSON).
  - Atomic write: write to `<filename>.tmp` then `os.replace`.
  - Mode `0600`.
  - Body: `verdict.model_dump_json(indent=2)` — pretty-printed because operators read these files directly.
- [ ] **Recommendation writer is invoked from S4-02 only when `--with-verdict` is set OR when `evaluate` flips `evidence_sufficient` from `False` to `True` between consecutive runs of the same task class.** This story owns the writer; S4-02 owns the call site for `--with-verdict`. The "flip detection" path is documented but deferred to a follow-up story (a follow-up is filed if Phase 6.5 needs the auto-flip-detection in the CLI loop).
- [ ] **No Phase 6.5 code path reads the recommendation files as a control signal.** A static-introspection test (mirroring S1-05's import-ban) walks `src/codegenie/**/*.py` and fails if any file does `Path(".codegenie/eval/recommendations").glob(...)` or similar reads. Recommendation files are write-only from this phase's perspective; consumers (Phase 11/12) read them.
- [ ] The red test from §TDD plan exists, was committed at the red marker, and is now green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/test_trust_tiers_yaml.py tests/unit/test_recommendation_writer.py tests/unit/test_recommendation_not_consumed.py` all pass on touched files.

## Implementation outline

1. Write red tests — see §TDD plan.
2. Author `docs/trust-tiers.yaml` with the exact content shape from §Acceptance criteria. Include the SPDX header and the `UNCALIBRATED` disclaimer as the first non-blank comment.
3. Create `src/codegenie/eval/recommendation.py`:
   - `write_recommendation(verdict, out_dir)` per §Acceptance criteria.
   - One small helper `_utc_iso_filename() -> str` returning the hyphen-form ISO; share the format with S4-02's audit-JSON naming (consider hoisting both to a shared `_paths.py` if the duplication smells, but keep it inline for now per Rule 2).
4. Add the static-introspection test `tests/unit/test_recommendation_not_consumed.py` — AST-walks `src/codegenie/**/*.py`, looks for `recommendations` substring in any `Path(...)` literal that is *read* (passed to `glob` / `iterdir` / `open` for read).
5. Wire the writer call site from S4-02's `--with-verdict` flag (single import + single function call inside the deferred-import block).
6. Run `ruff format`, `ruff check`, `mypy --strict`, `pytest`.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/test_trust_tiers_yaml.py
from pathlib import Path
import pytest
from codegenie.eval.promotion import load_tier_config, PromotionGate, TierConfig
from codegenie.eval.errors import TierConfigInvalid


YAML_PATH = Path("docs/trust-tiers.yaml")


def test_trust_tiers_yaml_exists():
    assert YAML_PATH.exists(), "docs/trust-tiers.yaml is contract data — Phase 6.5 must ship it"


def test_trust_tiers_yaml_first_200_bytes_warn_uncalibrated():
    head = YAML_PATH.read_bytes()[:200].decode("utf-8", errors="replace")
    assert "UNCALIBRATED" in head, (
        "trust-tiers.yaml must declare UNCALIBRATED in its leading comments per ADR-0003 + ADR-0015"
    )


def test_trust_tiers_yaml_only_declares_bronze():
    cfg = load_tier_config(YAML_PATH)
    assert isinstance(cfg, TierConfig)
    assert set(cfg.thresholds) == {"bronze"}, (
        "Phase 6.5 ships only bronze; silver/gold/platinum are added by their consuming phase + ADR amendment"
    )
    # Bronze candidate is a sane float in (0, 1]
    assert 0.0 < cfg.thresholds["bronze"] <= 1.0


def test_trust_tiers_yaml_current_tiers_empty():
    cfg = load_tier_config(YAML_PATH)
    assert cfg.current_tiers == {}, (
        "current_tiers is empty until a human PR promotes a task class per ADR-0009"
    )


def test_promotion_gate_constructs_from_shipped_yaml():
    cfg = load_tier_config(YAML_PATH)
    gate = PromotionGate(tier_config=cfg)
    assert gate is not None  # construction did not raise


def test_unknown_tier_in_registration_raises_against_phase65_yaml(
    monkeypatch, registry_with_silver_min_cases
):
    """A TaskClass registering min_cases_for_promotion={'silver': 25} against Phase 6.5's
    bronze-only YAML must fail at PromotionGate.__init__ per ADR-0003 startup-validation."""
    cfg = load_tier_config(YAML_PATH)
    with pytest.raises(TierConfigInvalid) as exc_info:
        PromotionGate(tier_config=cfg, registry=registry_with_silver_min_cases)
    assert "silver" in str(exc_info.value)
```

```python
# tests/unit/test_recommendation_writer.py
import json
import os
import re
import stat
from pathlib import Path
import pytest

from codegenie.eval.recommendation import write_recommendation
from codegenie.eval.models import PromotionVerdict


@pytest.fixture
def sample_verdict() -> PromotionVerdict:
    return PromotionVerdict.model_construct(
        task_class="vuln-remediation",
        target_tier="bronze",
        current_tier="bronze",
        evidence_sufficient=True,
        reasons=(),
        chain_head="0" * 64,
        run_id="abc123def4",
    )


def test_writer_creates_out_dir_if_missing(tmp_path, sample_verdict):
    out = tmp_path / "fresh" / "recommendations"
    assert not out.exists()
    written = write_recommendation(sample_verdict, out_dir=out)
    assert written.exists()
    assert written.parent == out


def test_writer_filename_is_iso_hyphen_form(tmp_path, sample_verdict):
    written = write_recommendation(sample_verdict, out_dir=tmp_path)
    # YYYY-MM-DDTHH-MM-SSZ.json — hyphens not colons (filename-safe)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z\.json", written.name)


def test_writer_payload_round_trips_to_verdict(tmp_path, sample_verdict):
    written = write_recommendation(sample_verdict, out_dir=tmp_path)
    on_disk = json.loads(written.read_text())
    # Pretty-printed JSON (indent=2): consumers read it directly
    assert "\n" in written.read_text()
    # Round-trip into the wire model
    reread = PromotionVerdict.model_validate(on_disk)
    assert reread == sample_verdict


def test_writer_mode_is_0600(tmp_path, sample_verdict):
    written = write_recommendation(sample_verdict, out_dir=tmp_path)
    mode = stat.S_IMODE(os.stat(written).st_mode)
    assert mode == 0o600


def test_writer_atomic_no_temp_left_behind(tmp_path, sample_verdict):
    write_recommendation(sample_verdict, out_dir=tmp_path)
    leftover_tmps = list(tmp_path.glob("*.tmp"))
    assert leftover_tmps == [], f"atomic write left a .tmp file: {leftover_tmps}"
```

```python
# tests/unit/test_recommendation_not_consumed.py
"""Static guard: no Phase 6.5 code may read .codegenie/eval/recommendations as a control signal.
Recommendations are write-only from this phase per ADR-0009 and phase-arch-design §Failure modes."""
import ast
from pathlib import Path

SRC_ROOT = Path("src/codegenie")
FORBIDDEN_SUBSTR = "recommendations"
READ_CALLS = frozenset({"glob", "iterdir", "rglob", "read_text", "read_bytes"})


def _walk_py_files(root: Path):
    yield from root.rglob("*.py")


def test_no_codegenie_module_reads_recommendation_files():
    offenders: list[tuple[Path, int]] = []
    for f in _walk_py_files(SRC_ROOT):
        try:
            tree = ast.parse(f.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if FORBIDDEN_SUBSTR in node.value:
                    # Check whether this string is the *target* of a read call up the AST
                    # — for the static guard, any literal containing "recommendations"
                    # in code outside recommendation.py is suspicious.
                    if f.name != "recommendation.py":
                        offenders.append((f, node.lineno))
    assert offenders == [], (
        f"Phase 6.5 modules must not reference recommendation files: {offenders}"
    )
```

Run; confirm failures (missing YAML, missing module). Commit as the red marker.

### Green — make it pass

1. Author `docs/trust-tiers.yaml` per §Acceptance criteria.
2. Implement `src/codegenie/eval/recommendation.py`:
   ```python
   from datetime import datetime, timezone
   from pathlib import Path
   import os
   from codegenie.eval.models import PromotionVerdict


   def _utc_iso_filename() -> str:
       return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ") + ".json"


   def write_recommendation(
       verdict: PromotionVerdict,
       out_dir: Path = Path(".codegenie/eval/recommendations"),
   ) -> Path:
       out_dir.mkdir(parents=True, exist_ok=True)
       target = out_dir / _utc_iso_filename()
       tmp = target.with_suffix(target.suffix + ".tmp")
       tmp.write_text(verdict.model_dump_json(indent=2))
       os.chmod(tmp, 0o600)
       os.replace(tmp, target)
       return target
   ```
3. Wire S4-02's `--with-verdict` call site to import this module lazily and call `write_recommendation(verdict)` after `gate.evaluate(report)`.

### Refactor — clean up

- Type hints on every callable; `mypy --strict` clean.
- Module docstring cites ADR-0003 (YAML is contract data) and ADR-0009 (recommendation is the side-effect surface).
- The `_utc_iso_filename` helper is a single-line function but it's worth its own name because S4-02's audit JSON uses the same convention; if S4-02 already exports a similar helper, reuse rather than duplicate (Rule 8 — read before you write). If duplication is unavoidable, file a follow-up to consolidate into a shared `_paths.py`.
- The static-introspection test (`test_recommendation_not_consumed.py`) is a "fence" assertion in the same family as S1-05's import-ban tests; it gets stricter over time as the codebase grows. Document it in a comment so future contributors understand the intent.
- The YAML's `schema_version: 1` field is forward-looking — when production ADR-0015 calibrates real numbers, the schema may bump. Phase 6.5 ships v1; readers know how to detect drift.

## Files to touch

| Path | Why |
|---|---|
| `docs/trust-tiers.yaml` | New file — minimal schema, bronze candidate, UNCALIBRATED header per ADR-0003 + ADR-0015. |
| `src/codegenie/eval/recommendation.py` | New file — `write_recommendation(verdict, out_dir)` with atomic write + mode 0600. |
| `tests/unit/test_trust_tiers_yaml.py` | New file — YAML existence, header disclaimer, bronze-only, gate constructs, unknown-tier-rejected. |
| `tests/unit/test_recommendation_writer.py` | New file — directory creation, filename ISO format, payload round-trip, mode 0600, no `.tmp` leak. |
| `tests/unit/test_recommendation_not_consumed.py` | New file — static guard that no Phase 6.5 module reads recommendation files as control signal. |
| `src/codegenie/eval/cli.py` | Surgical edit — wire `write_recommendation` call into S4-02's `--with-verdict` block (deferred import). |

## Out of scope

- **Schema versioning beyond v1** — `schema_version: 1` is the lone field; per `phase-arch-design.md §Open Q #5`, versioning rules defer to ADR-0015.
- **Per-task-class threshold overrides** — also deferred per `phase-arch-design.md §Open Q #5`. The Phase 6.5 schema has only a global `thresholds` mapping.
- **Downgrade-threshold equality** — also deferred per `phase-arch-design.md §Open Q #5`.
- **`silver`, `gold`, `platinum` tier numbers** — Phase 7 (silver for migration), Phase 15 (recipe authoring), and ADR-0015 calibration will add these in their own PRs + ADR amendments.
- **Recommendation file consumers (Phase 11/12)** — `phase-arch-design.md §Open Q #7` defers; Phase 6.5 writes the contract; consumers ship later.
- **Auto-flip detection in the CLI loop** — the "flip from `False` to `True` between consecutive runs writes a recommendation" path is documented in §Acceptance criteria but the CLI implementation defers to a follow-up if needed; for Phase 6.5, the `--with-verdict` flag is the explicit trigger.
- **YAML migration tooling** — when ADR-0015 calibration ships real numbers, a script may convert candidate values; Phase 6.5 ships the file by hand.

## Notes for the implementer

- **The `UNCALIBRATED` header is load-bearing UX.** Future contributors who `grep` `docs/trust-tiers.yaml` for tier numbers must immediately understand these are not committed. The first 200 bytes test pins this — do not strip the comment to "save space."
- **`schema_version: 1` is structural.** A consumer in a later phase may branch on it. Phase 6.5 does not consume it; future readers will. Ship it now so v2 can detect drift cleanly.
- **Atomic write discipline** — `os.replace` is the POSIX-atomic rename; on Windows `os.replace` also works (Python 3.3+). Do not use `Path.write_text` directly because it overwrites partial-write debris on crash. The same pattern applies to the audit JSON in S4-02.
- **Mode `0600`** — recommendation files may contain task-class names and verdict reasons that name internal failure codes; default `0644` would expose them to other unprivileged users on shared CI runners. The mode-0600 discipline is consistent with the audit chain in S2-04.
- **Why pretty-print (`indent=2`) for recommendations but not necessarily for audit JSON?** Operators *read* recommendation files (decide whether to open a tier-promotion PR); audit JSON is machine-consumed (Phase 11 reads it). Pretty-printing audit JSON is fine but not required; for recommendations it is operator UX.
- **The static `test_recommendation_not_consumed` test is paranoid by design.** It will false-positive on any harmless string literal containing "recommendations" elsewhere in `src/codegenie/`. The mitigation is: there shouldn't be any such literal in Phase 6.5 code outside `recommendation.py`. If a legitimate use case appears in a later phase, refine the test; do not weaken it pre-emptively.
- **Coordinate the filename helper with S4-02.** S4-02 names audit JSONs `<run_started_iso>-<short>.json`; recommendation files use `<utc-iso>.json` (no run_id suffix, because a recommendation is point-in-time, not run-scoped). Different conventions are correct here — do not unify under pressure.
- **The YAML's `current_tiers: {}` empty mapping is intentional.** Phase 6.5 emits no committed tiers. Even `vuln-remediation` (which Phase 6.5 backfills with ≥10 cases) is *not* listed as bronze in `current_tiers` — its bronze status requires a human PR after S5-05 produces the first `BenchRunReport.lower_bound_95`. This is the architecture's commitment to humans-always-merge taken to its logical conclusion.
