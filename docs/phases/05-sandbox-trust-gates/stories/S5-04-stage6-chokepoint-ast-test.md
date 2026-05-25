# Story S5-04 — Stage 6 chokepoint AST test

**Step:** Step 5 — GateRunner three-retry loop + Phase 4 replan_hook integration
**Status:** Ready (HARDENED 2026-05-25 — see [`_validation/S5-04-stage6-chokepoint-ast-test.md`](_validation/S5-04-stage6-chokepoint-ast-test.md))
**Effort:** S
**Depends on:** S1-07 (`tests/schema/__init__.py` package marker + `tests/schema/_walkers.py` kernel — HARDENED, GREEN-pending), S5-02 (`src/codegenie/gates/runner.py` — HARDENED, GREEN-pending). **Cross-phase:** the second allowlisted call-site (`RemediationOrchestrator`) lands in Phase-3 S6-04 (`docs/phases/03-vuln-deterministic-recipe/stories/S6-04-remediation-orchestrator.md`, currently BLOCKED per Phase-3 ADR-0015 re-harden) — **not in this story**. See `## Validation notes (2026-05-25)` for the split-rationale.
**ADRs honored:** ADR-0001 (two-chokepoint sandbox seam), ADR-0006 (Protocol vs ABC convention). **Cross-phase context:** Phase-3 ADR-0015 (orchestrator self-loads repo context + resolves CVE) defines the orchestrator surface this fence eventually polices.

## Validation notes (2026-05-25)

Hardened by `/phase-story-validator` (scheduled task: story-validation-corrector). Full audit at [`_validation/S5-04-stage6-chokepoint-ast-test.md`](_validation/S5-04-stage6-chokepoint-ast-test.md). Most consequential changes:

