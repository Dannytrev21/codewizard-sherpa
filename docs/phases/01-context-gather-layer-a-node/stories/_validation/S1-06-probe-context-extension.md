# Validation report — S1-06 `ProbeContext` extension (`parsed_manifest` + `input_snapshot`)

**Story:** [S1-06-probe-context-extension.md](../S1-06-probe-context-extension.md)
**Validated:** 2026-05-14
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

The goal — amend `ProbeContext` with two additive `None`-defaulting fields (`parsed_manifest`, `input_snapshot`) plus a frozen `InputFingerprint` newtype, regenerate the Phase 0 ADR-0007 contract snapshot, and lock the surface so a third future field fails CI with an ADR-0002 pointer — is correct in intent and matches `phase-arch-design.md §"Data model"`, `§"Component design" #3`, `§"Gap analysis" Gap 1`, ADR-0002 (parsed_manifest portion), and `High-level-impl.md §"Constraints" (input_snapshot widening)`.

**The draft, however, prescribed mechanics that are structurally incompatible with the Phase 0 contract test surface that S2-02 actually shipped.** Five block-tier defects and twelve harden-tier gaps were identified. The most load-bearing:

1. **Script filename is wrong.** Story says `scripts/regen_probe_contract.py`; the file shipped by S2-02 is `scripts/regen_probe_contract_snapshot.py` ([scripts/regen_probe_contract_snapshot.py:1](../../../../scripts/regen_probe_contract_snapshot.py)). Two tests import from this exact path ([tests/unit/test_probe_contract.py:31-35](../../../../tests/unit/test_probe_contract.py)).
2. **`ALLOWED_PROBECONTEXT_FIELDS` doesn't exist.** The Phase 0 snapshot uses a dynamic `structural_signature(module)` walk (`scripts/regen_probe_contract_snapshot.py:182`) — there is no script-side constant to extend. Adding one is duplicative; the snapshot+regen workflow already makes a third future field fail CI. The right place for the *explicit ADR-0002 sentinel* is a dedicated test inside `tests/unit/test_probe_contract.py`, not a script constant.
3. **The prescribed `from codegenie.coordinator.input_snapshot import InputFingerprint` breaks the Phase 0 stdlib-only fence** on `base.py`. `ALLOWED_BASE_PY_IMPORTS = {"abc", "dataclasses", "logging", "pathlib", "typing"}` ([tests/unit/test_probe_contract.py:53](../../../../tests/unit/test_probe_contract.py)) — any non-stdlib import on `base.py` fails `test_base_py_imports_are_stdlib_only`. Likewise `from collections.abc import Callable, Mapping` requires widening the fence to add `"collections"`.
4. **The prescribed `CODEOWNERS` edit collides with the existing S5-02 TODO.** `base.py` carries `# TODO(S5-02): CODEOWNERS entry required for src/codegenie/probes/base.py, docs/localv2.md, tests/snapshots/ — see ADR-0007 §Reversibility` ([src/codegenie/probes/base.py:16](../../../../src/codegenie/probes/base.py)), and `test_base_py_carries_codeowners_todo_for_s5_02` ([tests/unit/test_probe_contract.py:324](../../../../tests/unit/test_probe_contract.py)) pins it. S1-06 must **preserve the TODO**; CODEOWNERS is S5-02's job.
5. **No AC pins the `localv2.md §4` doc update.** Phase 0 ADR-0007 says "the source of truth is `localv2.md`; any drift is *always* resolved by changing code to match the doc, never the inverse." The Phase 0 snapshot pins `doc_fingerprint = sha256(extract_section_4_body(localv2.md))` ([tests/unit/test_probe_contract.py:103-107](../../../../tests/unit/test_probe_contract.py)). If the code amends `ProbeContext` without the §4 block being amended in the same PR, the `doc_fingerprint` ⇄ code consistency is broken at *intent level* even though both can be made to match a regenerated snapshot. The ADR-0002 amendment must include the §4 doc edit — and the story must call that out.

Plus secondary issues: input-snapshot fields not pinned for type (a mutation could swap `frozenset` → `set` and pass); no test of Phase-0 construction-with-kwargs still working; no test pinning the type-annotation shape on the two new fields (the snapshot test catches it but a dedicated mutation-killer makes the intent explicit); the `_yarn`/`_pnpm` parsers (S1-07/S1-08) don't yet exist so the import-cycle claim in the story's note 3 was not validated against actual layering.

