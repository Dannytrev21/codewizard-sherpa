"""S7-05 AC-9 — plaintext never escapes through ``Finding.metadata``.

The hardened invariant: a ``Finding`` whose ``metadata`` carries a
plaintext secret-shaped value, threaded through ``redact_secrets`` at the
scanner-outcome boundary, must produce a ``RedactedSlice.slice`` JSON
that contains **zero** substring matches against the plaintext. This is
the cross-check that 02-ADR-0005 (no-plaintext-persistence) + 02-ADR-0010
(smart-constructor) hold at the seam where scanner findings meet the
sanitizer.

The property tests in ``tests/property/test_sum_types_roundtrip.py``
exercise round-trip identity over the typed surface; this unit test
exercises the redaction defense on a representative shape.
"""

from __future__ import annotations

from codegenie.output.sanitizer import redact_secrets
from codegenie.probes._shared.scanner_outcome import Finding, ScannerRan
from codegenie.types.identifiers import ProbeId

# A literal github-token-shaped secret. The sanitizer's ``github_token``
# pattern (``ghp_[A-Za-z0-9]{36}``) will catch this on the redaction pass.
_PLAINTEXT_SECRET = "ghp_" + "a" * 36


def test_finding_metadata_plaintext_is_redacted_at_the_seam() -> None:
    """Plaintext secret in a ``Finding.metadata`` value never reaches the
    redacted slice. ``RedactedSlice.slice`` (post-``redact_secrets``) must
    contain zero substring matches against the cleartext.
    """
    # Build a ScannerRan with a plaintext-secret-bearing finding,
    # serialize it to a JSON-shaped dict (the canonical slice payload),
    # then thread it through ``redact_secrets`` exactly the way the
    # scanner-outcome writer chokepoint does.
    scanner_outcome = ScannerRan(
        findings=[
            Finding(
                id="probe.test_finding_redaction",
                severity="high",
                metadata={"raw": _PLAINTEXT_SECRET},
            )
        ]
    )
    slice_payload = {"outcome": scanner_outcome.model_dump(mode="json")}

    redacted, secret_findings = redact_secrets(
        slice_payload, probe_name=ProbeId("test.finding_redaction")
    )

    # AC-9 cross-check: the rendered JSON has no plaintext substring match.
    redacted_json = redacted.model_dump_json()
    assert _PLAINTEXT_SECRET not in redacted_json, (
        "plaintext secret leaked through Finding.metadata into RedactedSlice"
    )

    # Sanity: the audit trail noticed the cleartext (this is the
    # in-memory list — never persisted per 02-ADR-0005).
    assert len(secret_findings) >= 1, (
        f"expected at least one secret detection; got {secret_findings!r}"
    )
    assert redacted.findings_count >= 1
    assert redacted.fingerprints, "RedactedSlice must carry a fingerprint per cleartext"
