# Story S3-03 — Phase 3 plugin `api.py` import wiring + `tccm.yaml` row + bench regression gate

**Step:** Step 3 — `NpmVulnProvenanceAdapter` in Phase 3 plugin as additive new file (first byte-edit territory)
**Status:** BLOCKED (validator 2026-05-23) — three upstream preconditions missing; see *Validation notes → Upstream blockers* below. Promote to **Ready** only after the three blockers clear.
**Validator status:** HARDENED (2026-05-23) — see [`_validation/S3-03-npm-adapter-plugin-wiring.md`](_validation/S3-03-npm-adapter-plugin-wiring.md) for the full audit.
**Effort:** S (excluding blocker resolution)
**Depends on (HARD):**
- **S3-02** — `NpmVulnProvenanceAdapter` exists as a class decorated `@register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)` in `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py`. Currently **BLOCKED** (see `_attempts/S3-02-npm-vuln-provenance-adapter.md`).
- **S8-02 (promoted from soft-coupled to HARD)** — `src/codegenie/plugins/tccm.py` MUST already declare `derived_queries: list[DerivedQuery] = []` before this story executes. Rationale: ADR-0009 row #2 and ADR-0016 §Consequences row 5 pin the Phase-3-plugin tccm.yaml entry as a `derived_queries:` block; the Pydantic `extra="forbid"` discipline on the TCCM model will reject the YAML if the schema field is absent. The validator removes the prior "should_read: placeholder if S8-02 not yet landed" branch — it contradicted both ADRs and was the wrong fork.
- **Phase 3 npm plugin directory** — `plugins/vulnerability-remediation--node--npm/` must exist with `api.py` and `tccm.yaml` already present. The current repo has only `plugins/__init__.py`, `plugins/PLUGINS.lock`, `plugins/PLUGINS.lock.README.md` — the plugin tree has not been implemented yet (CLAUDE.md confirms Phase 3 not implemented). This is the root cause of S3-02's BLOCKED status and transitively blocks S3-03.
- **`bench/vuln-remediation/` cassette** — must exist before AC-6 can be evaluated. The cassette is the canonical "did we just regress Phase 3" detector. Story remains BLOCKED until the bench harness ships (typically a Phase 3 Step 9 deliverable per Phase 3's High-level-impl).

**ADRs honored:** [ADR-0009](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) — this story consumes **two byte-edit allowlist rows** simultaneously: one for `plugins/vulnerability-remediation--node--npm/tccm.yaml` (a `derived_queries:` block; ADR-0009 row #2) and one for `plugins/vulnerability-remediation--node--npm/api.py` (one new import line). **NOTE ON ROW NUMBERING:** ADR-0009 enumerates 10 rows but does NOT enumerate `plugins/vulnerability-remediation--node--npm/api.py` at all; the `api.py` row appears only in `High-level-impl.md §Step 5` (its own 10-row list, which disagrees with the ADR — ADR has `pyproject.toml`/dockerfile-parse, High-level-impl has `api.py`). **This is a real Phase-7-internal contradiction the validator surfaces — see *Validation notes → Open consistency question*.** Resolution path: amend ADR-0009 to add `plugins/.../api.py` as row #11 (or reconcile the two lists to one canonical enumeration) **before this story executes**. [ADR-0007](../ADRs/0007-provenance-adapter-registry-stores-classes.md) — the `api.py` import is precisely what triggers `@register_provenance_adapter` to fire at plugin-load time; the registry stores the class as a side-effect of the import. [ADR-0006](../ADRs/0006-adapter-dispatch-explicit-final-tuple.md) — explicit-import discipline (no `importlib.metadata` entry-point scan); the `# noqa: F401  # registers via decorator` comment makes the intent legible. [ADR-0016](../ADRs/0016-tccm-derived-queries-band.md) — pins the `derived_queries:` band shape and explicitly names the Phase-3-plugin tccm.yaml as a consumer (§Consequences row 5).

## Validation notes (2026-05-23, scheduled validator run)

### Verdict
**HARDENED with upstream BLOCKED status.** The story is well-structured but cannot execute until the upstream blockers clear. Once unblocked, the hardened ACs below give the executor a precise contract.

### Upstream blockers (must clear before this story is Ready)
1. **S3-02 BLOCKED.** Phase 3 npm plugin directory does not exist; the landed `VulnProvenanceAdapter.attribute(...)` Protocol has no `repo_context` parameter; required `Provenance` variant fields disagree with the story's ACs. See `_attempts/S3-02-npm-vuln-provenance-adapter.md` for the full diagnosis. **S3-03 cannot ship without S3-02 first shipping the adapter body.**
2. **`bench/vuln-remediation/` cassette does not exist.** AC-6 (cassette replay byte-equality) is unsatisfiable. Phase 3's bench harness must land before this AC is evaluable.
3. **ADR-0009 / High-level-impl.md Step 5 row enumeration inconsistency.** ADR-0009 (10 rows; includes `pyproject.toml`, omits `plugins/.../api.py`) disagrees with High-level-impl.md Step 5 (10 rows; includes `plugins/.../api.py`, omits `pyproject.toml`). Under ADR-0009's literal text, the `api.py` edit this story makes is a fence violation. The contradiction must be resolved by an ADR amendment (add `api.py` to ADR-0009 as row #11, or merge the two enumerations) before this story executes. The executor MUST NOT silently pick one interpretation over the other.

### Changes the validator applied
- **Pinned `derived_queries:` shape.** Removed the story's "should_read: placeholder if S8-02 not shipped" branch from the goal/AC text. It contradicted ADR-0009 row #2 and ADR-0016 §Consequences row 5, both of which pin `derived_queries:` definitively for the Phase-3-plugin tccm.yaml.
- **Promoted S8-02 from soft-coupled to HARD-depends.** Pydantic `extra="forbid"` makes the YAML un-parseable until the schema field lands.
- **Surfaced the ADR-0009 vs High-level-impl row inconsistency** as a precondition to be resolved before execution.
- **Strengthened AC-witness (now AC-5) to use the canonical loader path** rather than `importlib.import_module(...)` — the goal is to prove the production loader path fires the registration, not just that one specific Python import does.
- **Added AC-W-neg (negative witness test)** for mutation resistance.
- **Added AC-BC (backward-compat)** asserting the pre-existing `tccm.yaml` bands are byte-preserved (every existing line untouched).
- **Surfaced the rule-of-three Open/Closed concern** for plugin-api-wiring rows as a Notes-for-implementer paragraph (every new provenance plugin adding another allowlist row is a kernel-edit cliff).
- **Tightened the bench-replay AC** to explicitly require the cassette to exist as a precondition (the AC is unsatisfiable otherwise; that's an upstream block, not a failure to surface).


## Context

This story is short in line count and high in load-bearing CI gate weight. S3-01 wrote the contract test red-first. S3-02 landed the adapter body. S3-03 wires the explicit import so the decorator actually fires when the plugin loads — closing the loop and turning the integration test green for real (S3-02's `xfail`-removal is conditional on this wiring being in place — without `api.py`'s import line, the adapter is dead code).

**This story is also the regression gate for Step 3 as a whole.** Per `High-level-impl.md §"Step 3 — Done criteria"`:

> - `bench/vuln-remediation/` cassette replay green; cost-ledger byte-equality preserved (ε ≤ $0.01).
> - `make check` green; **Phase 3–6.5 regression suite green (hard pre-merge gate)**.

The bench cassette replay is the canonical "did we just regress Phase 3" detector. The cost ledger byte-equality assertion (ε ≤ $0.01) is the load-bearing assertion of the whole Phase 7 byte-edit-allowlist philosophy: even though three Phase 3-plugin allowlist rows are now consumed, the resulting Phase 3 plugin behavior must be observationally identical against the cassette replay. **If the cassette replay byte-equality fails, this story is BLOCKED and the path forward is to investigate what shifted — never to relax ε.**

The `tccm.yaml` edit is the trickiest piece. Phase 7 ADR-0009 row #10 allows exactly one new entry. The schema for that entry depends on whether S8-02 has shipped:

- **If S8-02 has shipped** (`derived_queries: list[DerivedQuery] = []` is in the `TCCM` Pydantic schema), the new entry is a `derived_queries:` block with one `DerivedQuery(name=..., compute="vuln.provenance", args={...})` row.
- **If S8-02 has NOT shipped** (the current Phase 3–6.5 TCCM schema has no `derived_queries` band), the new entry is a `should_read:` placeholder line — purely documentary, not load-bearing on dispatch.

The High-level impl document explicitly defers this decision to story-writing time and acknowledges the ambiguity:

> `plugins/vulnerability-remediation--node--npm/tccm.yaml` — **one** new line under an existing band documenting the adapter availability (TBD whether this is a `should_read:` entry or a `derived_queries:` entry — pinned in story-writing once Step 8's TCCM schema lands).

**This story PINS the decision:** if S8-02 has already landed by the time S3-03 executes, use `derived_queries:`. Otherwise, use `should_read:` as a temporary placeholder and add a `_attempts/`-tracked follow-up to migrate to `derived_queries:` after S8-02 lands. The fence test from S5-01 needs to know which row content to allowlist; this story coordinates that.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design §10 DistrolessMigrationPlugin"` (lines ~827–870) — the TCCM band shape (illustrates `must_read:` / `should_read:` / `derived_queries:` structure for the SISTER plugin; S3-03's edit follows the same shape applied to the Phase 3 plugin's existing TCCM).
  - `../phase-arch-design.md §"Integration tests"` line 1268 — `test_provenance_assembly_via_plugins.py` is the green-light witness for this wiring.
  - `../phase-arch-design.md §"CI gates"` (lines 1304–1311) — `test_phase7_no_byte_edits_to_locked_files.py` enforces the three Step-3-consuming rows match reality exactly.
- **Phase 7 ADRs:**
  - [ADR-0009](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) — the 10-row enumeration; rows #1 (S3-02), #9, #10 (this story) are the three Step-3-consuming rows.
  - [ADR-0006](../ADRs/0006-adapter-dispatch-explicit-final-tuple.md) — explicit-import collection point discipline.
  - [ADR-0007](../ADRs/0007-provenance-adapter-registry-stores-classes.md) — the `api.py` import side-effect IS what registers the class.
  - [ADR-0016](../ADRs/0016-tccm-derived-queries-band.md) — the TCCM `derived_queries:` band; this story may or may not use it depending on S8-02 timing.
- **High-level impl:** `../High-level-impl.md §"Step 3 — Features delivered"` bullets 3–4 + `§"Step 3 — Done criteria"` (bullet on cassette replay).
- **Existing Phase 3 plugin (read; touch SURGICALLY):**
  - `plugins/vulnerability-remediation--node--npm/api.py` — the explicit-import collection point; PRESERVE every existing line; ADD exactly one line.
  - `plugins/vulnerability-remediation--node--npm/tccm.yaml` — the TCCM; PRESERVE every existing line; ADD exactly one entry under exactly one existing band.
- **Bench cassette:**
  - `bench/vuln-remediation/` — cassette replay infrastructure. The implementer should be able to run it locally before opening the PR.
  - `bench/vuln-remediation/README.md` (if present) — how to run the replay and read the cost ledger.
- **Fence test (lands in S5-01; coordinate):**
  - Story S5-01 — `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` enumerates the 10 rows. S3-03's edits MUST match the exact row #9 + #10 verbatim text. If S5-01 has not shipped, S3-03 must publish its diff against the Phase 6.5 baseline as part of its attempt-log so S5-01 can encode the precise diff.

## Goal

Land the two Phase-3-plugin byte-edits that close Step 3:

1. One new import line in `plugins/vulnerability-remediation--node--npm/api.py`: `from .adapters import npm_provenance  # noqa: F401  # registers via decorator`.
2. One new top-level `derived_queries:` block in `plugins/vulnerability-remediation--node--npm/tccm.yaml` with one entry whose `compute` is `vuln.provenance` (shape pinned by ADR-0016 §Consequences row 5; **no `should_read:` placeholder fork — see *Validation notes***).

After this story lands, the integration test from S3-01 is green via the canonical plugin-load path (not test-fixture trickery); the bench cassette replay is byte-equal (ε ≤ $0.01); and the Step-3-consuming byte-edits to the Phase 3 plugin (the new `npm_provenance.py` adapter file from S3-02 plus the two edits in this story) are accounted for. **Row enumeration accounting deferred to the ADR-0009 amendment that resolves the api.py inclusion** (see header).

## Acceptance criteria

- [ ] `plugins/vulnerability-remediation--node--npm/api.py` has gained EXACTLY ONE new line. The line is `from .adapters import npm_provenance  # noqa: F401  # registers via decorator` (verbatim, including the comment — the comment is part of the explicit-import discipline). A `git diff` against the Phase 6.5 baseline shows exactly one added line with no other modifications.
- [ ] The import position in `api.py` follows the file's existing import-grouping conventions (stdlib → third-party → first-party → plugin-local). Specifically: the `from .adapters import npm_provenance` line is grouped with any existing plugin-local imports (e.g., `from .recipes import ...`). If there are no plugin-local imports yet, it lands as the first plugin-local import below the first-party block. Style consistency check: run `ruff format --check plugins/vulnerability-remediation--node--npm/api.py`.
- [ ] **AC-3 — `tccm.yaml` gains exactly one `derived_queries:` entry (no branching).** `plugins/vulnerability-remediation--node--npm/tccm.yaml` has gained EXACTLY ONE new top-level `derived_queries:` block containing one entry. Shape (pinned by ADR-0016 §Consequences row 5):
  ```yaml
  derived_queries:
    - name: provenance
      compute: vuln.provenance
      args:
        cve_id: $workflow.cve
        package_id: $workflow.package
        image_ref: $repo.image_ref
  ```
  The `should_read:` placeholder branch the prior story revision documented is **removed by the validator** — ADR-0009 row #2 and ADR-0016 §Consequences row 5 pin `derived_queries:` definitively; mixing schemas would fail the TCCM Pydantic `extra="forbid"` discipline. **Precondition:** S8-02 must have already shipped `derived_queries: list[DerivedQuery] = []` on the `Tccm` Pydantic model (HARD-depends; see header). Verify with `python -c "from codegenie.plugins.tccm import Tccm; assert 'derived_queries' in Tccm.model_fields"`.
- [ ] **AC-BC — TCCM backward-compat / byte-preservation.** Every line of the **pre-existing** `plugins/vulnerability-remediation--node--npm/tccm.yaml` is byte-preserved (no reformat, no reorder, no whitespace change, no comment edit). `git diff <phase-3-shipping-tag> -- plugins/vulnerability-remediation--node--npm/tccm.yaml` shows ONLY the new `derived_queries:` block as added lines; zero lines removed; zero lines modified in place. Verify with `git diff --stat` (`+N, -0`) on that file.
- [ ] **AC-4 — Integration test green via canonical loader path.** `tests/integration/test_provenance_assembly_via_plugins.py` (from S3-01, with any `xfail` markers stripped by S3-02's PR) passes via the canonical **production** plugin-load path — specifically, whichever entry point `src/codegenie/plugins/loader.py` exposes (e.g., `PluginLoader.load(...)`, `load_plugin(...)`, or the canonical resolver). **Forbidden test smells:** no `importlib.import_module("plugins...")`; no direct mutation of `_REGISTRY`; no monkey-patch / `setattr` on the registry module; no `@register_provenance_adapter` called in test setup. The test exercises the same path production uses; a regression that breaks the loader is caught by this test, not papered over.
- [ ] **AC-5 — Witness test asserts canonical loader fires the decorator.** A new unit test at `tests/unit/plugins/vulnerability_remediation_node_npm/test_api_imports.py::test_canonical_loader_registers_npm_provenance_adapter` invokes the **production loader's** entry point (NOT `importlib.import_module`), then asserts `_REGISTRY[(Layer.APP, Ecosystem.NPM)] is NpmVulnProvenanceAdapter`. Uses the `provenance_registry_reset` autouse fixture (S2-01) for isolation. Skeleton:
  ```python
  def test_canonical_loader_registers_npm_provenance_adapter(provenance_registry_reset):
      from codegenie.plugins.loader import load_plugin  # or whichever the canonical entry is
      from codegenie.primitives.vuln_provenance import Ecosystem, Layer
      from codegenie.primitives.vuln_provenance import registry as _registry_mod
      from plugins.vulnerability_remediation__node__npm.adapters.npm_provenance import (
          NpmVulnProvenanceAdapter,
      )

      load_plugin("vulnerability-remediation--node--npm")

      assert _registry_mod._REGISTRY[(Layer.APP, Ecosystem.NPM)] is NpmVulnProvenanceAdapter
  ```
- [ ] **AC-W-neg — Negative witness (mutation resistance).** A second test at the same path, `test_loader_without_api_import_line_does_not_register`, demonstrates that **without** the new `api.py` import line the registration does NOT happen. Concrete shape (one acceptable form):
  ```python
  def test_loader_without_api_import_line_does_not_register(provenance_registry_reset, monkeypatch):
      # Confirm that the canonical load path picks up the api.py import — and that
      # short-circuiting api.py leaves _REGISTRY empty. Catches a regression where the
      # registration side-effect leaks in via another import chain.
      from codegenie.primitives.vuln_provenance import Ecosystem, Layer
      from codegenie.primitives.vuln_provenance import registry as _registry_mod

      # Stub api.py to a body with NO `from .adapters import npm_provenance` line.
      monkeypatch.setattr(
          "plugins.vulnerability_remediation__node__npm.api",
          types.ModuleType("plugins.vulnerability_remediation__node__npm.api"),
      )
      # Re-running the loader should leave the (APP, NPM) slot empty.
      from codegenie.plugins.loader import load_plugin
      load_plugin("vulnerability-remediation--node--npm")
      assert (Layer.APP, Ecosystem.NPM) not in _registry_mod._REGISTRY
  ```
  Kills the mutant "registration happens via some other transitive import path." If a future PR makes the side-effect leak in from elsewhere (e.g., the loader scans for adapters via `importlib.metadata` — a violation of ADR-0006), this test fails loud.
- [ ] **AC-6 — Bench cassette replay byte-equal (precondition: cassette exists).** **Precondition (BLOCKING):** `bench/vuln-remediation/` must exist and contain a runnable cassette before this AC can be evaluated. If the directory is absent, this story is BLOCKED on the Phase 3 bench harness — surface in `_attempts/S3-03-npm-adapter-plugin-wiring.md`; do not relax the AC. **When the precondition is met:** the cost-ledger diff against the Phase-6.5 baseline has |Δcost| ≤ $0.01 (ε). Run via `make bench-replay` or `pytest bench/vuln-remediation/test_replay.py`; capture the cost-ledger diff in the PR description. If |Δ| > $0.01, **STOP** — the path forward is to investigate what shifted, never to relax ε.
- [ ] **Phase 3–6.5 regression suite green** (`make check`). The 2,300+ unit + integration + adversarial tests that existed at the Phase 6.5 baseline ALL pass without modification. **No test may be skipped, weakened, or marked `xfail` to make this story green.** A regression test that fails is a fence failure — surface in attempt log, treat as BLOCKED.
- [ ] `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` (from S5-01 — if it has shipped) passes. If S5-01 has not yet shipped, run the equivalent local check: `git diff Phase-6.5-baseline -- plugins/vulnerability-remediation--node--npm/` and confirm the diff contains exactly:
  - One added file: `adapters/__init__.py` (S3-02).
  - One added file: `adapters/npm_provenance.py` (S3-02 — row #1 of allowlist).
  - One added line in `api.py` (this story — row #9).
  - One added entry in `tccm.yaml` (this story — row #10).
  - And NOTHING ELSE.
- [ ] `mypy --strict plugins/vulnerability-remediation--node--npm/` clean (the import resolution under strict mode catches typos in the `from .adapters import npm_provenance` line).
- [ ] `ruff format`, `ruff check`, `make lint-imports` all clean.
- [ ] `make docs` green if the Phase 3 plugin has docs pages that reference the adapter availability (typically none — but check).
- [ ] Story Status updated to `Done`.

## Implementation outline

1. **Verify the hard preconditions FIRST (per *Validation notes*).** Run these three checks; if any fails, **STOP** and log to `_attempts/S3-03-npm-adapter-plugin-wiring.md` — do NOT proceed with a workaround:
   - `python -c "from codegenie.plugins.tccm import Tccm; assert 'derived_queries' in Tccm.model_fields"` — confirms S8-02 has shipped the schema field.
   - `test -d plugins/vulnerability-remediation--node--npm/adapters && test -f plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` — confirms S3-02 has shipped.
   - `test -d bench/vuln-remediation` — confirms the cassette replay precondition for AC-6.
   - Confirm ADR-0009 has been amended to include `plugins/vulnerability-remediation--node--npm/api.py` (or the row enumeration has been reconciled with `High-level-impl.md §Step 5`). If neither, surface and STOP — the executor must not silently pick one row enumeration over the other.
2. **Edit `api.py`.** Open `plugins/vulnerability-remediation--node--npm/api.py`. Locate the existing plugin-local import block (look for `from .recipes import ...` or similar). Insert `from .adapters import npm_provenance  # noqa: F401  # registers via decorator` in the right place. Save. Run `ruff format --check` to confirm formatting is preserved.
3. **Edit `tccm.yaml`.** Open `plugins/vulnerability-remediation--node--npm/tccm.yaml`. Append a NEW top-level `derived_queries:` block at the bottom of the file (do not interleave with existing bands; do not reorder existing bands). The block contains exactly one entry (shape per AC-3 / ADR-0016 §Consequences row 5). Save. Run two verifications:
   - YAML parse: `python -c "import yaml; yaml.safe_load(open('plugins/vulnerability-remediation--node--npm/tccm.yaml'))"`.
   - Pydantic parse against the live schema: `python -c "from codegenie.plugins.tccm import Tccm; import yaml; Tccm.model_validate(yaml.safe_load(open('plugins/vulnerability-remediation--node--npm/tccm.yaml')))"` — this catches `extra="forbid"` violations and unknown `compute:` references immediately.
   - Backward-compat byte-check (AC-BC): `git diff <phase-3-shipping-tag> -- plugins/vulnerability-remediation--node--npm/tccm.yaml | grep '^-'` — should show ZERO removed lines.
4. **Update `tests/integration/test_provenance_assembly_via_plugins.py`** — only if S3-02's PR did not already strip the `xfail` markers. If S3-02 closed those out, this story's only test edit is the new unit test in step 5.
5. **Add the explicit-import witness test.** `tests/unit/plugins/vulnerability_remediation_node_npm/test_api_imports.py`:
   ```python
   def test_plugin_api_import_registers_npm_provenance_adapter(provenance_registry_reset):
       # Import the api module; this should trigger the decorator side-effect.
       import importlib
       importlib.import_module("plugins.vulnerability_remediation__node__npm.api")
       from codegenie.primitives.vuln_provenance import Layer, Ecosystem
       from codegenie.primitives.vuln_provenance.registry import _REGISTRY
       from plugins.vulnerability_remediation__node__npm.adapters.npm_provenance import NpmVulnProvenanceAdapter
       assert _REGISTRY[(Layer.APP, Ecosystem.NPM)] is NpmVulnProvenanceAdapter
   ```
   The test uses the `provenance_registry_reset` fixture (S2-05) for isolation.
6. **Run the bench cassette replay.** Locally (before opening the PR):
   ```bash
   make bench-replay  # or pytest bench/vuln-remediation/ -v
   ```
   Capture the cost-ledger output. Diff against the Phase 6.5 baseline. If |Δ| > $0.01, STOP — investigate. Common culprits: the new explicit-import line caused a Phase 3 plugin module to load earlier and emit log output; or the TCCM band reordering changed dispatch order (it should NOT for `must_read:` semantics, but verify). If you cannot get the diff under ε, surface in the attempt log and treat this story as BLOCKED.
7. **Run the full regression suite.** `make check`. Every existing test must pass. If anything fails, the failure mode is named in the attempt log.
8. **Update story Status to `Done`** only after all CI gates green AND the cassette replay byte-equality is confirmed locally.

## Test-driven development plan

**Red.** The new unit test `tests/unit/plugins/vulnerability_remediation_node_npm/test_api_imports.py` is written FIRST. Without the new `api.py` line, it fails (the import-module call doesn't fire the decorator because `npm_provenance` is never imported transitively). Commit this red state with "RED" in the commit message.

**Green.** Add the `from .adapters import npm_provenance  # noqa: F401  # registers via decorator` line in `api.py`. The test passes. The integration test from S3-01 also passes via the canonical loader path (no monkey-patching). Add the `tccm.yaml` entry; confirm `yaml.safe_load` parses cleanly. Run the full suite + the cassette replay.

**Refactor.** None. This is a wiring story; the two edits are exactly what they are. Any refactor temptation ("while I'm here let me move the imports around in `api.py`") is a fence failure waiting to happen.

## Files to touch

- `plugins/vulnerability-remediation--node--npm/api.py` — **byte-edit allowlist row #9** (one new import line, verbatim with the documented comment).
- `plugins/vulnerability-remediation--node--npm/tccm.yaml` — **byte-edit allowlist row #10** (one new entry, shape pinned per S8-02-shipped check).
- `tests/unit/plugins/vulnerability_remediation_node_npm/test_api_imports.py` (new — the explicit-import witness test).
- `_attempts/S3-03-npm-adapter-plugin-wiring.md` (new — append-only attempt log; if `tccm.yaml` uses the `should_read:` placeholder shape, document the deferred migration to `derived_queries:` here).

## Out of scope

- The adapter body itself — S3-02 owns.
- The `derived_queries:` schema field in `src/codegenie/plugins/tccm.py` — S8-02 owns (row #5 of allowlist).
- The plugin-loader explicit-import line in `src/codegenie/plugins/loader.py` — S8-03 owns (row #7).
- The TCCM derived-queries resolver (`compute: vuln.provenance` → imported callable) — S8-03 owns.
- The base-image adapters and `Both` composition — Steps 4 + 11.
- The bench cassette regeneration — if the cassette is stale and needs regeneration for an UNRELATED reason, that's a separate story; if it needs regeneration because of THIS story, the story is BLOCKED.

## Notes for the implementer

- **The cassette replay byte-equality is non-negotiable.** ε = $0.01 is the documented tolerance. If your diff is $0.011, you do not relax ε — you find out what changed. Common silent culprits:
  - The new `tccm.yaml` entry changed YAML parse order (unlikely; YAML preserves declaration order in `must_read:` lists but reorder in `dict` form may matter depending on parser version).
  - The new `api.py` import caused a different module-import order, which caused a different log line to be emitted, which changed the cost ledger because logging is metered. (Yes, really. The cost ledger meters everything in some configurations.)
  - The decorator fired in a different order relative to other decorators, changing registry iteration order for an unrelated probe. (The `provenance_registry_reset` fixture handles per-test isolation; production bench-replay does NOT — it runs the full plugin-load sequence.)
- **The `# noqa: F401  # registers via decorator` comment is load-bearing.** Without `# noqa: F401`, `ruff` flags the unused import. Without `# registers via decorator`, future maintainers will "clean up" the import and break the registration silently. The comment IS the docs.
- **Re row enumeration in `tests/fence/test_phase7_no_byte_edits_to_locked_files.py`:** S5-01 lands the fence with all 10 rows. This story may execute BEFORE S5-01 in absolute order — the DAG (S3-03 → S5-01) makes this explicit. The fence catches up after S5-01 lands; this story's diff must be ready for it. The exact format of each row in the fence allowlist is S5-01's call — but the rows themselves are pinned in ADR-0009 and the path/line counts above are the authoritative source.
- **Re `tccm.yaml` schema timing:** if you're uncertain whether S8-02 has shipped, the safest path is `should_read:` placeholder + deferred-migration follow-up. The `should_read:` line is documentary; it doesn't constrain dispatch. The `derived_queries:` line is load-bearing for the future `compute: vuln.provenance` resolver. Either choice satisfies row #10 of the allowlist — but mixing schemas (e.g., adding `derived_queries:` while the schema doesn't yet support it) will fail TCCM Pydantic validation.
- **If `make check` fails in a Phase 3 test that has nothing to do with the adapter** (e.g., a Phase 3 recipe test fails with no apparent connection), STOP. The byte-edit allowlist philosophy treats that exact failure mode as a high-signal warning. Investigate before pushing. Possible cause: the new import line loaded `npm_provenance.py` which loaded `codegenie.primitives.vuln_provenance` which has a top-level side-effect that conflicts with Phase 3's loader. Pure imports should be side-effect-free at module-load time except for decorator registration; if the primitive does more, surface as a follow-up cleanup against the primitive.
- **Re "the headline regression gate":** this story's done-criteria are the most rigorous in Step 3 precisely because Step 3 is the first time Phase 7 byte-edits a Phase 0–6.5 surface. Future steps (S6-02, S7-04, S8-02, S8-03) consume more allowlist rows but rely on this story's discipline being the precedent. Get the cassette replay right; the rest of Phase 7 inherits.

- **(Validator surface — rule-of-three Open/Closed concern, not a blocker.)** This story creates a precedent: **every** future Phase-3-style task-class plugin that gains a provenance adapter will need (a) a new file (already an ADR-0009 allowlist row), AND (b) one new import line in *that plugin's* `api.py`, AND (c) one new `derived_queries:` entry in *that plugin's* `tccm.yaml`. Under the current ADR-0009 row enumeration, each new plugin requires its OWN per-file allowlist rows — i.e., the allowlist grows by 3 rows per provenance plugin. At the third such plugin (rule-of-three threshold), the kernel-edit cliff is no longer hypothetical. **Two alternative seams worth evaluating in a future ADR (Phase 8+ or Phase 4 amendment):**
  1. Centralize all per-plugin module wiring through `src/codegenie/plugins/loader.py`'s single explicit-import line (ADR-0009 row #10) — i.e., the loader imports each plugin's `api.py` once at the kernel; each plugin's `api.py` is then a NEW file under the plugin tree (not a byte-edit), no longer subject to the per-plugin allowlist row.
  2. Or formally adopt **"one allowlist row per existing-plugin-edited"** as Phase 7+ doctrine and ratify the linear-growth cost in production ADR-0043. Pick whichever the architects prefer.
  This story does NOT introduce either seam — pinning that decision belongs in an ADR amendment, not in a wiring story. Surface in the Phase 7 retrospective so the third-plugin case isn't a panic-edit.

- **Re the ADR-0009 vs High-level-impl.md row inconsistency:** do NOT silently pick one enumeration over the other. The validator's hard precondition (step 1 of the Implementation outline) requires ADR-0009 to be amended first. If you find yourself reaching for "I'll just use the High-level-impl numbering," STOP and write the ADR amendment — that's the canonical mechanism for resolving this kind of architectural disagreement.

- **Re the removed `should_read:` placeholder branch:** the prior story revision allowed a `should_read:` line if S8-02 hadn't shipped. The validator removed this branch — it contradicted ADR-0009 row #2 and ADR-0016 §Consequences row 5, both of which pin `derived_queries:` definitively. Mixing schemas (a `should_read:` entry today, migrating to `derived_queries:` later) would also fail TCCM Pydantic validation once the schema landed, and would leave a dead `should_read:` line nobody owned. Make S8-02 a HARD precondition; do not work around it.
