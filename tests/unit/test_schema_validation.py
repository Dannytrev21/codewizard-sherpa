"""Tests for ``codegenie.schema.validator`` — layered envelope + per-probe slice (ADR-0013).

Pins the layered-`additionalProperties` policy (`false` at envelope root, `true`
under ``probes.*``), `$ref` resolution to the first per-probe sub-schema
(`language_detection.schema.json`), the versioned `$id` strings ADR-0003's
S3-01 reader will scope cache invalidation off, and the `_validator()` lru_cache
hit that catches the no-cache mutant.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from codegenie.errors import SchemaValidationError
from codegenie.schema import validator as validator_mod
from codegenie.schema.validator import validate

_MINIMAL: dict[str, Any] = {
    "schema_version": "0.1.0",
    "generated_at": "2026-05-11T12:00:00Z",
    "repo": {"root": "/tmp/x", "git_commit": None},
    "probes": {},
}


def test_minimal_envelope_passes() -> None:
    validate(_MINIMAL)


def test_top_level_extra_key_fails() -> None:
    payload = {**_MINIMAL, "rogue_top_level_field": True}
    with pytest.raises(SchemaValidationError) as exc:
        validate(payload)
    msg = str(exc.value).lower()
    assert "rogue_top_level_field" in str(exc.value) or "additionalproperties" in msg


def test_unknown_probe_namespace_key_passes() -> None:
    """`additionalProperties: true` under `probes.*` — extension by addition (ADR-0013)."""
    validate(
        {
            **_MINIMAL,
            "probes": {"future_probe_not_yet_defined": {"anything": "goes"}},
        }
    )


def test_language_detection_slice_valid_payload_passes() -> None:
    """`$ref` resolution to the sub-schema wires up (catches un-wired-resolver mutant)."""
    validate(
        {
            **_MINIMAL,
            "probes": {
                "language_detection": {
                    "language_stack": {"counts": {"javascript": 3}, "primary": "javascript"}
                },
            },
        }
    )


def test_language_detection_slice_invalid_primary_type_fails() -> None:
    with pytest.raises(SchemaValidationError, match=r"primary"):
        validate(
            {
                **_MINIMAL,
                "probes": {"language_detection": {"language_stack": {"counts": {}, "primary": 42}}},
            }
        )


def test_language_detection_slice_invalid_counts_shape_fails() -> None:
    """`counts` must be `dict[str, int]` per the sub-schema, not a list."""
    with pytest.raises(SchemaValidationError):
        validate(
            {
                **_MINIMAL,
                "probes": {
                    "language_detection": {
                        "language_stack": {
                            "counts": ["javascript"],
                            "primary": "javascript",
                        }
                    },
                },
            }
        )


def test_language_detection_unknown_sub_key_fails_when_subschema_is_strict() -> None:
    """Phase 0's `language_detection.schema.json` sets the strict-at-slice precedent."""
    with pytest.raises(SchemaValidationError):
        validate(
            {
                **_MINIMAL,
                "probes": {
                    "language_detection": {
                        "language_stack": {
                            "counts": {"javascript": 1},
                            "primary": "javascript",
                        },
                        "unknown_extra_field": "should reject",
                    },
                },
            }
        )


def test_language_detection_primary_null_is_valid_for_empty_repo() -> None:
    """`primary: null` is a load-bearing AC-2/AC-3 affordance for the empty-repo case."""
    validate(
        {
            **_MINIMAL,
            "probes": {"language_detection": {"language_stack": {"counts": {}, "primary": None}}},
        }
    )


def test_envelope_schema_id_is_versioned() -> None:
    """ADR-0003: S3-01's `per_probe_schema_version(probe)` reads `$id`."""
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "codegenie"
        / "schema"
        / "repo_context.schema.json"
    )
    schema = json.loads(schema_path.read_text())
    assert "v0.1.0" in schema["$id"]


def test_language_detection_subschema_id_is_versioned() -> None:
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "codegenie"
        / "schema"
        / "probes"
        / "language_detection.schema.json"
    )
    schema = json.loads(schema_path.read_text())
    assert "language_detection/v0.1.1" in schema["$id"]


def test_validator_is_cached() -> None:
    """Catches the no-cache mutant: a `_validator()` that compiles every call (~30 ms)."""
    validator_mod._validator.cache_clear()
    validate(_MINIMAL)
    validate(_MINIMAL)
    info = validator_mod._validator.cache_info()
    assert info.hits >= 1
