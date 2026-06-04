# Story S4-05 — `docs/trust-tiers.yaml` + recommendation writer

**Step:** Step 4 — Wire the CLI and the read-only promotion gate
**Status:** HARDENED (phase-story-validator, 2026-06-04)
**Effort:** S
**Depends on:** S4-04 (HARDENED — `PromotionGate.evaluate` returns `PromotionVerdict`; `TierConfig` + `load_tier_config` live in `src/codegenie/eval/tier_config.py`, NOT in `promotion.py`; `PromotionGate.__init__` validates registered task-class tier slugs at startup per AC-3)

**ADRs honored:** ADR-0003 (tier IDs as `str`, validated at startup against `docs/trust-tiers.yaml`; YAML is contract data, CODEOWNERS-gated, candidate numbers only), ADR-0009 (automatic-demotion is a recommendation-shift; the recommendation file is the only side effect), Production ADR-0009 (humans always merge; the recommendation file is advisory data, not a control signal), Production ADR-0015 (calibration deferred; `docs/trust-tiers.yaml` carries candidates, not commitments)

## Validation notes

Validated: 2026-06-04
Verdict: HARDENED
Findings addressed: 16 total — 5 block, 8 harden, 3 nit

Conflict-resolution priority applied: **Consistency > Coverage > Test-Quality > Design-Patterns**. The story as authored predated the S4-04 HARDENED contract surface and the actual `PromotionVerdict` field shape; an executor following it verbatim would (a) import `load_tier_config` / `TierConfig` from `promotion.py` (wrong module — they live in `tier_config.py` per S4-04 AC-1); (b) build a `sample_verdict` fixture with non-existent fields `chain_head` and `run_id` (those live on `BenchRunReport`, not `PromotionVerdict`); (c) call `PromotionVerdict.model_construct(...)` (forbidden by S4-04 AC-10 — full Pydantic validation is required); (d) leave `schema_version: 1` as a load-bearing-but-unspec'd literal in the YAML (no fence against silent v2 drift); (e) emit a static-introspection test so coarse it false-positives on any docstring containing "recommendations". Every issue is patchable in place → **HARDENED**, not RESCUE.

- **`tier_config` module** — every import in the TDD plan moved from `codegenie.eval.promotion` to `codegenie.eval.tier_config` (Consistency F-CON-1; mirrors S4-04 HARDENED Implementation outline §2).
- **`sample_verdict` fixture rewritten** to populate all eight S1-02 required fields verbatim — `task_class`, `current_tier`, `target_tier`, `evidence_sufficient`, `reasons`, `lower_bound_95`, `threshold_at_target`, `requires_human_approval=True` (Consistency F-CON-2 + Coverage F-COV-1). `chain_head` / `run_id` removed (those are `BenchRunReport` fields).
- **`model_construct` retired** in the fixture — full `PromotionVerdict(...)` construction so a future runner-output drift cannot diverge from test fixtures (Consistency F-CON-3 + Test-Quality F-TQ-1; mirrors S4-04 F-TQ-1).
- **`schema_version: 1` forward-compat fence added** — `load_tier_config` accepts `{thresholds, current_tiers, schema_version}` only; unknown top-level keys or `schema_version != 1` raise `TierConfigInvalid` (Coverage F-COV-2 + Design-Patterns F-DP-1). Without this fence, a v2 YAML silently parses to v1 semantics — the worst kind of silent index staleness for contract data.
- **Deterministic-time injection on `write_recommendation`** — new keyword-only `now: datetime | None = None` parameter; defaults to `datetime.now(UTC)`; enables byte-identical-rerun + filename-proximity tests without monkeypatching `datetime` (Design-Patterns F-DP-2 — functional-core / imperative-shell; the filename derivation becomes a pure function of `now`). The new `_utc_iso_filename(now: datetime) -> str` is the pure helper; the public wrapper is the thin impure shell.
- **Filename test strengthened** — adds a ±10s proximity assertion between the filename's parsed UTC timestamp and an injected `now` to kill mutants that return a constant filename (Test-Quality F-TQ-2).
- **`mkdir(parents=True)` test strengthened** — nests three levels (`tmp_path / "a" / "b" / "c"`) to kill a `parents=False` mutant; one nested level admits a `parents=False` mutant that still passes (Test-Quality F-TQ-3).
- **Byte-identical-rerun test added** — two `write_recommendation(verdict, out_dir, now=fixed_dt)` calls produce equal bytes on disk; pins ADR-0002 §Consequences "byte-identical across reruns" determinism contract through to the recommendation surface (Coverage F-COV-3 + Test-Quality F-TQ-4).
- **Atomic-write-failure cleanup test added** — monkeypatches `os.replace` to raise; asserts target absent AND `.tmp` cleaned up; pins the half-tested "atomic" guarantee against a mutant that omits the cleanup branch (Test-Quality F-TQ-5).
- **Static-introspection test scoped** — only flags string literals that are *arguments to* read-shaped calls (`open`, `read_text`, `read_bytes`, `glob`, `iterdir`, `rglob`) AND contain `recommendations`; no longer false-positives on docstrings (Test-Quality F-TQ-6; mirrors the S1-05 import-ban discipline narrowed by AST role, not substring presence).
- **Same-second collision documented as known limitation** — keeping the arch's exact `<utc-iso>.json` filename (`phase-arch-design.md §Dynamic view → Sequence`); collision risk is accepted residual (Consistency over filename-suffix Design-Patterns suggestion; arch dictates filename literal).
- **Forward-compat note** added — when `silver`/`gold`/`platinum` thresholds land in a later phase, new top-level keys (e.g. `per_task_class_thresholds`) require an ADR amendment AND `schema_version` bump. The fence forces this loud.
- **Bench-registration tier-validation duplicate dropped** — the `test_unknown_tier_in_registration_raises_against_phase65_yaml` test lived under an undefined `registry_with_silver_min_cases` fixture; this responsibility belongs to S4-04 `test_promotion.py` AC-3 (which covers `min_cases_for_promotion` keys, `current_tiers` values, AND `thresholds` keys against the shipped YAML set). S4-05 references S4-04 instead of duplicating (Consistency F-CON-4).
- **`schema_version` accepted in YAML** — the shipped YAML retains `schema_version: 1` (it is now load-bearing for the forward-compat fence, not decorative).
- **Module constant** introduced — `DEFAULT_RECOMMENDATION_DIR = Path(".codegenie/eval/recommendations")` at module top of `recommendation.py` to mirror S4-02's pattern; the public default expression references it (nit).
- **Test docstring scope corrected** — `test_recommendation_not_consumed` walks `src/codegenie/eval/` only (not all of `src/codegenie/`); the doc matches the walk (nit).

