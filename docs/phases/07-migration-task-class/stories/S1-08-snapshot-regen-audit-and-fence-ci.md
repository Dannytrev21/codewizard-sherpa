# Story S1-08 — Land `snapshot_regen_audit.py` CI gate + fence-CI extension

**Step:** Step 1 — Establish the six additive seams, ADRs, and the contract-surface snapshot canary
**Status:** Ready
**Effort:** S
**Depends on:** S1-07

## Context

S1-07 lands the snapshot file and the permanent test, but the "regenerate + link ADR" discipline is still convention until a CI gate enforces it mechanically. This story closes Gap 5 in two complementary pieces: (1) `tools/snapshot_regen_audit.py` — a GitHub Actions step that, on any PR modifying `tools/contract-surface.snapshot.json`, scrapes the PR body for `ADR-(P\d+-\d+|0\d+)` references and asserts at least one corresponds to an ADR file *also modified in the same PR*; (2) the fence-CI extension that denies `anthropic|chromadb|sentence-transformers` imports under `probes/`, `transforms/`, `recipes/`, and `catalogs/` — the structural enforcement of G18 (zero LLM tokens inside Phase 7 boundary).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap 5` (lines ~1427–1431) — the audit script's exact behavior: regex `ADR-(P\d+-\d+|0\d+)`, must match a modified ADR file path under `docs/phases/*/ADRs/` or `docs/production/adrs/`, fails with a clear error.
  - `../phase-arch-design.md §Testing strategy ›CI gates #9` — fence-CI deny-import scope (`anthropic|chromadb|sentence-transformers` under `probes/transforms/recipes/catalogs/`).
  - `../phase-arch-design.md §Agentic best practices` — "Phase 7 itself does **not** import `anthropic`."
  - `../High-level-impl.md §Step 1 ›Features delivered` — `tools/snapshot_regen_audit.py` named explicitly.
- **Phase ADRs:**
  - `../ADRs/0009-contract-surface-snapshot-canary.md` — ADR-P7-009 — `tools/snapshot_regen_audit.py` is the *mechanical* enforcement of "ADR-or-revert"; closes Risk #4.
  - `../ADRs/0001-six-named-additive-seams-and-adr-0028-amendment.md` — ADR-P7-008 — the discipline this audit enforces.
- **Existing code (read before writing):**
  - The repo's existing GitHub Actions workflows under `.github/workflows/` — confirm whether a `fence_ci` workflow or job already exists (the architecture mentions `fence_ci.yaml`). If yes, extend it; if no, add it.
  - The existing fence-CI implementation (`tools/fence_ci.py` or similar) — read its allowlist mechanism; extend, do not fork.
  - The `gh` CLI / GitHub Actions environment variables to scrape PR body — `GITHUB_EVENT_PATH` is the typical path to the event JSON.

## Goal

A PR that touches `tools/contract-surface.snapshot.json` without modifying a matching per-phase or production ADR fails CI loudly; a PR that imports `anthropic`, `chromadb`, or `sentence-transformers` under `src/codegenie/{probes,transforms,recipes,catalogs}/` fails CI loudly; both failures are local-reproducible.

## Acceptance criteria

- [ ] `tools/snapshot_regen_audit.py` is committed and runnable as `python tools/snapshot_regen_audit.py --pr-body <text-or-file> --changed-files <file-list>`. Its behavior: (a) if `tools/contract-surface.snapshot.json` is in `--changed-files`, scan `--pr-body` for `ADR-(P\d+-\d+|0\d+)` matches; (b) for each match, resolve to a candidate path under `docs/phases/*/ADRs/` or `docs/production/adrs/`; (c) assert at least one such file is also in `--changed-files`; (d) exit 0 on success, exit non-zero with a clear stderr message naming the snapshot and the missing ADR.
- [ ] A GitHub Actions job (e.g., `snapshot-regen-audit` in `.github/workflows/ci.yml` or a dedicated workflow) runs `tools/snapshot_regen_audit.py` on every PR using `${{ github.event.pull_request.body }}` and the PR's changed-files list (resolved via `gh pr view` or the `paths-filter` action).
- [ ] `tests/integration/test_snapshot_regen_audit.py` is committed and green: drives `tools/snapshot_regen_audit.py` via `subprocess.run` against four cases — (1) snapshot changed + ADR link in body + ADR file in changed-files → exit 0; (2) snapshot changed + ADR link in body but ADR file NOT in changed-files → non-zero exit with `"missing matching ADR file"` (or similar) in stderr; (3) snapshot changed + no ADR link in body → non-zero exit with `"no ADR reference"` in stderr; (4) snapshot unchanged → exit 0 regardless of body content.
- [ ] Fence-CI extension: `tools/fence_ci.py` (or wherever the deny-import logic lives) blocks any import line matching `^(from|import) (anthropic|chromadb|sentence_transformers)\b` (handle both `sentence-transformers` and `sentence_transformers` — Python module name uses underscore) inside `src/codegenie/probes/`, `src/codegenie/transforms/`, `src/codegenie/recipes/`, and `src/codegenie/catalogs/`. Confirmed by adding the four scopes to the existing deny-list config and a test.
- [ ] `tests/integration/test_fence_ci_phase7_scope.py` is committed and green: creates a temporary Python file under each of the four scopes (using `tmp_path` + a monkey-patched scope root, or a real fixture directory) that imports `anthropic`; asserts `tools/fence_ci.py` (invoked as a subprocess or directly) fails with non-zero exit and a clear error citing the offending import + the rule.
- [ ] CI's `merge` lane invokes both `snapshot-regen-audit` and the fence-CI checks; both are required-to-pass status checks on the default branch.
- [ ] `ruff check`, `ruff format --check`, and `mypy --strict` pass on `tools/snapshot_regen_audit.py` and the two new test files.

## Implementation outline

1. Read existing fence-CI config under `.github/workflows/` and `tools/` — identify the existing deny-import mechanism. The architecture mentions `fence_ci.yaml`; confirm.
2. Write the failing tests in `tests/integration/test_snapshot_regen_audit.py` and `tests/integration/test_fence_ci_phase7_scope.py` (TDD red).
3. Author `tools/snapshot_regen_audit.py`:
   - Parse CLI args (`argparse`).
   - Regex: `ADR-(P\d+-\d+|0\d+)`.
   - For each match, candidate ADR paths: `docs/phases/*/ADRs/000N-*.md`, `docs/production/adrs/000N-*.md`. Use `pathlib.Path.glob` to resolve; match if the changed-files list contains any.
   - Exit 0 if the snapshot is not changed OR if a matching ADR file is in the changed-files list.
   - Exit 1 otherwise with `print(..., file=sys.stderr)`.
4. Extend fence-CI: add `probes/`, `transforms/`, `recipes/`, `catalogs/` to the scope under which `anthropic|chromadb|sentence_transformers` are denied. Use the existing config mechanism (YAML, JSON, or Python list — match precedent).
5. Add a `.github/workflows/snapshot-regen-audit.yml` job (or a step in `ci.yml`) invoking `tools/snapshot_regen_audit.py` with `${{ github.event.pull_request.body }}` and the PR's changed-files list. Mark the job as required-to-pass via branch protection (out of band — document in PR description).
6. Refactor: error messages must name the rule (`ADR-P7-009 snapshot-regen audit failed:`), the offending file (`tools/contract-surface.snapshot.json`), and the actionable fix (`add ADR-P7-NNN reference to PR body AND modify the corresponding ADR file`).

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test files:
- `tests/integration/test_snapshot_regen_audit.py`
- `tests/integration/test_fence_ci_phase7_scope.py`

```python
# tests/integration/test_snapshot_regen_audit.py
import subprocess, pathlib


SCRIPT = pathlib.Path("tools/snapshot_regen_audit.py")


def _run(pr_body: str, changed_files: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["python", str(SCRIPT), "--pr-body", pr_body, "--changed-files", *changed_files],
        capture_output=True, text=True, check=False,
    )


def test_passes_when_snapshot_changed_with_adr_link_and_adr_file_modified():
    result = _run(
        pr_body="Implements ADR-P7-002 (widen ObjectiveSignals)",
        changed_files=[
            "tools/contract-surface.snapshot.json",
            "docs/phases/07-migration-task-class/ADRs/0003-objective-signals-widening-and-allowlists.md",
        ],
    )
    assert result.returncode == 0, result.stderr


def test_fails_when_snapshot_changed_with_adr_link_but_no_adr_file_modified():
    result = _run(
        pr_body="Implements ADR-P7-002",
        changed_files=["tools/contract-surface.snapshot.json"],
    )
    assert result.returncode != 0
    assert "missing matching ADR file" in result.stderr.lower() or "adr" in result.stderr.lower()


def test_fails_when_snapshot_changed_with_no_adr_reference_in_body():
    result = _run(
        pr_body="Fixed a typo",
        changed_files=["tools/contract-surface.snapshot.json"],
    )
    assert result.returncode != 0
    assert "adr" in result.stderr.lower()


def test_passes_when_snapshot_unchanged_regardless_of_body():
    result = _run(
        pr_body="Anything at all",
        changed_files=["src/codegenie/probes/base.py"],
    )
    assert result.returncode == 0


def test_production_adr_reference_also_satisfies_the_rule():
    # ADR-0028 amendment is a legitimate snapshot-regen justification.
    result = _run(
        pr_body="Amends ADR-0028 per Phase 7's behavior-preserving additive extension.",
        changed_files=[
            "tools/contract-surface.snapshot.json",
            "docs/production/adrs/0028-task-class-introduction-order.md",
        ],
    )
    assert result.returncode == 0, result.stderr
```

```python
# tests/integration/test_fence_ci_phase7_scope.py
import subprocess, pathlib, textwrap


FENCE_CI = pathlib.Path("tools/fence_ci.py")  # adjust to actual location


def _write_offending_file(tmp_path, scope_subdir, content):
    target = tmp_path / "src" / "codegenie" / scope_subdir / "offender.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return target


def test_anthropic_import_under_probes_rejected(tmp_path, monkeypatch):
    # Either invoke fence_ci as a subprocess pointed at tmp_path, or import-and-call its main()
    _write_offending_file(tmp_path, "probes", "import anthropic\n")
    monkeypatch.chdir(tmp_path)
    result = subprocess.run(
        ["python", str(pathlib.Path.cwd().parents[0] / FENCE_CI)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert "anthropic" in result.stderr.lower()


def test_chromadb_import_under_transforms_rejected(tmp_path, monkeypatch):
    _write_offending_file(tmp_path, "transforms", "from chromadb import Client\n")
    # ... similar shape


def test_sentence_transformers_import_under_recipes_rejected(tmp_path, monkeypatch):
    _write_offending_file(tmp_path, "recipes", "import sentence_transformers\n")
    # ... similar shape


def test_anthropic_import_under_catalogs_rejected(tmp_path, monkeypatch):
    _write_offending_file(tmp_path, "catalogs", "import anthropic\n")
    # ... similar shape


def test_anthropic_import_under_planner_still_allowed(tmp_path, monkeypatch):
    # planner/ is allowed to import anthropic — FallbackTier LLM-fallback lives there.
    _write_offending_file(tmp_path, "planner", "import anthropic\n")
    # ... assert exit 0
```

Expected red failure mode: `FileNotFoundError: tools/snapshot_regen_audit.py` (script doesn't exist) → after authoring → `AssertionError: ...` if the audit logic is incomplete.

### Green — make it pass

1. `tools/snapshot_regen_audit.py`:

   ```python
   # tools/snapshot_regen_audit.py — sketch
   import argparse, pathlib, re, sys

   ADR_REGEX = re.compile(r"ADR-(P\d+-\d+|0\d+)")

   def main(argv: list[str] | None = None) -> int:
       parser = argparse.ArgumentParser()
       parser.add_argument("--pr-body", required=True)
       parser.add_argument("--changed-files", nargs="+", required=True)
       args = parser.parse_args(argv)

       snapshot = "tools/contract-surface.snapshot.json"
       if snapshot not in args.changed_files:
           return 0

       matches = ADR_REGEX.findall(args.pr_body)
       if not matches:
           print(
               f"snapshot-regen audit FAILED (ADR-P7-009): {snapshot} was modified but the PR body "
               f"contains no ADR-NNNN reference. Add the per-phase ADR you are implementing.",
               file=sys.stderr,
           )
           return 1

       adr_dirs = list(pathlib.Path("docs").rglob("ADRs")) + [pathlib.Path("docs/production/adrs")]
       for changed in args.changed_files:
           p = pathlib.Path(changed)
           if any(parent in p.parents for parent in adr_dirs) and p.suffix == ".md":
               return 0  # at least one ADR file modified
       print(
           f"snapshot-regen audit FAILED (ADR-P7-009): {snapshot} modified and ADR reference "
           f"{matches[0]!r} found in PR body, but no matching ADR file in changed-files list. "
           f"missing matching ADR file.",
           file=sys.stderr,
       )
       return 1


   if __name__ == "__main__":
       sys.exit(main())
   ```

2. Extend fence-CI: locate the existing deny-import config (likely a Python dict in `tools/fence_ci.py` or a YAML at `.github/workflows/fence_ci.yaml`). Add four entries to the scope:

   ```python
   FENCE_RULES = {
       # ... existing rules ...
       "src/codegenie/probes/": ["anthropic", "chromadb", "sentence_transformers"],
       "src/codegenie/transforms/": ["anthropic", "chromadb", "sentence_transformers"],
       "src/codegenie/recipes/": ["anthropic", "chromadb", "sentence_transformers"],
       "src/codegenie/catalogs/": ["anthropic", "chromadb", "sentence_transformers"],
   }
   ```

3. Add the GitHub Actions step (in an appropriate workflow file):

   ```yaml
   - name: snapshot-regen audit
     run: |
       gh pr view ${{ github.event.pull_request.number }} --json files --jq '.files[].path' > /tmp/changed.txt
       python tools/snapshot_regen_audit.py \
         --pr-body "${{ github.event.pull_request.body }}" \
         --changed-files $(cat /tmp/changed.txt)
     env:
       GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
   ```

### Refactor — clean up

- Error messages: every audit failure cites the rule (`ADR-P7-009`) and the actionable fix.
- `tools/snapshot_regen_audit.py` module docstring describes the discipline and references S1-07/S1-08.
- The audit script must support being invoked with zero changed-files (e.g., draft PRs) without crashing; it returns 0 in that case.
- Confirm the GitHub Actions step doesn't silently swallow audit-script stderr — pipe to step summary or fail-loud-and-stop.

## Files to touch

| Path | Why |
|---|---|
| `tools/snapshot_regen_audit.py` | New CLI tool — Gap 5 mechanical enforcement of "ADR-or-revert." |
| `tools/fence_ci.py` (or wherever fence-CI lives) | Extend deny-import scope with four Phase 7 directories. |
| `.github/workflows/ci.yml` (or new `snapshot-regen-audit.yml`) | Wire the audit as a required PR check. |
| `tests/integration/test_snapshot_regen_audit.py` | New test — four cases (passes / missing-file / missing-ref / unchanged) + production-ADR case. |
| `tests/integration/test_fence_ci_phase7_scope.py` | New test — verifies the four denied imports are blocked under the four new scopes; planner/ remains allowed. |

## Out of scope

- **Adding new ADRs to the audit's match scope (e.g., RFC-NNNN, DESIGN-NNNN)** — the regex is per ADR-P7-009's exact text (`ADR-(P\d+-\d+|0\d+)`). Future ID styles are a separate ADR.
- **PR-template enforcement (the checkbox "I have added/edited a per-phase ADR")** — convention only; ADR-P7-009 explicitly relies on the mechanical audit instead. Do not add template-validation logic.
- **Branch-protection rule setup** — that's a repo-admin step, document in the PR description; this story makes the check exist, the admin marks it required.
- **Snapshot-discipline rehearsal PRs (A: no-op edit fires canary; B: legitimate regen passes)** — S8-04.
- **Adding `litellm`, `openai`, or other LLM SDKs to the fence-CI deny-list** — only the three named SDKs are in scope per `phase-arch-design.md §Testing strategy ›CI gates #9`. Other SDKs are future work.

## Notes for the implementer

- The fence-CI test cases include a *negative* case (`planner/` still allowed to import `anthropic`) — without it, you could trivially over-fence and break Phase 4's existing LLM-fallback path. The test is the guard against an over-broad fence.
- The audit script's regex must match both `ADR-P7-001` (Phase 7 hyphenated form) and `ADR-0028` (production four-digit form). Both must be acceptable. If your regex misses one, the production-ADR-reference test case fails — that's the canary.
- Resolve ADR-link → file path via `pathlib.Path.glob`, not by parsing the ADR ID's number into a filename — filename slugs vary (e.g., `0002-register-gate-probe-new-registry.md`, not `0002.md`). The check is: any `.md` file under `docs/phases/*/ADRs/` or `docs/production/adrs/` modified in this PR satisfies the rule. The regex match in the body is the *justification*; the file modification is the *evidence*.
- A PR that touches the snapshot AND multiple ADRs (e.g., S1-07 itself, which touches ADR-P7-001..006 via S1-06's amendment) must pass — the audit asserts "at least one matching ADR file" not "exactly one." Test this case if you add a fifth test case.
- The GitHub Actions integration is the *enforcement*; the test integration is the *local-reproducibility*. Without the local test, debugging a CI failure means amending a PR and re-pushing — friction the discipline cannot afford. Run both locally before declaring done.
- `gh pr view --json files` can fail on draft PRs or PRs without head context; handle the exit code in the workflow step. The audit script itself must tolerate zero changed-files (return 0 — there's nothing to enforce).
- Fence-CI implementation likely already supports scope-based deny rules (Phase 0 ships some form of this). *Extend the existing config; do not fork* — per CLAUDE.md "Surgical Changes." If you find yourself rewriting fence-CI, stop and re-read the existing implementation.
- Per Rule 12 "Fail loud": the audit script must print to `stderr` with the rule ID, the offending file, and the actionable fix. Silent exit-1 is unhelpful; verbose exit-1 is the discipline's UX surface for the PR author.
- The snapshot file `tools/contract-surface.snapshot.json` is the *only* trigger surface for this audit. If S2-06 later extends the audit scope to `tools/digests.yaml` regens or `.codegenie/cache/base_catalog.json` shape, that's a *new ADR* — not an in-place edit to this audit.
- After this story lands, the next snapshot regen (likely in S2-06) is the *first live test* of the discipline. Document this in your PR description: "When S2-06 modifies the snapshot to include `base_catalog` shape, S2-06's PR must link ADR-P7-NNN and modify the corresponding ADR file in the same PR — `tools/snapshot_regen_audit.py` enforces."
