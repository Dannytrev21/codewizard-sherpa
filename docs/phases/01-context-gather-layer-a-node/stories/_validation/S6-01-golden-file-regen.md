# Validation Report — S6-01 Golden file `node_typescript_helm` + `scripts/regen_golden.py`

**Date:** 2026-05-15
**Validator:** phase-story-validator skill (Opus, scheduled-task autonomous run)
**Story:** `../S6-01-golden-file-regen.md`
**Verdict:** **HARDENED** — story had two structural bugs (one critical) and a number of harden-class gaps; edits applied; ready for executor.

## Summary

The original story's goal and structural intent were sound — a single seed golden + a sole-sanctioned regen script + an integration-test diff gate. But the prescribed `_strip_wall_clock` helper targeted a non-existent `data["audit"]` block and missed the two fields that **actually** make the envelope non-deterministic: `generated_at` (top-level UTC ISO timestamp) and `repo.git_commit` (resolves up the dir tree to codewizard-sherpa's own HEAD on fixture paths). As written, the regen would have produced a file that was byte-stable for ~1 second after creation, then drifted on the next gather (`generated_at`) and on the next commit to this repo (`repo.git_commit`) — CI would fail intermittently, the bug would look like "non-determinism in gather" rather than "wrong field list in regen."

After hardening, every AC is individually verifiable, the AC set collectively guarantees the goal, every test in the TDD plan would catch a plausible wrong implementation (mutation-resistance), and the prescribed implementation introduces exactly one Open/Closed seam (`_GOLDEN_PAIRS` + `GoldenPair`) for Phase 2 expansion without crossing into premature abstraction.

## Stage 1 — Context Brief

### Story snapshot

- **Goal:** Land `tests/golden/node_typescript_helm.repo-context.yaml` (canonical key-sorted YAML, non-deterministic fields normalized), `scripts/regen_golden.py` (the only sanctioned mutation path), and extend the S5-05 integration test to diff live output against the golden as a hard CI gate. Two consecutive regen runs produce byte-identical output, enforced by a unit test (originally a manual PR-body check).
- **Step:** Phase 1, Step 6 (Golden file, coverage ratchet, bench additions, Phase 2 handoff).
- **Depends on:** S5-05 (`tests/integration/probes/test_layer_a_end_to_end.py` — extended in this story; S5-05 has been hardened but is not yet implemented on disk).
- **Out-of-scope:** Multiple golden fixtures (Phase 2/7); schema-bump detection in regen; Python-version comparison; deep-walking probes for nested timestamps.

### Phase / arch constraints

- **ADR-0002** — `ParsedManifestMemo` + `input_snapshot` per gather; warm-path produces byte-identical slices. The golden is the proof.
- **ADR-0004** — every per-probe slice in the golden conforms to its sub-schema; integration test re-validates after diff. (AC-VAL-1.)
- **ADR-0007** — every warning ID in the golden matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. (AC-VAL-2.)
- **Phase 0 ADR-0008** (sanitizer chokepoint) — rendered envelope contains no host-specific path prefixes. The golden is a regression canary for this. (AC-NEG-1.)
- **Phase 0 envelope schema** (`src/codegenie/schema/repo_context.schema.json`) — `schema_version`, `generated_at`, `repo`, `probes` are required. **No `audit` block exists at envelope root.** Audit `RunRecord` lives in `.codegenie/context/runs/<run-id>.json`.

### Verified ground truth (consulted directly)

| Question | Source | Answer |
|---|---|---|
| Envelope root keys | `src/codegenie/cli.py:423-440` | `schema_version`, `generated_at`, `repo`, `probes`. No `audit`. |
| `generated_at` source | `src/codegenie/cli.py:425` | `datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")`. Wall-clock — non-deterministic. |
| `repo.git_commit` source | `src/codegenie/coordinator/snapshot.py:59` | `git rev-parse HEAD` from repo_root. Walks up dir tree → resolves to parent codewizard-sherpa HEAD on fixture paths → moves with every commit. |
| `audit.wall_clock_ms` location | `src/codegenie/audit.py:94` (`ProbeExecutionRecord`) | Per-probe field on `ProbeExecutionRecord`, written to `.codegenie/context/runs/*.json` sidecar — **not** to `repo-context.yaml`. |
| Writer `sort_keys` setting | `src/codegenie/output/writer.py:180` | `yaml.dump(..., sort_keys=False)` — writer does NOT canonicalize. The regen + integration test must re-serialize with `sort_keys=True`. |
| Sibling regen prior art | `scripts/regen_probe_contract_snapshot.py` | Single-fixture, hand-rolled regen. This story is the **2nd** regen script. Rule of three (third = Phase 7 distroless) not yet met → no shared kernel extracted. |
| S5-05 conftest seams | `tests/integration/probes/conftest.py:80-235` | `WARM_PATH_CACHE_HIT_PROBES`, `_load_envelope`, `_stub_node_version_check`, `_minimal_valid_envelope` already lifted to conftest. Reuse, don't shadow. |

