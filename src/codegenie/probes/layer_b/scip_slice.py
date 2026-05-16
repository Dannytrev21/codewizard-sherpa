"""``SemanticIndexSlice`` — smart-constructor for the SCIP slice (S4-03 AC-18).

Two consumers exist in this story alone:

1. The probe envelope (``ProbeOutput.schema_slice["semantic_index"]``).
2. The B2-facing sidecar JSON (``<output_dir>/raw/scip.json``).

S4-07 will add a third: ``model_json_schema()`` is the source for the
``semantic_index.schema.json`` sub-schema. Phase 3's ``ScipAdapter`` will add
a fourth (deserializing the sidecar JSON).

Lifting the shape into its own module — separate from the probe so the
sub-schema generator can import it without a circular dep on probe
machinery — is the smart-constructor pattern at the writer boundary
(production ADR-0033). Mirrors :class:`codegenie.output.redacted_slice.RedactedSlice`
precedent.

The model is ``frozen=True, extra="forbid"`` — instances are immutable and
unknown fields are rejected at construction. A renamed required field
would fail Pydantic validation, not produce a silent mis-key (the
F-TQ-6 mutation-killer the validation report names).

The optional fields per ``docs/localv2.md §5.2 B1`` lines 581-586
(``any_type_density`` / ``unresolved_dynamic_imports`` /
``unresolved_computed_access`` / ``symbol_count`` / ``exported_symbols``)
default to ``None`` and are dropped from the on-disk shape via
``model_dump(exclude_none=True)`` — the sub-schema in S4-07 will mark them
optional.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["SemanticIndexSlice"]


class SemanticIndexSlice(BaseModel):
    """The ``semantic_index`` slice the SCIP probe emits.

    Field ordering is load-bearing: the B2-required keys
    (``last_indexed_commit``, ``files_indexed``, ``files_in_repo``,
    ``indexer_errors``, ``last_indexed_at``) appear in the dict regardless
    of population order, but Pydantic preserves declaration order in
    ``model_dump`` and ``model_dump_json`` — the YAML/JSON renders are
    deterministic for golden-file tests.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    scip_index_uri: str
    indexer: Literal["scip-typescript"]
    indexer_version: str
    files_indexed: int = Field(ge=0)
    files_in_repo: int = Field(ge=0)
    coverage_pct: float = Field(ge=0.0, le=100.0)
    last_indexed_commit: str
    last_indexed_at: str
    indexer_errors: int = Field(ge=0)
    indexer_warnings: int = Field(ge=0)
    any_type_density: float | None = None
    unresolved_dynamic_imports: int | None = None
    unresolved_computed_access: int | None = None
    symbol_count: int | None = None
    exported_symbols: int | None = None
