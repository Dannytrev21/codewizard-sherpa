"""Phase-3 S3-01 — Hypothesis property tests over namespace + import-path grammars.

Pins AC-18 (namespace) and AC-19 (import-path). Each property draws strings
from the complement of the allowed regex; ``TCCM.model_validate`` must reject
*every* such input.
"""

from __future__ import annotations

import re

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from codegenie.plugins.tccm import TCCM

_BASE_MUST = [{"primitive": "scip.refs", "args": {}}]
_NS_RE = r"[a-z][a-z0-9_]*"
_IMPORT_RE = r"[a-zA-Z_][a-zA-Z0-9_.]*:[A-Z][a-zA-Z0-9_]*"


@given(bad_ns=st.text(min_size=1).filter(lambda s: not re.fullmatch(_NS_RE, s)))
def test_invalid_namespace_always_rejected(bad_ns: str) -> None:
    """AC-18 — any string outside the namespace regex is rejected."""
    with pytest.raises(ValidationError):
        TCCM.model_validate(
            {
                "must_read": _BASE_MUST,
                "provides": {bad_ns: {"nvd_parser": "x:Y"}},
            }
        )


@given(bad_path=st.text(min_size=1).filter(lambda s: not re.fullmatch(_IMPORT_RE, s)))
def test_invalid_import_path_always_rejected(bad_path: str) -> None:
    """AC-19 — any string outside the import-path regex is rejected."""
    with pytest.raises(ValidationError):
        TCCM.model_validate(
            {
                "must_read": _BASE_MUST,
                "provides": {"vuln_index_capabilities": {"nvd_parser": bad_path}},
            }
        )
