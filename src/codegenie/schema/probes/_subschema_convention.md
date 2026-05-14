# Per-probe sub-schema convention (Phase 1)

Every Phase-1 probe ships its own JSON Schema fragment at
`src/codegenie/schema/probes/<probe>.schema.json`. The envelope schema
(`repo_context.schema.json`) references those fragments by `$ref` and declares
each one **optional** at the `probes.*` level. Three load-bearing rules govern
how these fragments are shaped; the structural enforcement lives in
`tests/unit/test_sub_schemas.py` (landing in S2-01). This doc is the
human-facing rationale.

## Rule 1 — `"additionalProperties": false` at the sub-schema root

ADR
[`0004-per-probe-subschema-additional-properties-false`](../../../../docs/phases/01-context-gather-layer-a-node/ADRs/0004-per-probe-subschema-additional-properties-false.md)
makes each sub-schema root **strict**: a stray field at the top level fails
validation, so a renamed-but-not-deleted field surfaces immediately rather
than silently degrading downstream consumers. Nested objects may relax
this on a case-by-case basis (free-form `details` blobs); the root may not.

## Rule 2 — Slices are optional at the envelope

ADR
[`0010-layer-a-slices-optional-at-envelope`](../../../../docs/phases/01-context-gather-layer-a-node/ADRs/0010-layer-a-slices-optional-at-envelope.md)
declares every Layer-A slice optional under `probes.*`. A non-Node repo
produces a `RepoContext` with the `node_build_system` key absent (not
present-with-empty) and the envelope still validates. Skipped-probe
semantics live on the probe's own `status` field, not on slice presence.

## Rule 3 — `warnings[]` and structured `errors[]` use `WarningId`

ADR
[`0007-warnings-id-pattern`](../../../../docs/phases/01-context-gather-layer-a-node/ADRs/0007-warnings-id-pattern.md)
fixes the identifier pattern at `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`
(namespace dot subname; both segments lowercase ASCII). Every Phase-1
sub-schema applies this pattern to entries in its `warnings[]` and
structured `errors[]` arrays so grep-ability is preserved across probes.

## Canonical fragment

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://codewizard-sherpa/schema/probes/example.schema.json",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "status": { "enum": ["ok", "skipped", "error"] },
    "warnings": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "id": {
            "type": "string",
            "pattern": "^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$"
          },
          "message": { "type": "string" }
        },
        "required": ["id", "message"]
      }
    }
  },
  "required": ["status"]
}
```

The `"additionalProperties": false` line is the literal contract — see
`tests/unit/test_sub_schemas.py` for the structural test that walks every
`*.schema.json` under this directory and asserts the property is present at
each fragment's root. This doc is the rationale; the test is the
load-bearing guard.
