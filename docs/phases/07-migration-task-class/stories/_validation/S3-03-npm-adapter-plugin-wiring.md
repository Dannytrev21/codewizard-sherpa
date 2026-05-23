# Validation report: S3-03 — Phase 3 plugin `api.py` import wiring + `tccm.yaml` row + bench regression gate

**Story:** [`../S3-03-npm-adapter-plugin-wiring.md`](../S3-03-npm-adapter-plugin-wiring.md)
**Validator run:** 2026-05-23 (scheduled-task `story-validation-corrector`)
**Verdict:** **HARDENED — with upstream BLOCKED status surfaced**

The story has been edited in place to (a) remove a non-canonical branching path, (b) promote one soft-coupled dependency to HARD, (c) surface an internal Phase-7 architectural contradiction the executor must resolve before proceeding, (d) tighten the witness-test ACs to exercise the canonical loader path, (e) add a negative-witness AC for mutation resistance, and (f) add a backward-compat byte-preservation AC. Status changed from `Ready` → `BLOCKED (validator 2026-05-23)`. The story cannot ship until three upstream blockers clear.

## Findings (severity → finding → fix)

### F1 — `derived_queries:` vs `should_read:` branching contradicts Phase 7 ADRs (BLOCK)

**Critic lens:** Consistency.

**Finding.** The story's original AC-3 branched: use `derived_queries:` if S8-02 has shipped, otherwise `should_read:` placeholder. Both ADR-0009 row #2 ("`plugins/vulnerability-remediation--node--npm/tccm.yaml` — exactly one new `derived_queries:` block (one entry)") and ADR-0016 §Consequences row 5 ("`plugins/vulnerability-remediation--node--npm/tccm.yaml` adds one `derived_queries:` entry too (fence allowlist row #2). The Phase 3 plugin's TCCM grows additively") pin `derived_queries:` definitively. The `should_read:` placeholder fork was non-canonical.

Additionally, a `derived_queries:` YAML block cannot parse against the live `Tccm` Pydantic model (which uses `extra="forbid"`) until S8-02 has shipped `derived_queries: list[DerivedQuery] = []`. So the story's "soft-coupled to S8-02" framing was incorrect — it must be HARD-depends.

**Fix applied.**
- Removed the `should_read:` branch from the goal section and AC-3.
- Pinned AC-3 to the canonical `derived_queries:` shape (taken from ADR-0016 §Consequences row 5 + the worked example from the sister-plugin per `phase-arch-design.md §Component design §10`).
- Promoted S8-02 in the `Depends on:` header from soft-coupled to HARD.
- Added a Notes-for-implementer paragraph explaining why the branch was removed (to short-circuit any future "I'll just use should_read for now" temptation).

### F2 — Phase-7-internal contradiction: ADR-0009 row enumeration vs High-level-impl.md Step 5 (BLOCK)

**Critic lens:** Consistency.

**Finding.** Phase 7 has TWO documents that each enumerate the 10 byte-edit allowlist rows, and they disagree on the contents:

| Row | ADR-0009 (canonical-by-ADR-doctrine) | High-level-impl.md §Step 5 |
|---|---|---|
| 1 | `plugins/.../npm_provenance.py` (new file) | `src/codegenie/__init__.py` |
| 2 | `plugins/.../tccm.yaml` | `src/codegenie/schema/repo_context.schema.json` |
| … | … | … |
| 8 | `src/codegenie/exec/__init__.py` | `plugins/.../npm_provenance.py` |
| **9** | **`pyproject.toml` (dockerfile-parse)** | **`plugins/.../api.py`** |
| 10 | `src/codegenie/plugins/loader.py` | `plugins/.../tccm.yaml` |

