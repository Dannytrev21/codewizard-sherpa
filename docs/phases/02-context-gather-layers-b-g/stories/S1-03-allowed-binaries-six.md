# Story S1-03 — `ALLOWED_BINARIES` extension for the six new tools

**Step:** Step 1 — Plant sandbox extension, tool wrappers, tool-digest pin manifest, and the four Phase-0/1 in-place edits
**Status:** Ready
**Effort:** S
**Depends on:** S1-01, S1-02
**ADRs honored:** ADR-0005

## Context

Phase 0 introduced `src/codegenie/exec.ALLOWED_BINARIES` as the single sanctioned mechanism for invoking external CLIs (Phase 0 ADR-0006); Phase 1 added `node` per Phase 1 ADR-0001. Phase 2 extends the set by six: `scip-typescript`, `semgrep`, `syft`, `grype`, `gitleaks`, `docker`. The synthesis chose **one combined ADR with per-binary subsections** (ADR-0005) rather than six separate ADRs — review burden for near-identical "add binary X to allowlist" ADRs was the deciding factor.

This is one of the four ADR-gated in-place edits Phase 2 makes to Phase 0/1 code. The diff is a single `set.union(...)` over the existing constant — no edits to the chokepoint logic, no edits to existing `--version` cross-check policy beyond the wrappers (which land in S1-05/06/07).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #2` — names which wrapper invokes which binary.
  - `../phase-arch-design.md §"Goals" #14` — extension-by-addition with this as one of the four explicit Phase-0/1 edits.
- **Phase ADRs:**
  - `../ADRs/0005-allowed-binaries-additions.md` — ADR-0005 — the combined ADR with one subsection per binary; documents threat surface, invocation pattern, `--version` cross-check, sandbox profile, and digest cache-key contribution per binary; flags the `docker` open question (`buildx --driver=docker-container` fallback if host-daemon coupling fails).
  - `../ADRs/0003-subprocess-sandbox-profile-extension.md` — ADR-0003 — each new binary runs under the extended sandbox profile from S1-02.
  - `../ADRs/0004-tools-digests-yaml-pin-manifest.md` — ADR-0004 — each binary's digest participates in cache keys (manifest lands in S1-08).
- **Source design:**
  - `../final-design.md §"Goals (concrete, measurable)"` Extension-by-addition bullet — the explicit `ALLOWED_BINARIES` edit.
  - `../final-design.md §"Roadmap coherence check" New ADRs implied` #5 — the combined-ADR choice.
- **Existing code:**
  - `src/codegenie/exec.py` — `ALLOWED_BINARIES: frozenset[str]` declared at module scope; current value is `{"git", "node"}`.
  - `tests/unit/exec/test_allowed_binaries.py` (Phase 1 origin) — exists; extend with the six new entries.

## Goal

Extend `src/codegenie/exec.ALLOWED_BINARIES` from `{"git", "node"}` to `{"git", "node", "scip-typescript", "semgrep", "syft", "grype", "gitleaks", "docker"}` per ADR-0005, and extend `tests/unit/exec/test_allowed_binaries.py` to enumerate all eight binaries and assert the extended credential-strip behavior from S1-02 against a parametrized env.

## Acceptance criteria

- [ ] `src/codegenie/exec.ALLOWED_BINARIES` is `frozenset({"git", "node", "scip-typescript", "semgrep", "syft", "grype", "gitleaks", "docker"})`.
- [ ] The constant remains a `frozenset[str]` (Phase 0 invariant — immutable at module scope; mypy sees `Final[frozenset[str]]`).
- [ ] `tests/unit/exec/test_allowed_binaries.py` asserts the set equality against the documented eight-element set.
- [ ] A parametrized test verifies that invoking `run_in_sandbox` with an argv whose `argv[0]` is each of the six new binaries does **not** raise `DisallowedSubprocessError`.
- [ ] A negative test verifies that an argv whose `argv[0]` is a string not in the set (`"curl"`, `"wget"`) still raises `DisallowedSubprocessError` — the chokepoint is still closed.
- [ ] The credential-strip extension from S1-02 is re-asserted here for all eight binaries (one parametrized test) — every binary inherits the same credential-strip discipline.
- [ ] No edit to `run_in_sandbox` logic; the only diff in `exec.py` is the `ALLOWED_BINARIES` literal.
- [ ] The TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Extend `tests/unit/exec/test_allowed_binaries.py` (red) — assert the eight-element set, the per-binary positive cases, the negative case for `curl`, the credential-strip parametrization.
2. Edit `src/codegenie/exec.py`: change the `ALLOWED_BINARIES = frozenset({"git", "node"})` literal to include the six new entries. Sort alphabetically inside the literal for diff clarity, but the set's membership semantics are order-independent.
3. Confirm `Final[frozenset[str]]` annotation remains; if Phase 0/1 typed it as `Final`, do not weaken.
4. Run `pytest tests/unit/exec/test_allowed_binaries.py`, `ruff check`, `mypy --strict src/codegenie/exec.py`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/exec/test_allowed_binaries.py` (extend the existing Phase 1 test).

```python
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import codegenie.errors as e
from codegenie.exec import ALLOWED_BINARIES, run_in_sandbox

