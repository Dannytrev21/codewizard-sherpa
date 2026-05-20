# ADR-0009: Phase 7 fence allowlist — 10 enumerated byte-edit allowances

**Status:** Accepted
**Date:** 2026-05-19
**Tags:** extension-by-addition · fence · §2.5 · ship-of-theseus
**Related:** [0003](0003-sandbox-role-additive-enum-on-spawn.md), [0004](0004-vuln-provenance-primitive-home.md), [0005](0005-probes-live-under-plugin-not-core-tree.md), [0015](0015-allowed-binaries-amendment-dive-buildx.md), [0016](0016-tccm-derived-queries-band.md), [Phase 3 ADR-0001](../../03-vuln-deterministic-recipe/ADRs/0001-ship-phase5-contract-surface-by-name.md), [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md), [production §2.5](../../../production/design.md)

> **Amendment (2026-05-20) — superseded-in-principle by [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md).** ADR-0043 establishes that Phase 7's 10-row allowlist is the **last** per-phase enumerated allowlist. Statements below that assume Phase 8+ extend the fence or that the row-set "grows with each phase" (Tradeoffs rows 1 & 3; Consequences final bullet) are superseded: future phases add **no** allowlist rows and **no** new per-phase allowlist fence — a new frozen surface is a contract with a snapshot test (the probe-ABC pattern). The Phase 7 decision itself — the 10-row allowlist for Phase 7 — stands unchanged.

## Context

