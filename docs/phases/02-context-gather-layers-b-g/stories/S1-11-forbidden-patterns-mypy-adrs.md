# Story S1-11 — `forbidden-patterns` extension + `mypy --warn-unreachable` rollout + nine ADRs

**Step:** Step 1 — Plant new domain primitives, kernel contracts, and the nine new ADRs
**Status:** Ready
**Effort:** M
**Depends on:** S1-01, S1-02, S1-03, S1-04, S1-09, S1-10
**ADRs honored:** 02-ADR-0001 through 02-ADR-0010 (this story lands all nine and validates they exist; ADR-0010 is also landed via this story's PR but the smart-constructor *code* lands in S3-02)

## Context

The nine new ADRs document irreversible (or hard-to-reverse) Phase 2 commitments; they MUST land *with* the code that enforces them. This story finalizes Step 1 by (a) extending Phase 0's `forbidden-patterns` pre-commit hook to ban `model_construct` under the new Phase 2 packages (closing the smart-constructor escape hatch the architect's anti-patterns row 12 names), (b) enabling `mypy --warn-unreachable` *per-module* (not repo-wide — Phase 0/1 blast radius, final-design Open Q 5) for the five named modules, and (c) confirming all nine ADRs are present, Nygard-format, and linked from `docs/phases/02-context-gather-layers-b-g/README.md`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Anti-patterns avoided"` row 12 — `model_construct()` bypass; Phase 0's `forbidden-patterns` pre-commit (extended here) bans it under the new packages.
  - `../phase-arch-design.md §"Open questions deferred to implementation"` #5 — `mypy --warn-unreachable` rollout policy: per-module only in Phase 2; full-repo rollout is a tracked backlog item (S8-04 files the issue).
  - `../phase-arch-design.md §"Path to production end state"` — nine-ADR table with one-line records (the source of truth for the nine ADRs that must exist).
  - `../phase-arch-design.md §"CI gates"` job 7 (`mypy`) — `mypy --strict` repo-wide + `--warn-unreachable` per-module overrides.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md` — 02-ADR-0001
  - `../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md` — 02-ADR-0002
  - `../ADRs/0003-coordinator-heaviness-sort-annotation.md` — 02-ADR-0003
  - `../ADRs/0004-image-digest-as-declared-input-token.md` — 02-ADR-0004
  - `../ADRs/0005-secret-findings-no-plaintext-persistence.md` — 02-ADR-0005
  - `../ADRs/0006-index-freshness-sum-type-location.md` — 02-ADR-0006
  - `../ADRs/0007-no-plugin-loader-in-phase-2.md` — 02-ADR-0007
  - `../ADRs/0008-no-event-stream-in-phase-2.md` — 02-ADR-0008
  - `../ADRs/0009-pytest-xdist-veto-preserved.md` — 02-ADR-0009
  - `../ADRs/0010-redacted-slice-smart-constructor-at-writer-boundary.md` — 02-ADR-0010 (the smart-constructor *code* lands in S3-02; the ADR is among the Step-1 nine — note: the manifest says "nine ADRs land in Step 1"; the README counts ten ADR files. Reconcile: Step 1 lands the **nine** Step-1 ADRs (0001–0009); 0010 ships in Step 3 alongside S3-02 unless the README dates show it already drafted — verify and adjust the list).
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0033-typed-identifiers.md` — production ADR-0033 — the binding discipline for the newtypes S1-05 ships.
- **Source design:**
  - `../final-design.md §"Open Q 5"` — per-module rollout policy.
- **Existing code:**
  - `src/codegenie/output/sanitizer.py` — Phase 0's `forbidden-patterns` lives elsewhere (likely a pre-commit script); the manifest says "extend `output/sanitizer.py`'s `forbidden-patterns` pre-commit (Phase 0)" — read the Phase 0 implementation first; the hook is a regex-AST scan, not a runtime check.
  - `pyproject.toml` — `[tool.mypy]` section; `[[tool.mypy.overrides]]` is where per-module `warn_unreachable` lands.
  - `.pre-commit-config.yaml` (Phase 0) — the hook list; the `forbidden-patterns` hook is configured here.
