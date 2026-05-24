"""Phase 4 S1-02 — happy/sad paths for the ``PlanProposal`` closed union."""

from __future__ import annotations

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from codegenie.fallback.plan_proposal import (
    PlanProposal,
    PlanProposalCallsiteRewrite,
    PlanProposalDepBump,
    PlanProposalOverride,
    PlanProposalRefuse,
    SandboxedRelativePath,
    UnifiedDiff,
)

VALID_DEP_BUMP: dict[str, object] = {
    "kind": "dep_bump",
    "manifest_path": "package.json",
    "package": "lodash@4.17.21",
    "target_version": "4.17.21",
    "rationale": "Patch advisory CVE-2024-21501; minor bump.",
}
VALID_OVERRIDE: dict[str, object] = {
    "kind": "override",
    "manifest_path": "package.json",
    "package": "express@5.0.0",
    "forced_version": "5.0.0",
    "rationale": "Force resolution of transitive dep.",
}
GOOD_DIFF = (
    "--- a/src/app.ts\n"
    "+++ b/src/app.ts\n"
    "@@ -1,3 +1,3 @@\n"
    "-const x = 1;\n"
    "+const x = 2;\n"
    " // unchanged\n"
)
VALID_CALLSITE: dict[str, object] = {
    "kind": "callsite_rewrite",
    "manifest_path": "package.json",
    "files": ["src/app.ts"],
    "diff": GOOD_DIFF,
    "rationale": "Update callsite for new API.",
}
VALID_REFUSE: dict[str, object] = {
    "kind": "refuse",
    "reason": "insufficient_context",
    "rationale": "Not enough context to safely rewrite.",
}


# --- Discriminator routing (AC-5 happy / F11) ---


@pytest.mark.parametrize(
    "payload,expected_cls",
    [
        (VALID_DEP_BUMP, PlanProposalDepBump),
        (VALID_OVERRIDE, PlanProposalOverride),
        (VALID_CALLSITE, PlanProposalCallsiteRewrite),
        (VALID_REFUSE, PlanProposalRefuse),
    ],
)
def test_discriminator_routes(payload: dict[str, object], expected_cls: type[object]) -> None:
    obj = TypeAdapter(PlanProposal).validate_python(payload)
    assert isinstance(obj, expected_cls)
    for key, value in payload.items():
        assert getattr(obj, key) == value, f"field {key} not preserved"


# --- Discriminator rejects unknown tag (AC-5 sad) ---


def test_unknown_kind_rejected() -> None:
    adapter = TypeAdapter(PlanProposal)
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "shell_command", "cmd": "rm -rf /"})


# --- extra="forbid" (AC-5) ---


def test_extra_keys_rejected() -> None:
    with pytest.raises(ValidationError):
        PlanProposalDepBump.model_validate({**VALID_DEP_BUMP, "shell": "rm"})


# --- frozen=True (AC-5) ---


def test_frozen_immutable() -> None:
    m = PlanProposalDepBump.model_validate(VALID_DEP_BUMP)
    with pytest.raises(ValidationError):
        m.manifest_path = "other.json"  # type: ignore[misc]


# --- rationale length (AC-5) ---


def test_rationale_max_2048() -> None:
    big = {**VALID_DEP_BUMP, "rationale": "x" * 2049}
    with pytest.raises(ValidationError):
        PlanProposalDepBump.model_validate(big)


def test_rationale_at_boundary_accepted() -> None:
    ok = {**VALID_DEP_BUMP, "rationale": "x" * 2048}
    obj = PlanProposalDepBump.model_validate(ok)
    assert len(obj.rationale) == 2048


# --- files non-empty (AC-5) ---


def test_callsite_files_non_empty() -> None:
    payload = {**VALID_CALLSITE, "files": []}
    with pytest.raises(ValidationError):
        PlanProposalCallsiteRewrite.model_validate(payload)


# --- UnifiedDiff rejections (AC-4 / AC-5 / F9 distinctive-keyword) ---


def _err_text(exc: ValidationError) -> str:
    return " ".join(e["msg"].lower() for e in exc.errors())


def _bytes_header() -> str:
    return "--- a/src/app.ts\n+++ b/src/app.ts\n@@ -1 +1 @@\n-x\n+"