Three additional Stage-2D (Design-Patterns) findings:

- **Newtype location is wrong** for the stated layering. `InputFingerprint` belongs *in* `base.py` (alongside `ProbeContext` — it is a contract type, not a coordinator implementation type), so the optional `frozenset[InputFingerprint] | None` annotation type-checks without crossing the stdlib-only fence. Defining it in `coordinator/input_snapshot.py` (a) breaks the fence, (b) inverts the dependency arrow (contract types should not depend on a worker package), and (c) requires `TYPE_CHECKING` + `ForwardRef` gymnastics that complicate the snapshot's `f.type` repr.
- **`parsed_manifest` callable type should use `Mapping[str, Any]` not `Mapping[str, JSONValue]` at the base.py boundary.** `JSONValue` lives in `coordinator/validator.py` (`__all__ = ["JSONValue", ...]` at line 43) — importing it would cycle (`coordinator/validator.py` imports `probes.base.ProbeOutput`). The validator narrowing belongs downstream at `_ProbeOutputValidator`; at the contract surface the type stays loose-and-stdlib (`Any`). The Phase 0 §4 `dict[str, Any]` precedent on `RepoSnapshot.config`, `ProbeContext.config`, `ProbeOutput.schema_slice`, `Task.options` is the architectural precedent.
- **The "third future field fails CI" sentinel deserves its own named test, not a script constant.** Putting the assertion in the regen script is a smell: the script's job is *to regenerate the snapshot*, not to assert correctness. The dedicated test belongs in `tests/unit/test_probe_contract.py` next to the existing structural-signature tests, named explicitly (`test_probe_context_field_list_matches_adr_0002_amendment`), with a failure message that links to ADR-0002. This is the Open/Closed pattern at the file boundary: a contract change is a *test change* and a *snapshot change*, gated by ADR-0002, not a quiet script-internal assertion.

No `NEEDS RESEARCH` findings — every weakness is answerable from the Phase 0 source tree, ADR-0002, ADR-0007, `localv2.md §4`, and the existing structural-signature test ladder shipped by S2-02. Stage 3 skipped.

The synthesizer expanded ACs from **10 single-bullet items to 18 individually verifiable ACs**, rewrote the TDD plan with ~14 named tests each annotated with its AC and the mutation it catches, moved `InputFingerprint` into `base.py`, replaced the script-side constant with a dedicated test, widened `ALLOWED_BASE_PY_IMPORTS` by exactly `"collections"`, added a `localv2.md §4` doc-update AC, removed the spurious CODEOWNERS-edit AC, added the ADR-0002 amendment-text update AC, and surfaced the design-pattern observations under `Notes for the implementer`.

## Context Brief (Stage 1)

- **Goal as written:** Append `parsed_manifest` and `input_snapshot` to `ProbeContext` with `None` defaults; ship `InputFingerprint`; regenerate the contract snapshot; encode the allowed field list so a third future field fails CI with an ADR-0002 pointer.
- **Phase docs touched:**
  - `phase-arch-design.md §"Data model"` — shape (only `parsed_manifest` shown; arch is internally inconsistent on the count, but `High-level-impl.md §"Constraints"` + `§"Gap analysis" Gap 1` both confirm two-field landing under the same ADR-0002 amendment).
  - `phase-arch-design.md §"Component design" #3` — `parsed_manifest: Callable | None` is the seam, callable signature consumes a path and returns a `Mapping`.
  - `phase-arch-design.md §"Gap analysis" Gap 1` — `input_snapshot: frozenset[InputFingerprint] | None`; rationale: pre-dispatch fingerprint pass closes the TOCTOU window between `declared_inputs` content-hashing and parse-time `os.stat`.
  - `phase-arch-design.md §"Edge cases"` row 12 — `ctx.parsed_manifest is None` defensive check.
  - ADR-0002 (this phase) — amend in this story to include `input_snapshot` (or write a sibling ADR-0002a; story prefers in-place amendment per High-level-impl).