- **External docs (only if directly relevant):**
  - https://mypy.readthedocs.io/en/stable/config_file.html#per-module-and-global-options — `warn_unreachable` per-module override.

## Goal

(1) Extend Phase 0's `forbidden-patterns` pre-commit hook to ban `model_construct` under `src/codegenie/{indices,tccm,skills,conventions,adapters,depgraph,output}/**`; (2) enable `mypy --warn-unreachable` per-module in `pyproject.toml` for `codegenie.{indices, probes.layer_b.index_health, report, adapters, tccm}/**` (the five named modules); (3) verify the nine Step-1 ADR files exist, are Nygard-format, and are listed in `docs/phases/02-context-gather-layers-b-g/README.md`.

## Acceptance criteria

- [ ] **AC-1.** Phase 0's `forbidden-patterns` pre-commit hook (or equivalent — read the existing implementation first) is extended to fail when a `.py` file under `src/codegenie/{indices,tccm,skills,conventions,adapters,depgraph,output}/**` contains the string `.model_construct(` or `model_construct=` (regex; exact pattern documented in the hook's source). The error message names ADR-0010 §Decision + production ADR-0033 §3.
- [ ] **AC-2.** A *positive* test: a synthetic `.py` file containing `Foo.model_construct(...)` under each of the seven banned packages, fed through the hook, fails. The test uses `subprocess.run(["pre-commit", "run", "forbidden-patterns", "--files", path], ...)` against a temp file.
- [ ] **AC-3.** A *negative* test: a synthetic `.py` file containing `Foo.model_construct(...)` under `src/codegenie/probes/layer_a/` (a Phase 0/1 package NOT in the banned list) passes the hook — proving the ban is surgical, not repo-wide. (The architect's "no Phase 0/1 retrofit" discipline.)
- [ ] **AC-4.** `pyproject.toml` `[[tool.mypy.overrides]]` adds five per-module `warn_unreachable = true` entries:
  ```toml
  [[tool.mypy.overrides]]
  module = "codegenie.indices.*"
  warn_unreachable = true

  [[tool.mypy.overrides]]
  module = "codegenie.probes.layer_b.index_health"
  warn_unreachable = true

  [[tool.mypy.overrides]]
  module = "codegenie.report.*"
  warn_unreachable = true

  [[tool.mypy.overrides]]
  module = "codegenie.adapters.*"
  warn_unreachable = true

  [[tool.mypy.overrides]]
  module = "codegenie.tccm.*"
  warn_unreachable = true
  ```
  The repo-wide `[tool.mypy]` block is **not** changed (no `warn_unreachable = true` at the top level).
- [ ] **AC-5.** A *test* verifies the per-module rollout is real: delete an arm from the exhaustive `match` test in `tests/unit/indices/test_freshness.py` (e.g., remove the `case CommitsBehind():` arm) and run `mypy --strict` on that file. The build MUST fail with an `error: Right operand of "and" is never used` or `unreachable` diagnostic. The test is a manual-procedure check documented in the story's "Notes for the implementer" — automating it requires a subprocess `mypy` invocation. **Recommended automation**: a CI job `mypy-warn-unreachable-check` that runs `mypy --strict` on a deliberately-broken fixture and asserts non-zero exit. (Story S8-01 lands the canonical example; S1-11 ships the override.)
- [ ] **AC-6.** All nine Step-1 ADR files exist under `docs/phases/02-context-gather-layers-b-g/ADRs/` (`0001` through `0009`). Each contains the Nygard sections: `## Context`, `## Options considered`, `## Decision`, `## Tradeoffs`, `## Pattern fit`, `## Consequences`, `## Reversibility`, `## Evidence / sources`. (Verify against `0001`'s shape — already present from phase-architect output.)
- [ ] **AC-7.** `docs/phases/02-context-gather-layers-b-g/README.md` contains a list-of-ADRs section linking each of the nine. A test (or a simple `grep`) asserts every ADR filename appears at least once in the README.
- [ ] **AC-8.** A Step-1-completion smoke test: invoking `pytest tests/unit/{indices,adapters,tccm,types,depgraph,exec,probes}/` exits 0; every Step-1 story's test file is included.
- [ ] **AC-9.** Phase 0 `fence` job (no `anthropic`/`openai`/`langgraph`/`httpx`/`requests`/`socket` import under `src/codegenie/`) stays green — verify by running the existing fence CI script against the post-Step-1 tree.
- [ ] **AC-10.** Phase 0 `contract-freeze` job stays green — the only documented amendment is S1-09's `image_digest_resolver` field.
- [ ] **AC-11.** ADR-0010 reconciliation: the manifest says "nine ADRs land in Step 1." The ADRs/ directory currently contains ten files (0001–0010). Either (a) 0010 was prematurely drafted by the phase-architect and ships in Step 3 alongside S3-02 — in which case the test's "exists check" asserts files 0001–0009 only, and 0010 is documented as "Step-3 land" in the README; OR (b) 0010 already ships in Step 1 because the smart-constructor *contract* exists even if the code lands later. **Pick at impl time** — the architect's source ledger should clarify. Default: keep 0010 as a Step-3 deliverable per dependency-DAG ordering (manifest: "S3-02 → S3-03"); document the choice in the README's ADR list ordering.
- [ ] **AC-12.** The TDD plan's red test exists, was committed, and is green.
- [ ] **AC-13.** `ruff check`, `ruff format --check`, `mypy --strict` (repo-wide + per-module warn-unreachable on the five named modules) all pass; `pre-commit run --all-files` passes; `pytest` full suite passes.

## Implementation outline

1. Read the Phase 0 `forbidden-patterns` implementation — locate the hook (likely in `.pre-commit-config.yaml` + a Python script under `scripts/forbidden_patterns.py` or `tools/`). Extend with a new pattern: `model_construct` under the seven banned packages.
2. Add the five per-module `[[tool.mypy.overrides]]` entries to `pyproject.toml`.
3. Verify all nine ADR files exist and conform to Nygard format. They were generated by the phase-architect; this story is the validation step, not the authoring step. If any ADR is missing or non-conformant, file a fix here.
4. Verify the README lists all nine ADRs by filename + ADR ID.
5. Write the tests (forbidden-patterns positive/negative, README ADR-listing, fence + contract-freeze CI re-runs).
6. Refactor: ensure the hook's error message names ADR-0010 and production ADR-0033 (the binding rules).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/pre_commit/test_forbidden_patterns_phase2_extension.py`

```python
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


BANNED_PACKAGES = [
    "indices", "tccm", "skills", "conventions", "adapters", "depgraph", "output",
]

ALLOWED_PHASE0_PACKAGES = [
    "probes/layer_a",  # Phase 1 — model_construct not banned here
]


def _write_synth(tmp_path: Path, rel: str, body: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


@pytest.mark.parametrize("pkg", BANNED_PACKAGES)
def test_model_construct_banned_under_phase2_packages(tmp_path: Path, pkg: str) -> None:
    body = "from pydantic import BaseModel\n" \
           "class Foo(BaseModel): pass\n" \
           "Foo.model_construct(x=1)\n"
    target = _write_synth(tmp_path, f"src/codegenie/{pkg}/synth.py", body)
    # Invoke the forbidden-patterns hook directly (script path or pre-commit run).
    # Adapt the command to whatever Phase 0 ships; below is the most common shape.
    result = subprocess.run(
        [sys.executable, "scripts/forbidden_patterns.py", str(target)],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert result.returncode != 0, f"hook must reject model_construct under {pkg}"
    assert "model_construct" in result.stdout + result.stderr
    assert "ADR-0010" in result.stdout + result.stderr or "ADR-0033" in result.stdout + result.stderr


@pytest.mark.parametrize("pkg", ALLOWED_PHASE0_PACKAGES)
def test_model_construct_NOT_banned_under_phase0_phase1_packages(tmp_path: Path, pkg: str) -> None:
    """AC-3 — surgical rollout discipline. Phase 0/1 retrofit is explicitly
    out of scope (Open Q 5)."""
    body = "from pydantic import BaseModel\n" \
           "class Foo(BaseModel): pass\n" \
           "Foo.model_construct(x=1)\n"
    target = _write_synth(tmp_path, f"src/codegenie/{pkg}/synth.py", body)
    result = subprocess.run(
        [sys.executable, "scripts/forbidden_patterns.py", str(target)],
        capture_output=True, text=True, cwd=tmp_path,
    )
    # Phase 0/1 retrofit is out of scope. The hook may emit a warning, but
    # must NOT fail the build.
    assert result.returncode == 0
```

Test file path: `tests/unit/test_adr_inventory_phase2.py`

```python
from __future__ import annotations
from pathlib import Path

import pytest


ADR_DIR = Path(__file__).resolve().parents[2] / "docs" / "phases" / "02-context-gather-layers-b-g" / "ADRs"
README = ADR_DIR.parent / "README.md"

REQUIRED_ADRS = [
    "0001-add-docker-and-security-cli-tools-to-allowed-binaries.md",
    "0002-tree-sitter-grammars-phase-2-amendment.md",
    "0003-coordinator-heaviness-sort-annotation.md",
    "0004-image-digest-as-declared-input-token.md",
    "0005-secret-findings-no-plaintext-persistence.md",
    "0006-index-freshness-sum-type-location.md",
    "0007-no-plugin-loader-in-phase-2.md",
    "0008-no-event-stream-in-phase-2.md",
    "0009-pytest-xdist-veto-preserved.md",
    # 0010 lands in Step 3 alongside S3-02 (per the dependency DAG); not required for Step-1 completion.
]


@pytest.mark.parametrize("name", REQUIRED_ADRS)
def test_adr_file_exists_and_nygard_shape(name: str) -> None:
    path = ADR_DIR / name
    assert path.exists(), f"missing ADR: {name}"
    text = path.read_text()
    for section in ("## Context", "## Decision", "## Tradeoffs", "## Consequences", "## Reversibility"):
        assert section in text, f"{name} missing Nygard section: {section}"


def test_phase2_readme_lists_every_step1_adr() -> None:
    readme_text = README.read_text()
    for name in REQUIRED_ADRS:
        # Slugified ADR ID or filename presence — be lenient about exact format,
        # strict about presence.
        adr_id = name.split("-", 1)[0]  # "0001"
        assert adr_id in readme_text or name in readme_text, (
            f"docs/phases/02-context-gather-layers-b-g/README.md does not link ADR {name}"
        )
```

Test file path: `tests/unit/test_mypy_warn_unreachable_overrides.py`

```python
from __future__ import annotations
import tomllib
from pathlib import Path


def test_pyproject_has_five_per_module_warn_unreachable() -> None:
    cfg = tomllib.loads(Path("pyproject.toml").read_text())
    overrides = cfg.get("tool", {}).get("mypy", {}).get("overrides", [])
    enabled_modules = {o["module"] for o in overrides if o.get("warn_unreachable") is True}
    expected = {
        "codegenie.indices.*",
        "codegenie.probes.layer_b.index_health",
        "codegenie.report.*",
        "codegenie.adapters.*",
        "codegenie.tccm.*",
    }
    assert expected.issubset(enabled_modules), (
        f"missing per-module warn_unreachable overrides; got {enabled_modules}, expected {expected}"
    )


def test_mypy_top_level_warn_unreachable_is_NOT_set() -> None:
    """AC-4 — repo-wide rollout is explicitly out of scope (Open Q 5)."""
    cfg = tomllib.loads(Path("pyproject.toml").read_text())
    top = cfg.get("tool", {}).get("mypy", {})
    assert top.get("warn_unreachable", False) is False, (
        "warn_unreachable must NOT be set repo-wide; Phase 2 only enables per-module "
        "(Open Q 5 — Phase 0/1 blast radius)."
    )
```

Run — confirm tests fail because the hook isn't extended and the overrides aren't in `pyproject.toml`. Commit.

### Green — make it pass

1. In `scripts/forbidden_patterns.py` (or wherever Phase 0 ships the hook): extend the pattern list to include:
   ```python
   _PHASE2_BANNED_PACKAGES = (
       "indices", "tccm", "skills", "conventions", "adapters", "depgraph", "output",
   )
   _PHASE2_FORBIDDEN_PATTERN = re.compile(r"\.model_construct\s*\(|model_construct\s*=")

   def _is_in_phase2_banned(path: pathlib.Path) -> bool:
       parts = path.parts
       try:
           src_idx = parts.index("codegenie")
       except ValueError:
           return False
       if src_idx + 1 >= len(parts):
           return False
       return parts[src_idx + 1] in _PHASE2_BANNED_PACKAGES
   ```
   On match, emit: `f"{path}: forbidden `model_construct` under {pkg}/. See 02-ADR-0010 §Decision and production ADR-0033 §3 — smart constructors must be the only public path; use `from_validated_input(...)` or the public model factory."`
2. In `pyproject.toml`, append the five `[[tool.mypy.overrides]]` blocks.
3. Verify ADR existence + README listing (likely no edits required if the architect already shipped; this story is the validation gate).
4. Run full CI locally: `pre-commit run --all-files`, `mypy --strict src/codegenie/`, `pytest tests/`.

### Refactor — clean up

- The forbidden-patterns hook's error message must name ADR-0010 + production ADR-0033 explicitly — make the message grep-able for future debugging.
- `pyproject.toml` per-module overrides go in *one* contiguous block with a comment header: `# Phase 2 — mypy --warn-unreachable per-module (Open Q 5; Phase 0/1 NOT included).`
- If any of the nine ADR files are missing the Nygard sections, file the gaps as part of this story — the architect's output should be conformant, but verify.
- README ADR listing: each entry is a one-line bullet with ADR ID + title + status (`Accepted`).
- Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/`, `pre-commit run --all-files`, `pytest`.

## Files to touch

| Path | Why |
|---|---|
| `scripts/forbidden_patterns.py` (or `tools/forbidden_patterns.py`) | Extend Phase 0 hook with the `model_construct` ban under the seven new packages. |
| `pyproject.toml` | Append five `[[tool.mypy.overrides]]` blocks for per-module `warn_unreachable`. |
| `docs/phases/02-context-gather-layers-b-g/README.md` | Verify (and add if missing) the listing of all nine ADRs by filename + ID. |
| `tests/unit/pre_commit/test_forbidden_patterns_phase2_extension.py` | Positive + negative coverage of the ban surface. |
| `tests/unit/test_adr_inventory_phase2.py` | Nine ADR files exist + Nygard-conformant + linked from README. |
| `tests/unit/test_mypy_warn_unreachable_overrides.py` | Five per-module overrides exist; repo-wide is NOT set. |

## Out of scope

- **The `SecretRedactor` / `RedactedSlice` smart-constructor *code*** — handled by S3-01 / S3-02. This story only lands the `forbidden-patterns` discipline that those stories rely on.
- **`mypy --warn-unreachable` repo-wide rollout** — explicitly deferred to a backlog item filed in S8-04 per final-design Open Q 5.
- **The `tests/adv/phase02/test_no_inmemory_secret_leak.py` `inspect`-based boundary test** — handled by S7-04 (Gap 5 closure).
- **Phase-2-completion exit checklist** — handled by S8-04.
- **CI job authoring** (`fence`, `contract-freeze`, `unit`, `integration`, `portfolio`, `adv-phase02`, `mypy`, `bench`) — handled by S8-03.
- **ADR-0010 code (`RedactedSlice`)** — handled by S3-02. This story's ADR-inventory test does NOT require 0010 (the Step-1 nine are 0001–0009).
- **`@register_index_freshness_check`, `@register_dep_graph_strategy`, `@register_probe(heaviness=, runs_last=)` decorator implementations** — handled by S1-02, S1-10, S1-08 respectively.

## Notes for the implementer

- **Step 1 PR-size risk (manifest Implementation risk #1).** If the Step-1 PR exceeds 1,800 LOC during implementation, split into Step 1a (types: S1-01..S1-05, S1-11's type-side discipline) and Step 1b (kernel edits: S1-06..S1-10, S1-11's kernel-side discipline). The dependency edges in the DAG remain identical; the split is purely a delivery shape. Make the call before opening the PR — splitting later is review-pain.
- **The forbidden-patterns hook is the structural defense.** The architect's anti-patterns row 12 says `model_construct` bypasses Pydantic validation; the rationale is that smart-constructor invariants (S3-02's `RedactedSlice`, S1-04's `TCCM`) become fictional once `model_construct` is allowed. The hook ban is the only practical enforcement — mypy doesn't catch it (`model_construct` is a public Pydantic API).
- **Per-module rollout vs. repo-wide.** The architect's reasoning (final-design Open Q 5): Phase 0/1 has many legitimate "unreachable after raise" code paths in older error-handling style; flipping `warn_unreachable` repo-wide would generate hundreds of false-positives. Per-module is the surgical rollout. The five named modules are the ones whose exhaustiveness MATTERS (`IndexFreshness`, `ScannerOutcome`, `ScenarioResult`, etc.).
- **ADR-0010 reconciliation.** The architect appears to have pre-drafted ADR-0010 before its supporting code (S3-02) ships. That's a documentation/code-ordering question, not a correctness issue. This story's `REQUIRED_ADRS` list intentionally stops at 0009 — Step 1 ships the nine Step-1 ADRs; 0010 is a Step-3 deliverable per dependency DAG. If reviewers prefer to land 0010 here (since the file already exists), amend the test list and document in the README; either is defensible.
- **Reading the existing Phase 0 hook.** Before extending, run `cat scripts/forbidden_patterns.py` (or its equivalent path) to understand the data shape. Phase 0 likely already bans `subprocess.run` and `import os; os.system`; this story is one more pattern in the same file.
- **Path-component check for "is this file under one of the seven packages?"** Use `pathlib.Path.parts` and look for `codegenie` followed by one of the seven names. Do NOT regex against the full path — Windows path separators and symlinked checkout paths will trip you.
- **`tomllib` is stdlib in Python 3.11+.** Project baseline is 3.11+ (per Phase 0 `pyproject.toml`); no third-party `toml` dep needed.
- **The "delete an arm; mypy fails" check is manual.** Automating it requires invoking mypy in a subprocess against a fixture file with a deliberately-incomplete match. S8-01 (`ConfidenceSection`) is the canonical Phase-2 example; that story's tests are where automation should live, not here. This story's manual test is documented as a one-time integrity check in the implementer's notes.
- **CODEOWNERS for `pyproject.toml`.** If `.github/CODEOWNERS` exists, route `pyproject.toml` to the same Phase 2 architects. If not, this is a follow-up in S8-04 — do not file speculatively.
- **`Phase 0 fence` job stays green.** The fence asserts no LLM SDK imports under `src/codegenie/`. None of Step 1's stories add such an import; this is the structural backstop.
- **`Phase 0 contract-freeze` job stays green.** Only `image_digest_resolver` (S1-09) widens `ProbeContext`; the snapshot regen script encoded the allowed-field list so any further widening fails CI with an ADR-0004 pointer.
