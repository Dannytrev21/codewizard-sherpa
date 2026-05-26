"""Phase-4 S7-09 partial — plan-path-escape adversarial.

ADR-04-0001 §UnifiedDiff + ``_validate_sandboxed_relative_path``: a leaf
returning a :class:`PlanProposalDepBump` (or any variant carrying
``manifest_path``) with an escape pattern (``../``, absolute, NUL,
backslash) is rejected by the Pydantic smart-constructor **before** the
engine dispatches the transform. The behavior already lives at S1-02;
this test pins it under the ``adv`` marker so an adversarial-sweep run
verifies the chain end-to-end.

Coverage table (each row is one parametrized assertion):

* ``../../etc/passwd`` — classical parent-traversal.
* ``/etc/passwd`` — absolute path.
* ``package.json/../../secret`` — mid-path escape (validator must reject).
* ``a\\b.json`` — backslash separator smuggle.
* ``a\x00b.json`` — NUL byte truncation smuggle.
* ``""`` — empty string.

S7-09 corpus growth: this file is the SHAPE for plan-path-escape
adversarial coverage. Additional rows (Unicode homoglyph, URL-encoded
escapes if the SDK ever decodes them) land as additional parametrize
entries — no new test files needed.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from codegenie.fallback.plan_proposal import PlanProposalDepBump

pytestmark = pytest.mark.adv


@pytest.mark.parametrize(
    "evil_path",
    [
        pytest.param("../../etc/passwd", id="parent-traversal"),
        pytest.param("/etc/passwd", id="absolute-path"),
        pytest.param("package.json/../../secret", id="mid-path-escape"),
        pytest.param("a\\b.json", id="backslash-separator-smuggle"),
        pytest.param("a\x00b.json", id="nul-byte-truncation-smuggle"),
        pytest.param("", id="empty-string"),
    ],
)
def test_dep_bump_rejects_path_escape_via_smart_constructor(evil_path: str) -> None:
    """Each evil ``manifest_path`` value raises :class:`ValidationError` at
    model-validate time; no path escape ever reaches the engine.

    The PlanProposalDepBump constructor is the choke point — any LLM-
    produced JSON that survives to ``model_validate`` and proposes a
    transform must have a `manifest_path` that passes the smart
    constructor. A regression that softened the validator would surface
    here as a ValidationError that no longer fires.
    """
    with pytest.raises(ValidationError):
        PlanProposalDepBump.model_validate(
            {
                "kind": "dep_bump",
                "manifest_path": evil_path,
                "package": "vulnpkg",
                "target_version": "2.0.0",
                "rationale": "fix vuln",
            }
        )


def test_valid_relative_path_is_accepted() -> None:
    """Sanity — the smart constructor doesn't reject every input. A
    benign repo-relative path under the project root is accepted.
    Without this test, a pathological validator that "rejects everything"
    would pass the adversarial-rejection assertions trivially.
    """
    proposal = PlanProposalDepBump.model_validate(
        {
            "kind": "dep_bump",
            "manifest_path": "package.json",
            "package": "vulnpkg",
            "target_version": "2.0.0",
            "rationale": "fix vuln",
        }
    )
    assert proposal.manifest_path == "package.json"