CLAUDE.md and production design §2.5 commit to "Extension by addition — new language / new task type = new probes + new Skills, never edits to existing probes or the coordinator." The critic (§Roadmap-level critiques #4) flagged that all three lens designs treat the commitment elastically: "All three designs add wiring imports, schema `$ref` insertions, `ALLOWED_BINARIES` rows, `PLUGINS.lock` updates, fence-test allowlist amendments, and `tccm.yaml requires:` lines to existing files — and count them as 'additive' because the file *grows* rather than *mutates*. The commitment's force was 'no edits to existing plugins or stable existing behavior'; the designs read it as 'no semantic edits to existing behavior, but byte-edits to existing files are fine.'"

`final-design.md §Lens summary §4` and `phase-arch-design.md §Testing strategy §"Phase 7 fence allowlist (exhaustive)"` take a position: define "additive" mechanically. Enumerate every byte-edit to existing files Phase 7 is permitted to make. Anything else is a fence failure. The fence test grows by ADR amendment, not by quiet convention drift.

This is the **Ship-of-Theseus defense**: without the allowlist, "additive" decays into "any new row is fine," which decays into "any growing file is fine," which decays into a kernel that has been continuously modified across phases without any single phase noticing.

## Options considered

- **Option A — Treat "additive" as semantic: byte-edits to existing files are fine if they don't change behavior.** Status quo across the three lens designs. **Pattern:** Convention-policed discipline. Drifts; the fence becomes non-load-bearing.
- **Option B — Forbid all byte-edits to existing files; new phases ship entirely under new directories.** **Pattern:** Strict immutability. Impossible in practice — adding a probe requires one `import` line in the loader; adding a primitive requires one `import` line in `src/codegenie/__init__.py`; etc.
- **Option C — Enumerate the byte-edits Phase 7 is permitted to make as an explicit allowlist; CI fence asserts byte-identity for every other file under Phase 0–6.5 surface.** **Pattern:** Mechanical-additivity discipline via fence test.

## Decision

Adopt **Option C.** `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` (or equivalent — exact filename per implementation) asserts byte-identity against the Phase 6.5 baseline for every file under `src/codegenie/`, `plugins/`, and the kernel-frozen surface, **except** the 10 explicitly enumerated allowances:

1. `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` — **new file** (additive new file under Phase 3 plugin directory)
2. `plugins/vulnerability-remediation--node--npm/tccm.yaml` — exactly one new `derived_queries:` block (one entry)
3. `src/codegenie/__init__.py` — exactly one new `import` line for the `vuln_provenance` primitive
4. `src/codegenie/schema/repo_context.schema.json` — exactly two `$ref` insertions (one per new probe)
5. `src/codegenie/plugins/tccm.py` — exactly one new optional band: `derived_queries: list[DerivedQuery] = []`
6. `src/codegenie/sandbox/client.py` — exactly one new `role: SandboxRole = Role.GATE` parameter on `spawn(...)`
7. `src/codegenie/sandbox/__init__.py` — exactly one new export: `Role`
8. `src/codegenie/exec/__init__.py` — `ALLOWED_BINARIES` gains `dive` and `docker buildx` (two new rows; see [0015](0015-allowed-binaries-amendment-dive-buildx.md))
9. `pyproject.toml` — exactly one new runtime dependency: `dockerfile-parse`
10. `src/codegenie/plugins/loader.py` — exactly one new explicit-import line for the new plugin's modules

Any other byte-edit to a Phase 0–6.5 file is a fence failure.

## Tradeoffs

| Gain | Cost |
|---|---|
| "Additive" is mechanically defined; no Ship-of-Theseus drift across phases | The fence file is verbose (10 rows now; grows with each phase); maintenance cost is real but bounded |
| Every Phase-7 PR is gated against unanticipated byte-edits — the fence is CI-required and fails fast | Story ordering becomes load-bearing: S0 must land the fence amendment with the empty allowlist before any subsequent story adds files; otherwise the first file-adding PR fails CI. The arch spec's §Open question #7 names this |
| Phase 8+ inherit a fence shape they extend additively (their own allowlist rows under their own ADR) — no quiet kernel drift | Each phase reviews and ratifies its own byte-edits via ADR; the review cost is non-trivial but is the explicit cost of extension-by-addition done honestly |
| The allowlist makes critic roadmap-#4 mechanically true (`§2.5 Extension by addition` is now enforced, not aspirational) | The fence does not catch *semantic* drift inside the allowlist (e.g., a degenerate edit to `src/codegenie/sandbox/client.py` that adds the `role` parameter but breaks an unrelated behavior). Mitigated by `make check` regression suite + bench cassette replay |
| Future engineers reading the codebase see exactly what Phase 7 added to existing files in one place — the fence file is the audit trail | The fence couples Phase 7's adds tightly to specific files; a refactor that moves (e.g.) `ALLOWED_BINARIES` to a new module would require an ADR amendment and a fence revision. Acceptable |

## Pattern fit

Implements **Mechanical-policy enforcement** (toolkit §Operability — Policy as code, fence as test): the policy ("Phase 7 is additive") is asserted by a runtime fence test, not just stated in prose. Also instantiates **Open/Closed at the file boundary** (toolkit §Composition / coupling): closing the existing surface for arbitrary modification while opening a named, ADR-reviewed extension surface. Mirrors `tests/fence/test_pyproject_fence.py` (Phase 0's runtime-closure fence) and `make lint-imports` (cold-start defense). The allowlist itself is **data**, not branching code — adding rows is an additive change to the test fixture.

## Consequences

- `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` (or an extension of `tests/fence/test_kernel_frozen.py`) is CI-required.
- Implementation story ordering (`final-design.md §Open question #7`): Phase 7 **S0** lands the fence amendment with the empty Phase-7 row set; **S1+** add files and grow the allowlist row-by-row, each addition gated by ADR review.
- Each of the 10 rows is justified by its corresponding ADR or component spec; the fence file's docstring includes the ADR pointers.
- Rows beyond the enumerated 10 require an ADR amendment to this document (Phase 7 ADR-0009) plus the corresponding ADR for the underlying decision (e.g., adding a third probe to the plugin doesn't grow the allowlist; adding a third edit to an existing Phase 0–6.5 file does).
- The fence catches: a forgotten cleanup that left a print statement in `src/codegenie/probes/__init__.py`; a refactor that touched `src/codegenie/coordinator/coordinator.py`; a "while I'm here" formatting change to `src/codegenie/types/identifiers.py`. All of these would have shipped silently under semantic-additivity discipline.
- The fence does NOT catch: an edit to a Phase 7-owned file (e.g., `src/codegenie/primitives/vuln_provenance/assembly.py`) that introduces a regression; that's `make check`'s job.
- Phase 3's regression suite (`bench/vuln-remediation/` cassette replay with byte-equal cost ledger, ε ≤ $0.01) continues to be a separate hard pre-merge gate — Phase 7 cannot regress Phase 3 behavior even within the allowlist.
- Phase 8+ extend their own allowlist via a Phase-8 ADR that **extends** Phase 7's, not replaces it. The fence file accumulates one row-set per phase.

## Reversibility

**Medium.** Removing the fence is a one-line CI change but reintroduces the semantic-additivity drift that justified its creation. Adding rows to the allowlist is straightforward (ADR + fence edit + PR). Restructuring the allowlist (e.g., splitting into per-phase fence files) is a multi-phase coordination event but doesn't break Phase 7 specifically.

## Evidence / sources

- `../final-design.md §Lens summary §4` ("'Additive' is defined as `no byte-edit to existing plugin code or stable existing module bodies` — wiring lines […] ARE byte-edits and are explicitly enumerated"), §Test plan → Fence allowlist (exhaustive enumeration)
- `../phase-arch-design.md §Testing strategy §"Fence / structural"`, §"Phase 7 fence allowlist (exhaustive)" — the 10 rows above are the canonical list
- `../critique.md §Roadmap-level critiques §4` ("§2.5 Extension by addition is being treated as 'additive to the body of files'")
- [Phase 3 ADR-0001 — Phase-boundary stable contract](../../03-vuln-deterministic-recipe/ADRs/0001-ship-phase5-contract-surface-by-name.md) (precedent: contract-snapshot test as CI gate)
- CLAUDE.md "Load-bearing architectural commitments — Extension by addition"
