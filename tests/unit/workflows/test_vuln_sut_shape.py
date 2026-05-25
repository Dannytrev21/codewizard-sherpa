"""Phase 6 S1-01 — shape tests for the four ADR-0001 names.

Covers:
- AC-1 — canonical module + re-exports + import-identity.
- AC-2 — ``VulnRemediationSut`` Protocol shape (two methods, async / sync,
  byte-exact annotations, ``runtime_checkable``).
- AC-3 — ``VulnRemediationCase`` field shape (frozen, ``extra="forbid"``,
  five required fields, closed ``ExecutionMode`` Literal).
- AC-4 — ``VulnRemediationResult`` field shape (frozen, ``extra="forbid"``,
  cross-field invariants via ``model_validator``, AST walk over module
  asserting every ``BaseModel`` carries ``_FROZEN_FORBID``).
- AC-8 — JSON round-trip byte-determinism.
"""

from __future__ import annotations

import ast
import inspect
import typing
from pathlib import Path
from typing import Literal, get_args, get_type_hints

import pytest
from pydantic import ValidationError

import codegenie.workflows as workflows_pkg
from codegenie.types.identifiers import (
    CassetteId,
    CveId,
)
from codegenie.types.parsers import (
    parse_blob_digest,
    parse_repo_fixture_ref,
    parse_sut_digest,
    parse_vuln_case_id,
)
from codegenie.workflows import (
    SutDigest,
    VulnRemediationCase,
    VulnRemediationResult,
    VulnRemediationSut,
)
from codegenie.workflows import vuln_sut as vuln_sut_mod

_EXPECTED_PUBLIC = {
    "VulnRemediationCase",
    "VulnRemediationResult",
    "SutDigest",
    "VulnRemediationSut",
}

# S1-02 additive amendment — the ten ledger-substrate names extend the
# package allowlist. Re-pinning the four S1-01 names alone would fail
# the moment S1-02 lands additively (the AC-13 contract). The package
# allowlist is centrally pinned by
# ``tests/fence/test_workflows_public_surface.py``.
_S1_02_LEDGER_NAMES = {
    "AwaitingHumanReview",
    "Completed",
    "FailedUnrecoverable",
    "GateFailedRetryable",
    "LedgerStateKind",
    "NeedsPlan",
    "PatchApplied",
    "PlanReady",
    "TransitionEvent",
    "TransitionId",
    "VulnLedgerState",
}


# ---------------------------------------------------------------------------
# AC-1 — canonical module + re-exports + import-identity
# ---------------------------------------------------------------------------


def test_ac1_all_includes_s1_01_four_names() -> None:
    """S1-01 contract: the four ADR-0001 names are in the package ``__all__``."""
    assert _EXPECTED_PUBLIC.issubset(set(workflows_pkg.__all__))


def test_ac1_all_is_exact_union_of_s1_01_and_s1_02() -> None:
    """S1-02 AC-13 additive amendment — total surface is 4 + 11 names.

    The fence at ``tests/fence/test_workflows_public_surface.py`` carries
    the single allowlist pin; this test mirrors its expectation so a drift
    fails loud in both locations.
    """
    assert set(workflows_pkg.__all__) == _EXPECTED_PUBLIC | _S1_02_LEDGER_NAMES


def test_ac1_import_identity_between_module_and_package() -> None:
    """Importing from the package and the module yields the same object."""
    for name in _EXPECTED_PUBLIC:
        from_pkg = getattr(workflows_pkg, name)
        from_mod = getattr(vuln_sut_mod, name)
        assert from_pkg is from_mod, f"{name}: package re-export drifted from module identity"


def test_ac1_package_path_is_workflows() -> None:
    """File naming pin (DP-A): module is ``vuln_sut.py``, not ``sut.py``."""
    pkg_path = Path(workflows_pkg.__file__).resolve().parent
    assert (pkg_path / "vuln_sut.py").exists(), "AC-1: workflows/vuln_sut.py must exist"
    assert not (pkg_path / "sut.py").exists(), (
        "AC-1: workflows/sut.py is forbidden — file is named vuln_sut.py so future "
        "task-class SUTs (migration, planner) land alongside, not by edit."
    )


# ---------------------------------------------------------------------------
# AC-2 — VulnRemediationSut Protocol shape
# ---------------------------------------------------------------------------


def test_ac2_protocol_runtime_checkable() -> None:
    """Protocol is decorated with ``@runtime_checkable``."""
    assert getattr(VulnRemediationSut, "_is_runtime_protocol", False) is True


def test_ac2_protocol_method_set_is_exactly_two() -> None:
    """Exactly two declared methods: ``run_case`` (async) + ``digest`` (sync)."""
    declared = {
        name
        for name in dir(VulnRemediationSut)
        if not name.startswith("_") and callable(getattr(VulnRemediationSut, name))
    }
    assert declared == {"run_case", "digest"}, (
        f"AC-2: declared methods drifted: got {declared}, want "
        f"{{'run_case', 'digest'}}. Adding a method is an ADR-0001 amendment."
    )


