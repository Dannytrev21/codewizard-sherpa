"""Phase 6 S1-01 AC-7 — SutDigest stability + sensitivity + no-side-effects.

The pure helper :func:`_compute_sut_digest_input` is the byte-stable substrate
Phase-9 S4-05 G5 conformance later asserts byte-identical across
:class:`LocalVulnRemediationSut` and :class:`TemporalVulnRemediationSut`. The
helper is pure: no clock, env, filesystem, network — verified by an AST walk
that fails loud the moment a concrete ``digest()`` implementation introduces
any of those names.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from codegenie.types.identifiers import CassetteId, CveId
from codegenie.types.parsers import (
    parse_repo_fixture_ref,
    parse_sut_digest,
    parse_vuln_case_id,
)
from codegenie.workflows import VulnRemediationCase
from codegenie.workflows.vuln_sut import _compute_sut_digest_input

# Strategies ---------------------------------------------------------------

_CASE_IDS = [
    "01HXX00000000000000000000Z",
    "01HXX00000000000000000001Z",
    "01HXX00000000000000000002Z",
]
_FIXTURES = ["node_typescript_helm", "node_yarn_berry_pnp", "node_pnpm_native"]
_CVES = ["CVE-2024-12345", "CVE-2024-12346", "CVE-2025-00001"]
_CASSETTES = [
    "01HXX00000000000000000000Z",
    "01HXX00000000000000000003Z",
]
_MODES = ["dry_run", "apply", "replay"]


def _case_strategy() -> st.SearchStrategy[VulnRemediationCase]:
    return st.builds(
        lambda ci, fx, cv, ca, em: VulnRemediationCase(
            case_id=parse_vuln_case_id(ci).unwrap(),
            repo_fixture=parse_repo_fixture_ref(fx).unwrap(),
            cve=CveId(cv),
            cassette_id=CassetteId(ca),
            execution_mode=em,
        ),
        ci=st.sampled_from(_CASE_IDS),
        fx=st.sampled_from(_FIXTURES),
        cv=st.sampled_from(_CVES),
        ca=st.sampled_from(_CASSETTES),
        em=st.sampled_from(_MODES),
    )


# AC-7 #1 — stability ------------------------------------------------------


@given(case=_case_strategy())
@settings(max_examples=40)
def test_ac7_digest_is_byte_stable_for_same_case(case: VulnRemediationCase) -> None:
    first = _compute_sut_digest_input(case)
    second = _compute_sut_digest_input(case)
    assert first == second
    assert parse_sut_digest(first).is_ok(), "digest must match SutDigest grammar"


# AC-7 #2 — sensitivity ----------------------------------------------------


@given(a=_case_strategy(), b=_case_strategy())
@settings(max_examples=40)
def test_ac7_digest_is_sensitive_to_field_changes(
    a: VulnRemediationCase,
    b: VulnRemediationCase,
) -> None:
    """Two cases differing on at least one field hash to distinct digests."""
    if a == b:
        return
    da = _compute_sut_digest_input(a)
    db = _compute_sut_digest_input(b)
    assert da != db, (
        "AC-7: digest collision across distinct cases. A buggy implementation "
        "that omits a field from the hash silently fails this property."
    )


# AC-7 #3 — explicit per-field sensitivity (mutation-thinking) -------------


def _base_case() -> VulnRemediationCase:
    return VulnRemediationCase(
        case_id=parse_vuln_case_id("01HXX00000000000000000000Z").unwrap(),
        repo_fixture=parse_repo_fixture_ref("node_yarn_berry_pnp").unwrap(),
        cve=CveId("CVE-2024-12345"),
        cassette_id=CassetteId("01HXX00000000000000000000Z"),
        execution_mode="dry_run",
    )


@pytest.mark.parametrize(
    "field,new",
    [
        ("case_id", parse_vuln_case_id("01HXX00000000000000000001Z")),
        ("repo_fixture", parse_repo_fixture_ref("node_pnpm_native")),
        ("cve", CveId("CVE-2099-99999")),
        ("cassette_id", CassetteId("01HXX00000000000000000099Z")),
        ("execution_mode", "apply"),
    ],
)
def test_ac7_each_field_contributes_to_digest(field: str, new: object) -> None:
    """Mutating each field changes the digest output."""
    value = new.unwrap() if hasattr(new, "unwrap") else new  # type: ignore[union-attr]
    base = _base_case()
    mutated = base.model_copy(update={field: value})
    assert _compute_sut_digest_input(base) != _compute_sut_digest_input(mutated), (
        f"AC-7: mutating {field} did not change the digest — a buggy implementation "
        f"that omits {field} from the hash would pass."
    )


# AC-7 #4 — no-side-effects AST fence --------------------------------------

_BANNED_NAMES = frozenset(
    {
        "open",
        "socket",
        "urllib",
        "httpx",
        "requests",
        "time",
        "datetime",
        "os",
        "subprocess",
    }
)


def _digest_methods_in_workflows() -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Walk every Python file under ``codegenie.workflows`` for ``def digest``."""
    import codegenie.workflows as pkg

    root = Path(pkg.__file__).resolve().parent
    found: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for py in root.rglob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "digest":
                found.append(node)
    return found


def test_ac7_no_side_effects_in_any_concrete_digest_implementation() -> None:
    """AST walk: any ``digest()`` body must not mention I/O / clock / env names.

    Starts trivially passing because no concrete adapter exists yet; starts
    biting in S5-01 when ``LocalVulnRemediationSut.digest`` lands.
    """
    methods = _digest_methods_in_workflows()
    for fn in methods:
        # Skip the Protocol stub itself (a body of just ``...``).
        body_is_ellipsis = (
            len(fn.body) == 1
            and isinstance(fn.body[0], ast.Expr)
            and isinstance(fn.body[0].value, ast.Constant)
            and fn.body[0].value.value is Ellipsis
        )
        if body_is_ellipsis:
            continue
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Name) and sub.id in _BANNED_NAMES:
                raise AssertionError(
                    f"AC-7: digest implementation references {sub.id!r} — "
                    f"forbidden under the no-side-effects fence (Phase 9 S4-05 G5)."
                )
            if isinstance(sub, ast.Attribute):
                # Match os.environ, os.getenv, time.time, datetime.now, etc.
                if isinstance(sub.value, ast.Name) and sub.value.id in _BANNED_NAMES:
                    raise AssertionError(
                        f"AC-7: digest implementation references "
                        f"{sub.value.id}.{sub.attr} — forbidden."
                    )


# AC-7 — digest matches grammar -------------------------------------------


def test_ac7_digest_output_matches_blake3_grammar() -> None:
    case = _base_case()
    d = _compute_sut_digest_input(case)
    assert re.fullmatch(r"blake3:[0-9a-f]{64}", d), (
        f"AC-7: digest output {d!r} violates ^blake3:[0-9a-f]{{64}}$ grammar."
    )