- **Phase 0 contract (load-bearing):**
  - ADR-0007 (Phase 0): `localv2.md §4` is the source of truth. Code-vs-doc drift is *always* resolved by changing code to match the doc — meaning the doc must be amended **first** in the same PR.
  - S2-02 contract snapshot: lives at `tests/snapshots/probe_contract.v1.json`, with both `doc_fingerprint` and `structural_signature` halves pinned ([tests/unit/test_probe_contract.py:103-113](../../../../tests/unit/test_probe_contract.py)).
  - Regen script: `scripts/regen_probe_contract_snapshot.py` (not `regen_probe_contract.py`).
  - `ALLOWED_BASE_PY_IMPORTS = {"abc", "dataclasses", "logging", "pathlib", "typing"}` — every import added to `base.py` requires either being in this set or widening it (the widening itself is part of the S1-06 ADR-0002 amendment scope).
  - `test_base_py_carries_codeowners_todo_for_s5_02` pins `TODO(S5-02): CODEOWNERS entry required` in `base.py`. CODEOWNERS routing is S5-02's job; S1-06 must preserve the TODO, **not** add the CODEOWNERS entry.
- **Phase 0 type precedent:** `RepoSnapshot.config: dict[str, Any]`, `ProbeContext.config: dict[str, Any]`, `ProbeOutput.schema_slice: dict[str, Any]`, `Task.options: dict[str, Any]` — the contract surface uses `Any` at the dict/Mapping boundary. `JSONValue` narrowing lives in `coordinator/validator.py` ([src/codegenie/coordinator/validator.py:43-60](../../../../src/codegenie/coordinator/validator.py)) and is enforced at probe-emit time by `_ProbeOutputValidator`. S1-06's `parsed_manifest` callable annotation should respect this layering: `Callable[[Path], Mapping[str, Any] | None] | None`.
- **Open ambiguities surfaced:**
  1. **Arch goal #4 says "zero edits to base.py"** ([phase-arch-design.md:21](../phase-arch-design.md)) but `§"Data model"`, `§"Component design" #3`, ADR-0002, and `High-level-impl.md` all require the edit. The intent is clear (the edit is allowed because it's ADR-gated and additive); goal #4 is aspirational shorthand. The story is correct to amend. Validator surfaces this contradiction explicitly in the synthesizer report so it's visible.
  2. **ADR-0002 only formally documents `parsed_manifest`** (line 24: "exposes it to each probe via `ProbeContext.parsed_manifest`"). The Consequences section names `input_snapshot` as a "future amendment to this ADR if Phase 14's concurrent-gather threat model demands it" (line 51). `High-level-impl.md` line 31 then says "same ADR-0002 amendment, scoped to two fields". S1-06 must therefore include an ADR-0002 amendment edit — pinned as an AC.
  3. **`InputFingerprint` location.** Story says `src/codegenie/coordinator/input_snapshot.py`. Validator moves it to `src/codegenie/probes/base.py` (contract type, lives with the contract; preserves stdlib-only fence; preserves DIP — contract types must not import from worker packages). The `path: str` (not `Path`) keeps the NamedTuple hashable across platforms and avoids the case-sensitivity-on-macOS-comparison footgun.
  4. **`parsed_manifest` type narrowness.** Story specifies `Mapping[str, JSONValue]`. Validator narrows to `Mapping[str, Any]` at the contract boundary — `JSONValue` import would cycle and break the stdlib fence; the validator pass downstream re-narrows. Phase 0 precedent supports the looser boundary type.

## Stage 2 — critic reports (synthesized in-head from S1-02/03/04/05 precedent + this story's specifics)

The Phase 0 contract test surface is now well-known from S2-02's shipped artifacts. The validator skill's parallel-subagent fan-out is omitted in this case (token economy):

- Every recurring finding from prior validation reports reappears identically here (markers-only construction, structured-field event assertions, default-None pinning, fence-imports widening).
- All story-specific deltas required first-principles analysis against `scripts/regen_probe_contract_snapshot.py`, `tests/unit/test_probe_contract.py`, and `src/codegenie/probes/base.py` directly — three files, ~600 lines total.
- No external research needed; canonical patterns (NamedTuple hashability, structural snapshot tests, dataclass field inspection) are stdlib-documented.

### Coverage (verdict: COVERAGE-HARDEN)