Full audit log: [`_validation/S4-05-trust-tiers-yaml-and-recommendation-writer.md`](_validation/S4-05-trust-tiers-yaml-and-recommendation-writer.md)

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

### `docs/trust-tiers.yaml` — contract data (Consistency F-CON-1 / F-CON-4 + Coverage F-COV-2)

- [ ] **AC-1.** `docs/trust-tiers.yaml` exists and parses to **exactly** the following shape (the `schema_version` field is load-bearing for the forward-compat fence in AC-7, not decorative):
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
- [ ] **AC-2.** The first 500 bytes of `docs/trust-tiers.yaml` contain the literal substring `"UNCALIBRATED"` (read via `Path.read_bytes()[:500].decode("utf-8", errors="replace")`). 500 bytes — not 200 — to survive an SPDX-header or licence-block prefix without forcing a comment-strip refactor (Test-Quality F-TQ-7 widening).
- [ ] **AC-3.** Only `bronze` is declared in `thresholds`: `set(loaded.thresholds) == {"bronze"}` and `0.0 < loaded.thresholds["bronze"] <= 1.0`. `silver` / `gold` / `platinum` are absent — Phase 7 / Phase 15 add them via their own ADR amendments per ADR-0003.
- [ ] **AC-4.** `current_tiers` is an empty mapping (`loaded.current_tiers == {}`); no task class is registered as currently-tiered until a human-authored PR lands one (per ADR-0009 + Production ADR-0009).

### `tier_config` module — imports + round-trip + forward-compat fence (Consistency F-CON-1 + Coverage F-COV-2 + Design-Patterns F-DP-1)

- [ ] **AC-5.** Every test in this story imports `load_tier_config` and `TierConfig` from `codegenie.eval.tier_config` (the module S4-04 AC-1 created), **not** from `codegenie.eval.promotion`. `PromotionGate` is imported from `codegenie.eval.promotion`.
- [ ] **AC-6.** `load_tier_config(Path("docs/trust-tiers.yaml"))` round-trips to a `TierConfig` whose `thresholds == MappingProxyType({"bronze": 0.70})` and `current_tiers == MappingProxyType({})` (compared via dict equality — `MappingProxyType` `__eq__` against a `dict` returns True). `PromotionGate(tier_config=load_tier_config(...))` constructs without raising **on a fresh `TaskClassRegistry()`** (so the test isolates the contract from whatever `default_registry` happens to carry).
- [ ] **AC-7. Forward-compat fence on `schema_version`.** `load_tier_config` accepts top-level keys ⊆ `{"schema_version", "thresholds", "current_tiers"}` only; raises `TierConfigInvalid` on:
  - any unknown top-level key (e.g. `per_task_class_thresholds`) — `exc.args == ("unknown_key", unknown_key, ("current_tiers", "schema_version", "thresholds"))`;
  - `schema_version` absent — `exc.args == ("schema_version_missing", (1,))`;
  - `schema_version != 1` — `exc.args == ("schema_version", schema_version, (1,))`.
  This forces a v2 YAML to crash old loaders loudly rather than silently parse to v1 semantics. **Tests:** three parametrized cases under `test_trust_tiers_yaml.py::test_load_tier_config_forward_compat_fence`, each writing a synthetic YAML to `tmp_path` and asserting the exact `TierConfigInvalid.args` tuple.
- [ ] **AC-8. Bench-registration tier validation is owned by S4-04, not this story.** The `PromotionGate.__init__` startup check that any `TaskClass.min_cases_for_promotion` key absent from `tier_config.thresholds` raises `TierConfigInvalid` is covered by S4-04 `test_promotion.py` AC-3. This story neither duplicates that test nor introduces a `registry_with_silver_min_cases` fixture (Consistency F-CON-4).

### `write_recommendation` — contract surface (Coverage F-COV-1 + Design-Patterns F-DP-2 + Test-Quality F-TQ-1 .. F-TQ-5)