class _ConformingStub:
    """Hand-written stub used to verify async / sync method classification."""

    async def run_case(self, request: VulnRemediationCase) -> VulnRemediationResult:
        raise NotImplementedError

    def digest(self) -> SutDigest:
        raise NotImplementedError


def test_ac2_run_case_is_coroutine_function_on_conforming_stub() -> None:
    stub = _ConformingStub()
    assert inspect.iscoroutinefunction(stub.run_case)
    assert not inspect.iscoroutinefunction(stub.digest)


def test_ac2_annotations_are_byte_equal_to_adr0001() -> None:
    """run_case(request: VulnRemediationCase) -> VulnRemediationResult; digest() -> SutDigest."""
    run_case_hints = get_type_hints(VulnRemediationSut.run_case)
    assert run_case_hints == {
        "request": VulnRemediationCase,
        "return": VulnRemediationResult,
    }, "AC-2: run_case annotations drifted from ADR-0001."
    digest_hints = get_type_hints(VulnRemediationSut.digest)
    assert digest_hints == {"return": SutDigest}, "AC-2: digest annotations drifted from ADR-0001."


# ---------------------------------------------------------------------------
# AC-3 — VulnRemediationCase field shape
# ---------------------------------------------------------------------------


def test_ac3_case_field_set_and_required() -> None:
    fields = VulnRemediationCase.model_fields
    assert set(fields.keys()) == {
        "case_id",
        "repo_fixture",
        "cve",
        "cassette_id",
        "execution_mode",
    }, f"AC-3: VulnRemediationCase fields drifted: {sorted(fields.keys())}"
    for name, info in fields.items():
        assert info.is_required(), f"AC-3: {name} must be required (no defaults)"


def test_ac3_execution_mode_literal_is_byte_equal_triple() -> None:
    """The execution_mode Literal is exactly {'dry_run', 'apply', 'replay'}."""
    em = VulnRemediationCase.model_fields["execution_mode"].annotation
    assert typing.get_origin(em) is Literal
    assert set(get_args(em)) == {"dry_run", "apply", "replay"}, (
        "AC-3: ExecutionMode membership drifted. Adding a fourth mode is an "
        "ADR-0001 amendment, not a str-widening."
    )


def _ok_case() -> VulnRemediationCase:
    return VulnRemediationCase(
        case_id=parse_vuln_case_id("01HXX00000000000000000000Z").unwrap(),
        repo_fixture=parse_repo_fixture_ref("node_yarn_berry_pnp").unwrap(),
        cve=CveId("CVE-2024-12345"),
        cassette_id=CassetteId("01HXX00000000000000000000Z"),
        execution_mode="dry_run",
    )


def test_ac3_case_is_frozen() -> None:
    c = _ok_case()
    with pytest.raises(ValidationError):
        c.execution_mode = "apply"  # type: ignore[misc]


def test_ac3_case_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        VulnRemediationCase(
            case_id=parse_vuln_case_id("01HXX00000000000000000000Z").unwrap(),
            repo_fixture=parse_repo_fixture_ref("node_yarn_berry_pnp").unwrap(),
            cve=CveId("CVE-2024-12345"),
            cassette_id=CassetteId("01HXX00000000000000000000Z"),
            execution_mode="dry_run",
            extra_field="forbidden",  # type: ignore[call-arg]
        )