- **CV1 (block)** — No AC pins the `localv2.md §4` doc update. Per ADR-0007, code-doc divergence is forbidden. The PR must amend both the §4 block and `base.py` in the same commit, then regenerate the snapshot. Without this AC, a contributor could amend `base.py` alone, regenerate the structural-signature half, and ship a doc-vs-code drift that the next localv2.md edit silently surfaces.
- **CV2 (block)** — No AC pins the `ALLOWED_BASE_PY_IMPORTS` widening (`{"abc", "dataclasses", "logging", "pathlib", "typing"} + {"collections"}`). Without this, the `from collections.abc import Callable, Mapping` line on `base.py` fails `test_base_py_imports_are_stdlib_only` at red-commit.
- **CV3 (block)** — No AC pins **type annotation** of the two new fields. A mutation that swaps `frozenset[InputFingerprint] | None` → `set[InputFingerprint] | None` (or `list[...]`) defeats the hashability invariant and passes the field-name test. The structural-signature snapshot does catch it, but a dedicated test makes the intent explicit and gives the engineer a named regression signal.
- **CV4 (block)** — No AC pins the ADR-0002 amendment text update. ADR-0002 currently does not name `input_snapshot` in its Decision section; the story implies the ADR is widened but doesn't require it. An out-of-date ADR is a load-bearing-doc rot.
- **CV5 (block)** — Story's "CODEOWNERS entry" AC contradicts the Phase-0 `test_base_py_carries_codeowners_todo_for_s5_02` invariant. AC must be **removed**, and the TODO **preserved**.
- **CV6 (harden)** — No AC pins `InputFingerprint` as a Phase 0 contract type via the structural_signature snapshot. If it lives in `base.py`, it auto-shows in the structural_signature; if it lives elsewhere, it must be explicitly tested. Either way pin it.
- **CV7 (harden)** — No AC pins that `dataclasses.asdict(ProbeContext(...))` round-trip works (callable serializes as `<function>`; the dataclass shouldn't try to deepcopy it). A test that constructs `ProbeContext(parsed_manifest=lambda p: None, input_snapshot=frozenset())` and reads back via attribute access pins the construction path without touching `asdict`.
- **CV8 (harden)** — No AC pins that the Phase 0 construction site (`ProbeContext(cache_dir=..., output_dir=..., workspace=..., logger=..., config={})`) keeps working without the new fields. Defaults-of-None should make this pass automatically; pin it explicitly so a mutation that removed the default breaks the test, not the call site.
- **CV9 (harden)** — No AC pins immutability of `InputFingerprint`. `NamedTuple` is auto-immutable, but a mutation that swapped to `dataclass(frozen=False)` would pass field-presence tests. A `with pytest.raises(AttributeError): fp.path = "x"` test pins intent.
- **CV10 (harden)** — No AC pins the `path: str` (not `Path`) choice for `InputFingerprint`. Story line 52 says "Field order: `(path, mtime_ns, size, content_hash)`" — order is pinned, but type isn't. Test: `assert isinstance(fp.path, str)`. Why `str` not `Path`: cross-platform hashable + comparable; Path equality on macOS case-insensitive FS is a foot-gun.
- **CV11 (harden)** — No AC pins `mtime_ns` integer-type discipline (`int`, not `float`). `os.stat().st_mtime_ns` returns `int`; mixing `float` would silently lose ns precision.
- **CV12 (harden)** — No AC pins the regen-script invocation as part of the implementer's red→green flow. The structural-signature test fails until the snapshot is regenerated; the story should require the engineer to run `python scripts/regen_probe_contract_snapshot.py` and commit `tests/snapshots/probe_contract.v1.json` as part of the green phase.

### Test Quality (verdict: TESTS-BLOCK)

Mutation analysis (~12 plausible wrong implementations):

| # | Wrong implementation | Caught by draft TDD? | Severity |
|---|---|---|---|
| 1 | Wrong script name (`regen_probe_contract.py` doesn't exist) | **No** — test would `ModuleNotFoundError` at import-time, looking like infra noise. AC + test reshaped to the actual path. | **block** |
| 2 | Append fields with wrong default (e.g. `... = ...` instead of `None`) | Partially — `fields_by_name["..."].default is None` pinned. Keep. | n/a |
| 3 | Append fields with wrong type (`set` not `frozenset`) | **No** — draft only asserted name+default. CV3 fix: pin annotation repr. | **block** |
| 4 | Re-order ProbeContext fields (move `config` to the end after new fields) | **No** — draft asserted `field_names[-2:] == [...]` but didn't pin the leading 5. Fix: assert full ordered tuple. | harden |
| 5 | Define `InputFingerprint` as a regular `class` (not hashable) | **No** — draft's `frozenset({fp})` test would fail at runtime, but the failure mode is opaque. Add explicit `hash(fp); fp == fp; isinstance(fp, tuple)` triplet. | harden |
| 6 | Make `InputFingerprint` mutable (`dataclass(frozen=False)`) | **No** — draft doesn't test setting an attribute. Add `with pytest.raises(AttributeError): fp.path = "x"`. | harden |
| 7 | Forget to widen `ALLOWED_BASE_PY_IMPORTS` | **No** — but `test_base_py_imports_are_stdlib_only` fails loudly. Pin a dedicated test that asserts `"collections" in ALLOWED_BASE_PY_IMPORTS`. | block |
| 8 | Delete `TODO(S5-02): CODEOWNERS entry required` | **No** — but `test_base_py_carries_codeowners_todo_for_s5_02` catches it. Reinforce by pinning the negative-direction: the new story does **not** add a CODEOWNERS entry, and the TODO survives. | harden |
| 9 | Forget to amend `localv2.md §4` to include the new fields | **No** — `test_probe_contract_doc_fingerprint_matches_snapshot` fails after regen, **but** the failure is generic. Add a dedicated test that greps `localv2.md §4` for the literal `parsed_manifest:` and `input_snapshot:` lines. | block |
| 10 | Forget to amend ADR-0002 to document `input_snapshot` | **No** — no test catches this. Add a doc-grep test: `assert "input_snapshot" in ADR_0002_PATH.read_text()`. | harden |
| 11 | Forget to regenerate snapshot JSON | **No** — structural_signature test fails generically. The story's note should pin the regen invocation as part of green. | harden |
| 12 | Re-introduce a 3rd field "while we're amending" | **No** — story's script-side constant approach was the proposed defense; validator replaces it with a dedicated test (`test_probe_context_field_list_matches_adr_0002_amendment`) that hard-codes the 7-tuple. | block |

### Consistency (verdict: CONSISTENCY-HARDEN)

- **CN1 (block)** — Story references `scripts/regen_probe_contract.py`; actual file is `scripts/regen_probe_contract_snapshot.py`. Path corrected across the story.
- **CN2 (block)** — Story references `tests/unit/test_probe_contract.snapshot.json`; actual file is `tests/snapshots/probe_contract.v1.json`. Path corrected.
- **CN3 (block)** — Story prescribes `from codegenie.coordinator.input_snapshot import InputFingerprint` on `base.py`; this violates the stdlib-only fence pinned by `test_base_py_imports_are_stdlib_only`. Resolution: define `InputFingerprint` in `base.py` itself; remove the cross-package import.
- **CN4 (block)** — Story uses `Callable[[Path], Mapping[str, JSONValue] | None] | None`; `JSONValue` lives in `coordinator/validator.py` and cannot be imported into `base.py` (cycle + fence). Resolution: use `Mapping[str, Any]` at the contract boundary; narrowing is downstream.
- **CN5 (block)** — Story prescribes adding to `CODEOWNERS`; collides with `test_base_py_carries_codeowners_todo_for_s5_02`. Resolution: remove the CODEOWNERS-edit AC; preserve the S5-02 TODO; explicitly note in `Out of scope` that CODEOWNERS routing is S5-02.
- **CN6 (harden)** — ADR-0002 Decision section currently names only `parsed_manifest`. Story implies the ADR is widened but doesn't pin the edit. Add an AC requiring the ADR-0002 amendment text to land in the same PR.
- **CN7 (harden)** — Arch goal #4 ("zero edits to base.py") contradicts the story. This is the arch design's internal inconsistency, not the story's fault. Surface the contradiction in the `Notes for the implementer` so the implementer doesn't get blindsided in PR review.
- **CN8 (harden)** — Story's note 3 claims "`probes/base` should be the leaf" — true, and validated by the stdlib-only fence. Reinforced in Notes.
- **CN9 (harden)** — `phase-arch-design.md §"Data model"` line 666-668 shows only one field added (`parsed_manifest`). Inconsistent with story (two fields). The arch document's data-model snippet is stale relative to `High-level-impl.md §"Constraints"` (line 31) and Gap 1 (line 990). The story's two-field landing is correct; the arch doc needs a one-line fix in a follow-up PR. Validator surfaces this for a Phase-1 arch-doc-correction issue.

### Design Patterns (verdict: PATTERNS-HARDEN)

- **DP1 (harden)** — **Newtype location.** `InputFingerprint` is a contract type (it crosses module boundaries — coordinator computes it, probes consume it via `ctx`). Contract types live with the contract surface (`base.py`), not in worker packages (`coordinator/`). Putting it in `coordinator/input_snapshot.py` inverts the dependency arrow (contract types should not depend on worker packages, and `base.py`'s stdlib-only fence enforces this structurally). Resolution: define it in `base.py`. Story implementation outline rewritten.
- **DP2 (harden)** — **Capability pattern is correctly chosen** for `parsed_manifest`. The field is `Callable[[Path], Mapping[str, Any] | None] | None` — probes depend on the *capability* (a parser-by-path function), not on a concrete `ParsedManifestMemo` class. This is the Strategy / Dependency-Inversion pattern at the contract surface, and it composes with S1-07's memo implementation cleanly. Reinforced in Notes.
- **DP3 (harden)** — **Primitive obsession check on `path`.** The story has `path: str`. The pure-newtype version would be `path: NormalizedAbsPath` (a `NewType`). For Phase 1 this is over-engineering (Rule 2 — three similar lines before abstraction); the `str` choice is defensible (cross-platform hashable, comparable, serializable). Recorded as a Phase-2 sharpening opportunity in Notes, not pinned as an AC.
- **DP4 (harden)** — **Open/Closed at the file boundary.** The "third future field" sentinel belongs in the test layer (`tests/unit/test_probe_contract.py`), not in the regen script. The script's responsibility is regenerating the snapshot; the test's responsibility is asserting correctness. Putting the sentinel in the test makes the failure self-documenting (test name → ADR pointer) and aligns with the existing tier ladder (`Tier 4 — structural-signature mutation killers`). Resolution: replace the script-side `ALLOWED_PROBECONTEXT_FIELDS` constant with a dedicated test named `test_probe_context_field_list_matches_adr_0002_amendment`. The test hard-codes the 7-tuple and emits a failure message that names ADR-0002.
- **DP5 (harden)** — **Make illegal states unrepresentable.** Both new fields are `None`-able. The alternative (always-present empty `frozenset()` for `input_snapshot`, always-present no-op callable for `parsed_manifest`) would lift Edge case #12's defensive check into the type system. But:
  - It would break the additive-optional invariant (Phase 0 construction sites would need new kwargs).
  - It would be a behavior change disguised as a type tightening.
  - The defensive check is one line per consumer probe; not load-bearing complexity.
  - Recorded as a Phase-2/Phase-14 sharpening opportunity in Notes, not an AC.
- **DP6 (harden)** — **Pure-impure split.** `InputFingerprint` is pure data; computing it is impure (touches `os.stat` + `blake3`). The pure-impure boundary is correctly drawn here (S1-08 owns the impure computation in the coordinator pre-dispatch pass). Reinforced in Notes.
- **DP7 (harden)** — **No premature plugin/registry.** A single allowlist (`{"package.json"}`) doesn't warrant a registry; the third future allowlist entry crosses the rule-of-three threshold (Phase 2's SCIP index manifests + Phase 7's distroless additions). Recorded as a forward-looking observation in Notes.

## Stage 4 — synthesis log

Edits to the story file, in order, with before/after for the load-bearing ones:

### Edit 1 — fix script path globally

`regen_probe_contract.py` → `regen_probe_contract_snapshot.py` (4 occurrences). Updated paths to `tests/snapshots/probe_contract.v1.json` (1 occurrence).

### Edit 2 — move `InputFingerprint` into `base.py`; drop `coordinator/input_snapshot.py`

Story's AC-2, implementation outline step 1, and Files-to-touch all updated. New file `src/codegenie/coordinator/input_snapshot.py` and `tests/unit/coordinator/__init__.py` are no longer created. Test file `tests/unit/test_input_fingerprint.py` (new) replaces `tests/unit/coordinator/test_input_snapshot_shape.py`.

### Edit 3 — narrow `parsed_manifest` callable type at the boundary

`Mapping[str, JSONValue] | None` → `Mapping[str, Any] | None`. Rationale recorded as Note 2 in `Notes for the implementer`. The JSONValue narrowing happens downstream at `_ProbeOutputValidator`; the contract surface preserves Phase 0's `dict[str, Any]` precedent.

### Edit 4 — remove CODEOWNERS-edit AC; preserve S5-02 TODO

Story AC-6 (the CODEOWNERS one) deleted entirely. `Notes for the implementer` gains an explicit note that the `TODO(S5-02): CODEOWNERS entry required` comment in `base.py` must survive the amendment unchanged; pinned by `test_base_py_carries_codeowners_todo_for_s5_02`.

### Edit 5 — replace script-side `ALLOWED_PROBECONTEXT_FIELDS` with test-side sentinel

Story AC-5 reshaped: instead of "regen script encodes the allowed list", the AC becomes "a dedicated test `test_probe_context_field_list_matches_adr_0002_amendment` in `tests/unit/test_probe_contract.py` hard-codes the 7-tuple and fails on a third field with a message naming ADR-0002." Implementation outline step 4 updated accordingly. TDD plan rewritten.

### Edit 6 — add `localv2.md §4` doc-update AC

New AC-10 (and corresponding TDD-plan test) added: the `ProbeContext` block in `docs/localv2.md §4` is amended to include the two new fields (and `InputFingerprint`); the `doc_fingerprint` re-matches the regenerated snapshot.

### Edit 7 — add `ALLOWED_BASE_PY_IMPORTS` widening AC

New AC-9: the `ALLOWED_BASE_PY_IMPORTS` set in `tests/unit/test_probe_contract.py` is widened by `"collections"`. A dedicated test asserts the widening so a future revert is a loud regression.

### Edit 8 — add ADR-0002 amendment-text AC

New AC-11: `docs/phases/01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md` is amended (or replaced with a renamed file) to document `input_snapshot` in its Decision and Consequences sections. A doc-grep test asserts `"input_snapshot"` is named in the ADR.

### Edit 9 — strengthen field-type assertions in the TDD plan

Annotation tests added for both new fields. Field-order full-tuple assertion replaces the trailing-two-only pattern. `InputFingerprint` immutability + hashability + tuple-base tests broken out.

### Edit 10 — strengthen `Notes for the implementer`

Added sections: (a) Stdlib-only fence widening rationale and surgery checklist; (b) `JSONValue`-vs-`Any` at the boundary rationale; (c) `InputFingerprint`-in-base.py rationale (contract type, DIP, fence); (d) arch goal #4 contradiction surfacing; (e) script-vs-test sentinel design rationale (Open/Closed at file boundary); (f) Phase 2/14 sharpening opportunities (newtype, illegal-states); (g) explicit pinning of the S5-02 CODEOWNERS TODO preservation requirement.

## Final verdict: HARDENED

Story is ready for executor. The amendment surface is now precisely:

- 1 file edited: `src/codegenie/probes/base.py` (additive — two fields appended + `InputFingerprint` defined, S5-02 TODO preserved).
- 1 doc edited: `docs/localv2.md §4` (additive — two fields and `InputFingerprint` shown in the §4 contract block).
- 1 ADR amended: `docs/phases/01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md` (Decision + Consequences naming `input_snapshot`).
- 1 test file edited: `tests/unit/test_probe_contract.py` (widened `ALLOWED_BASE_PY_IMPORTS` + new dedicated sentinel test + new `InputFingerprint` mutation-killer tier + new doc-grep tests for §4 and ADR-0002).
- 1 snapshot file regenerated: `tests/snapshots/probe_contract.v1.json` (both halves updated by `python scripts/regen_probe_contract_snapshot.py`).
- 0 files created (`InputFingerprint` moved to `base.py`).
- 0 files in `CODEOWNERS` touched (preserved for S5-02).

Every AC is mutation-resistant against the 12-row mutation table above. No `NEEDS RESEARCH` items.
