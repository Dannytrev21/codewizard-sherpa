# Story S6-07 — `Gitleaks` scanner + `secret_in_source` adversarial

**Step:** Step 6 — Ship Layer D + E + G probes (skills, conventions, ADRs, ownership, scanners)
**Status:** Ready
**Effort:** M
**Depends on:** S6-06 (three sibling Layer G scanners — `gitleaks` is the *fourth* and final scanner; landing it in its own story makes the no-shared-`ScannerRunner` discipline visible in the PR queue), S3-03 (writer signature tightened to `RedactedSlice`; `SecretRedactor` is the composition pass at the writer chokepoint)
**ADRs honored:** 02-ADR-0001 (`gitleaks` added to `ALLOWED_BINARIES`), **02-ADR-0005** (no plaintext persistence — this story is the load-bearing test of that ADR), **02-ADR-0010** (`RedactedSlice` smart constructor at writer boundary — the test confirms a caller cannot bypass the redactor)
**Phase-2 LOAD-BEARING ADVERSARIAL:** [`README.md` Step 6 table S6-07](README.md) — "gitleaks finds a seeded secret; `SecretRedactor` replaces it in `repo-context.yaml` + every raw artifact + cache blob + audit anchor. Plaintext in **zero** persisted files."

## Context

`GitleaksProbe` is the fourth Layer G scanner, structurally similar to S6-06's three (`run_external_cli` → JSON → `ScannerOutcome`). What makes it warrant its own story is the **`test_secret_in_source.py` adversarial test** — the load-bearing CI gate for the entire phase's security commitment. Phase 2's design ledger states: "secret findings redacted at writer chokepoint; plaintext in zero persisted files (G5)." That commitment is enforced by exactly this test: seed a known secret in a fixture repo, run the full gather, walk every file in the output directory (artifact, raw, cache, audit anchor), and assert the seeded plaintext appears in **zero** of them. Mutation of the test catches any future change that bypasses the redactor.

Two design discipline notes:

1. **The fourth scanner does NOT trigger a shared `ScannerRunner` extraction.** Gitleaks has its own JSON shape (`[{Description, RuleID, File, StartLine, Match, Secret}]`), its own flag set (`--no-banner`, `--report-format=json`, `--report-path=-`), its own error model (exit 1 = leaks found; exit 0 = none; exit ≥ 2 = scan error — same shape as semgrep), and its own runtime considerations (it walks git history if pointed at a `.git`; the probe constrains it to working-tree scan via `--source <repo>` + omitting `--git`). Final-design Design-patterns row 7 holds: four scanners, four shapes.
2. **The redactor is the chokepoint, not the probe.** `GitleaksProbe._run` returns *raw* findings — the writer's `SecretRedactor` composition pass (S3-03) walks the slice and replaces matches before any persistence. The adversarial test verifies this end-to-end: feed a secret in, walk every output file, find no plaintext anywhere. The probe code itself is dumb; the security boundary lives at the writer.

