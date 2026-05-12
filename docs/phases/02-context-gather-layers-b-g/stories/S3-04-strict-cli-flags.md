# Story S3-04 — `--strict` + `--strict-domains` CLI flags + exit-code mapping

**Step:** Step 3 — Ship `IndexHealthProbe` (B2) and `BuildGraphProbe` (B5)
**Status:** Ready
**Effort:** S
**Depends on:** S3-01 (`IndexHealthProbe` emits the `confidence_summary` slice that this CLI logic reads)
**ADRs honored:** ADR-0011 (`--strict` is the supported failure-loud path; advisory budget never fails the gather), ADR-0012 (`--strict-domains` selective flag), production ADR-0006 (no LLM in gather — confidence is objective)

## Context

`IndexHealthProbe` never fails the gather (ADR-0011). The supported way for CI to fail-loud on `low` confidence is the `--strict` CLI flag: `codegenie gather --strict` exits with code **3** if any `index_health.<domain>.confidence == "low"`. The default (`codegenie gather`) exits 0 with a `confidence_summary` slice surfacing the degradation — operators reading dashboards see the signal; CI gates fail-loud only when they opt in.

ADR-0012 adds `--strict-domains <list>` for selective gating: a Phase 3 vuln-remediation rollout might want `--strict-domains cve` so it fails only when CVE-feed staleness drops the `cve` domain to `low`, but tolerates a stale semgrep rule pack. This story implements both flags, the exit-code mapping (3 = strict B2 low), and the integration tests covering the three permutations (default → 0, `--strict` → 3 on any low, `--strict-domains cve` → 3 only on `cve` low).

**The envelope is written *before* the non-zero exit** — operators always have the YAML to debug. The exit code is the gate; the envelope is the evidence.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Goals" #9` — `--strict` exits 3 on any B2 low; `--strict-domains` selective.
  - `../phase-arch-design.md §"Control flow" "Happy path"` final sentence — "**exit 3** if `--strict` is set and any `index_health.<domain>.confidence == "low"`."
  - `../phase-arch-design.md §"Decision points"` — the `--strict` flag (CLI layer) "maps `index_health.<domain>.confidence == "low"` to exit code 3 after envelope is written."
- **Phase ADRs:**
  - `../ADRs/0011-index-health-advisory-budget-and-strict-flag.md` — ADR-0011 — `--strict` is the supported failure-loud path; B2 never fails the gather itself.
  - `../ADRs/0012-audit-chain-blake3-rolling-head.md` — confirm; the `--strict-domains` flag spec lives in this phase's `High-level-impl.md §"Step 3"` and synth ledger; cross-link the actual `--strict-domains` ADR from the ADR README (file naming may differ — see Notes).
- **Production ADRs:**
  - `../../../production/adrs/0006-deterministic-gather-no-llm.md` — confidence is objective; `--strict` consumes objective signals.
- **Source design:**
  - `../final-design.md §"Goals (concrete, measurable)"` `--strict` bullet.
  - `../final-design.md §"Failure modes & recovery"` `--strict` row — exit 3 = strict B2 low.
- **High-level impl:**
  - `../High-level-impl.md §"Step 3"` deliverable bullet for `cli.py` extension.
- **Existing code (Phase 0/1 + Step 1/3 output):**
  - `src/codegenie/cli.py` — Phase 0/1 `click` CLI with `gather` subcommand and existing exit-code conventions.
  - `src/codegenie/probes/index_health.py` (S3-01) — emits `slice.confidence_summary.per_domain: dict[str, "high"|"medium"|"low"]` + `slice.confidence_summary.overall`.
  - `src/codegenie/coordinator.py` — gather entry point; current behavior writes envelope then returns exit code 0/2.
  - `src/codegenie/errors.py` — Phase 0/1 typed exceptions.

## Goal

Extend `codegenie gather` with `--strict` (exits 3 on **any** `index_health.<domain>.confidence == "low"`) and `--strict-domains <list>` (exits 3 only when the listed domain(s) are `low`), preserving the architectural invariant that the envelope is always written before the non-zero exit.

## Acceptance criteria

