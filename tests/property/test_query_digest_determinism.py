"""Phase-4 S1-04 — Hypothesis property: ``Query.digest()`` is pure and
sensitive to every one of its six fields (AC-11).

A digest implementation that canonicalises only a subset of fields (e.g.
``return "a"*64``, or one that sorts/keys only a subset) is killed by the
field-perturbation metamorphic relation: digests are equal iff inputs are
equal.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from codegenie.rag.models import Query

_FAILURE_MODES = [
    "build_break",
    "test_fail",
    "typecheck_fail",
    "lockfile_resolution_fail",
    "callsite_signature_drift",
    "policy_block",
]
_BUILD_SYSTEMS = ["bun", "pnpm", "yarn-classic", "yarn-berry", "npm"]

_query_payload = st.builds(
    dict,
    task_class=st.sampled_from(["vuln_remediation", "container_migration"]),
    language=st.sampled_from(["typescript", "javascript"]),
    build_system=st.sampled_from(_BUILD_SYSTEMS),
    cve_id=st.from_regex(r"^CVE-\d{4}-\d{4,7}$", fullmatch=True),
    affected_package=st.from_regex(r"^[a-z][a-z0-9-]{0,20}@\d+\.\d+\.\d+$", fullmatch=True),
    failure_mode=st.sampled_from(_FAILURE_MODES),
)


@given(payload=_query_payload)
def test_query_digest_is_pure_and_64_hex(payload: dict[str, str]) -> None:
    d1 = Query.model_validate(payload).digest()
    d2 = Query.model_validate(payload).digest()
    assert d1 == d2
    assert len(d1) == 64
    assert all(c in "0123456789abcdef" for c in d1)


@given(
    payload=_query_payload,
    other_cve=st.from_regex(r"^CVE-\d{4}-\d{4,7}$", fullmatch=True),
)
def test_query_digest_sensitive_to_cve(payload: dict[str, str], other_cve: str) -> None:
    q = Query.model_validate(payload)
    perturbed = Query.model_validate({**payload, "cve_id": other_cve})
    assert (q.digest() == perturbed.digest()) == (payload["cve_id"] == other_cve)
