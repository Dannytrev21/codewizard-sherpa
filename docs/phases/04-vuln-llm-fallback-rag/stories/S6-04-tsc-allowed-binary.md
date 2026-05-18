# Story S6-04 — `./node_modules/.bin/tsc` admitted to `ALLOWED_BINARIES`

**Step:** Step 6 — Compose FallbackTier + register typecheck.typescript SignalKind + integration
**Status:** Ready
**Effort:** S
**Depends on:** S1-05 (path-scoped fence amendment lands cleanly)
**ADRs honored:** ADR-04-0015 (`typecheck.typescript` SignalKind + `./node_modules/.bin/tsc` admitted), production Phase-2 ADR-0001 (omnibus subprocess-allowlist), production Phase-3 ADR-0012 (ALLOWED_BINARIES amendment via ADR pattern)

## Context

Phase 0–3 hold the invariant: every external binary called from Phase-3+ runtime is in the closed `ALLOWED_BINARIES` frozenset; admission requires an ADR amendment (Phase 3 ADR-0012's pattern; Phase 2 ADR-0001 omnibus). `tsc` is currently **not** on the allowlist. S6-05 cannot ship the `TypecheckTypescriptSignal` collector until this story merges, because every invocation goes through `codegenie.exec.run_allowlisted` (CLAUDE.md §Subprocess discipline) which will reject an unallowlisted path.

[ADR-04-0015](../ADRs/0015-typecheck-typescript-signal-and-tsc-allowed-binary.md) is the amendment. The admitted path is **`./node_modules/.bin/tsc`** — repo-local, content-hashed per major Node version per the Phase-3 ADR-0012 amendment pattern. Phase 7's distroless plugin won't have a Node toolchain at all; it simply doesn't register the signal, so the admission is harmless for Phase 7.

This story is mechanically small but contract-load-bearing: a deliberate-violation fixture asserting *other* `tsc` paths (`/usr/local/bin/tsc`, system-installed `tsc`) **stay rejected** is what proves the amendment narrowed to exactly the intended path.

## References — where to look

- **Architecture:** [phase-arch-design.md §Component 11 — TypecheckTypescriptSignal](../phase-arch-design.md) (line 619 — "Phase-4 ADR amendment to ADR-0012 adds `./node_modules/.bin/tsc` to `ALLOWED_BINARIES`"); §Deployment view (line 854 — "SubprocessJail allowlist amended"); §Harness (subprocess discipline).
- **Phase ADRs:** [ADR-04-0015](../ADRs/0015-typecheck-typescript-signal-and-tsc-allowed-binary.md) (the amendment).
- **Production ADRs:** Phase 3 ADR-0012 (amendment-via-ADR pattern); Phase 2 ADR-0001 (omnibus allowlist).
- **High-level impl:** [High-level-impl.md §Step 6](../High-level-impl.md) Features delivered ("ADR-04-0001 amends `ALLOWED_BINARIES` to admit `./node_modules/.bin/tsc`").
- **Existing code:** `src/codegenie/exec/` — `ALLOWED_BINARIES` frozenset + `run_allowlisted` + `run_external_cli`. The exact module that owns the constant (`exec/__init__.py` or `exec/allowlist.py`) is where the row lands.
- **Existing tests:** `tests/unit/exec/` — the subprocess discipline test that walks the allowlist. The deliberate-violation fixture must compose with the existing test pattern.

## Goal

Add `./node_modules/.bin/tsc` to the `ALLOWED_BINARIES` frozenset (content-hashed per major Node version where applicable per Phase-3 ADR-0012 pattern) so `run_allowlisted` accepts it; assert via a deliberate-violation fixture that other `tsc` paths (`/usr/local/bin/tsc`, plain `tsc` resolved by PATH) remain rejected.

## Acceptance criteria

- [ ] **`./node_modules/.bin/tsc` admitted**: the row appears in `ALLOWED_BINARIES` exactly once, alphabetically ordered consistent with surrounding entries (match the existing convention per Global Rule 11).
- [ ] **`run_allowlisted("./node_modules/.bin/tsc", ["--noEmit", "--pretty", "false"], cwd=...)` succeeds at the allowlist check** (subprocess may still fail if `tsc` isn't installed in the fixture — that's S6-05's concern). Asserted by `tests/unit/exec/test_allowlist_admits_tsc.py`.
- [ ] **Deliberate-violation fixture**: `run_allowlisted("/usr/local/bin/tsc", ...)` raises the allowlist's typed rejection error; `run_allowlisted("tsc", ...)` (PATH-resolved) raises; `run_allowlisted("./node_modules/.bin/something_else", ...)` raises. Asserted by `tests/unit/exec/test_allowlist_rejects_system_tsc.py` — load-bearing: proves the admission is narrowly scoped.
- [ ] **ADR cross-reference**: the comment/docstring next to the new allowlist row cites `docs/phases/04-vuln-llm-fallback-rag/ADRs/0015-typecheck-typescript-signal-and-tsc-allowed-binary.md` so the next reader sees *why* the row is there (matches existing convention for prior admissions).
- [ ] **Existing allowlist tests stay green**: `tests/unit/exec/test_allowlist_closure.py` (or whatever the closed-set walker is named) still passes and the count of allowed binaries advances by exactly one.
- [ ] **No edits to `run_allowlisted` logic**: the amendment is one row, not a code change. AST-walking diff check (or simple `git diff --stat`) shows the lines-changed footprint is bounded to `ALLOWED_BINARIES` definition + the new tests.
- [ ] **Pre-commit forbidden-patterns hook**: still rejects `subprocess.run(..., shell=True)`, `os.system`, etc. — the amendment doesn't widen the broader subprocess discipline (CLAUDE.md §Subprocess discipline).
- [ ] `make check`, `make lint`, `make lint-imports`, `make fence` (production-ADR-0005 fence test) all green.

## Implementation outline

1. Read `src/codegenie/exec/` first (Global Rule 8). Identify the `ALLOWED_BINARIES` frozenset's exact location and the existing convention (path style — relative repo-local vs absolute; with/without content-hash sidecar).
2. Add the row `"./node_modules/.bin/tsc"` (or whatever form the existing convention uses for repo-local binaries) with a citation comment to ADR-04-0015.
3. If the existing convention includes content-hash sidecars (per Phase-3 ADR-0012 pattern), provide the content-hash entry for `tsc` — coordinate the major-Node-version detail with the test harness fixture's Node version. If the existing convention is path-only, follow that and surface the content-hash question per Global Rule 7.
4. Add `tests/unit/exec/test_allowlist_admits_tsc.py` and `tests/unit/exec/test_allowlist_rejects_system_tsc.py`.
5. Run the existing allowlist closure test to verify nothing else admitted accidentally; the closed-set delta is +1.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/exec/test_allowlist_admits_tsc.py
import pytest
from pathlib import Path
from codegenie.exec import run_allowlisted, AllowlistViolation

def test_node_modules_tsc_is_admitted(tmp_path: Path):
    """ADR-04-0015: ./node_modules/.bin/tsc must pass run_allowlisted's
    allowlist check. Why this matters: S6-05's TypecheckTypescriptSignal
    cannot ship until this admission lands."""
    # Construct a fake repo-local tsc shim that exits 0 cleanly.
    tsc_dir = tmp_path / "node_modules" / ".bin"
    tsc_dir.mkdir(parents=True)
    shim = tsc_dir / "tsc"
    shim.write_text("#!/usr/bin/env bash\nexit 0\n")
    shim.chmod(0o755)

    # Should NOT raise AllowlistViolation.
    result = run_allowlisted(
        "./node_modules/.bin/tsc", ["--version"], cwd=tmp_path
    )
    assert result.exit_code == 0  # the shim exited 0


# tests/unit/exec/test_allowlist_rejects_system_tsc.py
import pytest
from codegenie.exec import run_allowlisted, AllowlistViolation

@pytest.mark.parametrize("path", [
    "/usr/local/bin/tsc",
    "/opt/homebrew/bin/tsc",
    "tsc",  # PATH-resolved
    "./node_modules/.bin/tsc-something-else",
    "./tools/.bin/tsc",
])
def test_other_tsc_paths_stay_rejected(path):
    """ADR-04-0015: admission is narrow.  System-installed tsc, PATH-resolved
    tsc, and any other path stays rejected — supply-chain surface is
    bounded to repo-local node_modules."""
    with pytest.raises(AllowlistViolation):
        run_allowlisted(path, ["--version"], cwd=".")
```

### Green — make it pass

- Add `"./node_modules/.bin/tsc"` to `ALLOWED_BINARIES` with the ADR citation comment.
- Verify the existing test `tests/unit/exec/test_allowlist_closure.py` still passes with count + 1.

### Refactor — clean up

- Resist the urge to refactor the allowlist module while adding the row — Global Rule 3 (surgical changes).
- If the existing convention for the comment cite format differs from "see docs/...", follow the existing convention.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/exec/<module>.py` (the `ALLOWED_BINARIES` host) | Add the row + ADR comment. |
| `tests/unit/exec/test_allowlist_admits_tsc.py` | New — positive case. |
| `tests/unit/exec/test_allowlist_rejects_system_tsc.py` | New — narrow-admission proof. |
| `tests/unit/exec/test_allowlist_closure.py` (existing) | Closure-count delta updated if the test pins absolute count (read it first per Global Rule 8). |

## Out of scope

- The `TypecheckTypescriptSignal` collector that actually invokes `tsc` — **S6-05**.
- The applicability matrix (`tsconfig.json` + `.ts` files detection) — **S6-06**.
- Phase 7's distroless plugin question (does it inherit `typecheck.typescript` or not) — Phase 7 / Phase 6.5 decision.
- Promoting `typecheck.typescript` to a shared `vulnerability-remediation--node--*` base plugin per ADR-0031 — deferred per arch open question 3.

## Notes for the implementer

- Read `src/codegenie/exec/` before adding the row. The existing convention is the answer to the path-form question (relative `./node_modules/.bin/tsc` vs an absolute repo-rooted form). If you can't tell which convention is "the" convention, surface per Global Rule 7.
- The deliberate-violation fixture is the load-bearing assurance — without it, a future contributor could widen the allowlist to admit system `tsc` and pass tests by accident. The negative-case test is what makes the admission narrow.
- Content-hashed-per-major-Node-version (ADR-04-0015 §Decision) is the durable shape; if the existing allowlist plumbing doesn't yet support content-hashing per-row, this story may need to ship the path-only form and surface the content-hashing follow-up per Global Rule 7. The Phase-3 ADR-0012 pattern is the precedent.
- This story is small (S effort). Do not gold-plate by refactoring the allowlist module or adding general-purpose tooling. Surgical (Global Rule 3).
