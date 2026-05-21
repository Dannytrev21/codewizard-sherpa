# Story S13-03 — Amendment-A probe sub-schemas + envelope `$ref` wiring + ADR-0029 fence amendment

**Step:** Step 13 — Amendment-A gather deepening: source-side secret acquisition (G1) + target-image content inventory (G2)
**Status:** Ready
**Effort:** M
**Depends on:** S13-01 (`DockerfileSecretPatternProbe` slice shape pinned — this story serializes it as JSON Schema), S13-02 (`TargetImageContentProbe` slice shape pinned + the `crane` `ALLOWED_BINARIES` edit made — this story amends the **fence** that must permit that edit)

**ADRs honored:** [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) (this story is the **canonical implementer** of the Amendment-A byte-edit allowlist amendment — it grows `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` by the enumerated row-categories); [ADR-0009](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) (the byte-edit fence this story amends — the Ship-of-Theseus defense; the original 10 rows are untouched); [ADR-0018](../ADRs/0018-dockerfile-secret-pattern-probe.md) (`SecretPatternSlice` shape — schema'd here); [ADR-0019](../ADRs/0019-target-image-content-probe.md) (`TargetImageContentSlice` shape — schema'd here); [ADR-0028](../ADRs/0028-allowed-binaries-amendment-crane.md) (the `crane` `ALLOWED_BINARIES` row whose fence-allowlist entry this story adds); [ADR-0005](../ADRs/0005-probes-live-under-plugin-not-core-tree.md) (sub-schemas live under `plugins/distroless-migration--node--npm/schema/`, NOT `src/codegenie/schema/probes/`); [Phase 1 ADR-0004](../../01-context-gather-layer-a-node/ADRs/0004-per-probe-subschema-additional-properties-false.md) (per-probe sub-schemas `additionalProperties: false` at every node; envelope `probes.*` is `additionalProperties: true`); [Phase 0 ADR-0013](../../00-bullet-tracer-foundations/ADRs/0013-layered-additional-properties-schema.md) (envelope `properties.probes` is the integration seam — adding a probe requires landing its sub-schema **and** wiring a `$ref`); [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md) (extension by addition; Amendment A is the terminal growth of the Phase 7 allowlist).

## Context

This story closes the **schema seam** for both Amendment-A Step-13 probes — `DockerfileSecretPatternProbe` (S13-01) and `TargetImageContentProbe` (S13-02) — and is the **canonical implementer of the [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) fence amendment** for the Step-13 slice of Amendment A.

Three threads converge here:

1. **The schema seam (Phase 0 / Phase 1 discipline).** Every probe's slice is validated by a strict per-probe JSON Schema (`additionalProperties: false` recursively, [Phase 1 ADR-0004](../../01-context-gather-layer-a-node/ADRs/0004-per-probe-subschema-additional-properties-false.md)) and wired into the envelope schema (`src/codegenie/schema/repo_context.schema.json`) via `$ref` ([Phase 0 ADR-0013](../../00-bullet-tracer-foundations/ADRs/0013-layered-additional-properties-schema.md)). Without this story, the two new probes' outputs flow through the sanitizer unvalidated; with it, the envelope schema is the single source of truth for what an Amendment-A `repo-context.yaml` is allowed to contain. The sub-schemas live under the **plugin** per [ADR-0005](../ADRs/0005-probes-live-under-plugin-not-core-tree.md) — `plugins/distroless-migration--node--npm/schema/{secret_pattern,target_image_content}.schema.json` — exactly as S7-03 placed `base_image.schema.json` / `shell_invocation_trace.schema.json`.