PHASE2_BINARIES = {"scip-typescript", "semgrep", "syft", "grype", "gitleaks", "docker"}


def test_allowed_binaries_equals_eight_documented_entries():
    assert ALLOWED_BINARIES == {"git", "node"} | PHASE2_BINARIES


@pytest.mark.parametrize("binary", sorted(PHASE2_BINARIES))
def test_each_new_binary_is_allowed(binary: str):
    # spawn is mocked; we only need to ensure the allowlist gate doesn't raise
    with patch("codegenie.exec._spawn") as spawn:
        spawn.return_value = ("", "", 0)
        run_in_sandbox(
            [binary, "--version"],
            allowlist=[binary], env={}, timeout_s=1.0, cwd=Path("/tmp"),
        )


def test_unlisted_binary_still_blocked():
    with pytest.raises(e.DisallowedSubprocessError):
        run_in_sandbox(
            ["curl", "https://example.invalid"],
            allowlist=["curl"], env={}, timeout_s=1.0, cwd=Path("/tmp"),
        )


@pytest.mark.parametrize("binary", sorted({"git", "node"} | PHASE2_BINARIES))
def test_credential_strip_applies_to_every_allowed_binary(binary: str):
    parent_env = {"PATH": "/usr/bin", "OPENAI_API_KEY": "sk-x", "GITHUB_TOKEN": "g"}
    with patch("codegenie.exec._spawn") as spawn:
        spawn.return_value = ("", "", 0)
        run_in_sandbox(
            [binary, "--version"],
            allowlist=[binary], env=parent_env, timeout_s=1.0, cwd=Path("/tmp"),
        )
    argv = spawn.call_args.args[0]
    assert "OPENAI_API_KEY" in argv
    assert "GITHUB_TOKEN" in argv
```

Run; confirm `AssertionError` on the set equality and probable `DisallowedSubprocessError` on the per-binary positive cases. Commit as red marker.

### Green — make it pass

Edit `src/codegenie/exec.py`:

```
ALLOWED_BINARIES: Final[frozenset[str]] = frozenset({
    "docker",
    "gitleaks",
    "git",
    "grype",
    "node",
    "scip-typescript",
    "semgrep",
    "syft",
})
```

(One literal edit; preserve `Final` annotation and `frozenset` type. The comment line above the constant — if any — gains a Phase 2 ADR-0005 reference.)

### Refactor — clean up

- Move the docstring above the constant to name ADR-0005 explicitly: `"""ADR-0005: Phase 2 added six binaries (scip-typescript, semgrep, syft, grype, gitleaks, docker)."""`.
- Do not reorder unrelated module content.
- Confirm `mypy --strict src/codegenie/exec.py` clean.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/exec.py` | Extend `ALLOWED_BINARIES` literal; add ADR-0005 reference comment |
| `tests/unit/exec/test_allowed_binaries.py` | Extend assertions to cover all eight binaries + credential-strip parity |

## Out of scope

- **The seven tool wrappers** (`semgrep.py`, `syft.py`, `grype.py`, `gitleaks.py`, `scip_typescript.py`, `docker.py`, `treesitter.py`) — handled by S1-05, S1-06, S1-07. This story only mutates the allowlist.
- **Tool digest pinning + install-time verifier** — handled by S1-08. This story does not assert digests; it only asserts the allowlist gate is open.
- **The `docker buildx --driver=docker-container` open question** — surfaces in S1-06 (`docker` wrapper) and resolves in S6-01 (`SyftSBOMProbe` integration). This story does not pre-resolve it.
- **Phase 7's distroless additions** (`crane`, `cosign`, `chainctl`) — those land in a Phase 7 ADR; do not pre-add.

## Notes for the implementer

- Keep the literal alphabetically sorted. Future contributors adding a binary should drop the new entry at its sort position, which makes the diff one line. Phase 0's `{"git", "node"}` happened to be alphabetical; this carries that forward.
- The constant **must** stay a `frozenset`, not a `set`. Phase 0's invariant: top-level allowlist is immutable at import time. If your IDE auto-formats it to `set(...)`, revert.
- The negative test (`curl` still blocked) is load-bearing. Per Rule 12 (Fail loud), the *positive* tests prove the new binaries got in; the *negative* test proves the allowlist is still a gate, not a free pass. Do not delete it under the heading "now obviously redundant" — it pins the chokepoint discipline.
- The credential-strip parametrization across all eight binaries is intentional. ADR-0003 says the sandbox profile applies uniformly; this test pins that uniformity at the allowlist surface. If the test surfaces an inconsistency, the bug is in S1-02's implementation, not this story.
- Do **not** introduce a per-binary policy struct (e.g., `BinaryPolicy(name, default_network, ...)`) in this story. ADR-0005 explicitly chose to keep the allowlist as a flat `frozenset[str]`; per-binary policy lives inside each wrapper (S1-05/06/07). Adding a struct here would surface every wrapper's policy at the `exec.py` layer and violate the "wrapper owns its tool" boundary.
- This story is `Effort: S` for a reason — it's almost entirely the test surface. The src edit is one literal. Resist the temptation to "improve" `exec.py` while editing (Rule 3 — Surgical Changes).
