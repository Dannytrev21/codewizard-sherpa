# Story S5-01 — Phase 7 byte-edit allowlist fence (10 enumerated rows)

**Step:** Step 5 — Phase 7 byte-edit allowlist fence + import-linter contracts + `PLUGINS.lock`
**Status:** Ready
**Effort:** M
**Depends on:** S3-03 (npm adapter wiring lands the first Phase-7 byte-edit to a Phase-3 plugin file), S4-04 (SBOM tampering property + AST fence — the last Phase-7 plugin file added before this story closes)
**ADRs honored:** Phase 7 ADR-0009 (the 10-row byte-edit allowlist — verbatim source of truth); Phase 7 ADR-0001 (mechanical-additivity discipline keeps `MultiPluginCoordinator` out of Phase 7 by stopping byte-edits at the kernel boundary); Phase 7 ADR-0005 (probes live under the plugin — this fence is the structural enforcer); Phase 7 ADR-0007 (registry stores classes — primitive surface is closed by the fence + import-linter pair); production ADR-0031 (plugin architecture); Phase 3 ADR-0011 (honest framing — audit + lint posture, not runtime guarantee; CODEOWNERS on `tests/fence/` is the social anchor).

## Context

CLAUDE.md and production design §2.5 commit to **"Extension by addition — new language / new task type = new probes + new Skills, never edits to existing probes or the coordinator."** Across Phase 7's three lens designs, the critic (`critique.md §Roadmap-level critiques §4`) caught the commitment decaying into "byte-edits to existing files are fine because the file grows rather than mutates." Without a mechanical definition of "additive," every future phase silently widens the kernel and we land in Ship-of-Theseus territory — by Phase 10 the coordinator looks nothing like its Phase-0 self and no single phase admits to having changed it.

Phase 7 ADR-0009 takes a position: define "additive" mechanically. Enumerate every byte-edit to a Phase 0–6.5 file Phase 7 is permitted to make. Anything else fails CI before merge. The ADR lists exactly **10 rows** (see Acceptance criteria AC-2); this story lands the fence test that enforces them.

This is the **load-bearing test of Phase 7's headline claim.** If S5-01 ships with a hole (a forgotten row, a regex too loose, a baseline mis-pinned), the entire "extension by addition" framing of Phase 7 — and every later phase that extends this fence — is unprotected. False negatives here invalidate the headline.

The order is deliberate: Steps 3 + 4 land first (the npm adapter wiring and the new Phase-7 plugin tree), then this story lands the fence with rows for the edits Steps 3 + 4 already shipped plus rows reserved for Steps 6–11 still to come. The reserved rows are enumerated in ADR-0009 so the allowlist is the same whether you read it before or after the corresponding step.

**Honest framing (Phase 3 ADR-0011 carry-forward):** this is an audit-and-lint fence, not a runtime guarantee. A PR that edits both the fence file and a violation defeats it; CODEOWNERS on `tests/fence/` + the Phase-6.5 baseline file is the social anchor. The module docstring states this verbatim.

## References — where to look

- **Phase ADR — primary source of truth:**
  - `../ADRs/0009-phase-7-byte-edit-allowlist-fence.md` §Decision — **the 10 enumerated rows below come from here verbatim**. Read cover-to-cover; embed the row text in the fence file's module docstring.