- [ ] **AC-9.** `src/codegenie/eval/recommendation.py` defines a module-top constant:
  ```python
  DEFAULT_RECOMMENDATION_DIR: Final[Path] = Path(".codegenie/eval/recommendations")
  ```
  and the public function:
  ```python
  def write_recommendation(
      verdict: PromotionVerdict,
      out_dir: Path = DEFAULT_RECOMMENDATION_DIR,
      *,
      now: datetime | None = None,
  ) -> Path: ...
  ```
  The `now` parameter is **keyword-only**; defaults to `datetime.now(UTC)` when `None`. This is the functional-core / imperative-shell split: filename derivation becomes a pure function of `now`; the only impurity is the default. (Design-Patterns F-DP-2.)
- [ ] **AC-10. Filename shape.** The returned `Path.name` matches `<utc-iso>.json` where `<utc-iso> == now.strftime("%Y-%m-%dT%H-%M-%SZ")` (hyphens, not colons — same `<utc-iso>` convention as the audit JSON in S4-02). The literal filename pattern is fixed by `phase-arch-design.md §Dynamic view → Sequence` line 496 — no `-<short>` hex suffix (same-second collisions are an accepted residual; see Notes for implementer).
- [ ] **AC-11. `_utc_iso_filename(now: datetime) -> str`** is a module-private pure helper returning `now.astimezone(UTC).strftime("%Y-%m-%dT%H-%M-%SZ") + ".json"`. Test isolates it directly — `_utc_iso_filename(datetime(2026, 6, 4, 12, 30, 45, tzinfo=UTC)) == "2026-06-04T12-30-45Z.json"` (mutation-resistant byte-string pin).
- [ ] **AC-12. Filename-proximity guard against constant-return mutants.** A test calls `write_recommendation(verdict, out_dir, now=datetime(2026,6,4,12,30,45,tzinfo=UTC))` and asserts `written.name == "2026-06-04T12-30-45Z.json"` exactly. A *second* test calls with `now=None` and asserts the filename's parsed UTC timestamp falls within ±10 s of `datetime.now(UTC)` captured before/after the call. Kills mutants that return `"2000-01-01T00-00-00Z.json"` regardless of `now`.
- [ ] **AC-13. Directory creation.** `out_dir.mkdir(parents=True, exist_ok=True)` is invoked exactly once before the temp write. The test uses `tmp_path / "a" / "b" / "c"` (three nested levels) to kill a `parents=False` mutant. (Test-Quality F-TQ-3.)
- [ ] **AC-14. Atomic write contract.** Implementation pattern:
  ```python
  tmp = target.with_suffix(target.suffix + ".tmp")
  tmp.write_text(verdict.model_dump_json(indent=2))
  os.chmod(tmp, 0o600)
  os.replace(tmp, target)
  ```
  No partial-write debris is reachable via `Path.write_text(target, ...)` direct call. Atomicity is verified by the failure-cleanup test in AC-16.