def test_diff_at_64kb_boundary_accepted() -> None:
    header = _bytes_header()
    diff = header + "y" * (65_536 - len(header.encode()) - 1) + "\n"
    assert len(diff.encode()) == 65_536
    obj = PlanProposalCallsiteRewrite.model_validate({**VALID_CALLSITE, "diff": diff})
    assert isinstance(obj, PlanProposalCallsiteRewrite)


def test_diff_one_byte_over_boundary_rejected() -> None:
    header = _bytes_header()
    diff = header + "y" * (65_537 - len(header.encode()) - 1) + "\n"
    assert len(diff.encode()) == 65_537
    with pytest.raises(ValidationError) as exc:
        PlanProposalCallsiteRewrite.model_validate({**VALID_CALLSITE, "diff": diff})
    text = _err_text(exc.value)
    assert "64 kb" in text or "exceeds" in text, text


def test_diff_path_escape_rejected() -> None:
    bad = "--- a/../../etc/passwd\n+++ b/../../etc/passwd\n@@ -1 +1 @@\n-x\n+y\n"
    payload = {**VALID_CALLSITE, "files": ["src/app.ts"], "diff": bad}
    with pytest.raises(ValidationError) as exc:
        PlanProposalCallsiteRewrite.model_validate(payload)
    text = _err_text(exc.value)
    assert "path" in text or "escape" in text, text


def test_no_op_diff_rejected() -> None:
    no_op = "--- a/src/app.ts\n+++ b/src/app.ts\n@@ -1 +1 @@\n unchanged\n"
    with pytest.raises(ValidationError) as exc:
        PlanProposalCallsiteRewrite.model_validate({**VALID_CALLSITE, "diff": no_op})
    assert "no-op" in _err_text(exc.value)


def test_empty_diff_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        PlanProposalCallsiteRewrite.model_validate({**VALID_CALLSITE, "diff": ""})
    assert "empty" in _err_text(exc.value)


def test_new_file_diff_rejected() -> None:
    new_file = "--- /dev/null\n+++ b/src/app.ts\n@@ -0,0 +1 @@\n+x\n"
    with pytest.raises(ValidationError) as exc:
        PlanProposalCallsiteRewrite.model_validate({**VALID_CALLSITE, "diff": new_file})
    text = _err_text(exc.value)
    assert "new file" in text or "/dev/null" in text, text


def test_crlf_diff_rejected() -> None:
    crlf = GOOD_DIFF.replace("\n", "\r\n")
    with pytest.raises(ValidationError) as exc:
        PlanProposalCallsiteRewrite.model_validate({**VALID_CALLSITE, "diff": crlf})
    text = _err_text(exc.value)
    assert "crlf" in text or "carriage return" in text, text


# --- manifest_path / SandboxedRelativePath rejections (AC-5 / AC-12, F6) ---


@pytest.mark.parametrize("bad_path", ["../../etc/passwd", "/etc/passwd", ""])
def test_manifest_path_rejected(bad_path: str) -> None:
    with pytest.raises(ValidationError):
        PlanProposalDepBump.model_validate({**VALID_DEP_BUMP, "manifest_path": bad_path})


@pytest.mark.parametrize("bad_path", ["../escape", "/abs", "", "with\x00nul", "back\\slash"])
def test_sandboxed_relative_path_rejects(bad_path: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(SandboxedRelativePath).validate_python(bad_path)


@pytest.mark.parametrize("ok_path", ["package.json", "src/app.ts", "a/b/c.txt"])
def test_sandboxed_relative_path_accepts(ok_path: str) -> None:
    assert TypeAdapter(SandboxedRelativePath).validate_python(ok_path) == ok_path


# --- UnifiedDiff direct round-trip via TypeAdapter ---


def test_unified_diff_accepts_good_diff() -> None:
    assert TypeAdapter(UnifiedDiff).validate_python(GOOD_DIFF) == GOOD_DIFF


# --- Data round-trip property (AC-6 / F12) ---


@pytest.mark.parametrize("payload", [VALID_DEP_BUMP, VALID_OVERRIDE, VALID_CALLSITE, VALID_REFUSE])
def test_json_round_trip_identity(payload: dict[str, object]) -> None:
    adapter = TypeAdapter(PlanProposal)
    obj = adapter.validate_python(payload)
    again = adapter.validate_python(json.loads(json.dumps(obj.model_dump(mode="json"))))
    assert again == obj
