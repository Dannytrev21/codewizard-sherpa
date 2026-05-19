# Story S7-03 — Sub-schemas + envelope `$ref` insertions + golden files

**Step:** Step 7 — `BaseImageProbe` + `ShellInvocationTraceProbe` under the plugin (sandboxed)
**Status:** Ready
**Effort:** M
**Depends on:** S7-01 (`BaseImageProbe` slice shape pinned), S7-02 (`ShellInvocationTraceProbe` slice shape pinned). This story consumes the slice shapes the previous two stories defined and serializes them as JSON Schema + golden fixtures.
**ADRs honored:** Phase 7 ADR-0009 **row #4** (envelope schema gains exactly **two** `$ref` insertions — one per new probe — and nothing more; the byte-edit fence enforces this); Phase 1 ADR-0004 (per-probe sub-schemas with `additionalProperties: false` at every node; envelope `probes.*` is `additionalProperties: true`); Phase 7 ADR-0005 (sub-schemas live under `plugins/distroless-migration--node--npm/schema/`, NOT under `src/codegenie/schema/probes/`); Phase 0 ADR-0013 (envelope `properties.probes` is the integration seam — adding a probe requires landing its sub-schema **and** wiring a `$ref` into the envelope; S4-07 is the precedent).

## Context

This story closes the **schema seam** for both new probes. The Phase 0 / Phase 1 discipline is that every probe's slice is validated by a strict per-probe JSON Schema (`additionalProperties: false` recursively) and the schemas are wired into the envelope schema (`src/codegenie/schema/repo_context.schema.json`) via `$ref`. Without this story, the probes' outputs flow through the sanitizer unvalidated; with this story, the envelope schema is the single source of truth for what a Phase 7 `repo-context.yaml` is allowed to contain.

Two byte-edit allowlist consequences are load-bearing here:

1. **Phase 7 ADR-0009 row #4** is the **one row** that authorizes envelope-schema edits: "exactly two `$ref` insertions (one per new probe)." Anything else (e.g., adding a top-level `properties` key, editing `additionalProperties`, removing a sibling `$ref`) is a fence failure. The fence test (`tests/fence/test_phase7_no_byte_edits_to_locked_files.py` from S5-01) computes the diff against the Phase 6.5 baseline and counts the additions; this story must produce a diff of exactly two additive `$ref` lines (plus minimum syntactic glue — JSON comma) and nothing else.