The two lists disagree on two contents: **ADR-0009 has `pyproject.toml` but no `api.py`**; **High-level-impl.md has `api.py` but no `pyproject.toml`**. Both claim 10 rows. The story uses High-level-impl row numbering (#8 / #9 / #10) — but under ADR-0009's literal text, editing `api.py` is a fence violation (the ADR's "Any other byte-edit to a Phase 0–6.5 file is a fence failure" line).

Production ADR-0043 amendment states "the Phase 7 decision itself — the 10-row allowlist for Phase 7 — stands unchanged," which makes ADR-0009 the canonical source. But the High-level-impl.md disagreement is itself an architectural document Phase 7 references — silently picking ADR-0009 over High-level-impl.md is the wrong call for an executor.

**Fix applied.**
- Removed the explicit "rows #8, #9, #10" claim from the ADRs-honored line in the header (it was wrong against ADR-0009).
- Surfaced the contradiction explicitly in the new *Validation notes* block.
- Added a hard precondition (step 1 of the Implementation outline): the executor MUST confirm an ADR-0009 amendment has landed (adding `api.py` as row #11 or reconciling the two enumerations) before proceeding.
- Added a Notes-for-implementer paragraph warning the executor NOT to silently pick one enumeration over the other.

**Recommended ADR amendment** (not made by this validator — outside skill scope): amend ADR-0009 to add `plugins/vulnerability-remediation--node--npm/api.py — exactly one new import line for the adapter (Step 3)` as row #11, OR reconcile to a single 10-row list that includes both `api.py` and `pyproject.toml` (would make 11 rows; the choice of which to omit needs an architectural call).

### F3 — Upstream BLOCKED dependency not surfaced (BLOCK)

**Critic lens:** Consistency / Coverage.

**Finding.** S3-03 hard-depends on S3-02, which is currently **BLOCKED** (see `_attempts/S3-02-npm-vuln-provenance-adapter.md`). The S3-02 attempt log documents three independent blockers:

1. **The Phase 3 npm plugin directory does not exist.** `plugins/` today contains only `__init__.py`, `PLUGINS.lock`, `PLUGINS.lock.README.md`. No `vulnerability-remediation--node--npm/` subtree, no `api.py`, no `tccm.yaml`. S3-03 cannot edit files that do not exist.
2. **`bench/vuln-remediation/` cassette does not exist.** AC-6 (cost-ledger byte-equality |Δ| ≤ $0.01) is unsatisfiable.
3. **The landed `VulnProvenanceAdapter.attribute(...)` Protocol contract has no `repo_context` parameter** (positional `cve_id, package_id, image_ref, sbom` only). This is upstream of S3-03 but constrains how S3-02 lands.

S3-03's original `Status: Ready` was incorrect — the story cannot execute. The original `Depends on:` did not surface any of these blockers.

**Fix applied.**
- Status changed from `Ready` → `BLOCKED (validator 2026-05-23)`.
- The `Depends on:` block in the header was rewritten to enumerate ALL four hard preconditions (S3-02, S8-02, plugin directory existence, bench cassette existence).
- Added a precondition-verification step as Implementation outline step 1, instructing the executor to STOP and log to `_attempts/` if any precondition fails — not to work around them.

### F4 — Witness test uses non-canonical loader path (HARDEN)

**Critic lens:** Test-Quality.

**Finding.** Original AC for the new unit test asserted that `importlib.import_module("plugins.vulnerability_remediation__node__npm.api")` fires the decorator. The story's stated goal is to prove the canonical plugin-load path fires the registration. `importlib.import_module(...)` is NOT the canonical path — it's a direct Python import that bypasses whatever the production `PluginLoader.load(...)` (or equivalent) does. A wrong implementation could leave `api.py` correct but `PluginLoader.load(...)` broken; the original test would still pass.

**Fix applied.**
- AC-5 now requires the witness test to call the production loader entry point (e.g., `load_plugin(...)`), not `importlib.import_module(...)`.
- Added explicit forbidden test smells to AC-4 (no `importlib.import_module("plugins...")`; no monkey-patch; no direct `_REGISTRY` mutation).

### F5 — Missing negative witness for mutation resistance (HARDEN)

**Critic lens:** Test-Quality.

**Finding.** AC-5's witness asserts `_REGISTRY[(APP, NPM)] is NpmVulnProvenanceAdapter` after the loader runs. But if a wrong implementation has the registration happening via some unrelated transitive import path (e.g., a `setup.cfg` entry-point, an unintended `importlib.metadata` scan, an import in `__init__.py` somewhere else), AC-5 still passes. The test doesn't kill the "registration leaks in from elsewhere" mutant.

**Fix applied.**
- Added **AC-W-neg**: a negative-witness test that demonstrates registration does NOT happen WITHOUT the `api.py` import line (via `monkeypatch` to swap `api.py`'s body). If a future PR makes the side-effect leak in from elsewhere, this test fails loud.

### F6 — Missing backward-compat / byte-preservation AC for the existing `tccm.yaml` (HARDEN)

**Critic lens:** Coverage.

**Finding.** ADR-0016 §Tradeoffs row 4: "Existing TCCMs (Phase 3, Phase 6.5, etc.) parse unchanged — `derived_queries: list[DerivedQuery] = []` default makes the band purely additive." The story's ACs did not encode a byte-preservation check for the **existing** bands of `plugins/vulnerability-remediation--node--npm/tccm.yaml`. Without it, a reformat-while-I'm-here that touches whitespace or reorders an existing `must_read:` entry would silently slip in and break the byte-equality bench cassette replay.

**Fix applied.**
- Added **AC-BC**: `git diff <phase-3-shipping-tag> -- tccm.yaml` shows ONLY new lines added (`+N, -0`); zero lines removed; zero lines modified in place.
- Implementation outline step 3 now requires running the `git diff | grep '^-'` byte-check before opening the PR.

### F7 — Open/Closed cliff at the third provenance plugin (DESIGN, note only)

**Critic lens:** Design-Patterns.

**Finding.** ADR-0009's per-plugin allowlist rows mean each new provenance plugin requires three rows: (a) the new adapter file, (b) one import line in *that plugin's* `api.py`, (c) one new `derived_queries:` entry in *that plugin's* `tccm.yaml`. The Phase 7 plugins are `vulnerability-remediation--node--npm` (Phase 3, edited) and `distroless-migration--node--npm` (new). At Phase 4+ the third provenance plugin makes this a rule-of-three case — the allowlist grows linearly with plugins, which is the kernel-edit cliff Phase 7's mechanical-additivity discipline was designed to prevent.

Per the validator skill's editor rules: design-pattern advice that would introduce a new kernel **before** the third concrete consumer is YAGNI. So this finding is **NOT promoted to an AC** — instead it lands as a Notes-for-implementer paragraph naming two alternative seams (centralize wiring through `src/codegenie/plugins/loader.py`; or formally ratify linear-growth doctrine in production ADR-0043) and recommending the Phase 7 retrospective evaluate them before the third plugin lands.

**Fix applied.** Added the Notes-for-implementer paragraph; no AC change.

## Findings NOT made (and why)

- **No new pattern abstraction introduced.** Per CLAUDE.md "Don't add abstractions for single-use code" and Rule 2 (Simplicity First), this story is two byte-edits and two tests. The pattern temptation (centralized loader wiring) is rule-of-three territory — surfaced in Notes-for-implementer, not landed as code.
- **No re-typing of the goal.** The goal (close Step 3 with two specific edits + bench-replay green) is sound. The validator's job is not to rewrite the goal; the writer's framing is correct.
- **No edit to `_REGISTRY` exposure / isolation pattern.** S2-01's autouse `provenance_registry_reset` fixture is the established precedent; this story already consumes it. Nothing to change.

## Recommendations to the user (out-of-scope for this validation)

1. **Amend ADR-0009** to resolve the row-enumeration contradiction with High-level-impl.md Step 5. Recommended path: add `plugins/vulnerability-remediation--node--npm/api.py` as row #11 (or merge to a single canonical list). Either approach unblocks S3-03.
2. **Triage S3-02's BLOCKED state.** S3-02's three blockers (Phase 3 plugin directory, bench cassette, Protocol contract divergence) need separate resolution — they aren't all in Phase 7's scope. Some belong to the Phase 3 implementation track.
3. **Consider the rule-of-three Open/Closed amendment** before the third provenance plugin lands. Either ADR-0009 amendment to row enumeration policy, or a refactor of the wiring seam.

## What "good" looks like for this story post-edit

The story now (when its blockers clear) gives the executor:

- A precise, unbranched AC for the `derived_queries:` block — pinned to ADR-0016's shape.
- A canonical-loader-path witness test that proves the production load path fires the registration.
- A negative-witness test that kills the "leaks in from elsewhere" mutant.
- A byte-preservation AC for the existing `tccm.yaml`.
- An explicit precondition step that stops the executor cold if any of the four hard dependencies isn't satisfied — no quiet workarounds.

## Mark of completion

The story file has been edited in place. This validation report has been written. The story header now carries a `**Validator status:** HARDENED (2026-05-23)` line linking back here.
