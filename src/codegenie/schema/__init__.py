"""``codegenie.schema`` — JSON Schema envelope + per-probe sub-schemas (ADR-0013).

The envelope (``repo_context.schema.json``) constrains the top-level shape of
``.codegenie/context/repo-context.yaml`` with ``additionalProperties: false``
at the root and ``true`` under ``probes.*`` — so adding a new probe is "drop a
sub-schema file and add one ``$ref`` line", never an envelope edit.

Per-probe sub-schemas live under :mod:`codegenie.schema.probes`. The first one
(``language_detection.schema.json``) sets the convention Phase 1's six probes
inherit: versioned ``$id`` (ADR-0003), strict ``additionalProperties: false``
at the slice (the precedent for Phase 1).
"""