2. **Open question §8** (`BaseImageProbe` slice — `unresolved FROM ARG` as separate variant vs `kind="unknown"` with typed reason) is **pinned in this story**. The sub-schema commits to `kind: unknown` with a typed `reason: UnknownReason` (matching S7-01's slice shape). The schema encodes this via a `oneOf` over the `kind` enum + a conditional `required: ["reason"]` when `kind == "unknown"`. The schema makes the open-question decision mechanical.

Sub-schemas live under the **plugin** per Phase 7 ADR-0005 — `plugins/distroless-migration--node--npm/schema/{base_image,shell_invocation_trace}.schema.json` — not under `src/codegenie/schema/probes/`. The envelope schema's `$ref` insertions cross the core/plugin boundary; this is allowed and is the second consequence-of-ADR-0005 that the byte-edit fence row #4 makes explicit.

Golden files land under `tests/golden/probes/{base_image,shell_invocation_trace}/` and follow the existing Phase 1 / Phase 2 golden discipline (one JSON file per fixture, the file is the canonical expected slice). The integration test in S7-05 validates **fixture → probe → schema → golden** round-trip; without the goldens this story produces, S7-05 has nothing to assert against.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §8 (BaseImageProbe slice fields)` + `§9 (ShellInvocationTraceProbe slice fields)` — the canonical field list.
  - `../phase-arch-design.md §Testing strategy §Golden fixtures` — golden discipline.
- **Phase ADRs:**
  - `../ADRs/0009-phase-7-byte-edit-allowlist-fence.md` row #4 — the two `$ref` insertions. **Verbatim**: "exactly two `$ref` insertions (one per new probe)."
  - `../ADRs/0005-probes-live-under-plugin-not-core-tree.md` — schema location.
- **Existing code:**
  - `src/codegenie/schema/repo_context.schema.json` — the envelope. **Read its current state before editing.** Note the `properties.probes` object's shape; sibling `$ref` insertions land alphabetically (mirror the existing convention).
  - `src/codegenie/schema/probes/dockerfile.schema.json` — Phase 2 per-probe sub-schema; **the structural template** for both new schemas. Mirror its `$schema`, `$id`, `title`, `additionalProperties: false`-at-every-node discipline.
  - `tests/golden/probes/dockerfile/*.json` (Phase 2) — golden-file format precedent. Each file is the expected slice payload (no wrapper). Filename = fixture name.
- **Sibling stories:**
  - `S7-01-base-image-probe.md` AC-4 — the slice shape this story encodes.
  - `S7-02-shell-invocation-trace-probe.md` AC-9 — the trace-probe slice shape this story encodes.
  - `S5-01-phase7-byte-edit-allowlist-fence.md` — the fence test that asserts row #4 holds.
  - `S7-05-probe-conformance-and-envelope-integration.md` — the integration test that round-trips fixture → slice → schema-validate → golden.

## Goal

Land two new JSON Schema files under the plugin (`plugins/distroless-migration--node--npm/schema/{base_image,shell_invocation_trace}.schema.json`), each `additionalProperties: false` at every node, encoding the slice shapes pinned by S7-01 + S7-02. Land **exactly two `$ref` insertions** in `src/codegenie/schema/repo_context.schema.json` (Phase 7 ADR-0009 row #4) — one per probe — and nothing else. Land the nine golden files (six base-image variants + three shell-trace variants) that S7-05's integration tests round-trip against.

## Acceptance criteria

**Sub-schema files (AC-1 through AC-4)**
- [ ] **AC-1** `plugins/distroless-migration--node--npm/schema/base_image.schema.json` exists. Top-level: `$schema = "https://json-schema.org/draft/2020-12/schema"`, `$id = "https://codewizard-sherpa.dev/schema/probes/base_image.schema.json"`, `title = "BaseImageSlice"`, `type = "object"`, `additionalProperties: false`. Required keys: `dockerfiles`, `confidence`. Each `dockerfile` entry: `additionalProperties: false`, required `["path", "stages"]`; each `stage`: `additionalProperties: false`, required `["stage_index", "stage_name", "from_image", "image_digest", "kind", "reason"]`. `kind` is an `enum` matching S7-01 AC-5 verbatim. `reason` is `oneOf: [null, enum["unresolved_from_arg", "unrecognized_image", "dockerfile_parse_failed"]]`. **`additionalProperties: false` at EVERY object node** — verified by `tests/unit/schema/test_base_image_schema_strict.py::test_every_object_has_additional_properties_false` (walks the JSON tree and asserts).
- [ ] **AC-2** `plugins/distroless-migration--node--npm/schema/shell_invocation_trace.schema.json` exists. Top-level: same `$schema` / `$id` pattern, `title = "ShellInvocationTraceSlice"`, `type = "object"`, `additionalProperties: false`. Required keys: `["count", "invocations", "trace_available", "build_target", "image_digest", "confidence"]`. `invocations` is an array of objects with `additionalProperties: false` and required `["shell", "argv", "captured_at_phase", "source_dockerfile_line"]`. `captured_at_phase` is `enum["build", "startup"]`. Same recursive-additionalProperties:false walker test applies.
- [ ] **AC-3** **Conditional `required` for the `unknown` kind** (open question §8 pinned). The base-image stage subschema uses JSON Schema's `if/then/else` (or `allOf`-with-`if/then`) to assert: `if kind == "unknown" then reason != null else reason == null`. Verified by parametrized test rows: `{kind: "unknown", reason: null}` → invalid; `{kind: "unknown", reason: "unrecognized_image"}` → valid; `{kind: "alpine", reason: "unrecognized_image"}` → invalid; `{kind: "alpine", reason: null}` → valid.
- [ ] **AC-4** `mypy --strict`-compatible Pydantic models that mirror the schema land under `plugins/distroless-migration--node--npm/schema/_models.py` (frozen Pydantic v2 models: `BaseImageSlice`, `BaseImageDockerfile`, `BaseImageStage`, `ShellInvocationTraceSlice`, `ShellInvocation`). Each `model_config = ConfigDict(frozen=True, extra="forbid")`. A round-trip test asserts `Slice.model_validate(json.load(open(golden))).model_dump(mode="json") == json.load(open(golden))` for every golden file.

**Envelope `$ref` insertions (AC-5 through AC-7) — Phase 7 ADR-0009 row #4**
- [ ] **AC-5** `src/codegenie/schema/repo_context.schema.json` gains **exactly two** new `$ref` entries under `properties.probes.properties` (or the equivalent path matching the current envelope shape). The new keys are `"base_image"` and `"shell_invocation_trace"`. Each maps to `{"$ref": "<relative-or-absolute-resolvable-path>/<schema-file>.json"}`. The `$ref` target path resolves correctly from the envelope file location (verified by loading the envelope schema with `jsonschema` and validating a golden slice against it).
- [ ] **AC-6** **Diff discipline** — `git diff src/codegenie/schema/repo_context.schema.json` shows exactly: (a) two new `$ref` entries, (b) commas / closing brackets adjusted to keep JSON syntactically valid, (c) nothing else. Verified by `tests/fence/test_phase7_envelope_diff_shape.py` that re-loads the envelope from baseline + current, computes the structural diff, and asserts the only changes are the two named additions. **No `additionalProperties` flip, no top-level key addition, no sibling `$ref` removal.**
- [ ] **AC-7** Phase 7 ADR-0009 byte-edit allowlist fence (`tests/fence/test_phase7_no_byte_edits_to_locked_files.py` from S5-01) green: the envelope-schema edit consumes **row #4 only** (no other allowlist row is touched). The fence's row-#4 sub-assertion specifically counts the diff lines and asserts `count(added_$ref_keys) == 2 AND count(removed_lines) == 0`.

**Golden files — BaseImage (AC-8 through AC-13)**
- [ ] **AC-8** `tests/golden/probes/base_image/distroless-target.json` — fixture `tests/fixtures/portfolio/node-distroless-target/Dockerfile` (from S7-02). Expected slice: one dockerfile, one stage, `kind: "distroless"`, `image_digest: "sha256:<pinned>"`, `reason: null`, `confidence: "high"`.
- [ ] **AC-9** `tests/golden/probes/base_image/alpine.json` — fixture `node-vulnerable-alpine/Dockerfile`. `kind: "alpine"`, `confidence: "high"`.
- [ ] **AC-10** `tests/golden/probes/base_image/multi-stage.json` — fixture `multi-stage-dockerfile/Dockerfile`. Two stages: `{stage_name: "builder", kind: "alpine"}` and `{stage_name: "runtime", kind: "distroless"}`. `confidence: "high"`.
- [ ] **AC-11** `tests/golden/probes/base_image/scratch.json` — `FROM scratch` fixture. `kind: "scratch"`, `image_digest: null`, `reason: null`, `confidence: "high"` (no resolver call expected; explicit zero-evidence-needed case).
- [ ] **AC-12** `tests/golden/probes/base_image/unknown.json` — fixture `base-image-unknown/Dockerfile` (`FROM internal.registry/secret-corp:v1`). `kind: "unknown"`, `reason: "unrecognized_image"`, `confidence: "medium"` (static evidence; unresolved digest from a stub-resolver returning `None` for unknown registries).
- [ ] **AC-13** `tests/golden/probes/base_image/debian-slim.json` — fixture `tests/fixtures/portfolio/base-image-debian-slim/Dockerfile` (`FROM node:18-bullseye-slim`). `kind: "debian"`, `confidence: "high"`. (Adds one fixture to the S7-01 set — the `-slim` tag pattern.)

**Golden files — ShellInvocationTrace (AC-14 through AC-16)**
- [ ] **AC-14** `tests/golden/probes/shell_invocation_trace/distroless-target.json` — fixture `node-distroless-target/Dockerfile` + canned `SUCCESS_NO_SHELL` `SpawnResult`. Expected: `count: 0, invocations: [], trace_available: true, build_target: "builder", image_digest: "sha256:<pinned>", confidence: "high"`.
- [ ] **AC-15** `tests/golden/probes/shell_invocation_trace/with-shell.json` — fixture `node-with-shell/Dockerfile` + canned `SUCCESS_WITH_SHELL`. Expected: `count: 1, invocations: [{shell: "sh", argv: ["-c", "apt-get update && rm -rf /var/lib/apt/lists/*"], captured_at_phase: "build", source_dockerfile_line: 4}], trace_available: true, confidence: "high"`.
- [ ] **AC-16** `tests/golden/probes/shell_invocation_trace/no-trace-available.json` — stub raises `SandboxBootError`. Expected: `count: 0, invocations: [], trace_available: false, build_target: "builder", image_digest: "<empty-string-or-null-per-fence-decision>", confidence: "low"`. (Implementer note: pin whether `image_digest` is `null` or `""` in the schema — the schema must explicitly allow the chosen sentinel and the integration test must validate.)

**Schema-validates-golden round-trip (AC-17)**
- [ ] **AC-17** `tests/unit/schema/test_phase7_goldens_validate_against_subschemas.py` — for each of the nine golden files, load the corresponding sub-schema and assert `jsonschema.validate(golden_slice, sub_schema)` passes. Any golden that fails validation is a story-level red. The test is parametrized over the nine fixtures.

**Lint + fence (AC-18, AC-19)**
- [ ] **AC-18** `tests/fence/test_every_probe_subschema_has_additional_properties_false.py` (or extension of an existing Phase 1 fence) — recursive AST-walk over both new sub-schemas asserting every `type: "object"` node carries `additionalProperties: false`. Planted-violation case (parametrized) flips one node to `true` and asserts the walker fires.
- [ ] **AC-19** `mypy --strict plugins/distroless-migration--node--npm/schema/_models.py` clean; `ruff check` clean; `make lint-imports` green.

## Implementation outline

1. **Read the Phase 6.5 envelope baseline first.** Open `src/codegenie/schema/repo_context.schema.json` and find the `properties.probes.properties` path. Note the existing keys (alphabetic order; `additionalProperties: true` at the `properties.probes` level per Phase 0 ADR-0013). Plan the diff: two new keys (`base_image` before `ci`, `shell_invocation_trace` after `semantic_index_meta` or wherever alphabetic order lands them) — one `$ref` value each, pointing at the plugin's schema files.

2. **Write `plugins/distroless-migration--node--npm/schema/base_image.schema.json`** mirroring the structural template of `src/codegenie/schema/probes/dockerfile.schema.json`:
   ```json
   {
     "$schema": "https://json-schema.org/draft/2020-12/schema",
     "$id": "https://codewizard-sherpa.dev/schema/probes/base_image.schema.json",
     "title": "BaseImageSlice",
     "type": "object",
     "additionalProperties": false,
     "required": ["dockerfiles", "confidence"],
     "properties": {
       "dockerfiles": {
         "type": "array",
         "items": {
           "type": "object",
           "additionalProperties": false,
           "required": ["path", "stages"],
           "properties": {
             "path": {"type": "string"},
             "stages": {
               "type": "array",
               "items": {
                 "type": "object",
                 "additionalProperties": false,
                 "required": ["stage_index", "stage_name", "from_image", "image_digest", "kind", "reason"],
                 "properties": {
                   "stage_index": {"type": "integer", "minimum": 0},
                   "stage_name": {"type": ["string", "null"]},
                   "from_image": {"type": "string"},
                   "image_digest": {
                     "oneOf": [
                       {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
                       {"type": "null"}
                     ]
                   },
                   "kind": {
                     "enum": ["alpine", "debian", "ubuntu", "rhel", "distroless", "scratch", "chainguard", "unknown"]
                   },
                   "reason": {
                     "oneOf": [
                       {"type": "null"},
                       {"enum": ["unresolved_from_arg", "unrecognized_image", "dockerfile_parse_failed"]}
                     ]
                   }
                 },
                 "allOf": [
                   {
                     "if": {"properties": {"kind": {"const": "unknown"}}, "required": ["kind"]},
                     "then": {"properties": {"reason": {"not": {"type": "null"}}}}
                   },
                   {
                     "if": {"properties": {"kind": {"not": {"const": "unknown"}}}, "required": ["kind"]},
                     "then": {"properties": {"reason": {"type": "null"}}}
                   }
                 ]
               }
             }
           }
         }
       },
       "confidence": {"enum": ["high", "medium", "low"]}
     }
   }
   ```
   Validate against each of the six base-image goldens locally before declaring AC-1 green.

3. **Write `plugins/distroless-migration--node--npm/schema/shell_invocation_trace.schema.json`** by the same pattern:
   ```json
   {
     "$schema": "...", "$id": "...", "title": "ShellInvocationTraceSlice",
     "type": "object", "additionalProperties": false,
     "required": ["count", "invocations", "trace_available", "build_target", "image_digest", "confidence"],
     "properties": {
       "count": {"type": "integer", "minimum": 0},
       "invocations": {
         "type": "array",
         "items": {
           "type": "object", "additionalProperties": false,
           "required": ["shell", "argv", "captured_at_phase", "source_dockerfile_line"],
           "properties": {
             "shell": {"type": "string"},
             "argv": {"type": "array", "items": {"type": "string"}},
             "captured_at_phase": {"enum": ["build", "startup"]},
             "source_dockerfile_line": {"type": ["integer", "null"], "minimum": 0}
           }
         }
       },
       "trace_available": {"type": "boolean"},
       "build_target": {"type": "string"},
       "image_digest": {
         "oneOf": [
           {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
           {"type": "null"}
         ]
       },
       "confidence": {"enum": ["high", "medium", "low"]}
     }
   }
   ```

4. **Write `plugins/distroless-migration--node--npm/schema/_models.py`** with frozen Pydantic v2 mirrors (the `model_validate` round-trip is AC-4). Each model carries `model_config = ConfigDict(frozen=True, extra="forbid")`. Use `Literal[...]` for the `kind` / `confidence` / `captured_at_phase` enums (mypy-strict friendly; no `Any`).

5. **Edit `src/codegenie/schema/repo_context.schema.json`** — surgical. Two `$ref` entries; respect existing JSON formatting (2-space indent if that's the existing style; honor the trailing-comma policy if any). The diff is two contiguous lines (plus a comma on the prior key if it was the last) — that's the minimum surface area.

6. **Write the nine golden files** under `tests/golden/probes/{base_image,shell_invocation_trace}/`. Generate the initial content by running the probes against the fixtures with stub clients (S7-01 + S7-02 already produce the data); pretty-print with 2-space indent + trailing newline. Hand-verify one example per probe to ensure the field set is the canonical one.

7. **Write tests:**
   - `tests/unit/schema/test_base_image_schema_strict.py` — recursive `additionalProperties: false` walker + the `kind == "unknown"` conditional matrix.
   - `tests/unit/schema/test_shell_invocation_trace_schema_strict.py` — recursive walker.
   - `tests/unit/schema/test_phase7_goldens_validate_against_subschemas.py` — parametrized over the nine goldens.
   - `tests/unit/schema/test_phase7_subschema_pydantic_round_trip.py` — `_models.py` round-trip.
   - `tests/fence/test_phase7_envelope_diff_shape.py` — verifies the envelope diff is exactly the two `$ref` additions.

## TDD plan (red → green → refactor)

**Red 1** — write `test_phase7_goldens_validate_against_subschemas.py`. Pytest fails: schemas don't exist; goldens don't exist.

**Green 1** — land `base_image.schema.json`, `shell_invocation_trace.schema.json`, the nine goldens. The validation test now collects but fails until the schemas accept the goldens.

**Red 2** — write `test_base_image_schema_strict.py` (the recursive walker + the conditional matrix). Initially fails because the schema doesn't carry `additionalProperties: false` deep enough or doesn't enforce the conditional.

**Green 2** — iterate the schema until every object node has `additionalProperties: false` AND the `if/then` conditional fires correctly.

**Red 3** — write `test_phase7_envelope_diff_shape.py` referencing the Phase 6.5 baseline. Pytest fails because the envelope hasn't been edited yet.

**Green 3** — surgically insert the two `$ref` lines into `repo_context.schema.json`. Re-run; green.

**Red 4** — write `test_phase7_subschema_pydantic_round_trip.py`. Fails because `_models.py` doesn't exist.

**Green 4** — write the Pydantic models; round-trip green.

**Refactor** — extract a shared `$id` prefix constant if the repo has one; otherwise inline. Verify all 19+ tests green and `make check` passes.

## Files to touch

**New files:**
- `plugins/distroless-migration--node--npm/schema/__init__.py`
- `plugins/distroless-migration--node--npm/schema/base_image.schema.json`
- `plugins/distroless-migration--node--npm/schema/shell_invocation_trace.schema.json`
- `plugins/distroless-migration--node--npm/schema/_models.py`
- `tests/golden/probes/base_image/distroless-target.json`
- `tests/golden/probes/base_image/alpine.json`
- `tests/golden/probes/base_image/multi-stage.json`
- `tests/golden/probes/base_image/scratch.json`
- `tests/golden/probes/base_image/unknown.json`
- `tests/golden/probes/base_image/debian-slim.json`
- `tests/golden/probes/shell_invocation_trace/distroless-target.json`
- `tests/golden/probes/shell_invocation_trace/with-shell.json`
- `tests/golden/probes/shell_invocation_trace/no-trace-available.json`
- `tests/fixtures/portfolio/base-image-debian-slim/Dockerfile` (one additional fixture beyond S7-01's set)
- `tests/unit/schema/test_base_image_schema_strict.py`
- `tests/unit/schema/test_shell_invocation_trace_schema_strict.py`
- `tests/unit/schema/test_phase7_goldens_validate_against_subschemas.py`
- `tests/unit/schema/test_phase7_subschema_pydantic_round_trip.py`
- `tests/fence/test_phase7_envelope_diff_shape.py`

**Edited files (Phase 7 ADR-0009 byte-edit allowlist):**
- `src/codegenie/schema/repo_context.schema.json` — **row #4**: exactly two `$ref` insertions, nothing else.

## Out of scope

- **The Phase 7 byte-edit allowlist fence itself** (`tests/fence/test_phase7_no_byte_edits_to_locked_files.py`) — S5-01 owns. This story's edits CONSUME row #4 but do not modify the fence.
- **The `ALLOWED_BINARIES` + `dockerfile-parse` dep amendments** — S7-04 owns rows #8 + #9.
- **The plugin's `api.py` side-effect imports + loader wiring** — S8-03.
- **Probe-context conformance fence** — S7-05 owns.
- **End-to-end integration tests** — S12-02 / S12-03.
- **The Pydantic models becoming the source of truth (codegen path)**. Phase 7 keeps the JSON Schema files as the source of truth for cross-language consumers; the Pydantic models in `_models.py` are convenience mirrors. A future phase may invert this. **Do not** wire `pydantic-to-json-schema` codegen in this story — it's a Phase 8+ choice.

## Notes for the implementer

- **Rule 3 — surgical changes.** The envelope schema edit is two `$ref` lines + JSON-comma maintenance. Do not "improve adjacent code" — do not reformat the JSON, do not reorder existing keys, do not add a `$comment` describing the change. The byte-edit fence will fail on any of those. If `ruff`-on-JSON-files (if any) wants to reformat, configure it to skip this file rather than letting it sweep.
- **Rule 11 — match conventions.** Two-space indent if that's what the envelope already uses; trailing-newline policy matching the existing file; alphabetic key order under `properties.probes.properties`. Look before writing.
- **Rule 12 — fail loud.** If `jsonschema.validate` accepts a golden but you suspect a field shouldn't be allowed, **plant a violation** locally (add an `extra_key: "x"` to one golden) and verify the schema rejects it. The strict-additionalProperties walker is the load-bearing structural enforcer; thinness here will surface as wrong-shape slices reaching disk a phase later.
- **The `oneOf: [null, enum]` shape for `image_digest` + `reason` is intentional.** JSON Schema's `type: ["string", "null"]` is a valid alternative; `oneOf` is more explicit about the digest-pattern constraint. Either is defensible; pick one and apply uniformly.
- **The conditional `if/then` for `kind == "unknown"` is the open-question §8 commitment.** A future engineer who reads "the slice has `kind` and `reason`" and tries to set both `kind: "alpine", reason: "unrecognized_image"` is rejected by the schema — that is the design. The conditional rules out the schema-variant-explosion alternative.
- **Goldens are the contract.** Each golden file is a single JSON document — the expected slice payload, no wrapper, no metadata. Filename = fixture name (no `.expected.json` suffix; mirror Phase 2). Pretty-print with 2-space indent + trailing newline; UTF-8.
- **The `_models.py` Pydantic mirrors are convenience.** `mypy --strict` consumes them; downstream Python callers can import `BaseImageSlice` and get type-safe access. **Don't make them the source of truth.** The JSON Schema files are the cross-language contract.
- **Field-set ordering.** JSON has no key order in spec, but human readers care. Order keys as they appear in S7-01 AC-4 / S7-02 AC-9 — that's the canonical reading order. The schema's `required` list mirrors the order.
- **Envelope sibling order.** `base_image` lands alphabetically; `shell_invocation_trace` likewise. Verify against the existing alphabetic placement of `dockerfile`, `ci`, `language_detection`, etc. Failure to maintain alphabetic ordering may not break tests today but will produce noisy diffs in future phase amendments.
- **Token budget guard (Rule 6).** The schema files are the largest LOC artifact; budget accordingly. If you find yourself writing duplicate JSON for similar shapes (`stage_name` and `image_digest` both nullable), DO NOT extract a `$defs` shared subschema in this story — JSON Schema `$defs` indirection complicates the byte-edit fence's diff-shape assertion and is a Phase 8+ refactor (Open/Closed). Keep the schemas flat for now.
