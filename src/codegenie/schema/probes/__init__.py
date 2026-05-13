"""Per-probe JSON Schema sub-schemas (ADR-0013).

Each ``<probe>.schema.json`` constrains the slice of ``probes.<probe>`` in the
envelope. Sub-schemas are composed by ``$ref`` from
``codegenie/schema/repo_context.schema.json``; adding a probe is a new file in
this directory + one ``$ref`` line in the envelope.
"""