- **Cross-cutting ADRs each row anchors to:**
  - Row 1 (`npm_provenance.py`) — Phase 7 ADR-0004 (primitive home) + Phase 3 ADR-0009 (registry of recipes — same Plugin/Registry shape).
  - Row 2 (`vulnerability-remediation--node--npm/tccm.yaml`) — Phase 7 ADR-0016 (`derived_queries:` band).
  - Row 3 (`src/codegenie/__init__.py`) — Phase 7 ADR-0004 (primitive home).
  - Row 4 (`repo_context.schema.json`) — Phase 7 ADR-0005 (probes under plugin — sub-schemas reach the envelope via `$ref`).
  - Row 5 (`tccm.py`) — Phase 7 ADR-0016.
  - Row 6 (`sandbox/client.py`) — Phase 7 ADR-0003 (additive `role:` enum).
  - Row 7 (`sandbox/__init__.py`) — Phase 7 ADR-0003.
  - Row 8 (`exec/__init__.py`) — Phase 7 ADR-0015 (`ALLOWED_BINARIES` amendment).
  - Row 9 (`pyproject.toml`) — Phase 7 ADR-0013 (`dockerfile-parse` runtime dep).
  - Row 10 (`plugins/loader.py`) — Phase 7 ADR-0005 (plugin's explicit-import).
- **Architecture:**
  - `../phase-arch-design.md §Testing strategy §"Fence / structural"` and §"Phase 7 fence allowlist (exhaustive)" — names the fence file and its row set.
  - `../phase-arch-design.md §Anti-patterns avoided` — calls out semantic-additivity drift as the named pattern this fence kills.
- **High-level-impl:**
  - `../High-level-impl.md §Step 5` — features delivered, exit criteria, risks (especially Risk #3: "byte-edit allowlist fence (Step 5) lands after Steps 3 + 4 have already edited Phase 3 plugin files").
- **Precedent fence (read first):**
  - `tests/fence/test_kernel_frozen.py` — the Phase 3 kernel-frozen fence. Same shape (git-diff against pinned baseline; per-phase `_BASELINES` tuple; CODEOWNERS social anchor; `_KERNEL_ALLOWLIST: Final[frozenset[Path]]` with `# adr:` inline tags). **Reuse the scanner; don't reimplement.** Add `("phase-6_5", Path("tests/fence/_phase6_5_baseline.txt"))` as a one-row append.
  - `tests/fence/_phase2_baseline.txt` — pinned baseline SHA format (40-char lowercase hex; one line). Mirror this shape for `_phase6_5_baseline.txt`.
  - `src/codegenie/_phase3_fence.py` — companion walker pattern. Phase 7's row enforcement does NOT need an AST walker (it's purely git-diff + path-set), but the test layout and `Violation` dataclass discipline mirror it (`Final` tuples, no primitive obsession).
- **Phase 6.5 baseline reference:** identify the last merged Phase 6.5 commit on `main` (likely tagged `phase-6.5-final` or referenced in `docs/phases/06.5-*/High-level-impl.md`); the SHA goes into `tests/fence/_phase6_5_baseline.txt` exactly as `_phase2_baseline.txt` carries Phase 2's.

## Goal

Land `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` so any PR after S5-01 that byte-edits a Phase 0–6.5 file outside the 10 enumerated rows from Phase 7 ADR-0009 fails CI before merge. The fence is git-diff-based, mechanical, and CODEOWNERS-anchored; the 10 rows from ADR-0009 §Decision live in a `Final[frozenset[Path]]` with one inline `# row:` comment per row naming the row number + the owning ADR.

## Acceptance criteria

**Test layout (AC-1)**
- [ ] **AC-1** `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` exists; module docstring (a) cites Phase 7 ADR-0009, (b) embeds the honest-framing language from Phase 3 ADR-0011 ("audit + lint, NOT runtime guarantee — CODEOWNERS on `tests/fence/` + the Phase-6.5 baseline file is the social anchor"), (c) names the CI `fetch-depth: 0` requirement (mirror `tests/fence/test_kernel_frozen.py` line 9–16), (d) lists ADR-0009's 10 rows verbatim. A meta-test scans the docstring for the literal strings `"ADR-0009"`, `"audit + lint"`, `"CODEOWNERS"`, `"fetch-depth"`, `"10 enumerated rows"`.

**The 10 enumerated rows (AC-2) — verbatim from ADR-0009 §Decision**
- [ ] **AC-2** `_PHASE7_BYTE_EDIT_ALLOWLIST: Final[frozenset[Path]]` contains exactly these 10 paths (no more, no fewer); each carries a `# row N` inline comment matching ADR-0009's enumeration:
  1. `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` — new file under Phase 3 plugin (S3-02 / S3-03)
  2. `plugins/vulnerability-remediation--node--npm/tccm.yaml` — one new `derived_queries:` block (S3-03)
  3. `src/codegenie/__init__.py` — one new `import` line for the `vuln_provenance` primitive (Step 1)
  4. `src/codegenie/schema/repo_context.schema.json` — exactly two `$ref` insertions, one per new probe (S7-03)
  5. `src/codegenie/plugins/tccm.py` — one new optional band `derived_queries: list[DerivedQuery] = []` (S8-02)
  6. `src/codegenie/sandbox/client.py` — one new `role: SandboxRole = Role.GATE` parameter on `spawn(...)` (S6-02)
  7. `src/codegenie/sandbox/__init__.py` — one new export `Role` (S6-01)
  8. `src/codegenie/exec/__init__.py` — `ALLOWED_BINARIES` gains `dive` + `docker buildx` (S7-04)
  9. `pyproject.toml` — one new runtime dep `dockerfile-parse` (S7-04)
  10. `src/codegenie/plugins/loader.py` — one new explicit-import line for the new plugin (S8-03)
- [ ] **AC-2.a** A unit test `test_allowlist_size_is_exactly_10` asserts `len(_PHASE7_BYTE_EDIT_ALLOWLIST) == 10`. Adding an 11th row without an ADR amendment fails immediately.
- [ ] **AC-2.b** A unit test `test_every_allowlist_row_matches_adr_0009` parses ADR-0009 §Decision (regex over the markdown numbered list) and asserts the path set is byte-identical to `_PHASE7_BYTE_EDIT_ALLOWLIST`. Drift between code and ADR fails CI loudly.

**Phase 6.5 baseline (AC-3)**
- [ ] **AC-3** `tests/fence/_phase6_5_baseline.txt` exists and contains exactly one line: a 40-char lowercase-hex commit SHA pointing to the last merged Phase 6.5 commit on `main`. `tests/fence/test_kernel_frozen.py::_BASELINES` is amended to `(("phase-2", ...), ("phase-6_5", Path("tests/fence/_phase6_5_baseline.txt")))` (one-row append; OPen/Closed at the file boundary).
- [ ] **AC-3.a** `test_phase6_5_baseline_is_a_real_commit_sha` asserts `re.fullmatch(r"[0-9a-f]{40}", baseline.strip())`.
- [ ] **AC-3.b** `test_phase6_5_baseline_resolves_to_ancestor_of_head` asserts `git merge-base --is-ancestor <baseline> HEAD` exits 0 AND `baseline != HEAD_SHA` (accidental `HEAD` paste rejected).
- [ ] **AC-3.c** `CODEOWNERS` covers `tests/fence/_phase6_5_baseline.txt` (add the path under the existing `tests/fence/` rule if not already covered transitively).

**Diff-scope coverage (AC-4)**
- [ ] **AC-4** The fence computes `git diff --name-status -M <baseline>..HEAD` (rename detection on; `R`/`D`/`A`/`M` all in scope) and filters to **paths matching the Phase 0–6.5 locked surface**:
  - `src/codegenie/**` (every file under the core tree)
  - `plugins/vulnerability-remediation--node--npm/**` (Phase 3 plugin)
  - `pyproject.toml`
  - `Makefile`
  - `src/codegenie/schema/repo_context.schema.json`
  - `plugins/PLUGINS.lock` (covered by S5-04; this fence allows the additive row but the path is allowed-IF-touched not via this allowlist — see Notes)
  - Every changed file in this filtered set must be in `_PHASE7_BYTE_EDIT_ALLOWLIST`, OR be a net-new file under `plugins/distroless-migration--node--npm/**` or `src/codegenie/primitives/vuln_provenance/**` (these are Phase-7-owned new trees and fall outside the fence's scope).
  - Any other path under the locked surface = fence failure with the file path named in the error message.

**Planted-violation evidence (AC-5) — Rule 12 fail-loud, the load-bearing assertion**
- [ ] **AC-5** Parametrized in-test planted-violation cases that exercise the fence under controlled conditions (red-by-construction every CI run; injects synthetic diff via dependency-injection on the diff source — mirrors `tests/fence/test_kernel_frozen.py::test_helpful_error_message`):
  - **AC-5.a** Plant a synthetic edit to `src/codegenie/coordinator/coordinator.py` → fence fails with an error message containing the literal path `"src/codegenie/coordinator/coordinator.py"` AND the strings `"ADR-0009"` AND `"byte-edit allowlist"`.
  - **AC-5.b** Plant a synthetic edit to `src/codegenie/probes/__init__.py` → fence fails (proves "while I'm here" formatting changes are caught).
  - **AC-5.c** Plant a synthetic edit to `plugins/vulnerability-remediation--node--npm/api.py` (Phase 3 plugin file outside the allowlist — `api.py` is NOT row 1; only `adapters/npm_provenance.py` is) → fence fails.
  - **AC-5.d** Plant a synthetic edit to `src/codegenie/output/sanitizer.py` → fence fails.
  - **AC-5.e** Plant a synthetic **rename** `src/codegenie/types/identifiers.py → src/codegenie/types/identifiers_renamed.py` → fence fails (rename detection works).
  - **AC-5.f** Plant a synthetic **delete** of `src/codegenie/exec/run_external_cli.py` → fence fails (`D` lines treated as in-scope).
- [ ] **AC-5.g** A complementary positive case: plant a synthetic edit to `src/codegenie/sandbox/client.py` (row 6) → fence **passes** (proves the allowlist is honored, not just that the fence is always-red).
- [ ] **AC-5.h** A complementary positive case: plant a synthetic ADD of a new file under `plugins/distroless-migration--node--npm/probes/some_new.py` → fence **passes** (proves Phase-7-owned new trees are out of scope).
- [ ] **AC-5.i** **Out-of-test planted-violation evidence:** on a throwaway branch, commit a real edit to `src/codegenie/probes/__init__.py` (e.g., add a trailing comment), run `pytest tests/fence/test_phase7_no_byte_edits_to_locked_files.py`, capture the red output (commit SHAs + failure message) into `_attempts/S5-01.md`; remove the edit, run again, capture green. The 3-line evidence block (red-SHA / removal-SHA / green-SHA) is recorded — missing evidence fails the executor's validation gate.

**Helpful-error-message guard (AC-6) — Rule 12**
- [ ] **AC-6** When the fence fails, the error message contains:
  - The path of every disallowed change (one per line).
  - The literal string `"Phase 7 ADR-0009"` (with markdown link to `docs/phases/07-migration-task-class/ADRs/0009-phase-7-byte-edit-allowlist-fence.md`).
  - The phrase `"ADR amendment required"` (mirrors `tests/fence/test_kernel_frozen.py`'s "ADR amendment" guard).
  - The exact 10-row allowlist text (so the engineer hitting the fence sees what's allowed without leaving the failure output).
  - Verified by `test_failure_message_is_helpful`.

**Determinism + CI requirement (AC-7)**
- [ ] **AC-7** Module docstring + `_attempts/S5-01.md` Notes name the **CI `fetch-depth: 0`** requirement (mirror `tests/fence/test_kernel_frozen.py` line 9–16). If `_ensure_baseline_reachable` cannot resolve the SHA, the fence surfaces a clear error naming the missing SHA + the recovery command (`git fetch --unshallow`). A unit test parametrizes a shallow-clone fixture and asserts the recovery message contains the literal `"fetch-depth"` AND `"unshallow"`.

**Wiring (AC-8 through AC-10)**
- [ ] **AC-8** `Makefile`'s `fence:` target is amended (within row 10's allowed envelope — no: `Makefile` is NOT in the allowlist; this story does NOT touch `Makefile`. Instead, this fence is collected transitively by `pytest tests/fence/` via the existing `make fence` recipe extended in S1-05's AC-3. Verify via `make fence` exit 0).
- [ ] **AC-9** `pytest tests/fence/test_phase7_no_byte_edits_to_locked_files.py -v` exits 0 on the current diff at story landing time.
- [ ] **AC-10** `ruff check`, `ruff format --check`, `mypy --strict tests/fence/test_phase7_no_byte_edits_to_locked_files.py` clean.

**Anti-pattern guard (AC-11)**
- [ ] **AC-11** A meta-assertion (not load-bearing; comment only) names that the fence does NOT catch *semantic* drift inside the allowlist (e.g., a degenerate edit to `src/codegenie/sandbox/client.py` that adds `role:` but breaks an unrelated behavior). The Phase 3–6.5 regression suite + `bench/vuln-remediation/` cassette replay is the named complement (`make check` is the hard pre-merge gate; this fence is necessary, not sufficient). The comment block in the test file cites Phase 7 ADR-0009 §Consequences verbatim on this.

## Implementation outline

1. **Identify the Phase 6.5 baseline SHA.** Walk `git log --oneline` for the last merged Phase 6.5 commit on `main` (or use the documented tag if one exists — check `docs/phases/06.5-*/High-level-impl.md` §Exit criteria). Write the 40-char hex SHA to `tests/fence/_phase6_5_baseline.txt`; commit on a branch that the fence's `_ensure_baseline_reachable` can resolve.
2. **Amend `_BASELINES` in `tests/fence/test_kernel_frozen.py`** (one-row append) — Phase 7 ADR-0009 row 0 (this is not in the 10-row allowlist; `test_kernel_frozen.py` is a fence file under `tests/fence/`, which is out of scope for this fence's path-filter — verify the filter excludes `tests/`).
3. **Write the new fence file** `tests/fence/test_phase7_no_byte_edits_to_locked_files.py`:
   - Module docstring (AC-1 strings embedded).
   - `_PHASE7_BYTE_EDIT_ALLOWLIST: Final[frozenset[Path]]` with the 10 rows + per-row `# row N` comments (AC-2).
   - `_LOCKED_SURFACE_GLOBS: Final[tuple[str, ...]]` = `("src/codegenie/**", "plugins/vulnerability-remediation--node--npm/**", "pyproject.toml", "Makefile", "src/codegenie/schema/repo_context.schema.json")`.
   - `_PHASE7_OWNED_NEW_TREES: Final[tuple[str, ...]]` = `("plugins/distroless-migration--node--npm/**", "src/codegenie/primitives/vuln_provenance/**")`.
   - `def _diff_against_phase6_5_baseline() -> list[tuple[str, Path]]`: returns `[(status, path), ...]` from `git diff --name-status -M`. Dependency-injected via a `diff_source: Callable[[], list[tuple[str, Path]]] | None = None` kwarg so AC-5's planted-violation cases can substitute synthetic diffs.
   - `def _file_is_violating(status: str, path: Path) -> bool`: returns `True` iff path matches a `_LOCKED_SURFACE_GLOBS` entry, is NOT in `_PHASE7_BYTE_EDIT_ALLOWLIST`, and does NOT match a `_PHASE7_OWNED_NEW_TREES` glob.
   - `test_no_byte_edits_outside_allowlist`: the live check.
   - `test_allowlist_size_is_exactly_10`: AC-2.a.
   - `test_every_allowlist_row_matches_adr_0009`: AC-2.b (parse ADR markdown).
   - `test_phase6_5_baseline_is_a_real_commit_sha` / `..._ancestor_of_head`: AC-3.
   - `test_synthetic_violations_caught` (parametrized over AC-5.a–f): the planted-violation matrix.
   - `test_synthetic_allowed_edits_pass` (parametrized over AC-5.g–h): the positive cases.
   - `test_failure_message_is_helpful`: AC-6.
   - `test_shallow_clone_recovery_message`: AC-7.
4. **Run the live check** — should pass on the current diff at story landing (all Step 3 + Step 4 edits are within rows 1–2; no other Phase 0–6.5 file has been touched).
5. **Capture out-of-test planted-violation evidence** (AC-5.i): on a throwaway branch, plant a real edit to `src/codegenie/probes/__init__.py`, screenshot/record the failure, remove, record green. Append to `_attempts/S5-01.md`.
6. **Run the full test suite** (`make check`) — Phase 3–6.5 regression suite green; no other fence regresses.

## TDD plan (red → green → refactor)

**Red:**
1. Write `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` with all ACs above, BUT in a tmp branch deliberately edit `src/codegenie/coordinator/coordinator.py` (add a trailing comment). Run `pytest tests/fence/test_phase7_no_byte_edits_to_locked_files.py -v` — expect `test_no_byte_edits_outside_allowlist` to fail with the helpful error message naming the coordinator path and ADR-0009.
2. Confirm `test_synthetic_violations_caught[edit-coordinator]` (parametrized case) is also red — this is the in-test mutation guard that stays red-by-construction every CI run after the planted edit is removed.

**Green:**
1. Remove the planted edit to `src/codegenie/coordinator/coordinator.py`.
2. Run `pytest tests/fence/test_phase7_no_byte_edits_to_locked_files.py -v` — `test_no_byte_edits_outside_allowlist` now green; the synthetic-injection tests remain green (they inject their own diff via the `diff_source` parameter).
3. Run `make check` — Phase 3–6.5 regression suite green.

**Refactor:**
1. Extract the diff-walking helper to a module-level `_compute_phase7_violations(diff_source, allowlist, locked_globs, owned_new_trees) -> list[Violation]` pure function so AC-5's parametrized tests share one code path with the live check (kills mutation-resistance gaps).
2. Confirm `ruff check` + `ruff format` + `mypy --strict` clean.
3. Ensure `_PHASE7_BYTE_EDIT_ALLOWLIST` rows are sorted in ADR-0009 numerical order — engineers reading the fence file see the row numbers in the same order as the ADR.

## Files to touch

- `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` — new test file (this story's load-bearing artifact).
- `tests/fence/_phase6_5_baseline.txt` — new baseline file (one-line SHA).
- `tests/fence/test_kernel_frozen.py` — `_BASELINES` tuple gains one row for Phase 6.5 (the Phase 3 `test_kernel_frozen.py` baseline tuple shape supports this via Open/Closed). Note: this edit is to a `tests/fence/` file, NOT to a Phase 0–6.5 locked-surface path, so it does not require an ADR-0009 allowlist row.
- `.github/CODEOWNERS` — add explicit coverage for `tests/fence/_phase6_5_baseline.txt` if not already transitive (verify; one-line edit if needed — this file is outside the Phase 7 byte-edit allowlist scope as CODEOWNERS is not under `src/codegenie/`).
- `_attempts/S5-01.md` — append-only attempt log with the 3-line out-of-test planted-violation evidence block.

## Out of scope

- **The actual Phase 6.5 baseline SHA value** — picked at implementation time from `git log` on `main`. Do not hardcode here; the implementer reads HEAD at the time S5-01 lands.
- **Semantic verification of the allowlisted edits.** That's `make check` + `bench/vuln-remediation/` cassette replay's job. This fence only catches *unallowlisted byte-edits*.
- **`PLUGINS.lock` row for the new plugin** — that's S5-04.
- **Plugin-directory probe-placement fence** — that's S5-02.
- **Import-linter contracts for the primitive + plugin tree** — that's S5-03.
- **Phase 8+ allowlist rows** — Phase 8 will land its own ADR amendment extending this fence with its row set. The `_PHASE7_BYTE_EDIT_ALLOWLIST` here is named so Phase 8 can introduce `_PHASE8_BYTE_EDIT_ALLOWLIST` as an additive tuple-of-frozensets one phase later (Open/Closed at the data boundary).

## Notes for the implementer

- **The 10 rows are not a guideline — they are the source of truth.** Phase 7 ADR-0009 §Decision is the canonical text; the fence's `_PHASE7_BYTE_EDIT_ALLOWLIST` must match the ADR byte-for-byte. AC-2.b's ADR-parsing test exists specifically to prevent silent drift; if you find the ADR text needs to change, amend the ADR first, then update the fence (never the reverse).
- **`api.py` vs `adapters/npm_provenance.py` distinction is load-bearing.** Row 1 names `adapters/npm_provenance.py` only. The Phase 3 plugin's `api.py` is NOT allowlisted by row 1 — if S3-03's wiring touches `api.py`, that's a separate question (and a separate row would be needed, which would require an ADR amendment). AC-5.c verifies this is caught.
- **Phase-7-owned new trees fall OUTSIDE the fence's scope, not INSIDE the allowlist.** The distinction matters: the allowlist is for byte-edits to *existing* files; new files under `plugins/distroless-migration--node--npm/**` and `src/codegenie/primitives/vuln_provenance/**` are unconstrained (they are the Phase-7 ownership surface). The fence's path-filter must include this exclusion — verified by AC-5.h.
- **CODEOWNERS is the social anchor (Phase 3 ADR-0011 carry-forward).** The fence catches accidents and "while I'm here" edits; a determined adversary editing both the fence file and the violation defeats it. Acceptable; the cost of stronger guarantees (cryptographic attestation) is deferred to the Sigstore migration in production ADR-0011 / Phase 11.
- **Order of operations during the in-test planted-violation matrix:** because the `diff_source` parameter is dependency-injected, the synthetic-injection tests do NOT mutate the working tree. This avoids the test-leakage problem where a parametrized test leaves the repo in a dirty state. **Do not be tempted to use `subprocess.run(["git", "checkout", ...])` in the tests** — `subprocess.run` with `shell=True` is banned (forbidden-patterns hook) and the dependency-injected path is cleaner.
- **`make fence` collects this transitively** via the existing `pytest tests/unit/test_pyproject_fence.py tests/fence/` recipe; no Makefile edit required (and Makefile is not in the allowlist).
- **Open/Closed at the data boundary:** the test layout (`_PHASE7_BYTE_EDIT_ALLOWLIST` + the per-phase baseline tuple) is shaped so Phase 8 extends it additively (`_PHASE8_BYTE_EDIT_ALLOWLIST` + `_phase7_baseline.txt`). Phase 8's ADR ratifies its own rows; this story does not anticipate Phase 8's row set.
- **Anti-pattern explicitly avoided:** do NOT extract a `Fence` ABC or a `BaseFence` class. The kernel-frozen fence and the byte-edit allowlist fence share *category* but not *input/output shape* (one walks a baseline diff; the other walks an AST). Rule 2 — extract only on the third copy, and these are still two distinct shapes.
- **Surface conflicts (Rule 7):** if at implementation time you find that ADR-0009's 10 rows have drifted from reality (e.g., S6-01 landed `Role` under `src/codegenie/sandbox/types.py` instead of `src/codegenie/sandbox/__init__.py`), STOP and surface the drift in `_attempts/S5-01.md`. The fix is an ADR amendment to ADR-0009, not a silent edit to the row text.