### Sibling-family lineage

- The `_GOLDEN_PAIRS` registry is the **2nd** Open/Closed-at-the-file-boundary seam in this phase (the 1st is `WARM_PATH_CACHE_HIT_PROBES` from S2-05/S5-05). Same shape — typed, frozen, additive, prohibits function-body edits for extension. Established convention; this story consumes it, does not invent it.
- The shared `_normalize_envelope` helper is the **3rd** consumer of "single source of truth for a closed-set field list" (S5-05's `PHASE_1_PROBE_NAMES` + `PHASE_1_PROBE_TO_SLICE` in conftest is the 1st/2nd). Rule of three reached for the *pattern* (closed-set in conftest); the actual content (`_NORMALIZED_FIELDS`) is the new entry.

### Open ambiguities (resolved during validation)

- ✅ Envelope vs audit shape — resolved against `cli.py:423-440` and `audit.py:94`. The audit lives in a sidecar; the envelope has no audit block.
- ✅ Why the original strip helper would silently no-op — `data.get("audit", {})` returns `{}` on every real envelope; the loop iterates nothing.
- ✅ Why `repo.git_commit` is non-deterministic on fixture paths — `git rev-parse` walks up to the parent repo's `.git/`. Confirmed in `coordinator/snapshot.py`.
- ✅ Should `repo.git_commit` be normalized rather than deleted — yes, because envelope schema requires the field. Sentinel preserves shape.
- ✅ Whether to use `subprocess.run(["codegenie", "gather", ...])` or `CliRunner` — `CliRunner` per S5-05's pattern; avoids PATH dependence and surfaces tracebacks.

## Stage 2 — Critic findings (synthesized inline)

The four critics (Coverage, Test Quality, Consistency, Design Patterns) ran inline because all findings had local, source-of-truth-anchored fixes that did not require external research (Stage 3 skipped — token economy). Findings are merged below by issue. Severity priority resolution: **Consistency > Coverage > Test-Quality > Design-Patterns** (per skill reference).

### Blocking — applied

**B1. `_strip_wall_clock` targets a non-existent envelope block.**
- *Where (before):* AC-2, Implementation outline §2, TDD red snippet — every reference to "strip `audit.wall_clock_ms` and `audit.completed_at`."
- *Source of truth:* `src/codegenie/cli.py:423-440` shows envelope root keys are exactly `{schema_version, generated_at, repo, probes}`. `src/codegenie/schema/repo_context.schema.json` has the same `required` list. Audit `RunRecord` (with `wall_clock_ms`) lives in `.codegenie/context/runs/*.json`, written by `_seam_audit_record`.
- *Failure mode if shipped:* `data.get("audit", {})` returns `{}` → loop iterates nothing → strip is a silent no-op → golden contains live `generated_at` ISO timestamp → CI fails on the next gather (within seconds).
- *Fix applied:* Helper renamed to `_normalize_envelope`; field list rewritten to the actual non-deterministic envelope paths; sentinel-replacement (not deletion) so envelope schema's required-fields invariant holds.

**B2. `repo.git_commit` non-determinism missed entirely.**
- *Where (before):* Story made no mention of `repo.git_commit`.
- *Source of truth:* `src/codegenie/coordinator/snapshot.py:59-77` runs `git rev-parse HEAD` from the fixture path. Fixtures (`tests/fixtures/node_typescript_helm/`) are subdirs of codewizard-sherpa, no `.git/` of their own → git walks up → returns this repo's HEAD → moves on every commit.
- *Failure mode if shipped:* Even after fixing B1, the golden would still contain a live SHA → CI fails on every commit to codewizard-sherpa.
- *Fix applied:* `("repo", "git_commit")` added to `_NORMALIZED_FIELDS` (AC-PURE-1).

**B3. Idempotence verification was a manual PR-body sha256 — humans skip it.**
- *Where (before):* AC-3 — "byte-identical output across two consecutive invocations on the same machine (verified locally before merge; surfaced in the PR body as a `sha256` line for each run)."
- *Source of truth:* CLAUDE.md Rule 12 ("Fail loud") + High-level-impl §"Implementation-level risks" #6 ("run twice locally before opening the PR" — presciently noted as risk-prone).
- *Fix applied:* AC-IDEM-1 promotes the check to a CI-enforced unit test (`tests/unit/scripts/test_regen_golden_idempotent.py`). Sha256-in-PR-body remains as a developer convenience (AC-SCRIPT-6) but is no longer the load-bearer.

**B4. `_strip_wall_clock` duplicated by design between script and test, with no parity test.**
- *Where (before):* Implementation outline §4 — "Implement the matching `_strip_wall_clock(data)` helper in the integration test file." Notes for the implementer — "duplication of six lines is cheaper than a shared-helper import path."
- *Source of truth:* CLAUDE.md Rule 7 ("Surface conflicts, don't average them") — duplication where one site is the source of truth and the other is a copy creates a parity-drift bug class. Concrete failure: a future story adds a third normalized field (e.g., a new `repo.machine_id`); the script is updated; the integration test is forgotten → script regenerates the golden with the third field stripped, integration test compares with the third field NOT stripped → diff fails on every run, root cause is silent drift.
- *Fix applied:* AC-PURE-1 hoists `_normalize_envelope` + `_golden_yaml_bytes` + `_NORMALIZED_FIELDS` to `tests/integration/probes/_golden_helpers.py`. Both the script and the integration test import from there. Single source of truth (Rule 7). The `tests/` import from `scripts/` is a deliberate one-line crossing — surfaced explicitly in the design-pattern guidance.

### Harden — applied

**H1. AC-PURE-3 mutation-killer for the field list.**
- *Issue:* Even with the right field list, a future refactor could degrade `_normalize_envelope` to "return data unchanged" (the original story's bug, in spirit). Without a test that exercises every field path, the bug returns silently.
- *Fix applied:* AC-PURE-3 prescribes a `pytest.parametrize` over `_NORMALIZED_FIELDS`; each parametrized run constructs a full envelope, calls the helper, and asserts the leaf at the path equals the sentinel. Adding a new field to `_NORMALIZED_FIELDS` automatically expands the parametrize — no test edit required.

**H2. AC-PURE-4 robustness to absent paths.**
- *Issue:* Non-coordinator-constructed envelopes (test paths) may omit fields. A naive `data["repo"]["git_commit"] = ...` would `KeyError`.
- *Fix applied:* AC-PURE-4 covers the `KeyError`-free path; `_normalize_envelope` uses key-defensive traversal.

**H3. Schema re-validation post-strip missing.**
- *Issue:* The story said "the integration test re-validates after diff" but no AC encoded it. A future strip choice that drops a required field would silently break ADR-0004.
- *Fix applied:* AC-VAL-1 — integration test calls `codegenie.schema.validator.validate(envelope)` on the live (pre-normalize) envelope. (Pre-normalize because schema requires the actual fields; the normalization is for the comparison, not for the contract.)

**H4. ADR-0007 warning-ID pattern not asserted in golden.**
- *Issue:* Story listed ADR-0007 in honored ADRs but no AC re-asserted it. A probe could regress and slip a prose warning into the golden — golden would still byte-equal itself but the structural defense degrades silently.
- *Fix applied:* AC-VAL-2 — integration test walks every `probes[*][slice_key].warnings` and asserts each entry matches the ADR-0007 regex.

**H5. Host-path leak negative test missing.**
- *Issue:* Phase 0 ADR-0008's sanitizer is the load-bearer for redacting host paths from the rendered envelope. If a probe ever bypasses the sanitizer and leaks a fixture absolute path (`/Users/danny/.../tests/fixtures/...`), the golden becomes machine-specific. Without a tripwire, CI would fail intermittently with "machine X passes, machine Y fails" — diagnosis takes hours.
- *Fix applied:* AC-NEG-1 — integration test asserts golden bytes contain none of `/Users/`, `/home/`, `/tmp/`, `/var/folders/`, or `os.path.expanduser("~")`. Belt-and-suspenders against a known regression class.

**H6. `_stub_node_version_check` missed — environment-dependent flake guaranteed.**
- *Issue:* `NodeBuildSystemProbe` cross-checks `node --version` against the fixture's `.nvmrc`. On a developer machine where Node ≠ pinned version, the slice carries a `node.version_declared_resolved_disagree` warning → golden diff fails on developer machines and passes in CI's pinned env (or the inverse).
- *Source of truth:* S5-05 hardening already established this pattern; `tests/integration/probes/conftest.py:194-224` documents the helper.
- *Fix applied:* AC-DIFF-3 mandates `_stub_node_version_check`. Implementation outline §4 calls it out. Notes for the implementer flag it as "non-negotiable."

**H7. Open/Closed seam for Phase 2 missing.**
- *Issue:* Original script had hardcoded `FIXTURE`, `GOLDEN`, and `required` set in the body of `main()`. Phase 2 will need to add a second golden — currently means editing `main()` (closed for extension, open for modification — backwards). Three triplicate hardcoded values is the prime smell.
- *Source of truth:* CLAUDE.md "Extension by addition." S5-05's `WARM_PATH_CACHE_HIT_PROBES` + `PHASE_1_PROBE_NAMES` is the precedent — typed frozenset/tuple at module top, body iterates.
- *Fix applied:* AC-SCRIPT-1 introduces `GoldenPair` (3-field `frozen dataclass` or `NamedTuple`) and `_GOLDEN_PAIRS: Final[tuple[GoldenPair, ...]]`. `main()` iterates; no fixture-specific literals in the body. Phase 2 adds a `GoldenPair(...)` entry — zero `main()` edits. Notes for the implementer call this out as the *one* abstraction this story introduces, deliberately not generalized further (Rule 2 + rule of three). Out-of-scope reaffirms: no `regen_kernel.py` extraction yet — Phase 7's third golden earns it.

**H8. `subprocess.run(["codegenie", ...])` brittleness.**
- *Issue:* The original outline used `subprocess.run` to invoke the CLI. Requires the package be `pip install`-ed in the developer's PATH; failures surface as opaque exit codes; no traceback.
- *Source of truth:* `tests/integration/probes/conftest.py` and S5-05 already use Click `CliRunner` against `codegenie.cli.cli` — established pattern.
- *Fix applied:* AC-SCRIPT-2 mandates `CliRunner`; outline §2 names the call signature.

**H9. Failure-message ergonomics.**
- *Issue:* Original failure message was short and generic. Reviewers seeing a CI failure want to know exactly what to type next.
- *Fix applied:* AC-DIFF-2 prescribes the literal text — `python scripts/regen_golden.py` and `Inspect the diff with: git diff tests/golden/`. Truncation thresholds tightened (80 lines / 4000 chars) for scannability. Distinct missing-golden setup error (AC-DIFF-4) so "you forgot to regen" is told apart from "real divergence."

**H10. Golden serializer parity (sort_keys, allow_unicode).**
- *Issue:* The writer uses `sort_keys=False, allow_unicode` defaults; original story specified `sort_keys=True, default_flow_style=False, width=120` but missed `allow_unicode=True`. If the live envelope contains a non-ASCII byte (e.g., a probe that surfaces a fixture file containing UTF-8) and the regen serializer omits `allow_unicode=True`, PyYAML emits `\uXXXX` escapes — different bytes than the original might encode. Belt: pin all four flags.
- *Fix applied:* AC-GOLDEN-1 + the helper's contract pin all four serializer flags; the integration test uses the same helper (AC-DIFF-1).

### Nit — applied

**N1.** Makefile `regen-golden:` target was "optional" in original; lifted to AC-DOC-2 for contributor ergonomics (`High-level-impl.md §"Step 6"` lists it under "features delivered").
**N2.** Module docstring on the script and on the integration test now explicitly state the workflow (AC-DOC-1, AC-DOC-3) — first-time readers get oriented.
**N3.** AC-DOD-3 added — no new dependencies. The script is stdlib + existing deps; no `dev`-extras gate at runtime.

### Conflicts resolved

- *Coverage* wanted "verify the regen script's exit code on every error path." *Test-Quality* pushed back: testing each exit-code branch in unit tests is high-cost / low-value (the `subprocess.CalledProcessError` path is stdlib behavior; the schema-validation-fail path is exercised by AC-SCRIPT-5 if the test invokes with a synthetic broken envelope, but constructing a broken envelope from a real fixture is pre-mature). Resolution: AC-SCRIPT-5 enumerates the contract (exit 1/2/3) but the unit-test surface is limited to AC-IDEM-1+2 (idempotence + sentinel-applied) for this PR. Future PR can add per-exit-code tests if a real bug ever lands there.
- *Design-Patterns* initially proposed factoring a generic `regen_kernel.py` taking a list of `GoldenPair`-shaped registries. *Consistency* + *Rule 2* pushed back: rule of three has not been met (script #2; #3 is Phase 7's distroless). Resolution: introduce `GoldenPair` + `_GOLDEN_PAIRS` (the *seam*, not the kernel); Out-of-scope reaffirms no kernel extraction. The seam is the discoverable extension point; the kernel waits for the third concrete consumer.
- *Coverage* wanted an AC for "deep-walking `probes.*` for nested timestamps." *Consistency* checked the schemas: Phase 1 probes emit facts not telemetry (per `production/design.md §2.2`); no probe slice carries a timestamp field. Resolution: deferred (named in Out-of-scope) — if a Phase-2 probe ever embeds a timestamp, the golden diff fails on the next CI run after that probe lands; the fix is one-line addition to `_NORMALIZED_FIELDS`. AC-PURE-3's parametrize automatically picks up the new entry — so the test surface scales free.

## Stage 3 — Researcher

**Skipped.** No findings tagged `NEEDS RESEARCH`. All issues had clear fixes from local source-of-truth (cli.py, schemas, ADRs, S5-05 validation report). The patterns invoked (Open/Closed at the file boundary, single source of truth, mutation-resistance via parametrize, sentinel-not-deletion for required fields) are already established in this codebase's prior validation reports. Token economy — research without an open question is overhead.

## Stage 4 — Edits applied

The story was rewritten in place. Major changes:

1. **Header**: Status flagged `Ready (HARDENED 2026-05-15)`. ADRs honored extended to include Phase 0 ADR-0008 (sanitizer) for traceability.
2. **Validation notes block** added under header summarizing the corrections (executor reads this first).
3. **Context** rewritten: explicit table of the actual non-deterministic fields with sources; explicit statement that no `audit` block exists in the envelope; explicit explanation of why `repo.git_commit` is non-deterministic on fixture paths; introduction of the `_GOLDEN_PAIRS` Open/Closed seam for Phase 2.
4. **References — where to look**: added `cli.py:423-440`, `repo_context.schema.json`, `coordinator/snapshot.py:59`, the writer's `sort_keys=False` line, conftest seams, prior `scripts/regen_probe_contract_snapshot.py`, and `_validation/S5-05`.
5. **Goal** rewritten — adds "enforced by a unit test" to the idempotence clause.
6. **Acceptance criteria** rewritten end-to-end into 8 grouped sections (`GOLDEN-`, `SCRIPT-`, `PURE-`, `IDEM-`, `DIFF-`, `VAL-`, `NEG-`, `DOC-`, `DOD-`) with 26 individual ACs replacing the first-draft's 7 unstructured ACs.
7. **Implementation outline** rewritten with explicit landing order (helper module first, then script, then integration test), correct CLI invocation pattern (`CliRunner`), correct conftest seam reuse (`_stub_node_version_check`).
8. **TDD plan red snippets** rewritten for three test files (helper unit tests, idempotence unit test, integration test) — each with mutation-killer assertions; the integration snippet pins the failure-message text and the host-path leak canary.
9. **Files to touch** table expanded — added `_golden_helpers.py`, `test_golden_helpers.py`, `test_regen_golden_idempotent.py`. Makefile lifted from "optional" to required.
10. **Out of scope** rewritten — explicitly names what's deferred (multiple goldens, schema-bump detection, generic kernel extraction) and why (rule-of-three, separation of concerns).
11. **Notes for the implementer** rewritten — load-bearing gotchas section (envelope shape, git_commit non-determinism, writer's `sort_keys=False`, `_stub_node_version_check`); design-pattern guidance section (the one introduced abstraction is `GoldenPair`+`_GOLDEN_PAIRS`, not a kernel); process / PR hygiene; what success looks like.

## Final verdict — HARDENED

**Story is ready for `phase-story-executor`.** The structural bug (no-op strip helper) is fixed; non-determinism inventory is complete and correct; idempotence is a CI gate, not a manual check; helper duplication is eliminated via a single source of truth in `_golden_helpers.py`; the Open/Closed seam for Phase 2 expansion is in place without crossing into premature abstraction; ADR-0004 / ADR-0007 / Phase 0 ADR-0008 traceability is enforced by integration-test ACs. Every AC is individually verifiable; mutation-resistance via parametrize covers the strip-helper field list; the failure mode "you forgot to run regen" is told apart from "real divergence" via distinct error messages.

The executor should land in the order described in **Implementation outline** §1–§5 — primitives first (helpers + types), script second, integration test third — with each step's tests landed in the same PR. Local verification (two `python scripts/regen_golden.py` runs + the three new test files passing) is the developer's belt; AC-IDEM-1 + AC-DIFF-1 + AC-VAL-1 + AC-NEG-1 are the CI safety nets.