2. **The fence amendment ([ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md)).** [ADR-0009](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) defined a closed 10-row byte-edit allowlist; [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) **amends** it (does not replace it) to enumerate every Amendment-A source-file addition by **row-category** — not as a glob (Option C, rejected: a glob cannot distinguish an additive new probe from an accidental edit to an existing one). This story adds the Step-13 slice of those rows to `tests/fence/test_phase7_no_byte_edits_to_locked_files.py`: the row-category for **new plugin-internal probe modules** (S13-01's + S13-02's probe files — wholly new files), the row-category for **new probe sub-schemas** (this story's two `*.schema.json` files), the row-category for **additive `$ref` insertions** into the envelope (this story's two `$ref` lines), and the row for **`src/codegenie/exec/__init__.py` `ALLOWED_BINARIES` gains `crane`** (S13-02's edit). The fence is the mechanical definition of "additive" — if S13-02's `crane` `exec/__init__.py` edit lands without this story's fence row, CI fails. **Story-ordering is load-bearing: this story must land alongside or before the file-adding stories' merge, per [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) §Consequences.**

3. **The planted-unauthorized-edit guard (Rule 12 — fail loud).** The fence is only worth its keep if it actually fails on an unauthorized edit. AC-9 requires a deliberately-planted edit to a locked file *outside* the amended allowlist to fail the fence with a helpful, ADR-citing message.

Golden fixtures land under `tests/golden/probes/{secret_pattern,target_image_content}/` per the existing Phase 1 / Phase 2 / S7-03 golden discipline (one JSON file per fixture, the file is the canonical expected slice). The S12 end-to-end / conformance tests round-trip **fixture → probe → schema → golden**; without the goldens this story produces, those tests have nothing to assert against.

## References — where to look

- **ADRs — primary sources of truth:**
  - `../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md` §Decision — the **eight row-categories** of the Amendment-A allowlist amendment; this story implements the Step-13 subset (categories 1, 2, 3, and the `crane` row of category 4). Read cover-to-cover; embed the row-category text in the fence file's docstring.
  - `../ADRs/0009-phase-7-byte-edit-allowlist-fence.md` §Decision — the original 10-row allowlist (untouched by this story) + §Consequences (the cross-link forward to ADR-0029).
  - `../ADRs/0018-dockerfile-secret-pattern-probe.md` — the `SecretPatternSlice` shape this story schema's.
  - `../ADRs/0019-target-image-content-probe.md` — the `TargetImageContentSlice` shape this story schema's.
  - `../ADRs/0005-probes-live-under-plugin-not-core-tree.md` — sub-schemas live under the plugin's `schema/`, not `src/codegenie/schema/probes/`.
- **Architecture:**
  - `../phase-arch-design.md §Component design — Amendment A §15 (DockerfileSecretPatternProbe slice fields)` + `§16 (TargetImageContentProbe slice fields)` — the canonical field lists.
  - `../phase-arch-design.md §Amendment A gaps` — "ADR-0029 amends ADR-0009's byte-edit allowlist for every Amendment-A source file."
- **Existing code / precedents:**
  - `src/codegenie/schema/repo_context.schema.json` — the envelope. **Read its current state before editing.** Note `properties.probes` is `additionalProperties: true` ([Phase 0 ADR-0013](../../00-bullet-tracer-foundations/ADRs/0013-layered-additional-properties-schema.md)); sibling `$ref` insertions land alphabetically.
  - `plugins/distroless-migration--node--npm/schema/base_image.schema.json` + `shell_invocation_trace.schema.json` + `_models.py` (S7-03) — the **structural template** for both new sub-schemas and the Pydantic-mirror discipline. Mirror the `$schema`, `$id`, `title`, recursive-`additionalProperties: false` exactly.
  - `tests/golden/probes/base_image/*.json` (S7-03) — golden-file format precedent: each file is the expected slice payload, no wrapper; filename = fixture name.
  - `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` (S5-01) — the fence this story amends. **Read S5-01 in full** for the `_PHASE7_BYTE_EDIT_ALLOWLIST` shape, the `_LOCKED_SURFACE_GLOBS` / `_PHASE7_OWNED_NEW_TREES` separation, the `diff_source` dependency-injection seam, and the planted-violation `test_synthetic_violations_caught` matrix.
- **Story-pipeline neighbors:**
  - `S13-01-dockerfile-secret-pattern-probe.md` AC-4 — the `SecretPatternSlice` shape this story encodes.
  - `S13-02-target-image-content-probe.md` AC-7 — the `TargetImageContentSlice` shape this story encodes; AC-19 — the fence-row dependency this story satisfies.
  - `S7-03-probe-sub-schemas-and-goldens.md` — the precedent schema-seam story; mirror its sub-schema + envelope-`$ref` + golden discipline.
  - `S5-01-phase7-byte-edit-allowlist-fence.md` — the fence whose allowlist this story amends.

## Goal

Land two new JSON Schema files under the plugin (`plugins/distroless-migration--node--npm/schema/{secret_pattern,target_image_content}.schema.json`), each `additionalProperties: false` at every node, encoding the slice shapes pinned by S13-01 + S13-02. Land **exactly two `$ref` insertions** in `src/codegenie/schema/repo_context.schema.json` — one per probe — and nothing else. Amend `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` per [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) so the fence permits the Step-13 Amendment-A additions (the two new probe modules, the two new sub-schemas, the two `$ref` insertions, and S13-02's `crane` `ALLOWED_BINARIES` row) while still failing on any *unenumerated* edit to a locked file. Land the golden fixtures under `tests/golden/probes/{secret_pattern,target_image_content}/`.

## Acceptance criteria

**Sub-schema files (AC-1 through AC-4)**
- [ ] **AC-1** `plugins/distroless-migration--node--npm/schema/secret_pattern.schema.json` exists. Top-level: `$schema = "https://json-schema.org/draft/2020-12/schema"`, `$id = "https://codewizard-sherpa.dev/schema/probes/secret_pattern.schema.json"`, `title = "SecretPatternSlice"`, `type = "object"`, `additionalProperties: false`. Required keys: `["patterns", "confidence"]`. Each `pattern` entry: `additionalProperties: false`, required `["dockerfile_path", "kind", "instruction_index", "instruction", "referenced_env", "referenced_path", "opaque"]`; `kind` is an `enum` of exactly the five S13-01 values `["buildkit_secret_mount", "env_arg_injection", "file_copy_credential", "auth_header_fetch", "external_script"]`; `referenced_env` / `referenced_path` are `["string", "null"]`; `opaque` is `boolean`; `instruction_index` is `integer, minimum 0`. **`additionalProperties: false` at EVERY object node** — verified by `tests/unit/schema/test_secret_pattern_schema_strict.py::test_every_object_has_additional_properties_false` (recursive JSON-tree walk).
- [ ] **AC-2** `plugins/distroless-migration--node--npm/schema/target_image_content.schema.json` exists. Top-level: same `$schema` / `$id` pattern, `title = "TargetImageContentSlice"`, `type = "object"`, `additionalProperties: false`. Required keys: `["target_image", "target_digest", "preinstalled_packages", "preinstalled_users", "ca_certificates", "shell_present", "default_workdir", "default_entrypoint", "supported_architectures", "already_satisfied_run_lines", "confidence"]`. `preinstalled_users` is an array of objects with `additionalProperties: false` and required `["name", "uid", "gid"]` (`uid`/`gid` `integer, minimum 0`); `target_digest` matches `^sha256:[0-9a-f]{64}$`; `default_workdir` is `["string", "null"]`; `default_entrypoint`, `preinstalled_packages`, `supported_architectures`, `already_satisfied_run_lines` are `array` of `string`. Same recursive-`additionalProperties:false` walker test (`test_target_image_content_schema_strict.py`).
- [ ] **AC-3** **Closed `kind` enum + `opaque` consistency for the secret-pattern schema.** The `secret_pattern` schema asserts via `if/then` (or `allOf`-with-`if/then`): `if kind == "external_script" then opaque == true else opaque == false`. Verified by parametrized rows: `{kind: "external_script", opaque: false}` → invalid; `{kind: "external_script", opaque: true}` → valid; `{kind: "file_copy_credential", opaque: true}` → invalid; `{kind: "file_copy_credential", opaque: false}` → valid. This encodes S13-01's "`opaque is True` iff `kind == external_script`" invariant in the schema so a malformed slice cannot reach disk.
- [ ] **AC-4** `mypy --strict`-compatible frozen Pydantic v2 models mirroring both schemas land in `plugins/distroless-migration--node--npm/schema/_models.py` (extend the S7-03 file additively — do **not** create a second `_models.py`): `SecretPatternSlice`, `SecretPattern`, `TargetImageContentSlice`, `PreinstalledUser`. Each `model_config = ConfigDict(frozen=True, extra="forbid")`; `Literal[...]` for `kind` / `confidence`. A round-trip test asserts `Slice.model_validate(json.load(open(golden))).model_dump(mode="json") == json.load(open(golden))` for every new golden file.

**Envelope `$ref` insertions (AC-5 through AC-7) — ADR-0029 row-category 3**
- [ ] **AC-5** `src/codegenie/schema/repo_context.schema.json` gains **exactly two** new `$ref` entries under `properties.probes.properties` — keys `"dockerfile_secret_pattern"` and `"target_image_content"` — each mapping to `{"$ref": "<resolvable-path>/<schema-file>.json"}` pointing at the plugin's `schema/` files. The `$ref` targets resolve correctly from the envelope file location — verified by loading the envelope with `jsonschema` and validating a golden slice of each probe against it.
- [ ] **AC-6** **Diff discipline** — `git diff src/codegenie/schema/repo_context.schema.json` shows exactly: (a) two new `$ref` entries, (b) commas / brackets adjusted to keep the JSON syntactically valid, (c) nothing else. Verified by `tests/fence/test_amendment_a_envelope_diff_shape.py` which re-loads the envelope from the pre-Amendment-A baseline + current, computes the structural diff, and asserts the only changes are the two named `$ref` additions. **No `additionalProperties` flip, no top-level key addition, no sibling `$ref` removal.**
- [ ] **AC-7** The two `$ref` insertions land alphabetically among the existing `properties.probes.properties` keys (mirroring S7-03's `base_image` / `shell_invocation_trace` placement). Verified by `test_envelope_probe_keys_sorted` which asserts `properties.probes.properties` key order is non-decreasing.

**Fence amendment (AC-8 through AC-11) — ADR-0029, the canonical implementer**
- [ ] **AC-8** `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` is amended so the fence **passes** with the Step-13 Amendment-A additions present: the two new probe modules (`dockerfile_secret_pattern_probe.py`, `target_image_content_probe.py`), the two new sub-schemas, the two envelope `$ref` insertions, and S13-02's `crane` row in `src/codegenie/exec/__init__.py`. The amendment adds the [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) row-categories (1: new plugin-internal probe modules; 2: new probe sub-schemas; 3: additive envelope `$ref`; 4: `ALLOWED_BINARIES` gains `crane`) to the fence's allowlist data structure, **each row carrying an inline `# adr:` comment naming its owning ADR**. The original [ADR-0009](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) 10 rows are **untouched** — verified by `test_original_adr_0009_rows_unchanged` asserting the original 10-path set is still a subset of the allowlist with byte-identical paths.
- [ ] **AC-9** **Planted-unauthorized-edit guard (Rule 12 — the load-bearing assertion).** A parametrized planted-violation case injects (via the `diff_source` dependency-injection seam established in S5-01) a synthetic edit to a locked file **outside** the amended allowlist — e.g. `src/codegenie/coordinator/coordinator.py` — and asserts the fence **fails** with an error message containing the literal path AND the strings `"ADR-0029"` (or `"ADR-0009"`) AND `"byte-edit allowlist"` AND `"ADR amendment required"`. A complementary positive case injects a synthetic ADD of `plugins/distroless-migration--node--npm/probes/dockerfile_secret_pattern_probe.py` and asserts the fence **passes** (the amended allowlist now permits it). Both halves are required — the fence must fail on the unauthorized edit *and* pass on the authorized one.
- [ ] **AC-10** **The `crane` `exec/__init__.py` row specifically.** A parametrized case injects a synthetic edit to `src/codegenie/exec/__init__.py` and asserts the fence **passes** (S13-02's `crane` `ALLOWED_BINARIES` row is authorized by [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) row-category 4). Before this story's amendment, that same synthetic edit would fail the fence — a meta-comment in the test cites that the fence row is what makes S13-02's edit legal, closing the story-ordering dependency S13-02 AC-19 names.
- [ ] **AC-11** **ADR-drift guard.** `test_amendment_a_allowlist_matches_adr_0029` parses [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) §Decision (regex over the row-category list) and asserts the fence's Amendment-A allowlist data structure enumerates the same row-categories — drift between the fence code and the ADR fails CI loudly. Mirrors S5-01 AC-2.b.

**Golden files (AC-12 through AC-16)**
- [ ] **AC-12** `tests/golden/probes/secret_pattern/buildkit-mount.json` — fixture `secret-buildkit-mount/Dockerfile` (S13-01 AC-8). One pattern, `kind: "buildkit_secret_mount"`, `referenced_env: "npmtoken"`, `opaque: false`, `confidence: "high"`.
- [ ] **AC-13** `tests/golden/probes/secret_pattern/external-script.json` — fixture `secret-external-script/Dockerfile` (S13-01 AC-12). One pattern, `kind: "external_script"`, `opaque: true`, `referenced_path: "/tmp/fetch-creds.sh"`, `confidence: "medium"` (opaque downgrade).
- [ ] **AC-14** `tests/golden/probes/secret_pattern/empty.json` — fixture with no secret acquisition (S13-01 AC-13). `patterns: []`, `confidence: "high"`.
- [ ] **AC-15** `tests/golden/probes/target_image_content/chainguard-distroless.json` — fixture `chainguard-distroless` (S13-02 AC-9). `shell_present: false`, `preinstalled_users` contains `{name: "nonroot", uid: 65532, ...}`, `ca_certificates: true`, `confidence: "high"`.
- [ ] **AC-16** `tests/golden/probes/target_image_content/chainguard-with-shell.json` — fixture `chainguard-with-shell` (S13-02 AC-10). `shell_present: true`, `confidence: "high"`. AC-15 + AC-16 are a true/false `shell_present` pair so the goldens themselves prove `shell_present` is evidence-derived.

**Schema-validates-golden round-trip (AC-17)**
- [ ] **AC-17** `tests/unit/schema/test_amendment_a_goldens_validate_against_subschemas.py` — for each of the five new golden files, load the corresponding sub-schema and assert `jsonschema.validate(golden_slice, sub_schema)` passes. Parametrized over the five fixtures; any golden that fails validation is a story-level red. The same test also validates each golden against the **envelope** schema (wrapped under `probes.<probe_name>`) to prove the `$ref` wiring resolves end-to-end.

**Lint + fence (AC-18, AC-19)**
- [ ] **AC-18** `tests/fence/test_every_probe_subschema_has_additional_properties_false.py` (the S7-03 / Phase 1 recursive fence) is extended (or a parametrized case added) to cover both new sub-schemas — every `type: "object"` node carries `additionalProperties: false`. A planted-violation parametrized case flips one node to `true` and asserts the walker fires.
- [ ] **AC-19** `mypy --strict plugins/distroless-migration--node--npm/schema/_models.py` clean; `ruff check`, `ruff format --check` clean; `make lint-imports` green; `make fence` exit 0; the full `make check` regression suite green.

## Implementation outline

1. **Read the pre-Amendment-A baselines first.** Open `src/codegenie/schema/repo_context.schema.json` and find `properties.probes.properties` — note the alphabetic key order and the `additionalProperties: true` at `properties.probes`. Open `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` (S5-01) and find the `_PHASE7_BYTE_EDIT_ALLOWLIST` data structure, the `_LOCKED_SURFACE_GLOBS` / `_PHASE7_OWNED_NEW_TREES` split, and the `diff_source` dependency-injection seam. Plan both diffs minimal.

2. **Write `plugins/distroless-migration--node--npm/schema/secret_pattern.schema.json`** mirroring the S7-03 `base_image.schema.json` structural template — recursive `additionalProperties: false`, the closed five-value `kind` enum, the `if/then` `opaque`-consistency conditional (AC-3). Validate against the three secret-pattern goldens locally before declaring AC-1 green.

3. **Write `plugins/distroless-migration--node--npm/schema/target_image_content.schema.json`** by the same pattern — recursive `additionalProperties: false`, the `preinstalled_users` nested-object array, the `target_digest` `sha256:` pattern. Validate against the two target-image goldens.

4. **Extend `plugins/distroless-migration--node--npm/schema/_models.py`** (the S7-03 file) **additively** with the four new frozen Pydantic v2 models. `Literal[...]` for the enums; `ConfigDict(frozen=True, extra="forbid")`. Do not create a second `_models.py`.

5. **Edit `src/codegenie/schema/repo_context.schema.json`** — surgical. Two `$ref` entries under `properties.probes.properties`, alphabetically placed, each pointing at the plugin's `schema/` file. The diff is two contiguous `$ref` lines + JSON-comma maintenance — the minimum surface area.

6. **Amend `tests/fence/test_phase7_no_byte_edits_to_locked_files.py`** per [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md):
   - Add the Amendment-A allowlist data structure (the row-categories) to the fence — implemented as additional rows in `_PHASE7_BYTE_EDIT_ALLOWLIST` for the enumerated edits (the `crane` `exec/__init__.py` row; the two `$ref` insertions, which are already covered by the existing envelope-schema row #4 *for two more `$ref`s* — confirm whether ADR-0029 widens row #4 or adds a new row, and follow the ADR text exactly) **and** as additions to `_PHASE7_OWNED_NEW_TREES` / the new-probe-module recognition for the new `*.py` and `*.schema.json` files. Each new row carries an inline `# adr:` comment.
   - Amend the module docstring to cross-link [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) alongside [ADR-0009](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md), and embed the Amendment-A row-category text.
   - Add the `test_amendment_a_allowlist_matches_adr_0029` ADR-drift guard, the `test_original_adr_0009_rows_unchanged` guard, and the AC-9 / AC-10 planted-violation parametrized cases (via the existing `diff_source` injection seam — **no working-tree mutation**, per S5-01's discipline).

7. **Write the five golden files** under `tests/golden/probes/{secret_pattern,target_image_content}/`. Generate the initial content by running S13-01's / S13-02's probes against their fixtures with stub clients; pretty-print with 2-space indent + trailing newline; hand-verify the field set against S13-01 AC-4 / S13-02 AC-7.

8. **Write tests:** `test_secret_pattern_schema_strict.py`, `test_target_image_content_schema_strict.py`, `test_amendment_a_goldens_validate_against_subschemas.py`, `test_amendment_a_subschema_pydantic_round_trip.py`, `test_amendment_a_envelope_diff_shape.py`, plus the fence-amendment tests inside `test_phase7_no_byte_edits_to_locked_files.py`.

## TDD plan — red / green / refactor

**Red 1** — write `test_amendment_a_goldens_validate_against_subschemas.py`. Pytest fails: the sub-schemas do not exist; the goldens do not exist. Right failure — the schema artifacts are absent.

**Green 1** — land `secret_pattern.schema.json`, `target_image_content.schema.json`, the five goldens. The validation test now collects but fails until the schemas accept the goldens.

**Red 2** — write `test_secret_pattern_schema_strict.py` (the recursive `additionalProperties: false` walker + the `if/then` `opaque`-consistency matrix). Initially red — the schema does not carry `additionalProperties: false` deep enough or does not enforce the conditional.

**Green 2** — iterate both schemas until every object node has `additionalProperties: false` AND the `external_script ⟺ opaque` conditional fires.

**Red 3** — write `test_amendment_a_envelope_diff_shape.py` against the pre-Amendment-A baseline. Pytest fails — the envelope has not been edited.

**Green 3** — surgically insert the two `$ref` lines into `repo_context.schema.json`. Re-run; green.

**Red 4** — write the fence-amendment tests inside `test_phase7_no_byte_edits_to_locked_files.py`: AC-9's planted-unauthorized-edit case (`coordinator.py`) and AC-10's authorized-`exec/__init__.py` case. Before amending the allowlist, AC-10's case is **red** (the fence rejects the `crane` edit) and AC-9's authorized-positive half is **red** (the fence rejects the new probe module). This is the right red: the fence is correctly strict and has not yet been amended.

**Green 4** — amend `_PHASE7_BYTE_EDIT_ALLOWLIST` (+ the new-probe-module / sub-schema recognition) per [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md). AC-10 + AC-9's positive half go green; AC-9's negative half (`coordinator.py` still fails the fence) stays green — the amendment widens the allowlist by exactly the enumerated rows, not by a glob.

**Red 5** — write `test_amendment_a_subschema_pydantic_round_trip.py`. Fails because `_models.py` lacks the four new models.

**Green 5** — extend `_models.py`; round-trip green.

**Refactor** — confirm the original [ADR-0009](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) 10 rows are byte-identical (`test_original_adr_0009_rows_unchanged`); confirm `test_amendment_a_allowlist_matches_adr_0029` (the ADR-drift guard) passes; verify all new tests green and `make check` + `make fence` pass.

## Files to touch

**New files:**

| Path | Purpose |
|---|---|
| `plugins/distroless-migration--node--npm/schema/secret_pattern.schema.json` | `SecretPatternSlice` sub-schema (AC-1, AC-3) |
| `plugins/distroless-migration--node--npm/schema/target_image_content.schema.json` | `TargetImageContentSlice` sub-schema (AC-2) |
| `tests/golden/probes/secret_pattern/buildkit-mount.json` | AC-12 golden |
| `tests/golden/probes/secret_pattern/external-script.json` | AC-13 golden (opaque) |
| `tests/golden/probes/secret_pattern/empty.json` | AC-14 golden |
| `tests/golden/probes/target_image_content/chainguard-distroless.json` | AC-15 golden (`shell_present: false`) |
| `tests/golden/probes/target_image_content/chainguard-with-shell.json` | AC-16 golden (`shell_present: true`) |
| `tests/unit/schema/test_secret_pattern_schema_strict.py` | AC-1, AC-3 (recursive walker + `opaque` matrix) |
| `tests/unit/schema/test_target_image_content_schema_strict.py` | AC-2 (recursive walker) |
| `tests/unit/schema/test_amendment_a_goldens_validate_against_subschemas.py` | AC-17 (golden → sub-schema + envelope round-trip) |
| `tests/unit/schema/test_amendment_a_subschema_pydantic_round_trip.py` | AC-4 (`_models.py` round-trip) |
| `tests/fence/test_amendment_a_envelope_diff_shape.py` | AC-6, AC-7 (envelope diff discipline) |

**Edited files (authorized — Amendment-A byte-edit allowlist, [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md)):**

| Path | Edit | Authorizing ADR |
|---|---|---|
| `src/codegenie/schema/repo_context.schema.json` | exactly two `$ref` insertions under `properties.probes.properties` | [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) row-category 3 |
| `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` | amend the allowlist with the Amendment-A row-categories; add the fence-amendment tests (AC-8 through AC-11) | [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) §Consequences (this story is the canonical implementer) |
| `plugins/distroless-migration--node--npm/schema/_models.py` | additively extend with the four new Pydantic models (plugin-owned file, outside fence scope) | [ADR-0019](../ADRs/0019-target-image-content-probe.md) / [ADR-0018](../ADRs/0018-dockerfile-secret-pattern-probe.md) |
| `tests/fence/test_every_probe_subschema_has_additional_properties_false.py` | extend to cover the two new sub-schemas (`tests/` file, outside fence scope) | [Phase 1 ADR-0004](../../01-context-gather-layer-a-node/ADRs/0004-per-probe-subschema-additional-properties-false.md) |

**Files NOT touched:** S13-01's / S13-02's probe modules (consumed for slice shape, never edited); `src/codegenie/exec/__init__.py` (S13-02 makes the `crane` edit; this story only adds the *fence row* that permits it — the two must land in the same PR window).

## Out of scope

- **The two Amendment-A probes themselves** — `DockerfileSecretPatternProbe` (S13-01) and `TargetImageContentProbe` (S13-02). This story consumes their pinned slice shapes and serializes them; it does not implement probe behavior.
- **The `crane` `ALLOWED_BINARIES` edit** — S13-02 makes the one-line `src/codegenie/exec/__init__.py` edit. This story adds the **fence-allowlist row** that authorizes it (AC-10) — the edit and the fence row must land in the same PR window, or this story first.
- **The remaining Amendment-A row-categories** — [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) enumerates eight; this story implements the Step-13 subset (the two probe modules, their sub-schemas, their `$ref`s, the `crane` row). The `outcomes.py` refusal variants (category 5, Step 16), the `NodeManifestProbe native_modules` field (category 6, Step 14), the `data/` catalogs (category 7, Step 14), and the `tccm.yaml must_read` additions (category 8) are owned by their own Amendment-A stories. **Each of those stories amends the fence allowlist for its own rows** — this story does not pre-add rows for files it does not create (that would make the fence permit a not-yet-existing file, defeating the row-by-row discipline of [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) §Decision).
- **The fence mechanism itself** (the diff-walking scanner, the `diff_source` injection seam) — S5-01 owns it. This story amends the *allowlist data*, not the scanner.
- **A second per-phase byte-edit allowlist fence** — forbidden by [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md). Amendment A is the **terminal** growth of the Phase 7 allowlist; do not design `_AMENDMENT_B_*` seams. S5-01 AC-12's terminal-allowlist guard still holds — verify it stays green after this story's amendment.
- **End-to-end / conformance tests** that round-trip fixture → probe → schema → golden at the pipeline level — S12-02 / S12-03 own those. This story produces the goldens those tests assert against.

## Notes for the implementer

- **Rule 3 — surgical changes.** The envelope-schema edit is two `$ref` lines + JSON-comma maintenance. Do **not** reformat the JSON, reorder existing keys, or add a `$comment` — the byte-edit fence (and AC-6's diff-shape test) will fail on any of those. If a JSON formatter wants to sweep the file, configure it to skip `repo_context.schema.json`.
- **Rule 8 — read before you write.** Read S5-01's `test_phase7_no_byte_edits_to_locked_files.py` cover-to-cover before amending it. The fence has a deliberate `_LOCKED_SURFACE_GLOBS` vs `_PHASE7_OWNED_NEW_TREES` split — net-new files under `plugins/distroless-migration--node--npm/**` are *already* outside the fence's scope (S5-01 AC-5.h), so the two new probe modules and the two new sub-schemas under that tree may need **no allowlist row at all** — only the *edits to existing files* (`exec/__init__.py`, `repo_context.schema.json`) need rows. Follow [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) §Decision exactly: it enumerates row-categories for "new plugin-internal probe modules" and "new probe sub-schemas" — confirm whether those are *recognized as out-of-scope new trees* or *enumerated allowlist rows* in the fence's implementation, and match the ADR. If the ADR text and the S5-01 fence implementation genuinely disagree, **STOP and surface it in `_attempts/S13-03.md`** (Rule 7) — the fix is an ADR clarification, not a silent reconciliation.
- **Rule 12 — fail loud.** AC-9 is the load-bearing assertion: the amended fence must still **fail** on an unauthorized edit (`coordinator.py`) with a helpful, ADR-citing message. A fence that passes everything is worse than no fence — it gives false confidence. Plant the violation via the `diff_source` injection seam (no working-tree mutation, per S5-01's discipline) and verify the red.
- **Rule 11 — match conventions.** S7-03 is the precedent for everything here: the sub-schema structural template, the `$id` URL pattern, the golden-file format (no wrapper, filename = fixture name, 2-space indent, trailing newline, UTF-8), the alphabetic `$ref` placement, and the additive `_models.py` extension. Mirror it.
- **The `external_script ⟺ opaque` conditional (AC-3) is the schema encoding S13-01's invariant.** S13-01 says `opaque is True` iff `kind == external_script`. Encoding that as an `if/then` in the schema means a malformed slice (`external_script` with `opaque: false`, or a non-script kind with `opaque: true`) is rejected *before it reaches disk* — the schema makes the invariant mechanical, not just a probe-side convention.
- **The original ADR-0009 10 rows are immutable here.** [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) §Decision is explicit: ADR-0009 stays the historical 10-row record; this story *adds* rows, never edits the 10. `test_original_adr_0009_rows_unchanged` (AC-8) is the guard. If you find yourself editing one of the original 10 paths, you have misread the amendment.
- **Story-ordering is load-bearing.** [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) §Consequences: "the fence-allowlist rows land alongside (or before) the files they permit, or the file-adding PR fails CI." S13-02's `crane` `exec/__init__.py` edit **cannot merge** until this story's fence row exists. Record the chosen sequencing (same PR, or S13-03 first) in `_attempts/S13-03.md`.
- **Token-budget guard (Rule 6).** The two schema files are the largest LOC artifact. If similar nullable shapes recur (`referenced_env` / `referenced_path` both `["string","null"]`), do **NOT** extract a `$defs` shared subschema — JSON Schema `$defs` indirection complicates the diff-shape fence and is a Phase 8+ refactor (Open/Closed, S7-03's precedent note). Keep the schemas flat. If the story approaches budget, land the two sub-schemas + goldens first (a self-contained green), then the fence amendment as a second focused pass.