The fixture is `tests/adv/phase02/fixtures/secret_in_source/`: a tiny repo with `src/config.ts` containing `const AWS_KEY = "AKIA1234567890ABCDEF";` (a regex-matchable AWS Access Key ID — high precision, deliberately constructed to match the AWS pattern in `SecretRedactor`). The fixture is committed; the test reads it, runs `codegenie gather`, then grep-walks the output.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md` §"Component design" #4 `SecretRedactor`](../phase-arch-design.md) — pattern set; chokepoint discipline.
  - [`../phase-arch-design.md` §"Gap analysis" Gap 4](../phase-arch-design.md) — the `RedactedSlice` smart-constructor improvement; this story's adversarial test is what makes Gap 4's improvement observable.
  - [`../phase-arch-design.md` §"Gap analysis" Gap 5](../phase-arch-design.md) — no in-memory secret leak (S7-04 ships the boundary test; this story ships the on-disk test).
  - [`../phase-arch-design.md` §"Design patterns applied"](../phase-arch-design.md) row 7 — final scanner; discipline holds across all four.
- **Phase ADRs:**
  - [`../ADRs/0005-secret-findings-no-plaintext-persistence.md`](../ADRs/0005-secret-findings-no-plaintext-persistence.md) — the ADR this story tests.
  - [`../ADRs/0010-redacted-slice-smart-constructor-at-writer-boundary.md`](../ADRs/0010-redacted-slice-smart-constructor-at-writer-boundary.md) — type-level enforcement.
  - [`../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md`](../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md) — `gitleaks` in the allowlist.
- **Source design:**
  - [`../High-level-impl.md` §"Step 6"](../High-level-impl.md) — gitleaks 30s timeout; `--no-banner` for deterministic stdout.
  - [`../../localv2.md` §5.6](../../../localv2.md) — gitleaks is a Layer G scanner.
- **Existing kernel:**
  - `src/codegenie/output/sanitizer.py` (S3-01..03) — `redact_secrets(...) -> tuple[RedactedSlice, list[SecretFinding]]`.
  - `src/codegenie/output/writer.py` (S3-03) — accepts `RedactedSlice`, not raw `dict`.
  - `src/codegenie/probes/_shared/scanner_outcome.py` (S5-01) — `ScannerOutcome` union.
  - `src/codegenie/exec.py` (S1-07) — `run_external_cli`.
  - `src/codegenie/probes/layer_g/semgrep.py` (S6-06) — sibling pattern (also handles exit-code-1-is-findings).

## Goal

1. Ship `src/codegenie/probes/layer_g/gitleaks.py` as the fourth Layer G scanner, ≤ 200 LOC, no shared base with S6-06's three siblings, `@register_probe(heaviness="medium")`, 30 s timeout, `--no-banner` flag.
2. Ship `tests/adv/phase02/test_secret_in_source.py` — the load-bearing adversarial test that seeds an AWS key in a fixture repo, runs the full gather, and asserts the plaintext appears in **zero** persisted files.

## Acceptance criteria

**Numbered for traceability to the TDD plan.**

- [ ] **AC-1.** `src/codegenie/probes/layer_g/gitleaks.py` exports exactly `__all__ = ["GitleaksProbe", "GitleaksFinding", "GitleaksSlice"]`.
- [ ] **AC-2.** Module is **≤ 200 LOC** including Pydantic models, imports, docstring (verified by `tests/unit/probes/layer_g/test_scanner_loc_ceiling.py` from S6-06 — this story extends that parametrize to include gitleaks).
- [ ] **AC-3.** `@register_probe(heaviness="medium")`; `probe_id = ProbeId("gitleaks")`; `applies_to_tasks=("*",)`; `applies_to_languages=("*",)`; `timeout_seconds=30`.
- [ ] **AC-4.** Invokes `run_external_cli("gitleaks", ["detect", "--source", str(ctx.repo_root), "--no-banner", "--report-format=json", "--report-path=-", "--no-git", "--exit-code", "0"], timeout_seconds=30)`. **Flag rationale:** `--no-banner` for deterministic stdout (AC-12 mutation: dropping it would inject ANSI banner into stdout, breaking JSON parse); `--report-path=-` writes JSON to stdout (not a temp file); `--no-git` constrains to working-tree (we don't want history scanning in Phase 2 — that's a Phase 3+ feature); `--exit-code 0` overrides gitleaks' default exit-1-on-findings (we prefer to treat findings via parsed JSON, like semgrep — but unlike semgrep, we *can* override gitleaks' exit code, so we do, for a simpler conditional in `_run`).
- [ ] **AC-5.** `GitleaksFinding` Pydantic `BaseModel(frozen=True, extra="forbid")` with `rule_id: str, file: str, line: int, description: str, match_fingerprint: str`. **`match_fingerprint` is BLAKE3_8 of the matched cleartext**, never the cleartext itself. Mutation caught: any future `match: str` field that ships cleartext through the probe.
- [ ] **AC-6.** `GitleaksSlice` Pydantic `BaseModel(frozen=True, extra="forbid")` with `outcome: ScannerOutcome, findings_count: int`.
- [ ] **AC-7.** **No shared base class with S6-06's scanners.** Architectural test (in S6-06's `test_scanner_loc_ceiling.py`, extended to include gitleaks) — same `ScannerRunner`/`BaseScanner`/`AbstractScanner` forbidden-substring check.
- [ ] **AC-8.** **`test_secret_in_source.py` exists at `tests/adv/phase02/test_secret_in_source.py`** and is part of the `adv-phase02` CI lane (S8-03). It is **NOT** skipped under any condition; if gitleaks is not on PATH, the test **fails** (because the adversarial guarantee requires gitleaks to actually find the seed). The CI image for `adv-phase02` installs gitleaks unconditionally.
- [ ] **AC-9.** **Fixture exists.** `tests/adv/phase02/fixtures/secret_in_source/` contains:
  - `src/config.ts` with the literal text `const AWS_KEY = "AKIA1234567890ABCDEF";` (a regex-matchable AWS Access Key ID).
  - `package.json` (minimal — so Phase 1's Layer A probes engage).
  - `README.md` documenting the seed pattern (so a contributor doesn't "fix" the secret).
  - The seed is **also** mentioned in a non-source file — `docs/internal-notes.md` — to prove the redactor covers non-scanner-found paths too (the field-name + entropy walk in `OutputSanitizer.scrub`).
- [ ] **AC-10.** **End-to-end gather → walk → assert zero plaintext.** The test runs `codegenie gather` on the fixture, then walks every file under `.codegenie/`:
  - `.codegenie/context/repo-context.yaml`
  - `.codegenie/context/raw/*.json`
  - `.codegenie/cache/**/*` (every cache blob)
  - `.codegenie/runs/*.json` (audit anchors)
  - asserts `"AKIA1234567890ABCDEF"` appears in **zero** of them.
- [ ] **AC-11.** **The seed *is* present in the input fixture.** The test asserts `"AKIA1234567890ABCDEF" in (fixture_root / "src" / "config.ts").read_text()` BEFORE the gather — so a future contributor who "fixes" the fixture by removing the secret fails the assertion immediately rather than silently invalidating the test.
- [ ] **AC-12.** **Gitleaks DID find the seed.** The test inspects the slice (via the test's separate read of the `repo-context.yaml`, post-redactor — fingerprints are visible) and asserts at least one `GitleaksFinding` with `rule_id` matching `aws-access-token` (or whatever gitleaks names the AWS-ID rule). Mutation caught: a future config change that disables AWS rules would silently kill the test's coverage.
- [ ] **AC-13.** **Fingerprint reproducibility.** The test computes BLAKE3_8 of `"AKIA1234567890ABCDEF"` independently and asserts that fingerprint appears in the redactor's `<REDACTED:fingerprint=...>` markers in the output files. This proves the redactor saw the exact seed (not a near-match).
- [ ] **AC-14.** **Cache lane is covered.** The test asserts that running `gather` a second time (warm cache) ALSO produces zero plaintext. Mutation caught: any future code path that bypasses the redactor on cache HIT (because "the slice was already redacted last time" — but the cache blob might have been written before redaction in a sloppy implementation).
- [ ] **AC-15.** **Audit anchor lane is covered.** Phase 0's audit anchor writes per-probe `Ran/CacheHit/Skipped` records to `.codegenie/runs/<utc-iso>-<short>.json`. The test verifies the audit anchor also contains zero plaintext. Mutation caught: a future debug-logging change that includes the raw slice in the audit record.
- [ ] **AC-16.** **`SecretFinding` list is NOT persisted.** The test reads every file in `.codegenie/` and asserts no `secret_finding` / `SecretFinding` key appears with cleartext data. The in-memory list returned by `redact_secrets` is for the CLI summary only — its persistence would defeat the chokepoint per Gap 4 / ADR-0010.
- [ ] **AC-17.** **`mypy --strict`** passes on `gitleaks.py`.
- [ ] **AC-18.** **CI gate.** `adv-phase02` job (defined in S8-03) imports this test file's lane; failure is build-fail (not advisory).
- [ ] **AC-19.** **Determinism.** Two gathers on the same fixture produce byte-identical `repo-context.yaml` (modulo `generated_at` timestamp). Fingerprints are deterministic (BLAKE3 is deterministic; the same cleartext → same 8-hex fingerprint).
- [ ] **AC-20.** **`secrets_redacted_count` log field positive.** The CLI's `secrets_redacted_count` log field (added in S3-03) is `>= 1` on the gather. Mutation caught: any redactor short-circuit that returns the slice unchanged would log 0 and the test would fail.

## Implementation outline

1. `src/codegenie/probes/layer_g/gitleaks.py`:
   - Mirror `semgrep.py` shape from S6-06 (separate file, no base class).
   - Pydantic `GitleaksFinding` with `match_fingerprint` (BLAKE3_8 of `Secret` field) — **NOT** the cleartext.
   - `_parse(raw) -> Result[tuple[list[GitleaksFinding], int], ParseError]` — parses gitleaks' JSON array; per finding, computes `match_fingerprint = blake3(finding["Secret"].encode()).hexdigest()[:16]` (8 bytes = 16 hex chars; matches the redactor's fingerprint format).
   - `_run` handles `ToolMissingError` → `ScannerSkipped`; invalid JSON → `ScannerFailed`; happy path → `ScannerRan(findings)`.
2. `tests/adv/phase02/fixtures/secret_in_source/`:
   - `src/config.ts` with `const AWS_KEY = "AKIA1234567890ABCDEF";`.
   - `package.json` (minimal valid Node manifest).
   - `docs/internal-notes.md` with a second instance of the seed (in markdown prose, not code).
   - `README.md` documenting the seed.
3. `tests/adv/phase02/test_secret_in_source.py`:
   - Set up: confirm seed present in fixture (AC-11).
   - Run: `subprocess.run(["codegenie", "gather", str(fixture)], check=True)` (or call the CLI's Python entry point in-process).
   - Walk: enumerate every file under `fixture / ".codegenie"`; for each, assert seed bytes absent (AC-10).
   - Verify: find at least one gitleaks finding for the seed (AC-12); find the expected BLAKE3_8 in redaction markers (AC-13).
   - Cache lane: run again (warm), repeat the walk (AC-14).
   - Audit anchor: explicit walk over `.codegenie/runs/` (AC-15).
   - Negative: assert no `secret_finding` key contains cleartext (AC-16).

## TDD plan — red / green / refactor

### Red — write the failing tests first

```python
# tests/unit/probes/layer_g/test_gitleaks.py
"""Unit tests for GitleaksProbe (S6-07)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from blake3 import blake3

from codegenie.probes.base import ProbeContext, _PROBE_REGISTRY
from codegenie.probes.layer_g import gitleaks as gl
from codegenie.probes._shared.scanner_outcome import ScannerRan, ScannerSkipped, ScannerFailed


_SEED = "AKIA1234567890ABCDEF"
_EXPECTED_FINGERPRINT = blake3(_SEED.encode()).hexdigest()[:16]


def test_gitleaks_argv_includes_no_banner_and_no_git(fp) -> None:
    """AC-4. Mutation caught: dropping `--no-banner` (would inject ANSI
    into stdout) or omitting `--no-git` (would silently scan history)."""
    fp.register(
        ["gitleaks", "detect", "--source", fp.any(), "--no-banner",
         "--report-format=json", "--report-path=-", "--no-git",
         "--exit-code", "0"],
        stdout=json.dumps([]).encode(),
        returncode=0,
    )
    ctx = ProbeContext.for_test(repo_root=Path("/tmp/repo"))
    output = gl.GitleaksProbe()._run(ctx)
    assert output.confidence in ("high", "medium")


def test_gitleaks_finding_carries_fingerprint_not_cleartext(fp) -> None:
    """AC-5. Mutation caught: a future `match: str` field on
    `GitleaksFinding` that shipped cleartext through the probe."""
    fp.register(
        ["gitleaks", "detect", fp.any(), fp.any(), fp.any(), fp.any(),
         fp.any(), fp.any(), fp.any(), fp.any()],
        stdout=json.dumps([{
            "RuleID": "aws-access-token",
            "Description": "AWS Access Token",
            "File": "src/config.ts",
            "StartLine": 1,
            "Secret": _SEED,
        }]).encode(),
        returncode=0,
    )
    output = gl.GitleaksProbe()._run(ProbeContext.for_test(repo_root=Path("/tmp/repo")))
    slice_ = gl.GitleaksSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.outcome, ScannerRan)
    f = slice_.outcome.findings[0]
    assert f.match_fingerprint == _EXPECTED_FINGERPRINT
    # Cleartext must not be in the Pydantic model.
    assert _SEED not in str(f.model_dump())


def test_gitleaks_tool_missing_yields_scanner_skipped(monkeypatch) -> None:
    """AC-4 + S6-06 AC-10. Mutation caught: raising past the probe."""
    from codegenie.exec import ToolMissingError

    def raise_missing(*args, **kwargs):
        raise ToolMissingError("gitleaks")

    monkeypatch.setattr("codegenie.probes.layer_g.gitleaks.run_external_cli", raise_missing)
    output = gl.GitleaksProbe()._run(ProbeContext.for_test(repo_root=Path("/tmp/repo")))
    slice_ = gl.GitleaksSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.outcome, ScannerSkipped)
    assert slice_.outcome.reason == "tool_missing"


def test_gitleaks_invalid_json_yields_scanner_failed(fp) -> None:
    """AC-4. Mutation caught: silent ValidationError swallow."""
    fp.register(
        ["gitleaks", fp.any(), fp.any(), fp.any(), fp.any(), fp.any(),
         fp.any(), fp.any(), fp.any(), fp.any()],
        stdout=b"not json",
        returncode=0,
    )
    output = gl.GitleaksProbe()._run(ProbeContext.for_test(repo_root=Path("/tmp/repo")))
    slice_ = gl.GitleaksSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.outcome, ScannerFailed)


def test_registry_heaviness_and_timeout() -> None:
    """AC-3."""
    assert _PROBE_REGISTRY["gitleaks"].heaviness == "medium"
    assert gl.GitleaksProbe.timeout_seconds == 30
```

```python
# tests/adv/phase02/test_secret_in_source.py
"""LOAD-BEARING adversarial test (S6-07).

Seeds a known AWS key in a fixture repo, runs `codegenie gather`, and
asserts the plaintext appears in ZERO persisted files. This is the
test the writer-chokepoint commitment (G5 / ADR-0005 / ADR-0010) is
verified by.

If this test fails, the phase fails its security commitment. No
"flake retry" — the build is broken.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from blake3 import blake3

SEED = "AKIA1234567890ABCDEF"
EXPECTED_FINGERPRINT = blake3(SEED.encode()).hexdigest()[:16]
FIXTURE = Path(__file__).parent / "fixtures" / "secret_in_source"


@pytest.fixture
def fresh_fixture(tmp_path: Path) -> Path:
    """Copy the committed fixture into tmp_path so the gather writes
    `.codegenie/` artifacts under an isolated location."""
    dst = tmp_path / "repo"
    shutil.copytree(FIXTURE, dst)
    return dst


def _walk_all_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            out.append(Path(dirpath) / fn)
    return out


def test_seed_is_present_in_fixture_input() -> None:
    """AC-11. Mutation caught: a future contributor "fixing" the
    fixture by removing the seed — the test fires immediately, not at
    the misleading "no plaintext found in output" success it would
    otherwise produce."""
    src = (FIXTURE / "src" / "config.ts").read_text()
    assert SEED in src, (
        f"Test fixture must contain the seed {SEED!r}. If you 'fixed' the "
        "fixture, restore the seed — this test depends on it."
    )


def test_gather_produces_zero_plaintext_in_any_persisted_file(fresh_fixture: Path) -> None:
    """AC-10, AC-15, AC-16. The load-bearing assertion."""
    subprocess.run(["codegenie", "gather", str(fresh_fixture)], check=True)

    codegenie_dir = fresh_fixture / ".codegenie"
    assert codegenie_dir.exists(), "gather did not produce .codegenie/"

    plaintext_found_in: list[str] = []
    for path in _walk_all_files(codegenie_dir):
        try:
            content = path.read_bytes()
        except OSError:
            continue
        if SEED.encode() in content:
            plaintext_found_in.append(str(path.relative_to(fresh_fixture)))

    assert not plaintext_found_in, (
        f"Plaintext seed appeared in {len(plaintext_found_in)} persisted files: "
        f"{plaintext_found_in}. The redactor at the writer chokepoint failed; "
        f"ADR-0005 / ADR-0010 violated."
    )


def test_gather_redacted_marker_carries_expected_fingerprint(fresh_fixture: Path) -> None:
    """AC-13. Mutation caught: the redactor saw a *different* secret
    (regex matched something adjacent) — the fingerprint would diverge."""
    subprocess.run(["codegenie", "gather", str(fresh_fixture)], check=True)
    artifact = (fresh_fixture / ".codegenie" / "context" / "repo-context.yaml").read_text()
    expected_marker = f"<REDACTED:fingerprint={EXPECTED_FINGERPRINT}>"
    assert expected_marker in artifact, (
        f"Expected redaction marker {expected_marker!r} not found. The redactor "
        "either missed the seed or matched a different cleartext."
    )


def test_gitleaks_actually_found_the_seed(fresh_fixture: Path) -> None:
    """AC-12. Mutation caught: a future config change disabling AWS
    rules in gitleaks — the test would still pass on AC-10 (the seed
    is also redacted by the field-name + entropy walk), but the
    gitleaks finding would vanish, weakening coverage. This test pins
    that gitleaks itself contributed to the redaction."""
    subprocess.run(["codegenie", "gather", str(fresh_fixture)], check=True)
    raw_dir = fresh_fixture / ".codegenie" / "context" / "raw"
    gitleaks_blobs = list(raw_dir.glob("gitleaks*.json"))
    assert gitleaks_blobs, "No gitleaks raw artifact found"
    findings = json.loads(gitleaks_blobs[0].read_text()).get("findings", [])
    aws_findings = [f for f in findings if "aws" in f.get("rule_id", "").lower()]
    assert aws_findings, "Gitleaks did not flag the seed as an AWS token"


def test_warm_cache_lane_still_zero_plaintext(fresh_fixture: Path) -> None:
    """AC-14. Mutation caught: a cache-hit path that writes the cache
    blob BEFORE the redactor runs (so subsequent warm gathers serve
    pre-redactor bytes from cache)."""
    subprocess.run(["codegenie", "gather", str(fresh_fixture)], check=True)
    # Second gather — warm cache.
    subprocess.run(["codegenie", "gather", str(fresh_fixture)], check=True)
    plaintext_found_in: list[str] = []
    for path in _walk_all_files(fresh_fixture / ".codegenie"):
        try:
            content = path.read_bytes()
        except OSError:
            continue
        if SEED.encode() in content:
            plaintext_found_in.append(str(path.relative_to(fresh_fixture)))
    assert not plaintext_found_in, (
        f"Warm-cache gather leaked plaintext in: {plaintext_found_in}"
    )


def test_audit_anchor_contains_no_plaintext(fresh_fixture: Path) -> None:
    """AC-15. Mutation caught: any debug-logging change that includes
    raw slice content in the audit record."""
    subprocess.run(["codegenie", "gather", str(fresh_fixture)], check=True)
    runs_dir = fresh_fixture / ".codegenie" / "runs"
    assert runs_dir.exists(), "Audit anchor directory missing"
    for anchor in runs_dir.glob("*.json"):
        text = anchor.read_text()
        assert SEED not in text, f"Audit anchor {anchor.name} contains plaintext"


def test_secrets_redacted_count_log_field_positive(fresh_fixture: Path) -> None:
    """AC-20. Mutation caught: any redactor short-circuit that returns
    the slice unchanged would log 0."""
    result = subprocess.run(
        ["codegenie", "gather", str(fresh_fixture), "--log-format=json"],
        check=True, capture_output=True, text=True,
    )
    log_lines = [json.loads(ln) for ln in result.stderr.splitlines() if ln.startswith("{")]
    writer_lines = [ln for ln in log_lines if "secrets_redacted_count" in ln]
    assert writer_lines, "No log line with `secrets_redacted_count` field"
    assert any(ln["secrets_redacted_count"] >= 1 for ln in writer_lines)


def test_secret_finding_key_not_persisted(fresh_fixture: Path) -> None:
    """AC-16. Mutation caught: a future contributor persisting the
    in-memory `SecretFinding` list to disk for "debugging" — would
    re-introduce cleartext via the structured shape."""
    subprocess.run(["codegenie", "gather", str(fresh_fixture)], check=True)
    for path in _walk_all_files(fresh_fixture / ".codegenie"):
        try:
            content = path.read_text(errors="ignore")
        except OSError:
            continue
        # SecretFinding's "cleartext" field is the discriminator — if
        # it appears, persistence has occurred.
        assert "cleartext" not in content, (
            f"SecretFinding cleartext field appears in {path}"
        )
```

### Green — make it pass

Skeleton for `gitleaks.py`:

```python
# src/codegenie/probes/layer_g/gitleaks.py
"""GitleaksProbe — Layer G, medium heaviness.

Fourth Layer G scanner. NO shared base class with semgrep/ast_grep/
ripgrep_curated per final-design Design-patterns row 7 (SRP + Rule of
Three). The probe ships findings as `match_fingerprint` (BLAKE3_8 of
the matched cleartext) — never the cleartext itself. The redactor at
the writer chokepoint (S3-03) handles non-gitleaks-found patterns
(field-name regex + entropy walk).

Sources:
- ../phase-arch-design.md §"Component design" #5 + Gap 4 (RedactedSlice).
- ../ADRs/0005-secret-findings-no-plaintext-persistence.md.
- ../ADRs/0010-redacted-slice-smart-constructor-at-writer-boundary.md.
"""
from __future__ import annotations

import json
from pathlib import Path

from blake3 import blake3
from pydantic import BaseModel, ConfigDict, ValidationError

from codegenie.exec import ProcessResult, ToolMissingError, run_external_cli
from codegenie.ids import ProbeId
from codegenie.probes._shared.scanner_outcome import (
    ScannerFailed,
    ScannerOutcome,
    ScannerRan,
    ScannerSkipped,
)
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, register_probe

__all__ = ["GitleaksProbe", "GitleaksFinding", "GitleaksSlice"]


class GitleaksFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    rule_id: str
    file: str
    line: int
    description: str
    match_fingerprint: str  # BLAKE3_8 (16 hex) — NEVER cleartext


class GitleaksSlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    outcome: ScannerOutcome
    findings_count: int


def _parse(raw: bytes) -> tuple[tuple[GitleaksFinding, ...], int] | str:
    try:
        data = json.loads(raw) if raw else []
    except json.JSONDecodeError as e:
        return f"invalid_json: {str(e)[:200]}"
    if not isinstance(data, list):
        return "invalid_json: top-level not a list"
    try:
        findings = tuple(
            GitleaksFinding(
                rule_id=f["RuleID"],
                file=f["File"],
                line=f["StartLine"],
                description=f.get("Description", ""),
                match_fingerprint=blake3(f["Secret"].encode()).hexdigest()[:16],
            )
            for f in data
        )
    except (KeyError, TypeError, ValidationError) as e:
        return f"invalid_json: {str(e)[:200]}"
    return findings, len(findings)


@register_probe(heaviness="medium")
class GitleaksProbe(Probe):
    probe_id = ProbeId("gitleaks")
    applies_to_tasks: tuple[str, ...] = ("*",)
    applies_to_languages: tuple[str, ...] = ("*",)
    timeout_seconds = 30

    def _run(self, ctx: ProbeContext) -> ProbeOutput:
        try:
            result: ProcessResult = run_external_cli(
                "gitleaks",
                ["detect", "--source", str(ctx.repo_root), "--no-banner",
                 "--report-format=json", "--report-path=-", "--no-git",
                 "--exit-code", "0"],
                timeout_seconds=self.timeout_seconds,
            )
        except ToolMissingError:
            return self._wrap(ScannerSkipped(reason="tool_missing"), 0, "low")
        if result.exit_code != 0:
            return self._wrap(
                ScannerFailed(exit_code=result.exit_code, stderr_tail=result.stderr_tail),
                0, "low",
            )
        parsed = _parse(result.stdout)
        if isinstance(parsed, str):
            return self._wrap(
                ScannerFailed(exit_code=0, stderr_tail=parsed), 0, "low",
            )
        findings, count = parsed
        return self._wrap(ScannerRan(findings=list(findings)), count, "high")

    def _wrap(self, outcome: ScannerOutcome, count: int, confidence: str) -> ProbeOutput:
        slice_ = GitleaksSlice(outcome=outcome, findings_count=count)
        return ProbeOutput(
            probe_id=self.probe_id, confidence=confidence,
            schema_slice=slice_.model_dump(mode="json"), errors=[],
        )
```

### Refactor

- The temptation here is high: at four scanners, the duplicate `try: run_external_cli except ToolMissingError` block is the fourth copy of the same code. **Do not extract.** Each scanner's error model and argv contract differ; the inline shape keeps the code readable as a single sitting. Final-design Design-patterns row 7 holds.
- The `_parse` helper is local to each scanner. Different stdout shapes; no kernel.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/layer_g/gitleaks.py` | New file ≤ 200 LOC — fourth scanner, no shared base. |
| `tests/unit/probes/layer_g/test_gitleaks.py` | New file — 5 unit tests. |
| `tests/unit/probes/layer_g/test_scanner_loc_ceiling.py` | Extended — add gitleaks to the SCANNER_MODULES parametrize. |
| `tests/adv/phase02/test_secret_in_source.py` | New file — load-bearing adversarial; 8 tests. |
| `tests/adv/phase02/fixtures/secret_in_source/src/config.ts` | New fixture file. |
| `tests/adv/phase02/fixtures/secret_in_source/package.json` | New fixture file (minimal Node manifest). |
| `tests/adv/phase02/fixtures/secret_in_source/docs/internal-notes.md` | New fixture file (second seed instance, prose form). |
| `tests/adv/phase02/fixtures/secret_in_source/README.md` | New fixture file (documents the seed; future contributors don't "fix" it). |

## Out of scope

- **`test_no_inmemory_secret_leak.py`** — S7-04 (the *boundary* check via `inspect`; this story is the *on-disk* check). The two together close Gap 4 + Gap 5.
- **Gitleaks rule-pack version recording.** That's S6-08 (`@register_index_freshness_check` for `gitleaks`).
- **Gitleaks git-history scanning.** Phase 2 uses `--no-git` (working tree only); history scanning is Phase 3+ if it lands at all.
- **Cross-scanner secret correlation.** Gitleaks finds X; semgrep's `p/secrets` may find Y. Phase 2 keeps them separate; the Planner correlates.

## Notes for the implementer

1. **The fingerprint is the contract.** `match_fingerprint = blake3(cleartext).hexdigest()[:16]` is computed in the probe and used by the writer's redactor to confirm "the regex saw the same cleartext gitleaks saw." If the formats diverge (e.g., the probe uses BLAKE3_8 = 16 hex chars; the redactor uses BLAKE3 = 64 hex chars), the marker won't match and AC-13 fails immediately.
2. **`--no-git` is non-negotiable in Phase 2.** History scanning requires a different threat model (the secret may have been committed and removed; do we redact past commits in audit anchors?) — a Phase-3+ design discussion. Phase 2 scans working tree only.
3. **The fixture's second seed instance** (in `docs/internal-notes.md`) is what proves the redactor's *non*-gitleaks coverage. Gitleaks scans source files; the markdown note is found by the field-name regex + entropy walk in `OutputSanitizer.scrub`. If only the gitleaks-found instance were redacted and the markdown one persisted, AC-10 would fail.
4. **`--exit-code 0` overrides gitleaks' default.** Without it, gitleaks exits with code 1 on findings (like semgrep). With `--exit-code 0` set, we get exit 0 on findings + exit ≥ 2 on actual error — a simpler conditional in `_run`. We can't do this trick for semgrep (no equivalent flag), which is why the semgrep code has the exit-1-is-findings carve-out and gitleaks does not.
5. **Subprocess shells out to the CLI in the adversarial test.** It does NOT call `codegenie.gather()` in-process. The reason: the test is verifying the *persisted-file* boundary, and any in-process call could accidentally hold the slice in memory in a way that escapes the typed `RedactedSlice` chokepoint. The subprocess-spawn forces the gather through the same surface a real user invokes.
6. **`subprocess.run(..., check=True)` is OK here.** Inside source code, the discipline is "no `subprocess.run` for external tools" (S6-06 AC-16 forbids it in the probes). Inside the adversarial test, we are *invoking the CLI itself* — that's appropriate; the `codegenie` binary is the SUT, not an external tool.
7. **AC-19 determinism is testable by extending the adversarial.** Two consecutive gathers; modulo `generated_at`, the redacted artifact bytes are equal. The 16-hex fingerprint is deterministic (BLAKE3 is deterministic).
8. **The fixture's `README.md` is documentation as code.** A contributor who runs `git grep AKIA` on the repo will find the fixture's README explaining "this is a deliberate seed; do not fix." That's the discoverability the Phase 2 commitment relies on.
9. **`adv-phase02` is build-fail, not advisory.** S8-03 lands the CI job; this story's tests are the load-bearing portion of that lane. If this test flakes, fix the root cause; do **not** add a retry decorator.
10. **The 100 % grep walk is the right shape.** A "smart" version that knows which file types might contain plaintext is fragile — a future probe ships a binary blob (e.g., SCIP index), and the smart walker skips it, and the seed leaks through. `os.walk` + `read_bytes` + `in` is the dumbest, most-mutation-resistant check.