- [ ] `src/codegenie/cli.py` adds two `click` options to the `gather` subcommand:
  - `--strict` — `is_flag=True, default=False, help="Exit 3 if any index_health domain reports confidence: low."`
  - `--strict-domains` — `type=str, default=None, multiple=False` (comma-separated string parsed inside the CLI; e.g., `--strict-domains cve,sbom`); help text `"Exit 3 only when the listed index_health domains report confidence: low. Comma-separated. Implies --strict semantics scoped to the listed domains."`
- [ ] Flag mutual relationship: `--strict` and `--strict-domains` are **independently** specifiable; if both appear, `--strict-domains` **narrows** `--strict` (semantically: the union of "all" + "subset" is "subset"); document the chosen precedence inline. Default for both is off.
- [ ] Exit-code mapping (codified in `src/codegenie/cli.py` after the gather completes):
  - **No flag.** Existing Phase 0/1 exit codes preserved. (Typically 0 on success, 2 on CLI-level error, etc.) Confidence-low is **not** an error.
  - **`--strict` alone.** If `index_health.confidence_summary.per_domain` contains any `"low"`, exit **3**. Otherwise the existing exit-code rules apply.
  - **`--strict-domains cve`** (or any subset). If any **listed** domain in `per_domain` is `"low"`, exit **3**. Domains not in the list are ignored.
  - **`--strict` + `--strict-domains cve`** combined. The narrower (`--strict-domains`) wins; exit 3 only on listed-domain `low`.
- [ ] **Envelope is always written before exit-3** — the gather completes fully (writes YAML, raw artifacts, audit chain head) before the strict-mode exit-code mapping evaluates `per_domain`.
- [ ] `src/codegenie/cli.py --help` text for `gather` documents both flags + the exit-code 3 meaning + the precedence rule.
- [ ] Invalid `--strict-domains` value (a domain name not in `{scip, sbom, cve, semgrep, gitleaks, runtime_trace}`) → CLI exits **2** at flag-parse time with a clear error message; the gather does **not** run. (Defensive: typos in CI configs surface immediately.)
- [ ] Red test exists and was committed failing; green tests cover:
  - `tests/unit/cli/test_strict_exit_codes.py`: (a) `--strict` against a synthetic envelope with one `low` → exit 3; (b) `--strict` against all-`high` → exit 0; (c) `--strict-domains cve` against `low` on `cve` → exit 3; (d) `--strict-domains cve` against `low` on `sbom` only → exit 0; (e) `--strict` + `--strict-domains cve` with `low` on `sbom` and `cve` `high` → exit 0 (narrower wins); (f) invalid `--strict-domains nonexistent` → exit 2 at parse; (g) envelope file exists on disk after a strict-mode exit 3 (envelope-before-exit invariant).
  - `tests/unit/probes/test_index_health_strict.py` (if not already covered by `test_index_health.py`): synthetic per-domain rollup that drives the integration paths above.
- [ ] `ruff format --check`, `ruff check`, `mypy --strict src/codegenie/cli.py`, and the unit tests pass.

## Implementation outline

