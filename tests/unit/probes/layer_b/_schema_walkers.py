"""S4-07 — test-only helpers that walk a JSON Schema document and report
every object node missing ``additionalProperties: false``.

This module is **test-only** (lives under ``tests/``) and is NOT promoted to
production: the schema-validation kernel (``codegenie.schema.validator``)
stays minimal — ``jsonschema`` + ``referencing`` is the whole kernel.

The walker traversal covers every keyword that can hold a subschema:

- ``properties.*``, ``patternProperties.*``, ``$defs.*``
- ``oneOf[*]``, ``anyOf[*]``, ``allOf[*]``, ``prefixItems[*]``
- ``if``/``then``/``else``, ``items``, ``not``
- ``additionalProperties`` when itself a schema (i.e., not a bool)

A node is treated as an object if ``type == "object"``, ``type`` is a list
containing ``"object"``, or no ``type`` is declared but it carries object-only
keywords (``properties``, ``patternProperties``). The string ``$defs.*``
descendants are treated as schemas regardless of their declared ``type``.
"""

from __future__ import annotations


def _is_object_node(node: object) -> bool:
    if not isinstance(node, dict):
        return False
    t = node.get("type")
    if t == "object":
        return True
    if isinstance(t, list) and "object" in t:
        return True
    if t is None and ("properties" in node or "patternProperties" in node):
        return True
    return False


def _walk_object_nodes(schema: object, path: str = "") -> list[str]:
    """Return a list of JSON-Pointer-ish paths for every object node missing
    an explicit ``additionalProperties``.

    Boolean values for ``additionalProperties`` count as explicit (whether
    ``true`` or ``false``); only nodes that omit the keyword entirely are
    flagged. The caller asserts the returned list is empty for ``Phase 1
    ADR-0004`` conformance.
    """
    missing: list[str] = []

    def _visit(node: object, p: str) -> None:
        if not isinstance(node, dict):
            return
        if _is_object_node(node) and "additionalProperties" not in node:
            missing.append(p or "<root>")
        props = node.get("properties")
        if isinstance(props, dict):
            for k, v in props.items():
                _visit(v, f"{p}/properties/{k}")
        pat = node.get("patternProperties")
        if isinstance(pat, dict):
            for k, v in pat.items():
                _visit(v, f"{p}/patternProperties/{k}")
        defs = node.get("$defs")
        if isinstance(defs, dict):
            for k, v in defs.items():
                _visit(v, f"{p}/$defs/{k}")
        for key in ("oneOf", "anyOf", "allOf", "prefixItems"):
            sub = node.get(key)
            if isinstance(sub, list):
                for i, v in enumerate(sub):
                    _visit(v, f"{p}/{key}/{i}")
        for key in ("if", "then", "else", "items", "not"):
            if key in node:
                _visit(node[key], f"{p}/{key}")
        ap = node.get("additionalProperties")
        if isinstance(ap, dict):
            _visit(ap, f"{p}/additionalProperties")

    _visit(schema, path)
    return missing
