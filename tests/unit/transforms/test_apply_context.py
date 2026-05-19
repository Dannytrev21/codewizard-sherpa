"""Unit tests for ``codegenie.transforms.apply_context`` — S1-04 AC-7 suite.

Covers every runtime-observable acceptance criterion in story
``docs/phases/03-vuln-deterministic-recipe/stories/S1-04-transform-abc-apply-context.md``
for ``AttemptSummary``, ``ApplyContext``, ``TransformProvenance``, and
``CapabilityBundle``. Tests are exhaustively parametrized to catch:

- Wrong-container regressions (list returned where tuple required).
- ``len(s)`` substituted for ``len(s.encode("utf-8"))`` (UTF-8 multi-byte cap).
- Missing ``field_validator`` for naive datetimes, NUL/control/bidi bytes,
  or non-semver version strings.
- Symmetric ``key`` → ``renamed_key`` JSON-shape regressions (AC-7j).
- ``frozen=True`` / ``extra="forbid"`` accidentally relaxed on any model.

Static-type assertions (AC-1, AC-1a class-level annotation pattern) live in
``test_transform_abc.py``; module-purity fences live in
``tests/fence/test_transforms_module_purity.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from codegenie.plugins.capabilities import NpmInstallCapability
from codegenie.transforms import (
    ApplyContext,
    AttemptSummary,
    CapabilityBundle,
    TransformProvenance,
)
from codegenie.types.identifiers import (
    AttemptNumber,
    EventId,
    PluginId,
    RecipeId,
    RegistryUrl,
    SignalKind,
    TransformId,
    TransformKind,
    WorkflowId,
)

# ---------------------------------------------------------------------------
# Fixtures — concrete constructors (NOT ``...`` ellipsis; story V-T-F4 closure).
# ---------------------------------------------------------------------------

_ULID_A: str = "01HXX00000000000000000000Z"
_ULID_B: str = "01HYY00000000000000000000Z"


def _empty_caps() -> CapabilityBundle:
    """S4-05 widens this — the substituted ``CapabilityBundle`` from
    ``codegenie.plugins.capabilities`` requires exactly one non-None
    capability slot. The fixture name is preserved for callsite
    stability; "empty" now means "no fs / no git" rather than literally
    zero capabilities (Phase-3-Step-1's empty shell)."""
    return CapabilityBundle(
        npm=NpmInstallCapability(
            registry=RegistryUrl("https://registry.npmjs.org"),
            _minted_by=PluginId("vulnerability-remediation--node--npm"),
        )
    )


def _provenance(**overrides: Any) -> TransformProvenance:
    base: dict[str, Any] = dict(
        plugin_id=PluginId("vulnerability-remediation--node--npm"),
        plugin_version="1.0.0",
        recipe_id=RecipeId("npm-lockfile-pin"),
        recipe_version="1.0.0",
        transform_kind=TransformKind("lockfile_pin"),
        applied_at=datetime.now(UTC),
        capability_use_id=EventId(_ULID_A),
    )
    base.update(overrides)
    return TransformProvenance(**base)


def _attempt(**overrides: Any) -> AttemptSummary:
    base: dict[str, Any] = dict(
        attempt=AttemptNumber(1),
        failing_signals=(SignalKind("tests"),),
        prior_failure_summary="ran out of retries",
        evidence_paths=(),
        transform_id=TransformId("a" * 64),
    )
    base.update(overrides)
    return AttemptSummary(**base)


def _context(**overrides: Any) -> ApplyContext:
    base: dict[str, Any] = dict(
        workflow_id=WorkflowId(_ULID_A),
        capabilities=_empty_caps(),
    )
    base.update(overrides)
    return ApplyContext(**base)


# ---------------------------------------------------------------------------
# AC-7a — defaults
# ---------------------------------------------------------------------------


def test_apply_context_defaults_to_empty_prior_attempts() -> None:
    ctx = _context()
    assert ctx.prior_attempts == ()
    assert ctx.attempt == AttemptNumber(1)


# ---------------------------------------------------------------------------
# AC-7b — round-trip identity parametrized over every model
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "instance_factory,model_cls",
    [
        (lambda: _attempt(), AttemptSummary),
        (
            lambda: _context(
                attempt=AttemptNumber(2),
                prior_attempts=(_attempt(),),
            ),
            ApplyContext,
        ),
        (lambda: _provenance(), TransformProvenance),
        (lambda: _empty_caps(), CapabilityBundle),
    ],
)
def test_round_trip_identity(instance_factory: Any, model_cls: type[BaseModel]) -> None:
    """AC-7b — every Phase-3 contract model survives JSON round-trip with
    *concrete* type preserved (catches a non-discriminated-union or
    upcasting regression)."""
    m = instance_factory()
    parsed = model_cls.model_validate_json(m.model_dump_json())
    assert type(parsed) is model_cls
    assert parsed == m