1. **Add the two `click` options** to the `gather` subcommand. Parse `--strict-domains` from the comma-separated string into a `frozenset[str]`; validate each token against the closed domain enum `{"scip","sbom","cve","semgrep","gitleaks","runtime_trace"}` from `INDEX_HEALTH_DOMAINS`; on mismatch raise `click.BadParameter` (`click` translates to exit-2 automatically).
2. **Wire the post-gather exit-code mapping.** After the existing gather flow returns, read `envelope["probes"]["index_health"]["confidence_summary"]["per_domain"]` (handle the slice being absent — e.g., LD-only repo where B2 didn't apply: treat as no `low`).
   - If `--strict-domains` is non-empty: `low_domains = {d for d in strict_domains if per_domain.get(d) == "low"}`.
   - Else if `--strict` is set: `low_domains = {d for d, c in per_domain.items() if c == "low"}`.
   - Else: `low_domains = set()`.
   - If `low_domains` is non-empty: emit a structured log event `strict.exit_3_triggered` with the offending domains; `sys.exit(3)`.
3. **Confirm the envelope-write-before-exit invariant** — the existing gather entry point writes the envelope inside the try/finally already; no change required. The strict-mode mapping runs **after** the gather returns.
4. **Update `--help`** docstrings on the two options to spell out exit code 3 + the precedence rule.
5. **No structural change** to `IndexHealthProbe` — this story is CLI-only.

## TDD plan — red / green / refactor

### Red — failing test first

Test file path: `tests/unit/cli/test_strict_exit_codes.py`.

```python
# tests/unit/cli/test_strict_exit_codes.py
"""Pins: --strict exits 3 on any low; --strict-domains narrows; envelope always written.
Traces to: phase-arch-design.md §Goals #9; ADR-0011; ADR-0012."""
from __future__ import annotations
from pathlib import Path
import pytest
from click.testing import CliRunner

from codegenie.cli import cli   # the click group entry point

def _patch_gather(monkeypatch, per_domain: dict[str, str], tmp_path: Path):
    """Replace the gather entry point with a stub that writes a minimal envelope
    containing the given per_domain confidences, then returns."""
    out = tmp_path / "repo-context.yaml"
    def _stub(*args, **kwargs):
        out.write_text(
            "probes:\n  index_health:\n    confidence_summary:\n"
            f"      per_domain: {per_domain!r}\n"
            f"      overall: {'low' if 'low' in per_domain.values() else 'high'}\n"
        )
        return 0   # gather itself always succeeds
    monkeypatch.setattr("codegenie.cli._run_gather", _stub)
    return out

def test_strict_exits_3_on_any_low(monkeypatch, tmp_path):
    env_file = _patch_gather(monkeypatch, {"cve": "low", "sbom": "high"}, tmp_path)
    r = CliRunner().invoke(cli, ["gather", "--strict", str(tmp_path)])
    assert r.exit_code == 3
    assert env_file.exists()   # envelope-before-exit invariant

def test_strict_exits_0_on_all_high(monkeypatch, tmp_path):
    _patch_gather(monkeypatch, {"cve": "high", "sbom": "high"}, tmp_path)
    r = CliRunner().invoke(cli, ["gather", "--strict", str(tmp_path)])
    assert r.exit_code == 0

def test_strict_domains_cve_exits_3_only_on_cve_low(monkeypatch, tmp_path):
    _patch_gather(monkeypatch, {"cve": "low", "sbom": "high"}, tmp_path)
    r = CliRunner().invoke(cli, ["gather", "--strict-domains", "cve", str(tmp_path)])
    assert r.exit_code == 3

def test_strict_domains_cve_ignores_sbom_low(monkeypatch, tmp_path):
    _patch_gather(monkeypatch, {"cve": "high", "sbom": "low"}, tmp_path)
    r = CliRunner().invoke(cli, ["gather", "--strict-domains", "cve", str(tmp_path)])
    assert r.exit_code == 0   # sbom low ignored

def test_strict_domains_narrows_strict(monkeypatch, tmp_path):
    _patch_gather(monkeypatch, {"cve": "high", "sbom": "low"}, tmp_path)
    r = CliRunner().invoke(cli, ["gather", "--strict", "--strict-domains", "cve", str(tmp_path)])
    assert r.exit_code == 0   # --strict-domains cve narrows; sbom-low ignored

def test_invalid_strict_domain_exits_2(monkeypatch, tmp_path):
    r = CliRunner().invoke(cli, ["gather", "--strict-domains", "nonexistent", str(tmp_path)])
    assert r.exit_code == 2
    assert "nonexistent" in r.output.lower() or "invalid" in r.output.lower()
```

Run `pytest tests/unit/cli/test_strict_exit_codes.py -q`. Expect import/option failures. Commit red.

### Green — smallest impl shape

1. Add the two `click` options to the `gather` subcommand.
2. Implement the post-gather exit-code mapping per **Implementation outline**.
3. Add the closed-set validation for `--strict-domains` tokens.
4. Iterate to green.

### Refactor — bounded cleanup

- Extract `_compute_strict_exit_code(per_domain, strict, strict_domains) -> int | None` as a pure function for direct unit testing (returns `3` or `None`). Keeps the click handler thin.
- Document the precedence rule inline at the function boundary with a one-line comment.
- Keep the closed-set domain enum literal in `src/codegenie/probes/index_health.py` (re-exported as `INDEX_HEALTH_DOMAINS`) — do not duplicate it in `cli.py`. Import it.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/cli.py` | Edit — add `--strict` + `--strict-domains` options; add post-gather exit-code mapping |
| `src/codegenie/probes/index_health.py` | Edit (minor) — re-export `INDEX_HEALTH_DOMAINS` as a module constant if not already public (S3-01 may have already done this; verify) |
| `tests/unit/cli/test_strict_exit_codes.py` | New — six-case CLI integration tests |
| `tests/unit/probes/test_index_health_strict.py` | New (or extension of S3-01's test file) — per-domain rollup → strict-mode exit-code permutations |

## Out of scope

- **End-to-end seeded-staleness fixtures** that prove `--strict` fires on real `stale_scip_repo/` / `stale_sbom_repo/` / `stale_semgrep_rulepack_repo/` envelopes — Step 8 (S8-04, `tests/integration/test_strict_flag_fails_on_low_confidence.py`).
- **`B2`'s wall-clock bench gate (200 ms p99)** — Step 8 (`tests/bench/test_index_health_budget.py`).
- **The `IndexHealthProbe` itself** — S3-01 owns the probe; this story is CLI-only.
- **Other CLI flags (`--skills-root`, `--no-cache`, etc.)** — Phase 0/1 + other phases; this story is scoped to the two strict flags.
- **JSON-output mode** — Phase 0/1 already may emit YAML; if a future consumer wants `--json` envelope output, that's a separate story.

## Notes for the implementer

- The **envelope-before-exit invariant** is the architectural promise: operators reading `repo-context.yaml` after a CI failure see the full evidence, then check the exit code. If you find yourself short-circuiting the gather flow before envelope-write, **stop** — restructure so the strict-mode mapping runs only after the existing `gather` returns.
- The `--strict-domains` token list is **closed**: `{scip, sbom, cve, semgrep, gitleaks, runtime_trace}`. `runtime_trace` will always be `not_applicable` in Phase 2 (per ADR-0002), but it's a valid token — a CI config that names it will simply never trigger exit-3 in Phase 2 (because `not_applicable` is not `"low"`). Phase 5 may change this behavior; the closed-set is forward-compatible.
- The exit code **3** is a Phase 2 convention. Phase 0/1 may already use 0 (success) and 2 (CLI error). Confirm by reading `src/codegenie/cli.py` before this story — if a Phase 0/1 exit code 3 already exists for a different reason, file a P0 bug (collision) before proceeding. The architectural intent is exit 3 = "strict B2 low".
- The `click` `--strict-domains` option uses a single string (comma-separated) rather than `multiple=True` because CI config files commonly express domain lists as comma-separated strings. The internal representation is `frozenset[str]`. Document the parsing inline.
- Do **not** add a `--strict-overall` flag in this story (e.g., "exit 3 only if `confidence_summary.overall == 'low'`"). Two flags is enough. If a consumer demands the overall-only variant, file a follow-up — `--strict-domains scip,sbom,cve,semgrep,gitleaks` is the workaround.
- The structlog event `strict.exit_3_triggered` is **not** in the eight event-names registered by S1-01. Use a generic `cli.exit_code` event instead, with `exit_code=3` + `strict_mode=true` fields, to avoid bloating the event-name registry. Document the choice inline.
- Cross-link ADR-0011 + ADR-0012 in the `--help` text for both flags — operators reading `codegenie gather --help` should be able to grep for the ADR names. (Keep help text terse; one short sentence referencing each ADR by number is enough.)
- ADR-0012's file name may be `0012-strict-domains-cli-flag.md` or `0012-audit-chain-blake3-rolling-head.md` depending on the phase's ADR README ordering — confirm the correct ADR file before linking. The **content** of `--strict-domains` is from `High-level-impl.md §"Step 3"` + the synth ledger; the ADR-0012 reference in this story's frontmatter should match whatever the actual ADR file is. If `--strict-domains` ended up grouped under ADR-0011 instead, drop the ADR-0012 cross-link and note the consolidation.