- **Walker target re-pointed from `codegenie.validation.*` (a package that does not exist on `master`) to `codegenie.transforms.trust_scorer.TrustScorer` (the canonical Phase-3 Stage-6 entrypoint per S6-02 GREEN).** The historical `validation.*` namespace is from an arch draft superseded by S6-02 / S6-03; the arch-text amendment is captured for S8-04 (out of this story's scope).
- **Orchestrator-wiring AC removed from this story.** `src/codegenie/orchestrator/remediation.py` is owned by Phase-3 S6-04 (BLOCKED). Bundling created a cross-phase extension-by-edit. S5-04 ships ONLY the chokepoint test promotion. The call-site swap (when S6-04 lands) is the natural job of S6-04 itself; Notes paragraph documents the handoff to whichever-story-lands-second.
- **Walker hardened against five Python import shapes** (`from-import`, `import-name`, `import-as`, `importlib.import_module`, `__import__`) — story's draft caught three, missed two. Each shape gets a parametrized planted-positive sub-test that exercises the same walker the main test uses (parity-with-Phase-0 `tests/fence/test_no_llm_in_transforms.py` mutation-resistance precedent).
- **`visit_Attribute` arm dropped.** Untracked binding produced false positives on any local name `validation`; the chokepoint policy is "the import IS the seam" — aliased call-sites are caught at the import-alias step.
- **Walker consumes `tests/schema/_walkers.py` kernel (S1-07).** Inline `_Walker` re-declaration removed; story is the seventh caller per S1-07 §Design-patterns finding 14.
- **Path normalization promoted to AC.** `path.resolve().relative_to(REPO_ROOT)` survives macOS case-insensitive FS + symlinked checkouts; allowlist is `frozenset[str]` of repo-relative paths.
- **`Offender` is a small frozen dataclass** (path / lineno / symbol) — primitive-obsessed `tuple[int, str]` replaced; failure message shape pinned by a sub-test asserting `Offender.__str__` matches the documented regex.
- **`Depends on:` widened to include S1-07** (the kernel + the package marker S5-04 imports from) and a cross-phase Phase-3 S6-04 note; `ADRs honored:` widened to include ADR-0006.
- **Hypothesis property added** — namespace-prefix metamorphic: walker's verdict on `prefix` == verdict on `prefix.suffix` for any valid Python identifier `suffix`.

## Context

The phase's first goal — "No transform leaves the sandbox unverified" — is structurally enforced by a single AST-walking CI test: only `src/codegenie/gates/runner.py` and the future `RemediationOrchestrator` (Phase-3 S6-04) may reach the Stage-6 Validate entrypoint, `codegenie.transforms.trust_scorer.TrustScorer.score()`. S1-07 lands this test as a *stub* (presence-only); now that `GateRunner` is shipping (S5-02), this story promotes it to a real AST walk that fails loud if any other module imports the `TrustScorer` class. The promotion is structurally vacuous on the current `master` (no `GateRunner.run` call-sites exist outside `gates/runner.py` because both S5-02 and S6-04 are pre-GREEN), so the load-bearing property is **mutation-resistance via in-memory planted positives** — the walker is exercised against synthetic `ast.parse(source_string)` payloads covering all five Python import shapes (`from X import …`, `import X`, `import X as Y`, `importlib.import_module("X")`, `__import__("X")`), each parametrized as a sub-test that fails loudly if the walker mis-classifies. The orchestrator wiring — the *call-site* swap from a direct `TrustScorer.score()` call to `GateRunner.run()` — is **deferred to Phase-3 S6-04** (the story that builds the orchestrator); whichever of S5-04 and S6-04 lands second updates the allowlist constant.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals` Goal 1 — "No transform leaves the sandbox unverified. Phase 3 Stage 6 `Validate` is the only callsite; it is wrapped by `GateRunner.run`. Static CI test asserts no other module under `src/codegenie/` calls the Stage-6 entrypoint directly (`tests/schema/test_stage6_chokepoint.py`)."
  - `../phase-arch-design.md §Testing strategy` — fence/structural tests inventory (the arch text uses the historical `validation.*` namespace; the actual call-site is `transforms.trust_scorer.TrustScorer` — text amendment deferred to S8-04 ADR audit).
  - `../phase-arch-design.md §Development view` — "Stage 6's previous direct call becomes `GateRunner.run(ctx)`." (the "previous direct call" is `TrustScorer.score()` per the actual Phase-3 surface.)
  - `../phase-arch-design.md §Happy path` — "The orchestrator instantiates `GateRunner(...)`. It calls `gate_runner.run(GateContext(...))`."
- **Phase ADRs:**
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — `GateRunner.run` is the only consumer of `SandboxClient` in this phase; chokepoint test is the enforcement.
  - `../ADRs/0006-protocol-vs-abc-convention.md` — `SubgraphNode` Protocol shapes the legitimate-caller set in S6-03.
- **Cross-phase context:**
  - `../../03-vuln-deterministic-recipe/ADRs/0015-orchestrator-self-loads-repo-context-and-resolves-cve.md` — settles Phase-3 S6-04 (`RemediationOrchestrator`) shape; the second allowlisted call-site lands there.
  - `../../03-vuln-deterministic-recipe/stories/S6-04-remediation-orchestrator.md` (BLOCKED) — owns the call-site swap.
- **Source design:**
  - `../final-design.md §Synthesis ledger — Stage 6 chokepoint row`.
- **Existing code (current `master`):**
  - `src/codegenie/transforms/trust_scorer.py` — the canonical Phase-3 Stage-6 entrypoint (S6-02 GREEN). `TrustScorer.score()` is what the chokepoint polices.
  - `src/codegenie/plugins/subgraph.py` (S6-03 GREEN) — `Stage6ValidateNode` per `SubgraphState.trust_outcome`; consumes `TrustScorer.score()` from within the orchestrator's subgraph.
  - `tests/schema/__init__.py` + `tests/schema/_walkers.py` (S1-07 HARDENED; expected on master once S1-07 GREENs) — the kernel this story consumes.
  - `tests/schema/test_stage6_chokepoint.py` (stubbed in S1-07) — promote.
  - `tests/fence/test_no_llm_in_transforms.py` — runtime-closure walker + planted-positive precedent.
  - `tests/fence/test_lint_imports_catches_planted_leak.py` — parametrized planted-positive idiom.
- **Prior validation reports:**
  - `_validation/S1-07-ci-fence-tests-digests-yaml.md` — `_walkers.py` kernel ownership + planted-positive idiom + relative-path-allowlist precedent.
  - `_validation/S5-02-gate-runner-retry-loop.md` — `src/codegenie/gates/runner.py` AC-PURITY-1 composition-root discipline (it IS the first allowlisted module).

## Goal

Promote `tests/schema/test_stage6_chokepoint.py` from a stub to a real AST walker that asserts: only `src/codegenie/gates/runner.py` (and, when Phase-3 S6-04 GREENs, the `RemediationOrchestrator` module) may import or alias `codegenie.transforms.trust_scorer.TrustScorer` — the canonical Phase-3 Stage-6 entrypoint. The walker catches all five Python import shapes (`from X import …`, `import X`, `import X as Y`, `importlib.import_module("X")`, `__import__("X")`), with parametrized in-memory planted positives proving mutation-resistance. The orchestrator call-site swap (replacing the direct `TrustScorer.score()` invocation with `GateRunner.run()`) is **deferred to Phase-3 S6-04**; this story ships only the structural fence.

## Acceptance criteria

### Walker target + allowlist

- [ ] **AC-TARGET-1** — `tests/schema/test_stage6_chokepoint.py` polices the forbidden module prefix tuple `_FORBIDDEN_PREFIX: Final[tuple[str, ...]] = ("codegenie.transforms.trust_scorer",)`. The chokepoint is on the **`TrustScorer` class import** — the re-exported type aliases `TrustOutcome` / `StageOutcome` are NOT policed (every gate reader needs the type; only the class is the structural seam). A Notes paragraph in the test file's module docstring documents this asymmetry.
- [ ] **AC-TARGET-2** — Allowlist is declared at module top as `_ALLOWLIST: Final[frozenset[str]] = frozenset({"src/codegenie/gates/runner.py", "src/codegenie/orchestrator/remediation.py"})`. Each entry has an inline `# ADR-0001:` comment citing the legitimacy reason. The orchestrator path is held as a placeholder constant with a `# TODO(cross-phase): Phase-3 S6-04 …` comment naming the cross-phase dependency.
- [ ] **AC-PATH-1** — Path comparisons use `str(path.resolve().relative_to(REPO_ROOT)) in _ALLOWLIST`. A sub-test exercises a symlinked-checkout case (build a symlinked `tmp_path / "symlinked-root"` pointing at `REPO_ROOT`, walk it, assert membership still hits) to prove the normalization holds on macOS case-insensitive FS + symlinks.

### Walker shape coverage

- [ ] **AC-SHAPE-1** — The walker catches **all five** Python import shapes that reach the forbidden prefix:
  - `ImportFrom` where `node.module` starts with any prefix in `_FORBIDDEN_PREFIX`.
  - `Import` where any `alias.name` starts with any prefix.
  - `Import … as <alias>` — the alias rebinds but the `alias.name` still starts with a forbidden prefix; the same `Import` rule catches it.
  - `Call(func=Attribute(attr="import_module"))` with a literal first arg whose string starts with any forbidden prefix.
  - `Call(func=Name(id="__import__"))` with a literal first arg whose string starts with any forbidden prefix.
- [ ] **AC-BIND-1** — `visit_Attribute` is intentionally **not** implemented. The walker's policy is "the import is the chokepoint"; aliased call-sites are caught at the alias-binding step (`Import.alias.asname` is still bound to the forbidden `alias.name`). The walker docstring pins this policy with the substring `"the import is the chokepoint"` (verified by AC-DOC-1).

### Mutation-resistance — planted positives

- [ ] **AC-PP-1** — A parametrized sub-test `test_walker_detects_planted_offender` exercises the walker against **all five shapes** in AC-SHAPE-1. Each parametrized case uses `tmp_path.write_text(...)` to construct a synthetic `.py` file with a forbidden import; calls the same `_walk(path)` or `_walk_source(source, fake_path)` callable the live test uses; asserts the offender list is non-empty AND contains the offending file's path AND the planted line number.
- [ ] **AC-PP-2** — `@pytest.mark.parametrize` includes at minimum these five sources:
  ```python
  ("from-import", "from codegenie.transforms.trust_scorer import TrustScorer\n"),
  ("import-name", "import codegenie.transforms.trust_scorer\n"),
  ("import-as", "import codegenie.transforms.trust_scorer as ts\n"),
  ("import_module", "import importlib\nimportlib.import_module('codegenie.transforms.trust_scorer')\n"),
  ("dunder-import", "__import__('codegenie.transforms.trust_scorer')\n"),
  ```
  Each is asserted to produce ≥1 offender.
- [ ] **AC-MUT-1** — The same `_walk` / `_walk_source` callable used by `test_only_allowlisted_modules_reach_trust_scorer` is used by the planted-positive sub-tests. A regression that empties `_walk` (e.g., `return []` at the top) fails the planted-positive parametrize AND the live test in lockstep. (Parity with `tests/fence/test_no_llm_in_transforms.py`.)
- [ ] **AC-MSG-1** — A sub-test plants a synthetic source containing `from codegenie.transforms.trust_scorer import TrustScorer` and asserts the offender's `str(offender)` matches `r"^[\w/\.\-]+:\d+ -> from codegenie\.transforms\.trust_scorer import \w+$"`. The failure message reads `tests/schema/test_stage6_chokepoint.py: violations:\n  - {path}:{lineno} -> {symbol}\n  ...`.

### Hypothesis property

- [ ] **AC-PROP-1** — One Hypothesis property `test_walker_is_namespace_prefix_metamorphic` — for any valid Python identifier `suffix` (Hypothesis `st.from_regex(r"[A-Za-z_][A-Za-z0-9_]*", fullmatch=True)`), the walker's verdict on `from codegenie.transforms.trust_scorer.<suffix> import X` equals its verdict on `from codegenie.transforms.trust_scorer import X` — both flagged. ≥ 50 examples; total runtime < 200 ms.

### Kernel consumption (S1-07)

- [ ] **AC-KERNEL-1** — The test imports `iter_py` and `iter_top_level_imports` (or equivalent walker primitives shipped by S1-07's `tests/schema/_walkers.py`); does NOT re-declare `_Walker` inline. If S1-07 has not yet GREEN-shipped when this story executes, the executor escalates (story is structurally BLOCKED-on-S1-07) — does NOT in-line a kernel copy. S5-04 is the **seventh** caller of the kernel per S1-07 §Design-patterns finding 14.
- [ ] **AC-OFF-1** — Offenders are returned as `Offender` instances — a `@dataclass(frozen=True, slots=True)` with fields `path: Path`, `lineno: int`, `symbol: str`, and a single-line `__str__` matching the AC-MSG-1 regex. If S1-07's kernel ships `Offender` already, this story consumes it; otherwise this story declares it under `tests/schema/_walkers.py` (kernel home — single declaration site, ADR-0010 spirit) and S1-07's next harden absorbs it.

### Pass-time gate + discipline

- [ ] **AC-PG-1** — `pytest --no-cov tests/schema/test_stage6_chokepoint.py` runs in **≤ 1 s on a clean checkout** (incl. collection). A `time.perf_counter()` wrap inside the live test asserts the body completes in `< 0.8 s`; total file `--durations` summary asserted via a separate teardown sub-test, OR the AC-PG-1 sub-test asserts `time.perf_counter()` delta with a generous 0.8 s budget so an executor's CI does not flake.
- [ ] **AC-PG-2** — No `pytest.mark.skip` or `pytest.mark.xfail` markers anywhere in `tests/schema/test_stage6_chokepoint.py` (mirrors `tests/fence/` discipline — every fence either passes loud or fails loud).
- [ ] **AC-PG-3** — `pytest --no-cov tests/schema/test_stage6_chokepoint.py` exits 0 on the Step-N codebase (vacuously — no callers exist outside `gates/runner.py` until Phase-3 S6-04 GREENs); the planted-positive parametrize is the live mutation guard.

### Docs + ADR citation

- [ ] **AC-DOC-1** — Module docstring at the top of `tests/schema/test_stage6_chokepoint.py` cites ADR-0001, names the canonical Stage-6 entrypoint (`codegenie.transforms.trust_scorer.TrustScorer.score`), and contains the substring `"the import is the chokepoint"` (verified by a sub-test asserting the substring's presence). Module-level Final-tuple comments explain why `TrustOutcome` / `StageOutcome` imports are NOT policed.

### Quality gates

- [ ] **AC-QG-1** — `ruff check tests/schema/test_stage6_chokepoint.py` clean.
- [ ] **AC-QG-2** — `ruff format --check tests/schema/test_stage6_chokepoint.py` clean.
- [ ] **AC-QG-3** — `mypy --strict tests/schema/test_stage6_chokepoint.py` clean (no `Any` in offender types).
- [ ] **AC-QG-4** — `pytest tests/schema/test_stage6_chokepoint.py` green; the existing `tests/schema/test_no_subprocess_outside_build_chokepoint.py` and `tests/schema/test_no_llm_imports_in_sandbox.py` (S1-07) remain green.
- [ ] **AC-QG-5** — Pre-existing Phase-5 structural fences (`tests/schema/test_objective_signals_static.py`, `tests/schema/test_env_allowlist_no_credentials.py`, `tests/schema/test_digests_yaml.py`) remain green.

### Out-of-scope explicit gate

- [ ] **AC-OOS-1** — No edit to `src/codegenie/orchestrator/remediation.py` (does not exist; owned by Phase-3 S6-04). No edit to `src/codegenie/transforms/trust_scorer.py` (Phase-3 surface; S6-04 is the call-site refactor home). A sub-test under `tests/fence/` (or this story's commit-discipline) verifies the touched-files diff for this story includes no `src/codegenie/transforms/` or `src/codegenie/orchestrator/` entries.

## Implementation outline

1. **Replace the S1-07 stub** with a real walker built on `tests/schema/_walkers.py` (kernel; AC-KERNEL-1). The test composes: `iter_py(REPO_ROOT / "src" / "codegenie")` → filter to non-allowlisted paths → for each path, `iter_top_level_imports(path)` → for each `(lineno, module_name)` tuple, check `any(module_name.startswith(p) for p in _FORBIDDEN_PREFIX)` → collect into a list of `Offender(path=relative_path, lineno=lineno, symbol=f"from {module_name} import …")`.
2. **Add dynamic-import detection**. The kernel may not catch `importlib.import_module(...)` or `__import__(...)`; if not, add a small `iter_dynamic_imports(path) -> Iterator[tuple[int, str]]` helper either in the kernel (preferred) or as a private module-level function in this test file (acceptable if the kernel's S1-07-author rejects the addition). AC-SHAPE-1 unions both iterators' outputs.
3. **Build the planted-positive parametrize**. `tmp_path.write_text(source)` for each of the five shapes; call the same `_walk(path)` or compose `_walk_source(source, fake_path)`; assert offender list non-empty + naming the planted line number. Run before the live test (the planted-positive is the load-bearing guarantee that the walker has teeth on Step-N codebase where the live test is vacuous).
4. **Path normalization.** Build a small helper `_relative_to_repo_root(path: Path) -> str = str(path.resolve().relative_to(REPO_ROOT))`. Use everywhere: the allowlist lookup AND the `Offender.path` formatting (relative-to-repo-root for grep-ability). AC-PATH-1's symlinked-tmp-path sub-test guards the normalization.
5. **Hypothesis property.** `@given(suffix=st.from_regex(r"[A-Za-z_][A-Za-z0-9_]*", fullmatch=True))` + a `@settings(max_examples=50, deadline=200)` decorator. Build the source string + parse + assert walker flags. AC-PROP-1.
6. **Module docstring.** Pin the policy ("the import is the chokepoint"), the canonical entrypoint name, the ADR-0001 citation, and the asymmetry note about `TrustOutcome` / `StageOutcome`. AC-DOC-1.
7. **Quality gates.** AC-QG-1..AC-QG-5 — run after the test is green.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/schema/test_stage6_chokepoint.py`. The test file is the load-bearing artifact; below is its target shape. The executor writes it incrementally, starting from a deliberately-broken stub (e.g., `_FORBIDDEN_PREFIX = ()`) and asserting the planted-positive parametrize fails first — that proves the test would catch a regression before it's written for real.

```python
# tests/schema/test_stage6_chokepoint.py
"""S5-04 — Stage-6 chokepoint AST fence.

ADR-0001 (two-chokepoint sandbox seam): only ``src/codegenie/gates/runner.py``
and the Phase-3 ``RemediationOrchestrator`` (lands in Phase-3 S6-04) may reach
``codegenie.transforms.trust_scorer.TrustScorer`` — the canonical Phase-3
Stage-6 entrypoint per S6-02 GREEN.

The chokepoint is the *import*. Aliased call-sites are caught at the alias-
binding step (``Import.alias.asname`` is bound to the forbidden
``alias.name``); attribute access is intentionally not tracked — see the
S5-04 validation report §Design-patterns 30. Imports of the re-exported type
aliases ``TrustOutcome`` / ``StageOutcome`` are NOT policed: every gate reader
consumes the type; only the ``TrustScorer`` class import is the structural
seam.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pytest
from hypothesis import given, settings, strategies as st

from tests.schema._walkers import (
    REPO_ROOT,
    Offender,
    iter_py,
    iter_top_level_imports,
    iter_dynamic_imports,  # may live here or be added by this story
)

_FORBIDDEN_PREFIX: Final[tuple[str, ...]] = ("codegenie.transforms.trust_scorer",)
_ALLOWLIST: Final[frozenset[str]] = frozenset(
    {
        # ADR-0001 — GateRunner is the only consumer of SandboxClient in this phase.
        "src/codegenie/gates/runner.py",
        # ADR-0001 — RemediationOrchestrator wires GateRunner.run at Stage 6.
        # TODO(cross-phase): Phase-3 S6-04 GREEN populates this module; the
        # second story to land (S5-04 or S6-04) updates this allowlist.
        "src/codegenie/orchestrator/remediation.py",
    }
)
SRC = REPO_ROOT / "src" / "codegenie"


def _relative_to_repo_root(path: Path) -> str:
    return str(path.resolve().relative_to(REPO_ROOT))


def _collect_offenders(path: Path) -> list[Offender]:
    offenders: list[Offender] = []
    rel = _relative_to_repo_root(path)
    if rel in _ALLOWLIST:
        return offenders
    for lineno, module_name in iter_top_level_imports(path):
        if any(module_name.startswith(p) for p in _FORBIDDEN_PREFIX):
            offenders.append(Offender(path=Path(rel), lineno=lineno, symbol=f"from {module_name} import …"))
    for lineno, module_name in iter_dynamic_imports(path):
        if any(module_name.startswith(p) for p in _FORBIDDEN_PREFIX):
            offenders.append(Offender(path=Path(rel), lineno=lineno, symbol=f"dynamic: {module_name}"))
    return offenders


def test_only_allowlisted_modules_reach_trust_scorer() -> None:
    start = time.perf_counter()
    offenders: list[Offender] = []
    for path in iter_py(SRC):
        offenders.extend(_collect_offenders(path))
    elapsed = time.perf_counter() - start
    assert elapsed < 0.8, f"AC-PG-1 — walker took {elapsed:.3f}s, budget 0.8s"
    assert not offenders, (
        "Stage 6 chokepoint violated (ADR-0001). "
        "Only GateRunner.run and RemediationOrchestrator may reach "
        "codegenie.transforms.trust_scorer.TrustScorer:\n  "
        + "\n  ".join(str(o) for o in offenders)
    )


@pytest.mark.parametrize(
    ("shape_name", "source"),
    [
        ("from-import", "from codegenie.transforms.trust_scorer import TrustScorer\n"),
        ("import-name", "import codegenie.transforms.trust_scorer\n"),
        ("import-as", "import codegenie.transforms.trust_scorer as ts\n"),
        ("import_module", "import importlib\nimportlib.import_module('codegenie.transforms.trust_scorer')\n"),
        ("dunder-import", "__import__('codegenie.transforms.trust_scorer')\n"),
    ],
)
def test_walker_detects_planted_offender(tmp_path: Path, shape_name: str, source: str) -> None:
    planted = tmp_path / f"_planted_{shape_name}.py"
    planted.write_text(source)
    # The walker is invoked the same way the live test invokes it — same
    # callable, same code path. A regression in iter_top_level_imports /
    # iter_dynamic_imports / _collect_offenders fails this AND the live test
    # in lockstep (AC-MUT-1).
    offenders = _collect_offenders(planted)
    assert offenders, f"AC-PP-1 — walker missed planted {shape_name} import"
    assert any(o.lineno >= 1 for o in offenders), f"AC-PP-1 — walker lost lineno for {shape_name}"


def test_failure_message_shape() -> None:
    o = Offender(path=Path("src/codegenie/_planted.py"), lineno=42, symbol="from codegenie.transforms.trust_scorer import TrustScorer")
    import re
    pattern = r"^[\w/\.\-]+:\d+ -> from codegenie\.transforms\.trust_scorer import \w+$"
    assert re.match(pattern, str(o)), f"AC-MSG-1 — Offender.__str__ broke shape: {o!s}"


def test_module_docstring_pins_policy() -> None:
    this = Path(__file__).read_text()
    assert "ADR-0001" in this, "AC-DOC-1 — module docstring must cite ADR-0001"
    assert "codegenie.transforms.trust_scorer.TrustScorer" in this, "AC-DOC-1 — entrypoint name"
    assert "the import is the chokepoint" in this, "AC-DOC-1 — policy substring"


def test_symlinked_checkout_normalizes(tmp_path: Path) -> None:
    # AC-PATH-1 — symlink resolution survives macOS case-insensitive FS.
    symlinked_root = tmp_path / "symlinked-root"
    symlinked_root.symlink_to(REPO_ROOT)
    runner = symlinked_root / "src" / "codegenie" / "gates" / "runner.py"
    if not runner.exists():
        pytest.skip("S5-02 has not GREEN-shipped — gates/runner.py absent")
    assert _relative_to_repo_root(runner) == "src/codegenie/gates/runner.py"


@given(suffix=st.from_regex(r"[A-Za-z_][A-Za-z0-9_]*", fullmatch=True))
@settings(max_examples=50, deadline=200)
def test_walker_is_namespace_prefix_metamorphic(suffix: str, tmp_path: Path) -> None:
    # AC-PROP-1 — verdict on `prefix` == verdict on `prefix.suffix` for any
    # valid identifier suffix. Both forms are flagged.
    src_prefix = f"from codegenie.transforms.trust_scorer import x_{suffix}\n"
    src_suffix = f"from codegenie.transforms.trust_scorer.{suffix} import x\n"
    p1 = tmp_path / "p1.py"
    p2 = tmp_path / "p2.py"
    p1.write_text(src_prefix)
    p2.write_text(src_suffix)
    assert _collect_offenders(p1), f"prefix import not flagged for {suffix=}"
    assert _collect_offenders(p2), f"prefix.suffix import not flagged for {suffix=}"
```

### Green — make it pass

- Ship `_collect_offenders`, the planted-positive parametrize, the module docstring, the failure-message dataclass `Offender` consumption (or declaration if S1-07's kernel does not yet expose it), and the path-normalization helper.
- If `tests/schema/_walkers.py` does not expose `iter_dynamic_imports`, add it to the kernel as part of this story (single declaration site; S1-07's HARDENED §finding 14 cleared the rule-of-three day-1 — adding a sixth helper to a six-walker kernel is in-scope).
- If S1-07 has not yet GREEN-shipped when this story executes, **escalate** (story is BLOCKED-on-S1-07). Do NOT in-line a kernel copy. The executor adds a `Status:` line update to "BLOCKED on S1-07 GREEN" and surfaces in the attempt log.
- Run `pytest --no-cov tests/schema/` until the planted-positive parametrize, the live test, the Hypothesis property, the module-docstring sub-test, and the symlink-normalization sub-test ALL pass.

### Refactor — clean up

- Verify `_FORBIDDEN_PREFIX` and `_ALLOWLIST` are `Final[...]`-typed module constants with inline ADR citations.
- Run `mypy --strict tests/schema/test_stage6_chokepoint.py`; eliminate any `Any` leakage from the kernel.
- Confirm `ruff check && ruff format --check` clean on the test file.
- Confirm the existing S1-07 chokepoint tests (`test_no_subprocess_outside_build_chokepoint.py`, `test_no_llm_imports_in_sandbox.py`) and the other Phase-5 structural fences remain green.
- Verify the touched-files diff for this story does NOT include any entries under `src/codegenie/transforms/`, `src/codegenie/orchestrator/`, or any file the cross-phase Phase-3 S6-04 owns (AC-OOS-1).

## Files to touch

| Path | Why |
|---|---|
| `tests/schema/test_stage6_chokepoint.py` | Promote S1-07 stub to a real AST walker with planted-positive parametrize + Hypothesis property. |
| `tests/schema/_walkers.py` (S1-07 kernel) | Add `iter_dynamic_imports(path) -> Iterator[tuple[int, str]]` if not already exposed; otherwise consume unchanged. |
| _(intentionally excluded)_ `src/codegenie/orchestrator/remediation.py` | Owned by Phase-3 S6-04 (BLOCKED). The call-site swap lands there, not in this story (AC-OOS-1). |
| _(intentionally excluded)_ `src/codegenie/transforms/trust_scorer.py` | Phase-3 surface; the only legitimate edit is the future allowlist row in `_ALLOWLIST`, and only when S6-04 GREENs. |

## Out of scope

- `GateRunner.run` implementation — S5-02.
- `RemediationOrchestrator` construction + the orchestrator-side call-site swap from `TrustScorer.score()` to `GateRunner.run()` — **Phase-3 S6-04** (the story that owns the orchestrator module). When S6-04 lands, its executor updates `_ALLOWLIST` to include the orchestrator's resolved path and adds the GateRunner call-site.
- VCR integration test against real Phase 4 — S5-05.
- `--max-attempts-override` CLI flag wiring — S8-02.
- Cost emission — S7-03.
- Concurrent-remediate flock — S7-04.
- Arch design text amendment (the §Testing strategy "`validation.*`" historical wording) — S8-04 (ADR audit + roadmap exit criteria).

## Notes for the implementer

- **The walker is structurally vacuous on Step-N codebase** (until Phase-3 S6-04 GREENs there are zero call-sites outside `gates/runner.py`). The load-bearing guarantee that the walker has teeth is the **parametrized planted-positive**, NOT the live test. Verify the planted-positive fails when you delete the walker's body; verify it passes when you restore it. That is the mutation-resistance contract.
- **The chokepoint is the import, not the call.** Do NOT add `visit_Attribute` to the walker. An aliased call-site (`import codegenie.transforms.trust_scorer as ts; ts.TrustScorer()`) is caught at the `Import` step (the alias's `.name` still starts with the forbidden prefix). Tracking attribute access against an unbound name produced false positives on parameter / local names in the draft — AC-BIND-1 forbids the arm.
- **Type aliases are not policed.** `from codegenie.transforms.trust_scorer import TrustOutcome` (or `StageOutcome`) is fine — every gate result reader consumes the type. The chokepoint is on the `TrustScorer` class only. The module docstring documents this asymmetry; AC-TARGET-1 pins the forbidden-prefix tuple to the *module path*, and the allowlist exception flow handles the symmetry.
- **Cross-phase ordering.** Either S5-04 lands first (the allowlist holds the orchestrator path as a placeholder; the live test is vacuous; the planted-positive is the mutation guard) or Phase-3 S6-04 lands first (the orchestrator's direct `TrustScorer.score()` call already exists; S5-04's live test now has a real allowlisted caller). The story is correct in both orderings.
- **Rule-of-Three opportunity (do NOT extract in this story).** The four namespace-chokepoint fences `test_no_llm_imports_in_sandbox.py` (S1-07), `test_no_subprocess_outside_build_chokepoint.py` (S1-07), `test_stage6_chokepoint.py` (this story), and Phase-7's eventual `test_no_pip_in_distroless_layer.py` share an identical shape: walk every `.py`, check imports against a forbidden-prefix set, allowlist exceptions. The first three clear Rule-of-Three. The natural extraction is `make_namespace_chokepoint_walker(forbidden_prefix, allowlist) -> Callable[[Path], list[Offender]]` in `tests/schema/_walkers.py`. **Do NOT extract in S5-04** — Rule-2 simplicity wins until a Phase-7 author with a concrete fourth use-case lands. Surface the opportunity in the Phase-7 story author's Context.
- **If S1-07 has not GREEN-shipped when you start.** The kernel + the `tests/schema/__init__.py` package marker do not exist yet. The executor must surface BLOCKED-on-S1-07 in the attempt log and stop — do NOT in-line a kernel copy. The story's whole point is to consume the kernel; re-declaring it forks the structural defense.
- **Path comparisons.** `path.resolve().relative_to(REPO_ROOT)` is mandatory (AC-PATH-1). A naive `path in _ALLOWLIST` against absolute `Path` objects silently fails open on macOS case-insensitive FS or symlinked checkouts (CI workers, `pyenv`, `direnv`). The symlinked-tmp-path sub-test exists specifically to prove this defense holds.
- **Pre-existing callers.** If running the walker on the current codebase surfaces a real call-site (not just the planted positives), the executor escalates via ADR amendment — does NOT silently broaden `_ALLOWLIST`. Default to refactoring the surfaced caller into the Phase-3 orchestrator (when it exists) or into `GateRunner.run` consumption.
- **`pytest --no-cov`.** Run the test file with `--no-cov` during local iteration to avoid the `--cov-fail-under=85` global gate falsely failing on a narrow file selection (CLAUDE.md pytest config note). The full `make test` still applies the gate.