# ---------------------------------------------------------------------------
# AC-7c — UTF-8 bytes cap on prior_failure_summary (NOT len(s))
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,verdict",
    [
        # 1-byte ASCII boundary.
        ("x" * 8192, "accept"),
        ("x" * 8193, "reject"),
        # 4-byte emoji boundary — emoji has byte width 4, so 2048 chars = 8192
        # bytes (accept) and 2049 chars = 8196 bytes (reject). This catches
        # ``len(s)`` substituted for ``len(s.encode("utf-8"))``: 2049 chars
        # would still slip past a char-counting check.
        ("\U0001f480" * 2048, "accept"),
        ("\U0001f480" * 2049, "reject"),
    ],
)
def test_prior_failure_summary_utf8_bytes_cap(raw: str, verdict: str) -> None:
    if verdict == "accept":
        _attempt(prior_failure_summary=raw, failing_signals=())
    else:
        with pytest.raises(ValidationError):
            _attempt(prior_failure_summary=raw, failing_signals=())


# ---------------------------------------------------------------------------
# AC-7d — NUL / control / bidi rejection in prior_failure_summary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "x\x00y",  # NUL
        "x\x01y",  # SOH
        "x\x08y",  # BS
        "x\x0by",  # VT
        "x\x0cy",  # FF
        "x\x1fy",  # US
        "x‪y",  # LRE (bidi)
        "x‫y",  # RLE
        "x‬y",  # PDF
        "x‭y",  # LRO
        "x‮y",  # RLO
        "x⁦y",  # LRI
        "x⁧y",  # RLI
        "x⁨y",  # FSI
        "x⁩y",  # PDI
    ],
)
def test_prior_failure_summary_rejects_nul_control_bidi(bad: str) -> None:
    with pytest.raises(ValidationError):
        _attempt(prior_failure_summary=bad, failing_signals=())


@pytest.mark.parametrize("ok", ["x\ty", "x\ny", "x\rz", "no controls here"])
def test_prior_failure_summary_admits_whitespace(ok: str) -> None:
    s = _attempt(prior_failure_summary=ok, failing_signals=())
    assert s.prior_failure_summary == ok


# ---------------------------------------------------------------------------
# AC-7e — extra="forbid" on every model
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs,model_cls",
    [
        (dict(workflow_id=WorkflowId(_ULID_A), capabilities=_empty_caps(), oops="x"), ApplyContext),
        (
            dict(
                attempt=AttemptNumber(1),
                failing_signals=(),
                prior_failure_summary="ok",
                evidence_paths=(),
                transform_id=None,
                oops="x",
            ),
            AttemptSummary,
        ),
        (
            dict(
                plugin_id=PluginId("p"),
                plugin_version="1.0.0",
                recipe_id=RecipeId("r"),
                recipe_version="1.0.0",
                transform_kind=TransformKind("lockfile_pin"),
                applied_at=datetime.now(UTC),
                capability_use_id=EventId(_ULID_A),
                oops="x",
            ),
            TransformProvenance,
        ),
        (dict(oops="x"), CapabilityBundle),
    ],
)
def test_extra_forbid_rejects_unknown_keys(
    kwargs: dict[str, Any], model_cls: type[BaseModel]
) -> None:
    with pytest.raises(ValidationError):
        model_cls(**kwargs)


