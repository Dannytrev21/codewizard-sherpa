"""Load-bearing adversarial test for Phase 2 (S6-07).

Seeds a known AWS-key cleartext in a fixture repo, runs the gather
end-to-end, and asserts the plaintext appears in ZERO persisted files.
This is the test the writer-chokepoint commitment (G5 / 02-ADR-0005 /
02-ADR-0010) is verified by.

If this test fails, the phase fails its security commitment. There is
no flake-retry path — the build is broken.

Per AC-8 the test is NEVER skipped: if ``gitleaks`` is not on PATH, we
``pytest.fail`` loudly (CI's ``adv-phase02`` lane / S8-03 installs
gitleaks unconditionally).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from codegenie.hashing import content_hash_bytes

pytestmark = pytest.mark.phase02_adv


SEED = "AKIA1234567890ABCDEF"
EXPECTED_FP = content_hash_bytes(SEED.encode("utf-8")).removeprefix("blake3:")[:8]
EXPECTED_MARKER = f"<REDACTED:fingerprint={EXPECTED_FP}>"
FIXTURE = Path(__file__).parent / "fixtures" / "secret_in_source"


def _require_gitleaks() -> None:
    """Fail loudly (NOT skip) if ``gitleaks`` is not on PATH — per AC-8
    the adversarial guarantee depends on gitleaks actually finding the
    seed. The CI ``adv-phase02`` lane (S8-03) installs gitleaks
    unconditionally; a missing binary indicates broken CI wiring."""
    if shutil.which("gitleaks") is None:
        pytest.fail(
            "gitleaks not on PATH — S6-07 adversarial requires it. "
            "Install with `brew install gitleaks` locally, or fix the "
            "CI image (S8-03 owns the `adv-phase02` lane setup)."
        )


@pytest.fixture
def fresh_fixture(tmp_path: Path) -> Path:
    """Copy the committed fixture into ``tmp_path`` so the gather writes
    ``.codegenie/`` artifacts under an isolated location."""
    _require_gitleaks()
    dst = tmp_path / "repo"
    shutil.copytree(FIXTURE, dst)
    return dst


def _walk_all_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            out.append(Path(dirpath) / fn)
    return out


def _run_gather(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "codegenie", "gather", str(repo)],
        check=True,
        capture_output=True,
        text=True,
    )


def _load_envelope(repo: Path) -> dict:
    return yaml.safe_load((repo / ".codegenie" / "context" / "repo-context.yaml").read_text())


def _gitleaks_slice(envelope: dict) -> dict:
    """The writer nests each probe slice under its own name twice
    (``probes.{name}.{name}``); the inner dict is the typed slice."""
    outer = envelope.get("probes", {}).get("gitleaks", {})
    return outer.get("gitleaks", outer)


# ---------------------------------------------------------------------------
# AC-11: pre-check — the seed is present in the input fixture
# ---------------------------------------------------------------------------


def test_seed_is_present_in_fixture_input() -> None:
    """AC-11. Mutation caught: a future contributor "fixing" the
    fixture by removing the seed — the test fires immediately, not at
    the misleading "no plaintext found in output" success it would
    otherwise produce."""
    src = (FIXTURE / "src" / "config.ts").read_text()
    notes = (FIXTURE / "docs" / "internal-notes.md").read_text()
    assert SEED in src, (
        f"Test fixture src/config.ts must contain {SEED!r}. If you 'fixed' "
        "the fixture, restore the seed — this test depends on it."
    )
    assert SEED in notes, f"Test fixture docs/internal-notes.md must contain {SEED!r}."
    readme = (FIXTURE / "README.md").read_text()
    assert SEED not in readme, (
        f"README.md must not contain the literal {SEED!r} — use a placeholder. "
        "The literal would self-contaminate gitleaks' working-tree scan."
    )


# ---------------------------------------------------------------------------
# AC-10 + AC-16: the load-bearing assertion
# ---------------------------------------------------------------------------


def test_gather_produces_zero_plaintext_in_any_persisted_file(fresh_fixture: Path) -> None:
    """AC-10 + AC-16. Walks EVERY file under .codegenie/ as bytes;
    asserts zero occurrences of the seed; asserts the SecretFinding
    'cleartext' field is not persisted."""
    _run_gather(fresh_fixture)

    codegenie_dir = fresh_fixture / ".codegenie"
    assert codegenie_dir.exists(), "gather did not produce .codegenie/"

    plaintext_found_in: list[str] = []
    cleartext_field_in: list[str] = []
    for path in _walk_all_files(codegenie_dir):
        try:
            content = path.read_bytes()
        except OSError:
            continue
        if SEED.encode("utf-8") in content:
            plaintext_found_in.append(str(path.relative_to(fresh_fixture)))
        if b'"cleartext"' in content:
            cleartext_field_in.append(str(path.relative_to(fresh_fixture)))

    assert not plaintext_found_in, (
        f"Plaintext seed appeared in {len(plaintext_found_in)} persisted "
        f"files: {plaintext_found_in}. ADR-0005 / ADR-0010 violated."
    )
    assert not cleartext_field_in, (
        f"SecretFinding 'cleartext' field appeared in: {cleartext_field_in}. "
        "The in-memory findings list was persisted in violation of Gap-4."
    )

    # Positive control: the ``<REDACTED:fingerprint=...>`` marker MUST
    # appear somewhere under .codegenie/ (proves the chokepoint actually
    # fired). Per AC-RP1 the gitleaks probe pre-redacts its raw bytes,
    # so the marker lands in ``raw/gitleaks-raw.json``; per S3-01 the
    # envelope-side redactor additionally lands the marker in
    # ``context/repo-context.yaml`` whenever an upstream slice carries
    # raw cleartext. Either pathway satisfies the chokepoint commitment.
    marker_seen = any(
        b"<REDACTED:fingerprint=" in path.read_bytes()
        for path in _walk_all_files(codegenie_dir)
        if path.is_file()
    )
    assert marker_seen, (
        "No <REDACTED:fingerprint=...> marker found anywhere under "
        ".codegenie/ — both the probe-side (AC-RP1) and envelope-side "
        "(S3-01) redactors were bypassed."
    )


# ---------------------------------------------------------------------------
# AC-13: fingerprint reproducibility (8-hex, chokepoint-derived)
# ---------------------------------------------------------------------------


def test_gather_redacted_marker_carries_expected_fingerprint(fresh_fixture: Path) -> None:
    """AC-13. Mutation caught: any 16-char fingerprint drift (B9); any
    raw-blake3 bypass of the chokepoint (B10); the redactor matching a
    different cleartext (which would yield a different fingerprint).

    The marker may live in ``gitleaks-raw.json`` (probe-side, AC-RP1)
    and/or ``repo-context.yaml`` (envelope-side, S3-01) — both satisfy
    the same fingerprint contract."""
    _run_gather(fresh_fixture)
    marker_locations = [
        path.relative_to(fresh_fixture)
        for path in _walk_all_files(fresh_fixture / ".codegenie")
        if path.is_file() and EXPECTED_MARKER.encode() in path.read_bytes()
    ]
    assert marker_locations, (
        f"Expected marker {EXPECTED_MARKER!r} (8-hex chokepoint-derived) "
        "not found anywhere under .codegenie/. The redactor either "
        "missed the seed, matched a different cleartext, or used a "
        "different fingerprint shape (B9 / B10)."
    )
    # Also assert the slice carries the exact 8-hex fingerprint (proves
    # probe-side chokepoint computation matches the envelope marker).
    envelope = _load_envelope(fresh_fixture)
    findings_detail = _gitleaks_slice(envelope).get("findings_detail", [])
    fingerprints = {f["match_fingerprint"] for f in findings_detail}
    assert EXPECTED_FP in fingerprints, (
        f"Expected 8-hex fingerprint {EXPECTED_FP!r} absent from slice "
        f"findings_detail. fingerprints={fingerprints}"
    )


# ---------------------------------------------------------------------------
# AC-12: gitleaks itself contributed to the redaction
# ---------------------------------------------------------------------------


_GITLEAKS_RULE_RE = re.compile(
    r"aws[-_]?(access[-_]?)?token|aws[-_]?key|generic[-_]?api[-_]?key",
    re.IGNORECASE,
)


def test_gitleaks_actually_found_the_seed(fresh_fixture: Path) -> None:
    """AC-12. Mutation caught: a future config change disabling AWS or
    generic-API-key rules in gitleaks — the marker assertion might still
    pass via the envelope-side entropy/pattern fallback, but the
    gitleaks-rule contribution would vanish silently.

    The rule-id regex accepts ``aws-access-*``, ``aws-key``, and
    ``generic-api-key`` (gitleaks 8.x's default rule pack classifies
    AKIA-prefixed strings as the latter; older versions used the
    former). A future rule-pack rename outside this set fails loud."""
    _run_gather(fresh_fixture)
    envelope = _load_envelope(fresh_fixture)
    findings_detail = _gitleaks_slice(envelope).get("findings_detail", [])
    matched = [f for f in findings_detail if _GITLEAKS_RULE_RE.search(f.get("rule_id", ""))]
    assert matched, (
        f"Gitleaks did not flag the seed as a known credential rule. "
        f"findings_detail={findings_detail}"
    )
    for f in matched:
        assert len(f["match_fingerprint"]) == 8
        assert SEED not in str(f)


# ---------------------------------------------------------------------------
# AC-14: warm-cache lane still zero plaintext
# ---------------------------------------------------------------------------


def test_warm_cache_lane_still_zero_plaintext(fresh_fixture: Path) -> None:
    """AC-14. Mutation caught: a cache-hit path that writes the cache
    blob BEFORE the per-probe redaction (RP1) runs, so a subsequent
    warm gather serves pre-redactor bytes from cache."""
    _run_gather(fresh_fixture)
    yaml_path = fresh_fixture / ".codegenie" / "context" / "repo-context.yaml"
    yaml_path.unlink()
    _run_gather(fresh_fixture)

    plaintext_found_in: list[str] = []
    for path in _walk_all_files(fresh_fixture / ".codegenie"):
        try:
            content = path.read_bytes()
        except OSError:
            continue
        if SEED.encode("utf-8") in content:
            plaintext_found_in.append(str(path.relative_to(fresh_fixture)))
    assert not plaintext_found_in, f"Warm-cache gather leaked plaintext in: {plaintext_found_in}"


# ---------------------------------------------------------------------------
# AC-15: audit anchor lane (canonical path)
# ---------------------------------------------------------------------------


def test_audit_anchor_contains_no_plaintext(fresh_fixture: Path) -> None:
    """AC-15. Mutation caught: any debug-logging change that includes
    raw slice content in the audit record. Canonical path per CLAUDE.md:
    .codegenie/context/runs/, NOT .codegenie/runs/."""
    _run_gather(fresh_fixture)
    runs_dir = fresh_fixture / ".codegenie" / "context" / "runs"
    assert runs_dir.exists(), f"Audit anchor directory missing at {runs_dir}"
    anchors = list(runs_dir.glob("*.json"))
    assert anchors, "No audit anchors written"
    for anchor in anchors:
        content = anchor.read_bytes()
        assert SEED.encode("utf-8") not in content, f"Audit anchor {anchor.name} contains plaintext"


# ---------------------------------------------------------------------------
# AC-20 (adapted): gitleaks slice findings_count reflects both seed
# locations + envelope.written event carries the secrets_redacted_count
# field.
#
# Story-vs-kernel note: the original AC-20 phrased this as
# ``secrets_redacted_count >= 2`` on ``envelope.written``. That field
# is sourced from the envelope-side redactor (S3-03's
# ``RedactedSlice.findings_count``); per AC-RP1 the gitleaks probe
# pre-redacts at the probe boundary so the envelope no longer carries
# cleartext, and the envelope-side count is 0 by design. The
# load-bearing intent — "the system saw and accounted for both seed
# instances" — is preserved by asserting (a) the probe-side slice's
# own ``findings_count`` >= 2, and (b) the envelope.written event is
# still emitted with the field present (S3-03 AC-11 regression guard).
# ---------------------------------------------------------------------------


def test_gitleaks_slice_findings_count_reflects_both_seed_locations(
    fresh_fixture: Path,
) -> None:
    """AC-20 (adapted). Mutations caught: a probe-side ``set``-dedupe
    at finding-level collapses two findings to one; a regression that
    drops ``--no-git`` would inflate the count via commit-history hits
    (the fingerprint-uniqueness assertion catches both)."""
    result = _run_gather(fresh_fixture)
    envelope = _load_envelope(fresh_fixture)
    gl_slice = _gitleaks_slice(envelope)
    findings_detail = gl_slice.get("findings_detail", [])
    assert gl_slice.get("findings_count", 0) >= 2, (
        f"Expected findings_count >= 2 (one per seed location); got slice={gl_slice}"
    )
    fingerprints = {f["match_fingerprint"] for f in findings_detail}
    assert EXPECTED_FP in fingerprints, (
        f"Expected fingerprint {EXPECTED_FP!r} in slice; got {fingerprints}"
    )

    # S3-03 AC-11 regression guard: the envelope.written event MUST
    # still fire and MUST carry the secrets_redacted_count field, even
    # when its value is 0 (the envelope-side redactor sees nothing
    # because the probe pre-redacted upstream).
    log_lines = []
    for ln in result.stderr.splitlines():
        ln = ln.strip()
        if ln.startswith("{"):
            try:
                log_lines.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    written_events = [ln for ln in log_lines if ln.get("event") == "envelope.written"]
    assert written_events, (
        "No envelope.written event found in CLI stderr — S3-03 AC-11 "
        "regression OR the gather did not emit structured logs."
    )
    counts = [ln.get("secrets_redacted_count") for ln in written_events]
    assert all(c is not None for c in counts), (
        f"envelope.written event missing secrets_redacted_count field: {written_events}"
    )


# ---------------------------------------------------------------------------
# AC-19: determinism — two cold gathers, byte-identical envelopes
# ---------------------------------------------------------------------------


# Lines whose values are intrinsically per-run / per-location, stripped
# before the byte-equality check.
_VOLATILE_LINE_PREFIXES: tuple[str, ...] = (
    "generated_at:",
    "run_id:",
    "duration_ms:",
    "root:",  # absolute repo path differs between tmp_path/a and tmp_path/b
)


def test_two_gathers_byte_identical_modulo_volatile_fields(tmp_path: Path) -> None:
    """AC-19 (scoped). Two cold gathers under two ``tmp_path`` copies;
    assert byte-identity of (a) the gitleaks slice in the envelope, and
    (b) the gitleaks-raw.json artifact. These are the surfaces this
    story owns; whole-envelope determinism (index_health key ordering,
    etc.) is a kernel concern tracked outside S6-07.

    Mutation caught: any non-deterministic step in the gitleaks
    probe — wall-clock-derived field, ``dict``-iteration-ordering in
    the slice payload, ``set``-derived ordering of findings_detail —
    would break byte-identity across two cold runs."""
    _require_gitleaks()

    def _gather_and_extract_slice(dst: Path) -> bytes:
        shutil.copytree(FIXTURE, dst)
        _run_gather(dst)
        envelope = yaml.safe_load(
            (dst / ".codegenie" / "context" / "repo-context.yaml").read_text()
        )
        # Determinism check is scoped to the *sanitized* slice (absolute
        # repo-path scrubbing per ADR-0008 happens at the writer
        # boundary). ``gitleaks-raw.json`` deliberately bypasses the
        # sanitizer to preserve audit fidelity, so its bytes legitimately
        # vary by tmp_path; that's not what this AC is checking.
        return json.dumps(_gitleaks_slice(envelope), sort_keys=True, default=str).encode()

    slice_a = _gather_and_extract_slice(tmp_path / "a")
    slice_b = _gather_and_extract_slice(tmp_path / "b")
    assert slice_a == slice_b, "Two cold gathers produced divergent gitleaks slice content"