def test_ac3_execution_mode_rejects_unknown() -> None:
    with pytest.raises(ValidationError):
        VulnRemediationCase(
            case_id=parse_vuln_case_id("01HXX00000000000000000000Z").unwrap(),
            repo_fixture=parse_repo_fixture_ref("node_yarn_berry_pnp").unwrap(),
            cve=CveId("CVE-2024-12345"),
            cassette_id=CassetteId("01HXX00000000000000000000Z"),
            execution_mode="rollback",  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# AC-4 — VulnRemediationResult field shape + cross-field invariants
# ---------------------------------------------------------------------------


def test_ac4_result_field_set() -> None:
    assert set(VulnRemediationResult.model_fields.keys()) == {
        "case_id",
        "terminal_state",
        "patch_digest",
        "gate_summary",
        "failure_modes",
        "cost_summary",
        "evidence_references",
        "sut_digest",
    }


def test_ac4_terminal_state_literal_is_byte_equal_triple() -> None:
    """terminal_state ⊆ {completed, awaiting_human_review, failed_unrecoverable}."""
    ts = VulnRemediationResult.model_fields["terminal_state"].annotation
    assert typing.get_origin(ts) is Literal
    assert set(get_args(ts)) == {
        "completed",
        "awaiting_human_review",
        "failed_unrecoverable",
    }, (
        "AC-4: TerminalState membership drifted. Adding a terminal state "
        "requires an ADR-0001 amendment. The four non-terminal ledger "
        "states MUST NOT appear here."
    )


@pytest.mark.parametrize(
    "non_terminal",
    ["needs_plan", "plan_ready", "patch_applied", "gate_failed_retryable"],
)
def test_ac4_terminal_state_excludes_non_terminal_ledger_names(non_terminal: str) -> None:
    ts = VulnRemediationResult.model_fields["terminal_state"].annotation
    assert non_terminal not in set(get_args(ts))


def _ok_result(**overrides: object) -> VulnRemediationResult:
    from codegenie.types.identifiers import AttemptNumber, TokenCount
    from codegenie.workflows.vuln_sut import CostSummary, GateSummary

    base: dict[str, object] = dict(
        case_id=parse_vuln_case_id("01HXX00000000000000000000Z").unwrap(),
        terminal_state="completed",
        patch_digest=parse_blob_digest("a" * 64).unwrap(),
        gate_summary=GateSummary(attempts=AttemptNumber(1), last_outcome="pass"),
        failure_modes=(),
        cost_summary=CostSummary(
            tokens_in=TokenCount(0),
            tokens_out=TokenCount(0),
            cassette_replays=0,
        ),
        evidence_references=(),
        sut_digest=parse_sut_digest("blake3:" + "f" * 64).unwrap(),
    )
    base.update(overrides)
    return VulnRemediationResult(**base)  # type: ignore[arg-type]


def test_ac4_result_is_frozen_and_extra_forbid() -> None:
    r = _ok_result()
    with pytest.raises(ValidationError):
        r.terminal_state = "failed_unrecoverable"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        _ok_result(extra_field="forbidden")


def test_ac4_completed_requires_patch_digest() -> None:
    """terminal_state='completed' requires patch_digest != None."""
    with pytest.raises(ValidationError):
        _ok_result(patch_digest=None)


@pytest.mark.parametrize("ts", ["awaiting_human_review", "failed_unrecoverable"])
def test_ac4_non_completed_rejects_patch_digest(ts: str) -> None:
    """patch_digest must be None on non-completed terminal states."""
    with pytest.raises(ValidationError):
        _ok_result(terminal_state=ts)


@pytest.mark.parametrize("ts", ["awaiting_human_review", "failed_unrecoverable"])
def test_ac4_non_completed_with_null_patch_and_failure_modes_ok(ts: str) -> None:
    """Non-completed states accept patch_digest=None + non-empty failure_modes."""
    from codegenie.types.identifiers import ErrorId

    r = _ok_result(
        terminal_state=ts,
        patch_digest=None,
        failure_modes=(ErrorId("recipe.no_match"),),
    )
    assert r.terminal_state == ts


def test_ac4_completed_rejects_non_empty_failure_modes() -> None:
    """failure_modes must be empty iff terminal_state == 'completed'."""
    from codegenie.types.identifiers import ErrorId

    with pytest.raises(ValidationError):
        _ok_result(failure_modes=(ErrorId("recipe.no_match"),))


def test_ac4_ast_every_basemodel_in_module_uses_frozen_forbid() -> None:
    """AST walk over vuln_sut.py asserts every BaseModel sets model_config = _FROZEN_FORBID."""
    src = Path(vuln_sut_mod.__file__).read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = [b for b in node.bases if isinstance(b, ast.Name)]
        if not any(b.id == "BaseModel" for b in bases):
            continue
        config_assigns = [
            stmt
            for stmt in node.body
            if isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == "model_config"
        ]
        assert config_assigns, f"{node.name}: BaseModel subclass missing model_config"
        rhs = config_assigns[0].value
        assert isinstance(rhs, ast.Name) and rhs.id == "_FROZEN_FORBID", (
            f"{node.name}: model_config must be the imported _FROZEN_FORBID constant, "
            f"not an inline ConfigDict(...). See AC-4 single-canonical-source discipline."
        )


# ---------------------------------------------------------------------------
# AC-8 — JSON round-trip + byte-determinism
# ---------------------------------------------------------------------------


def test_ac8_case_round_trip_preserves_equality() -> None:
    c = _ok_case()
    again = VulnRemediationCase.model_validate_json(c.model_dump_json())
    assert again == c


def test_ac8_result_round_trip_preserves_equality() -> None:
    r = _ok_result()
    again = VulnRemediationResult.model_validate_json(r.model_dump_json())
    assert again == r


def test_ac8_dump_json_is_byte_deterministic() -> None:
    """Two independent dumps emit byte-identical JSON."""
    c = _ok_case()
    assert c.model_dump_json() == c.model_dump_json()
    r = _ok_result()
    assert r.model_dump_json() == r.model_dump_json()