# ---------------------------------------------------------------------------
# AC-7f — frozen=True over every field of every model
# ---------------------------------------------------------------------------


def test_apply_context_frozen_rejects_attribute_reassignment() -> None:
    ctx = _context()
    for field in ("workflow_id", "attempt", "prior_attempts", "capabilities"):
        with pytest.raises(ValidationError):
            setattr(ctx, field, getattr(ctx, field))


def test_attempt_summary_frozen_rejects_attribute_reassignment() -> None:
    a = _attempt()
    for field in (
        "attempt",
        "failing_signals",
        "prior_failure_summary",
        "evidence_paths",
        "transform_id",
    ):
        with pytest.raises(ValidationError):
            setattr(a, field, getattr(a, field))


def test_transform_provenance_frozen_rejects_attribute_reassignment() -> None:
    p = _provenance()
    for field in (
        "plugin_id",
        "plugin_version",
        "recipe_id",
        "recipe_version",
        "transform_kind",
        "applied_at",
        "capability_use_id",
    ):
        with pytest.raises(ValidationError):
            setattr(p, field, getattr(p, field))


def test_capability_bundle_carries_frozen_and_extra_forbid_after_s4_05() -> None:
    """Post-S4-05 substitution: ``CapabilityBundle`` is the real model from
    ``codegenie.plugins.capabilities``. The frozen / extra-forbid contract
    survives the substitution; the bundle additionally carries an
    ``exactly-one-non-None`` validator (covered by AC-Sub-4 in
    ``tests/unit/plugins/test_capabilities.py``)."""
    cb = _empty_caps()
    assert cb.model_config.get("frozen") is True
    assert cb.model_config.get("extra") == "forbid"


# ---------------------------------------------------------------------------
# AC-7g — tuple immutability (no .append on the container itself)
# ---------------------------------------------------------------------------


def test_apply_context_prior_attempts_is_tuple_not_list() -> None:
    ctx = _context()
    assert isinstance(ctx.prior_attempts, tuple)
    with pytest.raises(AttributeError):
        ctx.prior_attempts.append(_attempt())  # type: ignore[attr-defined]


def test_attempt_summary_failing_signals_is_tuple_not_list() -> None:
    a = _attempt()
    assert isinstance(a.failing_signals, tuple)
    with pytest.raises(AttributeError):
        a.failing_signals.append(SignalKind("x"))  # type: ignore[attr-defined]


def test_attempt_summary_evidence_paths_is_tuple_not_list() -> None:
    a = _attempt()
    assert isinstance(a.evidence_paths, tuple)
    with pytest.raises(AttributeError):
        a.evidence_paths.append("x")  # type: ignore[attr-defined]


def test_list_to_tuple_coercion_on_ingest() -> None:
    """YAML / JSON arrays decode as Python lists. The boundary validator
    must coerce them to tuples so downstream code sees the truly-immutable
    container shape ADR-0010 prescribes."""
    a = AttemptSummary(
        attempt=AttemptNumber(1),
        failing_signals=[SignalKind("tests")],  # type: ignore[arg-type]
        prior_failure_summary="ok",
        evidence_paths=[],  # type: ignore[arg-type]
        transform_id=None,
    )
    assert isinstance(a.failing_signals, tuple)
    assert isinstance(a.evidence_paths, tuple)
    ctx = ApplyContext(
        workflow_id=WorkflowId(_ULID_A),
        capabilities=_empty_caps(),
        prior_attempts=[a],  # type: ignore[arg-type]
    )
    assert isinstance(ctx.prior_attempts, tuple)


# ---------------------------------------------------------------------------
# AC-7h — applied_at naive-datetime rejection
# ---------------------------------------------------------------------------


def test_transform_provenance_naive_datetime_rejected() -> None:
    with pytest.raises(ValidationError):
        _provenance(applied_at=datetime(2026, 5, 18))  # naive