- [ ] **AC-15. Mode `0o600` after replace.** `stat.S_IMODE(os.stat(written).st_mode) == 0o600`. The mode is set on `tmp` before `os.replace` so the renamed target inherits the mode atomically. (Linux + macOS both preserve source mode across `os.replace` within the same dir.)
- [ ] **AC-16. Atomic-write-failure cleanup.** A test monkeypatches `os.replace` to raise `OSError("disk full")`; calls `write_recommendation`; asserts that (a) `pytest.raises(OSError)` fires; (b) the target file does NOT exist; (c) the `.tmp` file is cleaned up (no leftover `*.tmp` in `out_dir`). Implementation MUST use `try/except` + `tmp.unlink(missing_ok=True)` in the failure branch to honor this contract.
- [ ] **AC-17. Body content.** `written.read_text() == verdict.model_dump_json(indent=2)`. The pretty-printed JSON (indent=2, ASCII keys sorted by Pydantic's deterministic field order) round-trips through `PromotionVerdict.model_validate(json.loads(written.read_text())) == verdict` — both `==` *and* `model_dump_json()` byte-equal (no float-formatting drift).
- [ ] **AC-18. Byte-identical reruns.** `write_recommendation(verdict, out_dir_a, now=fixed_dt)` and `write_recommendation(verdict, out_dir_b, now=fixed_dt)` produce identical bytes on disk (`Path.read_bytes()` equality). Pins the determinism contract from ADR-0002 §Consequences "byte-identical across reruns" through the recommendation surface. (The two writes go to **different** out_dirs to avoid the second `os.replace` clobbering the first when `now` is the same.)

### Wire-up boundary (Coverage F-COV-4 — wire-up tests live in S4-02)

- [ ] **AC-19. Wire-up boundary.** S4-02's `--with-verdict` flag invokes `write_recommendation(verdict)` (single import + single call inside the deferred-import block). **This story exports the function; S4-02 owns and tests the call site.** The auto-flip-detection path (recommendation triggered when `evaluate` flips `evidence_sufficient` `False→True` between consecutive runs) is documented in Notes for implementer and **deferred** — no Phase 6.5 code path is required to detect the flip.

### Write-only guard (Test-Quality F-TQ-6 — AST-narrowed)

- [ ] **AC-20.** `tests/unit/test_recommendation_not_consumed.py` enforces that **no module under `src/codegenie/eval/` reads the recommendation directory as a control signal**. The walk:
  - Iterates `src/codegenie/eval/**/*.py` (NOT `src/codegenie/**/*.py` — the doc-comment scope correction).
  - For each module, walks the AST and **only** flags an `ast.Constant(str)` containing `"recommendations"` if:
    1. its parent is an `ast.Call` whose `.func` resolves to one of `{"open", "read_text", "read_bytes", "glob", "iterdir", "rglob"}` (read-shaped), AND
    2. the file is not `recommendation.py` (the writer module itself).
  - This kills the docstring-false-positive failure mode while preserving the "no silent reader" invariant. Implementation walks `ast.parse(src)` and inspects `ast.Call` nodes for `Attribute.attr` / `Name.id` matches; the read-call name set is a module-level `Final[frozenset[str]]`.

### Quality gates

- [ ] **AC-21.** The red tests from §TDD plan exist, were committed at the red marker, and are now green.
- [ ] **AC-22.** `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/eval/recommendation.py`, and `pytest tests/unit/test_trust_tiers_yaml.py tests/unit/test_recommendation_writer.py tests/unit/test_recommendation_not_consumed.py` all pass on touched files.

## Implementation outline

1. Write red tests in this order (each commit gates on `pytest` failing at the import / fixture step):
   1. `tests/unit/test_trust_tiers_yaml.py` — file existence + UNCALIBRATED marker + bronze-only + empty `current_tiers` + round-trip + forward-compat fence (`schema_version`, unknown keys).
   2. `tests/unit/test_recommendation_writer.py` — `_utc_iso_filename` pure pin + `write_recommendation` (filename, mkdir 3-deep, atomic + cleanup-on-failure, mode 0600, body round-trip, byte-identical reruns, deterministic-time injection).
   3. `tests/unit/test_recommendation_not_consumed.py` — AST-narrowed read-call walk over `src/codegenie/eval/`.
2. Author `docs/trust-tiers.yaml` with the exact content shape from AC-1. Include the SPDX header and the `UNCALIBRATED` disclaimer as a leading comment within the first 500 bytes.
3. Extend `src/codegenie/eval/tier_config.py` (the module S4-04 created) so `load_tier_config` enforces the forward-compat fence per AC-7:
   - Parse YAML → `dict[str, Any]`.
   - Reject unknown top-level keys (raise `TierConfigInvalid("unknown_key", <key>, ("current_tiers", "schema_version", "thresholds"))`).
   - Require `schema_version` (raise `TierConfigInvalid("schema_version_missing", (1,))`).
   - Reject `schema_version != 1` (raise `TierConfigInvalid("schema_version", <got>, (1,))`).
   - Construct `TierConfig(thresholds=..., current_tiers=...)` only after the fence passes.
4. Create `src/codegenie/eval/recommendation.py`:
   - Module-top imports: stdlib only (`from __future__ import annotations`, `os`, `stat` if needed for docs, `from datetime import UTC, datetime`, `from pathlib import Path`, `from typing import Final`), plus `from codegenie.eval.models import PromotionVerdict`.
   - `DEFAULT_RECOMMENDATION_DIR: Final[Path] = Path(".codegenie/eval/recommendations")`.
   - `_READ_CALL_NAMES: Final[frozenset[str]] = frozenset({"open", "read_text", "read_bytes", "glob", "iterdir", "rglob"})` (consumed only by the static-introspection test via import; placing it here ensures the canonical set is single-sourced — recommended, not required).
   - `_utc_iso_filename(now: datetime) -> str` — pure helper; returns `now.astimezone(UTC).strftime("%Y-%m-%dT%H-%M-%SZ") + ".json"`.
   - `write_recommendation(verdict, out_dir=DEFAULT_RECOMMENDATION_DIR, *, now=None) -> Path` — the impure shell:
     ```python
     resolved_now = now if now is not None else datetime.now(UTC)
     out_dir.mkdir(parents=True, exist_ok=True)
     target = out_dir / _utc_iso_filename(resolved_now)
     tmp = target.with_suffix(target.suffix + ".tmp")
     tmp.write_text(verdict.model_dump_json(indent=2))
     os.chmod(tmp, 0o600)
     try:
         os.replace(tmp, target)
     except OSError:
         tmp.unlink(missing_ok=True)
         raise
     return target
     ```
5. Add the AST-narrowed static-introspection test `tests/unit/test_recommendation_not_consumed.py` per AC-20.
6. Wire the writer call site from S4-02's `--with-verdict` flag (single import + single function call inside the deferred-import block). **Verification:** S4-02's existing tests cover the wire-up; no test in this story duplicates them.
7. Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/eval/recommendation.py`, the full pytest set from AC-22.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/test_trust_tiers_yaml.py
from pathlib import Path
import pytest
# NOTE: tier_config — NOT promotion — per S4-04 AC-1 module split.
from codegenie.eval.tier_config import load_tier_config, TierConfig
from codegenie.eval.promotion import PromotionGate
from codegenie.eval.registry import TaskClassRegistry
from codegenie.eval.errors import TierConfigInvalid


YAML_PATH = Path("docs/trust-tiers.yaml")


def test_trust_tiers_yaml_exists():
    assert YAML_PATH.exists(), "docs/trust-tiers.yaml is contract data — Phase 6.5 must ship it"


def test_trust_tiers_yaml_first_500_bytes_warn_uncalibrated():
    # 500 bytes (not 200) — survives an SPDX/licence prefix without forcing a comment-strip.
    head = YAML_PATH.read_bytes()[:500].decode("utf-8", errors="replace")
    assert "UNCALIBRATED" in head, (
        "trust-tiers.yaml must declare UNCALIBRATED in its leading comments per ADR-0003 + ADR-0015"
    )


def test_trust_tiers_yaml_only_declares_bronze():
    cfg = load_tier_config(YAML_PATH)
    assert isinstance(cfg, TierConfig)
    assert set(cfg.thresholds) == {"bronze"}, (
        "Phase 6.5 ships only bronze; silver/gold/platinum are added by their consuming phase + ADR amendment"
    )
    assert 0.0 < cfg.thresholds["bronze"] <= 1.0


def test_trust_tiers_yaml_current_tiers_empty():
    cfg = load_tier_config(YAML_PATH)
    assert cfg.current_tiers == {}, (
        "current_tiers is empty until a human PR promotes a task class per ADR-0009"
    )


def test_promotion_gate_constructs_from_shipped_yaml():
    # Isolate from default_registry — the YAML-vs-registry contract is the focus.
    cfg = load_tier_config(YAML_PATH)
    gate = PromotionGate(tier_config=cfg, registry=TaskClassRegistry())
    assert gate is not None  # construction did not raise


# ---------- Forward-compat fence on schema_version (AC-7) ----------

@pytest.mark.parametrize(
    "yaml_text, expected_args",
    [
        # Unknown top-level key — sorted available set for "did you mean" diagnostics.
        (
            "schema_version: 1\nthresholds:\n  bronze: 0.7\ncurrent_tiers: {}\nper_task_class_thresholds: {}\n",
            ("unknown_key", "per_task_class_thresholds", ("current_tiers", "schema_version", "thresholds")),
        ),
        # schema_version absent.
        (
            "thresholds:\n  bronze: 0.7\ncurrent_tiers: {}\n",
            ("schema_version_missing", (1,)),
        ),
        # schema_version != 1.
        (
            "schema_version: 2\nthresholds:\n  bronze: 0.7\ncurrent_tiers: {}\n",
            ("schema_version", 2, (1,)),
        ),
    ],
    ids=["unknown_top_level_key", "schema_version_missing", "schema_version_not_one"],
)
def test_load_tier_config_forward_compat_fence(tmp_path, yaml_text, expected_args):
    p = tmp_path / "trust-tiers.yaml"
    p.write_text(yaml_text)
    with pytest.raises(TierConfigInvalid) as exc_info:
        load_tier_config(p)
    assert exc_info.value.args == expected_args, (
        f"forward-compat fence args mismatch: got {exc_info.value.args!r}, expected {expected_args!r}"
    )
```

```python
# tests/unit/test_recommendation_writer.py
import json
import os
import re
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
import pytest

from codegenie.eval.recommendation import (
    DEFAULT_RECOMMENDATION_DIR,
    _utc_iso_filename,
    write_recommendation,
)
from codegenie.eval.models import PromotionVerdict


@pytest.fixture
def sample_verdict() -> PromotionVerdict:
    # All EIGHT S1-02-required fields explicit; full validation (NOT model_construct,
    # which S4-04 AC-10 forbids). `chain_head` / `run_id` are BenchRunReport fields
    # — they are NOT on PromotionVerdict; including them would violate extra="forbid".
    return PromotionVerdict(
        task_class="vuln-remediation",
        current_tier="bronze",
        target_tier="bronze",
        evidence_sufficient=True,
        reasons=("all conditions met",),
        lower_bound_95=0.78,
        threshold_at_target=0.70,
        requires_human_approval=True,
    )


# ---------- Pure helper pin (AC-11) ----------

def test_utc_iso_filename_is_pure_and_byte_pinned():
    got = _utc_iso_filename(datetime(2026, 6, 4, 12, 30, 45, tzinfo=UTC))
    assert got == "2026-06-04T12-30-45Z.json"


def test_utc_iso_filename_normalizes_naive_to_utc_via_astimezone():
    # A non-UTC tz-aware input is normalized via astimezone — same byte-string output.
    from datetime import timezone
    cst = timezone(timedelta(hours=-6))
    got = _utc_iso_filename(datetime(2026, 6, 4, 6, 30, 45, tzinfo=cst))
    assert got == "2026-06-04T12-30-45Z.json"


# ---------- Filename + proximity (AC-10, AC-12) ----------

def test_writer_filename_exact_with_injected_now(tmp_path, sample_verdict):
    fixed = datetime(2026, 6, 4, 12, 30, 45, tzinfo=UTC)
    written = write_recommendation(sample_verdict, out_dir=tmp_path, now=fixed)
    assert written.name == "2026-06-04T12-30-45Z.json"


def test_writer_filename_default_now_within_10s(tmp_path, sample_verdict):
    before = datetime.now(UTC)
    written = write_recommendation(sample_verdict, out_dir=tmp_path)
    after = datetime.now(UTC)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z\.json", written.name)
    parsed = datetime.strptime(written.stem, "%Y-%m-%dT%H-%M-%SZ").replace(tzinfo=UTC)
    # ±10s window kills mutants that return a constant filename.
    assert before - timedelta(seconds=10) <= parsed <= after + timedelta(seconds=10)


# ---------- Directory creation (AC-13) ----------

def test_writer_creates_three_nested_levels(tmp_path, sample_verdict):
    out = tmp_path / "a" / "b" / "c"  # 3 levels — kills parents=False mutant
    assert not out.exists()
    written = write_recommendation(sample_verdict, out_dir=out)
    assert written.exists()
    assert written.parent == out


def test_writer_idempotent_on_existing_dir(tmp_path, sample_verdict):
    out = tmp_path / "exists"
    out.mkdir()
    written = write_recommendation(sample_verdict, out_dir=out, now=datetime(2026, 6, 4, 0, 0, 0, tzinfo=UTC))
    assert written.exists()


# ---------- Atomic write + cleanup on failure (AC-14, AC-16) ----------

def test_writer_atomic_no_temp_left_behind_on_success(tmp_path, sample_verdict):
    write_recommendation(sample_verdict, out_dir=tmp_path)
    assert list(tmp_path.glob("*.tmp")) == []


def test_writer_cleans_up_tmp_when_os_replace_raises(tmp_path, sample_verdict, monkeypatch):
    target_dt = datetime(2026, 6, 4, 12, 30, 45, tzinfo=UTC)

    def boom(_src, _dst):
        raise OSError("disk full")

    monkeypatch.setattr("codegenie.eval.recommendation.os.replace", boom)
    with pytest.raises(OSError, match="disk full"):
        write_recommendation(sample_verdict, out_dir=tmp_path, now=target_dt)
    # Target absent, no .tmp leak.
    assert not (tmp_path / "2026-06-04T12-30-45Z.json").exists()
    assert list(tmp_path.glob("*.tmp")) == [], (
        "atomic-write failure path must unlink the temp file"
    )


# ---------- Mode 0o600 (AC-15) ----------

def test_writer_mode_is_0600(tmp_path, sample_verdict):
    written = write_recommendation(sample_verdict, out_dir=tmp_path)
    assert stat.S_IMODE(os.stat(written).st_mode) == 0o600


# ---------- Payload + round-trip + byte-identical reruns (AC-17, AC-18) ----------

def test_writer_payload_round_trips_to_verdict(tmp_path, sample_verdict):
    written = write_recommendation(sample_verdict, out_dir=tmp_path)
    text = written.read_text()
    assert "\n" in text, "indent=2 pretty-printed for operator UX"
    assert text == sample_verdict.model_dump_json(indent=2)
    reread = PromotionVerdict.model_validate(json.loads(text))
    assert reread == sample_verdict
    # And the rehydrated model serializes byte-equal.
    assert reread.model_dump_json(indent=2) == text


def test_writer_byte_identical_reruns_same_verdict_same_now(tmp_path, sample_verdict):
    fixed = datetime(2026, 6, 4, 12, 30, 45, tzinfo=UTC)
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    w_a = write_recommendation(sample_verdict, out_dir=out_a, now=fixed)
    w_b = write_recommendation(sample_verdict, out_dir=out_b, now=fixed)
    assert w_a.read_bytes() == w_b.read_bytes()


# ---------- Default-dir constant pin (AC-9) ----------

def test_default_recommendation_dir_is_module_constant():
    assert DEFAULT_RECOMMENDATION_DIR == Path(".codegenie/eval/recommendations")
```

```python
# tests/unit/test_recommendation_not_consumed.py
"""Static guard: no module under src/codegenie/eval/ may read .codegenie/eval/recommendations
as a control signal. Recommendations are write-only from this phase per ADR-0009 and
phase-arch-design §Failure modes ("the system never branches on 'evidence sufficient'
automatically"). Scoped to `src/codegenie/eval/` only — the writer module itself is exempt.
The walk is AST-narrowed: only flags string literals passed as arguments to read-shaped calls
(open / read_text / read_bytes / glob / iterdir / rglob), so docstrings and log messages
mentioning the word do not false-positive."""
from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path("src/codegenie/eval")  # phase-scoped, not repo-wide
FORBIDDEN_SUBSTR = "recommendations"
READ_CALL_NAMES = frozenset({"open", "read_text", "read_bytes", "glob", "iterdir", "rglob"})
EXEMPT_FILES = frozenset({"recommendation.py"})


def _is_read_call(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr in READ_CALL_NAMES
    if isinstance(func, ast.Name):
        return func.id in READ_CALL_NAMES
    return False


def _literal_contains_forbidden(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and FORBIDDEN_SUBSTR in node.value
    )


def test_no_eval_module_reads_recommendation_files_via_read_calls():
    offenders: list[tuple[Path, int, str]] = []
    for f in SRC_ROOT.rglob("*.py"):
        if f.name in EXEMPT_FILES:
            continue
        try:
            tree = ast.parse(f.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not _is_read_call(node):
                continue
            # Check every arg + keyword value for a literal with the forbidden substring.
            candidates: list[ast.AST] = list(node.args) + [kw.value for kw in node.keywords]
            # Also check Path(...)/Path("...") receivers: e.g. Path("…recommendations…").glob(...)
            if isinstance(node.func, ast.Attribute):
                candidates.append(node.func.value)
            for cand in candidates:
                if _literal_contains_forbidden(cand):
                    offenders.append((f, node.lineno, getattr(cand, "value", "")))
    assert offenders == [], (
        f"src/codegenie/eval/ modules must not read recommendation files as a control signal: {offenders}"
    )
```

Run; confirm failures (missing YAML, missing module). Commit as the red marker.

### Green — make it pass

1. Author `docs/trust-tiers.yaml` per AC-1.
2. Extend `src/codegenie/eval/tier_config.py` (existing) with the forward-compat fence per AC-7. Sketch:
   ```python
   _ALLOWED_TOP_LEVEL_KEYS = frozenset({"schema_version", "thresholds", "current_tiers"})
   _SUPPORTED_SCHEMA_VERSIONS: Final[tuple[int, ...]] = (1,)


   def load_tier_config(path: Path) -> TierConfig:
       data = yaml.safe_load(path.read_text()) or {}
       if not isinstance(data, dict):
           raise TierConfigInvalid("top_level_not_mapping", type(data).__name__)
       extras = sorted(set(data) - _ALLOWED_TOP_LEVEL_KEYS)
       if extras:
           # First extra wins for diagnostic clarity; sorted available set for "did you mean".
           raise TierConfigInvalid(
               "unknown_key", extras[0], tuple(sorted(_ALLOWED_TOP_LEVEL_KEYS))
           )
       if "schema_version" not in data:
           raise TierConfigInvalid("schema_version_missing", _SUPPORTED_SCHEMA_VERSIONS)
       if data["schema_version"] not in _SUPPORTED_SCHEMA_VERSIONS:
           raise TierConfigInvalid(
               "schema_version", data["schema_version"], _SUPPORTED_SCHEMA_VERSIONS
           )
       return TierConfig(
           thresholds=data.get("thresholds", {}),
           current_tiers=data.get("current_tiers", {}),
       )
   ```
3. Implement `src/codegenie/eval/recommendation.py`:
   ```python
   from __future__ import annotations
   import os
   from datetime import UTC, datetime
   from pathlib import Path
   from typing import Final

   from codegenie.eval.models import PromotionVerdict

   DEFAULT_RECOMMENDATION_DIR: Final[Path] = Path(".codegenie/eval/recommendations")


   def _utc_iso_filename(now: datetime) -> str:
       return now.astimezone(UTC).strftime("%Y-%m-%dT%H-%M-%SZ") + ".json"


   def write_recommendation(
       verdict: PromotionVerdict,
       out_dir: Path = DEFAULT_RECOMMENDATION_DIR,
       *,
       now: datetime | None = None,
   ) -> Path:
       resolved_now = now if now is not None else datetime.now(UTC)
       out_dir.mkdir(parents=True, exist_ok=True)
       target = out_dir / _utc_iso_filename(resolved_now)
       tmp = target.with_suffix(target.suffix + ".tmp")
       tmp.write_text(verdict.model_dump_json(indent=2))
       os.chmod(tmp, 0o600)
       try:
           os.replace(tmp, target)
       except OSError:
           tmp.unlink(missing_ok=True)
           raise
       return target
   ```
4. Wire S4-02's `--with-verdict` call site to import this module lazily and call `write_recommendation(verdict)` after `gate.evaluate(report, target_tier)`.

### Refactor — clean up

- Type hints on every callable; `mypy --strict` clean.
- Module docstring cites ADR-0003 (YAML is contract data) and ADR-0009 (recommendation is the side-effect surface).
- The `_utc_iso_filename` helper is a single-line function but it's worth its own name because S4-02's audit JSON uses the same convention; if S4-02 already exports a similar helper, reuse rather than duplicate (Rule 8 — read before you write). If duplication is unavoidable, file a follow-up to consolidate into a shared `_paths.py`.
- The static-introspection test (`test_recommendation_not_consumed.py`) is a "fence" assertion in the same family as S1-05's import-ban tests; it gets stricter over time as the codebase grows. Document it in a comment so future contributors understand the intent.
- The YAML's `schema_version: 1` field is forward-looking — when production ADR-0015 calibrates real numbers, the schema may bump. Phase 6.5 ships v1; readers know how to detect drift.

## Files to touch

| Path | Why |
|---|---|
| `docs/trust-tiers.yaml` | New file — minimal schema (`schema_version: 1` load-bearing), bronze candidate, UNCALIBRATED header per ADR-0003 + ADR-0015. |
| `src/codegenie/eval/tier_config.py` | **Surgical extension** of the module S4-04 created — `load_tier_config` gains the forward-compat fence (allowed-keys set + `schema_version` validation). The `TierConfig` dataclass and `MappingProxyType` normalization stay as S4-04 shipped them. |
| `src/codegenie/eval/recommendation.py` | New file — `DEFAULT_RECOMMENDATION_DIR` constant + `_utc_iso_filename(now)` pure helper + `write_recommendation(verdict, out_dir, *, now=None)` impure shell with atomic write, mode 0600, and OSError-cleanup. |
| `tests/unit/test_trust_tiers_yaml.py` | New file — YAML existence, 500-byte UNCALIBRATED disclaimer, bronze-only, empty `current_tiers`, gate constructs against fresh registry, parametrized forward-compat fence (`unknown_top_level_key`, `schema_version_missing`, `schema_version_not_one`). |
| `tests/unit/test_recommendation_writer.py` | New file — `_utc_iso_filename` pure pin (+ tz-normalization), filename exact-with-injected-now + ±10s default-now proximity, 3-level `parents=True` mkdir, atomic + OSError-cleanup, mode 0600, body round-trip, byte-identical reruns, `DEFAULT_RECOMMENDATION_DIR` constant. |
| `tests/unit/test_recommendation_not_consumed.py` | New file — AST-narrowed static guard: walks `src/codegenie/eval/` only, flags only string literals passed to read-shaped calls (`open` / `read_text` / `read_bytes` / `glob` / `iterdir` / `rglob`) containing `recommendations`; `recommendation.py` exempt. |
| `src/codegenie/eval/cli.py` | Surgical edit — wire `write_recommendation` call into S4-02's `--with-verdict` block (deferred import). Tests for this wire-up live in S4-02. |

## Out of scope

- **Schema versioning beyond v1** — `schema_version: 1` is the lone field; per `phase-arch-design.md §Open Q #5`, versioning rules defer to ADR-0015.
- **Per-task-class threshold overrides** — also deferred per `phase-arch-design.md §Open Q #5`. The Phase 6.5 schema has only a global `thresholds` mapping.
- **Downgrade-threshold equality** — also deferred per `phase-arch-design.md §Open Q #5`.
- **`silver`, `gold`, `platinum` tier numbers** — Phase 7 (silver for migration), Phase 15 (recipe authoring), and ADR-0015 calibration will add these in their own PRs + ADR amendments.
- **Recommendation file consumers (Phase 11/12)** — `phase-arch-design.md §Open Q #7` defers; Phase 6.5 writes the contract; consumers ship later.
- **Auto-flip detection in the CLI loop** — the "flip from `False` to `True` between consecutive runs writes a recommendation" path is documented in §Acceptance criteria but the CLI implementation defers to a follow-up if needed; for Phase 6.5, the `--with-verdict` flag is the explicit trigger.
- **YAML migration tooling** — when ADR-0015 calibration ships real numbers, a script may convert candidate values; Phase 6.5 ships the file by hand.

## Notes for the implementer

- **The `UNCALIBRATED` header is load-bearing UX.** Future contributors who `grep` `docs/trust-tiers.yaml` for tier numbers must immediately understand these are not committed. The first 500 bytes test pins this — do not strip the comment to "save space."
- **`schema_version: 1` is load-bearing, not decorative.** The forward-compat fence (AC-7) raises on missing or non-`1` values AND on any unknown top-level key. When `silver`/`gold`/`platinum` thresholds land in a later phase, that phase's ADR amendment must either (a) keep `schema_version: 1` AND extend the allowed-keys set in `tier_config.py` (extension by addition), or (b) bump to `schema_version: 2` with a v2 loader. Adding `per_task_class_thresholds` without one of those — silent admission — is exactly the failure mode the fence prevents. Do not weaken `_ALLOWED_TOP_LEVEL_KEYS` to make a v2 YAML "just work"; force the ADR amendment loud.
- **`load_tier_config` is the loader. `TierConfig` is the value.** Per S4-04 Design-Patterns F-DP-3 (functional-core / imperative-shell), the loader lives in `tier_config.py` with the only `import yaml` in `src/codegenie/eval/`. Do not move `pyyaml` into `promotion.py` or `recommendation.py`.
- **Filename helper is pure.** `_utc_iso_filename(now: datetime) -> str` takes `now` as a parameter so tests can pin the byte string without monkeypatching `datetime`. The impure shell `write_recommendation(..., now=None)` resolves the default. This is functional-core / imperative-shell at the smallest possible scope; do not collapse them.
- **Same-second collision is an accepted residual.** `phase-arch-design.md §Dynamic view → Sequence` line 496 specifies the filename literal `<utc-iso>.json` — no `-<short>` hex suffix. Two writes in the same UTC second collide; the second's `os.replace` clobbers the first. Operators rarely flip verdicts twice in one second; if it happens, both writes contain the same verdict shape if the eval inputs are identical, so the loss is point-in-time advisory data only. Document, do not fix.
- **Atomic write discipline** — `os.replace` is the POSIX-atomic rename; on Windows `os.replace` also works (Python 3.3+). Do not use `Path.write_text` directly because it overwrites partial-write debris on crash. The same pattern applies to the audit JSON in S4-02.
- **Mode `0600`** — recommendation files may contain task-class names and verdict reasons that name internal failure codes; default `0644` would expose them to other unprivileged users on shared CI runners. The mode-0600 discipline is consistent with the audit chain in S2-04. The chmod is on `tmp` **before** `os.replace`, so the renamed target inherits the mode atomically on both Linux and macOS.
- **OSError-cleanup branch is contract, not "nice to have."** AC-16 pins it. A future "let's simplify" PR that removes the `try/except + unlink + raise` would silently leave `.tmp` files on disk-full scenarios. The test will fail loud; do not skip it.
- **`PromotionVerdict` fields the fixture pins.** All eight S1-02-required fields: `task_class`, `current_tier`, `target_tier`, `evidence_sufficient`, `reasons`, `lower_bound_95`, `threshold_at_target`, `requires_human_approval=True`. `chain_head` and `run_id` belong to `BenchRunReport`, not `PromotionVerdict` — including them would violate `extra="forbid"` and raise `ValidationError`. `PromotionVerdict.model_construct` is **forbidden** per S4-04 AC-10 — full Pydantic validation must succeed.
- **Why pretty-print (`indent=2`) for recommendations but not necessarily for audit JSON?** Operators *read* recommendation files (decide whether to open a tier-promotion PR); audit JSON is machine-consumed (Phase 11 reads it). Pretty-printing audit JSON is fine but not required; for recommendations it is operator UX.
- **The static `test_recommendation_not_consumed` test is paranoid by design.** It will false-positive on any harmless string literal containing "recommendations" elsewhere in `src/codegenie/`. The mitigation is: there shouldn't be any such literal in Phase 6.5 code outside `recommendation.py`. If a legitimate use case appears in a later phase, refine the test; do not weaken it pre-emptively.
- **Coordinate the filename helper with S4-02.** S4-02 names audit JSONs `<run_started_iso>-<short>.json`; recommendation files use `<utc-iso>.json` (no run_id suffix, because a recommendation is point-in-time, not run-scoped). Different conventions are correct here — do not unify under pressure.
- **The YAML's `current_tiers: {}` empty mapping is intentional.** Phase 6.5 emits no committed tiers. Even `vuln-remediation` (which Phase 6.5 backfills with ≥10 cases) is *not* listed as bronze in `current_tiers` — its bronze status requires a human PR after S5-05 produces the first `BenchRunReport.lower_bound_95`. This is the architecture's commitment to humans-always-merge taken to its logical conclusion.
