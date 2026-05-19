# Story S3-03 — Phase 3 plugin `api.py` import wiring + `tccm.yaml` row + bench regression gate

**Step:** Step 3 — `NpmVulnProvenanceAdapter` in Phase 3 plugin as additive new file (first byte-edit territory)
**Status:** Ready
**Effort:** S
**Depends on:** S3-02 (`NpmVulnProvenanceAdapter` exists as a class decorated `@register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)` in `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py`); soft-coupled to S8-02 (the `derived_queries:` schema must be backward-compat — a TCCM line that S3-03 lands MUST parse cleanly against both the pre-S8-02 schema and the post-S8-02 schema; if S8-02 has not yet landed, the line uses `should_read:` placeholder per the deferral pinned in `High-level-impl.md §Step 3`)
**ADRs honored:** [ADR-0009](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) — **this story consumes TWO byte-edit allowlist rows simultaneously: row #9 (`plugins/vulnerability-remediation--node--npm/api.py` — one new import line) and row #10 (`plugins/vulnerability-remediation--node--npm/tccm.yaml` — one new entry under an existing band). Together with row #8 (S3-02's `adapters/npm_provenance.py` new file), these are the three Step-3-consuming rows of the 10-row Phase 7 allowlist.** [ADR-0007](../ADRs/0007-provenance-adapter-registry-stores-classes.md) — the `api.py` import is precisely what triggers `@register_provenance_adapter` to fire at plugin-load time; the registry stores the class as a side-effect of the import. [ADR-0006](../ADRs/0006-adapter-dispatch-explicit-final-tuple.md) — explicit-import discipline (no `importlib.metadata` entry-point scan); the `# noqa: F401  # registers via decorator` comment makes the intent legible.

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
2. One new entry in `plugins/vulnerability-remediation--node--npm/tccm.yaml` (pinned: `derived_queries:` block if S8-02 has shipped; `should_read:` placeholder otherwise).

After this story lands, the integration test from S3-01 is green via the canonical plugin-load path (not test-fixture trickery); the bench cassette replay is byte-equal (ε ≤ $0.01); and the three Step-3-consuming rows of Phase 7 ADR-0009 are accounted for.

## Acceptance criteria

- [ ] `plugins/vulnerability-remediation--node--npm/api.py` has gained EXACTLY ONE new line. The line is `from .adapters import npm_provenance  # noqa: F401  # registers via decorator` (verbatim, including the comment — the comment is part of the explicit-import discipline). A `git diff` against the Phase 6.5 baseline shows exactly one added line with no other modifications.
- [ ] The import position in `api.py` follows the file's existing import-grouping conventions (stdlib → third-party → first-party → plugin-local). Specifically: the `from .adapters import npm_provenance` line is grouped with any existing plugin-local imports (e.g., `from .recipes import ...`). If there are no plugin-local imports yet, it lands as the first plugin-local import below the first-party block. Style consistency check: run `ruff format --check plugins/vulnerability-remediation--node--npm/api.py`.
- [ ] `plugins/vulnerability-remediation--node--npm/tccm.yaml` has gained EXACTLY ONE new entry. Decision rule:
  - **If S8-02 has landed**, the new entry is a `derived_queries:` band addition. Example shape (final fields pinned by S8-02):
    ```yaml
    derived_queries:
      - name: vuln_provenance
        compute: vuln.provenance
        args:
          cve_id: $workflow.cve
          package_id: $workflow.package
          image_ref: $repo.image_ref
    ```
  - **If S8-02 has NOT landed**, the new entry is a single `should_read:` line documenting the adapter's availability. Example:
    ```yaml
    should_read:
      - vuln_provenance  # populated by NpmVulnProvenanceAdapter at assemble_provenance() dispatch
    ```
    Plus an `_attempts/S3-03-npm-adapter-plugin-wiring.md` entry naming the deferred migration to `derived_queries:` after S8-02 lands.
- [ ] `tests/integration/test_provenance_assembly_via_plugins.py` (from S3-01, now sans `xfail` markers per S3-02's PR) passes via the canonical plugin-load path. No test-fixture monkey-patching of `_REGISTRY`; the test relies on the loader importing the plugin and the side-effect of `from .adapters import npm_provenance` firing the decorator.
- [ ] A new unit test under `tests/unit/plugins/vulnerability_remediation_node_npm/test_api_imports.py` asserts that after `import plugins.vulnerability_remediation__node__npm.api` (or whichever the canonical module path is), `_REGISTRY[(Layer.APP, Ecosystem.NPM)] is NpmVulnProvenanceAdapter`. This is the "explicit-import collection point fires" witness.
- [ ] **`bench/vuln-remediation/` cassette replay byte-equal.** The cost ledger diff against the Phase 6.5 baseline has |Δcost| ≤ $0.01 (ε). The cassette replay is the single most important assertion of this story. Run via `make bench-replay` or `pytest bench/vuln-remediation/test_replay.py` per the bench's own conventions; capture the cost-ledger diff in the PR description.
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

1. **Coordinate the TCCM decision FIRST.** Check whether `src/codegenie/plugins/tccm.py` declares `derived_queries: list[DerivedQuery] = []` (the S8-02 shape). If yes, use `derived_queries:`. If no, use `should_read:` placeholder + log the deferred migration in `_attempts/`.
2. **Edit `api.py`.** Open `plugins/vulnerability-remediation--node--npm/api.py`. Locate the existing plugin-local import block (look for `from .recipes import ...` or similar). Insert `from .adapters import npm_provenance  # noqa: F401  # registers via decorator` in the right place. Save. Run `ruff format --check` to confirm formatting is preserved.
3. **Edit `tccm.yaml`.** Open `plugins/vulnerability-remediation--node--npm/tccm.yaml`. Identify the existing band that this entry belongs in (`should_read:` if it exists, else `must_read:` adjacent; or open a new top-level `derived_queries:` block if using S8-02 shape). Insert exactly one entry. Save. Run `python -c "import yaml; yaml.safe_load(open('plugins/vulnerability-remediation--node--npm/tccm.yaml'))"` to verify the file still parses.
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