def test_transform_provenance_non_utc_timezone_rejected_or_coerced() -> None:
    """A non-UTC timezone is either rejected or coerced to UTC. Either is a
    valid interpretation of ADR-0010's 'UTC-aware'; the bug we're guarding
    against is silently accepting a non-UTC tz and downstream reading it as
    UTC."""
    from datetime import timedelta, timezone

    plus_five = timezone(timedelta(hours=5))
    naive_eq = datetime(2026, 5, 18, 10, 0, 0)
    aware_plus5 = naive_eq.replace(tzinfo=plus_five)
    try:
        p = _provenance(applied_at=aware_plus5)
    except ValidationError:
        return  # rejection is fine
    # Acceptance is OK only if it was normalized to UTC.
    assert p.applied_at.utcoffset() == timedelta(0)


# ---------------------------------------------------------------------------
# AC-7i — plugin_version / recipe_version regex
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_version", ["not-a-semver", "1", "1.2", "1.2.3.4.5", "", "v1.2.3", "1.2.3-"]
)
def test_transform_provenance_plugin_version_rejects_non_semver(
    bad_version: str,
) -> None:
    with pytest.raises(ValidationError):
        _provenance(plugin_version=bad_version)


@pytest.mark.parametrize("bad_version", ["not-a-semver", "1", "1.2", "1.2.3.4.5", "", "v1.2.3"])
def test_transform_provenance_recipe_version_rejects_non_semver(
    bad_version: str,
) -> None:
    with pytest.raises(ValidationError):
        _provenance(recipe_version=bad_version)


@pytest.mark.parametrize(
    "ok_version", ["0.0.0", "1.2.3", "10.20.30", "1.2.3-alpha.1", "1.2.3+build.42"]
)
def test_transform_provenance_admits_valid_semver(ok_version: str) -> None:
    p = _provenance(plugin_version=ok_version, recipe_version=ok_version)
    assert p.plugin_version == ok_version
    assert p.recipe_version == ok_version


# ---------------------------------------------------------------------------
# AC-7j — JSON shape pinning on TransformProvenance
# ---------------------------------------------------------------------------


def test_transform_provenance_json_shape_pinned() -> None:
    """Pin the exact set of top-level JSON keys. Catches symmetric
    rename regressions (``key`` → ``renamed_key``) that would otherwise
    leave round-trip identity passing."""
    dumped = _provenance().model_dump(mode="json")
    assert set(dumped.keys()) == {
        "plugin_id",
        "plugin_version",
        "recipe_id",
        "recipe_version",
        "transform_kind",
        "applied_at",
        "capability_use_id",
    }


def test_apply_context_json_shape_pinned() -> None:
    dumped = _context().model_dump(mode="json")
    assert set(dumped.keys()) == {
        "workflow_id",
        "attempt",
        "prior_attempts",
        "capabilities",
    }


def test_attempt_summary_json_shape_pinned() -> None:
    dumped = _attempt().model_dump(mode="json")
    assert set(dumped.keys()) == {
        "attempt",
        "failing_signals",
        "prior_failure_summary",
        "evidence_paths",
        "transform_id",
    }


# ---------------------------------------------------------------------------
# AC-4 — model_copy immutable-update idiom is the Phase-5 retry path
# ---------------------------------------------------------------------------


def test_prior_attempts_grow_via_model_copy() -> None:
    """Phase 5's ADR-P5-002 retry envelope grows ``prior_attempts`` via
    ``ctx.model_copy(update={"prior_attempts": ctx.prior_attempts + (new,)})``.
    Verify the idiom works against the immutable shape this story ships."""
    ctx = _context()
    new = _attempt()
    ctx2 = ctx.model_copy(update={"prior_attempts": ctx.prior_attempts + (new,)})
    assert ctx2.prior_attempts == (new,)
    assert ctx.prior_attempts == ()  # original untouched


# ---------------------------------------------------------------------------
# AttemptSummary — transform_id may be None when failure precedes Transform
# ---------------------------------------------------------------------------


def test_attempt_summary_admits_none_transform_id() -> None:
    a = _attempt(transform_id=None)
    assert a.transform_id is None
