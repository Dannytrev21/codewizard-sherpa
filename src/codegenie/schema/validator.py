"""RepoContext schema validator (ADR-0013) — chokepoint for envelope+probe JSON Schema checks.

The validator is built once per process and cached via :func:`functools.cache`
on :func:`_validator`; the no-cache mutant costs roughly 30 ms per
``validate(...)`` call (envelope load + parse + sub-schema registry build +
compile) so the cache is load-bearing for performance, not a hot-path
micro-optimization. ``_validator()`` is module-scope so tests can clear it
via ``_validator.cache_clear()`` between assertions.

Layered ``additionalProperties`` policy (ADR-0013):

- envelope root: ``false`` — top-level shape is closed; rogue keys fail.
- ``probes.*``: ``true`` — adding a probe is "drop a sub-schema file +
  one ``$ref`` line", never an envelope edit.
- per-probe sub-schemas: MAY be strict; Phase 0's ``language_detection``
  sets the precedent (strict) for Phase 1.

`$ref` resolution uses the modern :mod:`referencing` library — sub-schemas
are registered by their ``$id`` (the absolute URI in the sub-schema's
``$id`` field) so the envelope's ``$ref`` is a stable absolute URI rather
than a path-relative string subject to base-URI surprises.

Errors surface as :class:`SchemaValidationError` with the failing JSON
Pointer path (``err.json_path``) in the message, so callers (S3-02 probe
output validation, S4-02 CLI gather, S5-02 audit verify) can pinpoint
*which* slice failed without reparsing the exception.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

import jsonschema
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012  # noqa: F401  # surfaces meta-schema for clarity

from codegenie.errors import SchemaValidationError

__all__ = ["validate"]


_SCHEMA_DIR = Path(__file__).resolve().parent


@functools.lru_cache(maxsize=1)
def _validator() -> jsonschema.Draft202012Validator:
    """Build the compiled validator once; subsequent calls are O(1) cache hits."""
    envelope = json.loads((_SCHEMA_DIR / "repo_context.schema.json").read_text())
    sub_schemas = [
        json.loads(p.read_text()) for p in (_SCHEMA_DIR / "probes").glob("*.schema.json")
    ]
    registry: Registry = Registry().with_resources(
        [
            (s["$id"], Resource.from_contents(s, default_specification=DRAFT202012))
            for s in sub_schemas
        ]
    )
    return jsonschema.Draft202012Validator(envelope, registry=registry)


def validate(repo_context: dict[str, object]) -> None:
    """Validate ``repo_context`` against the envelope schema.

    Raises :class:`SchemaValidationError` whose message names the failing
    JSON Pointer and the underlying ``jsonschema`` error message. The
    Pointer is the canonical "where did it fail" address — callers should
    surface it verbatim rather than reparse it.
    """
    try:
        _validator().validate(repo_context)
    except jsonschema.ValidationError as err:
        pointer = err.json_path
        raise SchemaValidationError(f"validation failed at {pointer}: {err.message}") from err
