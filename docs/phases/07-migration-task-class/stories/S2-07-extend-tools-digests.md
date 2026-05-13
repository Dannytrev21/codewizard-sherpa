# Story S2-07 — Extend `tools/digests.yaml` additively

**Step:** Step 2 — Tool wrappers and the pre-rendered base catalog hot view
**Status:** Ready
**Effort:** S
**Depends on:** S2-06
**ADRs honored:** ADR-0009 (contract-surface snapshot — `digests.yaml` is the single source of truth for tool pinning), ADR-P7-002 (the additive seam includes pinned tool versions for the newly-allowed binaries), ADR-0013 (`gate.shell_trace.budget_s` configurable consumed at gate time)

## Context

`tools/digests.yaml` is the single source of truth for upstream tool digests + budget configuration (`phase-arch-design.md §Harness engineering ›Configuration`). Step 2's wrappers (S2-01..S2-05) and S2-06's catalog all *require* pinned values: `sandbox.dive`, `sandbox.strace`, `sandbox.strace_sidecar`, `sandbox.buildkit_image`, plus the gate budget `gate.shell_trace.budget_s`. This story closes Step 2 by landing all those entries **additively** (no edits to existing keys) and proving the precedence chain — CLI flag > env var > `digests.yaml` > hardcoded default — works for at least the `gate.shell_trace.budget_s` value (the one Step 3 / Step 7 will probe under load).

This is also the seam where `phase-arch-design.md §Risks #3` ("toolchain pinning drift across CI runners") lands its mechanical defense.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Harness engineering ›Configuration` — precedence chain spec: CLI flag > env var > `tools/digests.yaml` > hardcoded default.
  - `../phase-arch-design.md §Component design — 2. ShellInvocationTraceProbe` — `timeout_seconds: ClassVar[int] = 30` consumes `gate.shell_trace.budget_s`.
  - `../phase-arch-design.md §Component design — 4 / 7 / 8` — `tools/buildkit.py`, `tools/dive.py`, `tools/strace.py` all reference their pinned digest names.
  - `../phase-arch-design.md §Persisted-on-disk shapes` — `tools/digests.yaml` is in the persistence ledger as Phase 7 additions.
  - `../phase-arch-design.md §Gap analysis — Gap 4` — strace sidecar Alpine image pinned in `tools/digests.yaml#sandbox.strace_sidecar`.
- **Phase ADRs:**
  - `../ADRs/0009-contract-surface-snapshot-canary.md` — `digests.yaml` additions appear in the snapshot canary diff; same-PR ADR linkage enforced by S1-08.
  - `../ADRs/0013-shell-trace-runs-gate-time-in-phase5-chokepoint.md` — `gate.shell_trace.budget_s` is the configurable that S7-04 will calibrate.
- **High-level impl:**
  - `../High-level-impl.md §Step 2` — names the four `sandbox.*` keys and `gate.shell_trace.budget_s` (default 30).
  - `../High-level-impl.md §Implementation-level risks #3` — pin every binary by digest; runner image rebuild on every digest bump.
- **Existing code:**
  - `tools/digests.yaml` — the live file. Read its top-level structure before adding. Do **not** edit any existing key.

## Goal

`tools/digests.yaml` contains the five new entries (`sandbox.dive`, `sandbox.strace`, `sandbox.strace_sidecar`, `sandbox.buildkit_image`, `gate.shell_trace.budget_s=30`), every Step 2 wrapper reads its pinned value from this file, and `tests/integration/test_digests_precedence.py` proves the precedence chain CLI > env > digests.yaml > default works for `gate.shell_trace.budget_s`.

## Acceptance criteria

- [ ] `tools/digests.yaml` has five new entries, none of which collide with or modify existing keys:
  - `sandbox.dive` — pinned digest reference for the `dive` binary.
  - `sandbox.strace` — pinned digest reference for the `strace` binary.
  - `sandbox.strace_sidecar` — pinned digest reference for the Alpine strace sidecar image (Gap 4).
  - `sandbox.buildkit_image` — pinned digest reference for `moby/buildkit:<digest>` (Gap 7).
  - `gate.shell_trace.budget_s: 30` — integer seconds.
- [ ] A shared `codegenie.tools.config.resolve_setting(key: str, cli_value=None, default=None)` helper exists and implements the precedence chain: `cli_value` (non-None) > `CODEGENIE_<UPPER_KEY>` env var > `tools/digests.yaml` value > `default`.
- [ ] `tests/integration/test_digests_precedence.py` exercises **every** rung of the chain for `gate.shell_trace.budget_s`: (a) CLI flag = 45 wins over env=20, yaml=30; (b) env=20 wins over yaml=30 when no CLI; (c) yaml=30 wins over default=10 when no CLI and no env; (d) default=10 wins when key absent everywhere.
- [ ] `tools/strace.py` (S2-04) `_resolve_budget_s` calls into the shared helper; assertion: passing `budget_s=None` to `run_strace` resolves to 30 when no env override.
- [ ] `tools/buildkit.py`, `tools/dive.py` read their pinned-digest values via the same helper (no hardcoded digests in Python source).
- [ ] S1-07's `tools/contract-surface.snapshot.json` is regenerated in the same PR (the additive `digests.yaml` additions show up in the snapshot diff because the snapshot canonicalizes the additional keys); the per-phase ADR linkage is satisfied via ADR-P7-002 / ADR-P7-003 / ADR-P7-007 — `tools/snapshot_regen_audit.py` (S1-08) accepts.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest tests/integration/test_digests_precedence.py` and `pytest tests/unit/tools/test_config.py` all pass.

## Implementation outline

1. Read `tools/digests.yaml` end-to-end. Note the existing key paths and the file's YAML style; match conventions (Rule 11 — match conventions).
2. Write the failing precedence test in `tests/integration/test_digests_precedence.py`; commit.
3. Implement `src/codegenie/tools/config.py` with `resolve_setting(key, *, cli_value=None, default=None)`:
   - `cli_value is not None` → return it.
   - `os.environ.get(f"CODEGENIE_{key.upper().replace('.', '_')}")` if present → coerce via the registered type (int/str), return.
   - Load `tools/digests.yaml` (cached at module level, content-hashed); descend the dotted-key path; return if present.
   - Else → return `default`.
4. Append the five new entries to `tools/digests.yaml`. Preserve the file's existing structure; place new keys lexicographically under `sandbox:` and `gate:` blocks as appropriate.
5. Update `tools/strace.py` (S2-04) `_resolve_budget_s` to delegate to `resolve_setting`.
6. Update `tools/buildkit.py` (S2-02) and `tools/dive.py` (S2-03) to read their pinned digests via `resolve_setting`.
7. Regenerate `tools/contract-surface.snapshot.json` via `pytest --update-contract-snapshot` (per S1-07). Confirm the PR description links ADR-P7-002 / ADR-P7-003 / ADR-P7-007 so S1-08's `snapshot_regen_audit.py` accepts.
8. Refactor; mypy strict.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/test_digests_precedence.py`

```python
# tests/integration/test_digests_precedence.py
import os
import pytest
from codegenie.tools.config import resolve_setting


def test_precedence_cli_wins_over_env_and_yaml(monkeypatch):
    """CLI flag value=45 wins over env=20 and yaml=30."""
    monkeypatch.setenv("CODEGENIE_GATE_SHELL_TRACE_BUDGET_S", "20")
    # yaml on disk is the seed value 30
    result = resolve_setting(
        "gate.shell_trace.budget_s",
        cli_value=45,
        default=10,
    )
    assert result == 45


def test_precedence_env_wins_over_yaml_and_default(monkeypatch):
    """env=20 wins over yaml=30 when CLI is None."""
    monkeypatch.setenv("CODEGENIE_GATE_SHELL_TRACE_BUDGET_S", "20")
    result = resolve_setting(
        "gate.shell_trace.budget_s",
        cli_value=None,
        default=10,
    )
    assert result == 20


def test_precedence_yaml_wins_over_default(monkeypatch):
    """yaml=30 wins over default=10 when CLI and env are absent."""
    monkeypatch.delenv("CODEGENIE_GATE_SHELL_TRACE_BUDGET_S", raising=False)
    result = resolve_setting(
        "gate.shell_trace.budget_s",
        cli_value=None,
        default=10,
    )
    assert result == 30


def test_precedence_default_when_key_absent_everywhere(monkeypatch):
    """default returned when the key is missing from yaml + env + CLI."""
    monkeypatch.delenv("CODEGENIE_UNKNOWN_KEY", raising=False)
    result = resolve_setting(
        "unknown.test.key",
        cli_value=None,
        default=42,
    )
    assert result == 42


def test_digests_yaml_contains_required_phase7_keys():
    """The five new entries from Step 2 are present."""
    # yaml-on-disk must contain these five keys
    for key in [
        "sandbox.dive",
        "sandbox.strace",
        "sandbox.strace_sidecar",
        "sandbox.buildkit_image",
        "gate.shell_trace.budget_s",
    ]:
        # absent → resolve_setting returns the sentinel; present → returns a value
        v = resolve_setting(key, cli_value=None, default=None)
        assert v is not None, f"missing key in tools/digests.yaml: {key}"


def test_gate_shell_trace_budget_s_yaml_default_is_30():
    """Architecture default per phase-arch-design §Component 2."""
    monkeypatch_env = os.environ.pop("CODEGENIE_GATE_SHELL_TRACE_BUDGET_S", None)
    try:
        v = resolve_setting("gate.shell_trace.budget_s", cli_value=None, default=10)
        assert v == 30, f"yaml default for gate.shell_trace.budget_s must be 30 (got {v})"
    finally:
        if monkeypatch_env is not None:
            os.environ["CODEGENIE_GATE_SHELL_TRACE_BUDGET_S"] = monkeypatch_env
```

Run; tests fail because `codegenie.tools.config` doesn't exist and `tools/digests.yaml` lacks the keys. Commit.

### Green — make it pass

- Add `src/codegenie/tools/config.py` with `resolve_setting()`. Cache the parsed YAML at module level keyed by file mtime + content hash.
- Append the five new entries to `tools/digests.yaml`. Use:
  - `sandbox.dive` — placeholder `wagoodman/dive@sha256:<placeholder>` until operator pins.
  - `sandbox.strace` — placeholder for the strace binary (apt-pinned version + sha256).
  - `sandbox.strace_sidecar` — `alpine:3.20@sha256:<placeholder>` for the sidecar image (Gap 4 names this).
  - `sandbox.buildkit_image` — `moby/buildkit:v0.13.1@sha256:<placeholder>` (Gap 7 names this).
  - `gate.shell_trace.budget_s: 30`.
- Update the three Step 2 wrappers (S2-02, S2-03, S2-04) to read their pinned values via `resolve_setting`.
- Regenerate the contract-surface snapshot.

### Refactor — clean up

- Type hints; PEP 604 unions; module docstring documenting the precedence chain in plain words (so the next person doesn't have to read the test to understand it).
- `int` coercion of env-var strings is explicit (so a typo in `export CODEGENIE_GATE_SHELL_TRACE_BUDGET_S=thirty` raises `ValueError` loudly, not silently falls through to yaml).
- Confirm no `random`, no `time.time()` for control flow (fence-CI).
- The placeholder digests in `tools/digests.yaml` are clearly labeled with a `# TODO: operator pins real digest` comment so they're not mistaken for production values.

## Files to touch

| Path | Why |
|---|---|
| `tools/digests.yaml` | Add five new keys (additive — no edits to existing keys). |
| `src/codegenie/tools/config.py` | New — `resolve_setting()` precedence-chain helper. |
| `tests/integration/test_digests_precedence.py` | New — red phase + every-rung precedence assertion. |
| `tests/unit/tools/test_config.py` | New — unit tests for the helper's coercion + caching. |
| `src/codegenie/tools/strace.py` (touched) | Replace local `_resolve_budget_s` with delegation to `resolve_setting`. |
| `src/codegenie/tools/buildkit.py` (touched) | Read pinned `sandbox.buildkit_image` digest via `resolve_setting`. |
| `src/codegenie/tools/dive.py` (touched) | Read pinned `sandbox.dive` digest via `resolve_setting`. |
| `tools/contract-surface.snapshot.json` | Regenerate via `pytest --update-contract-snapshot`; same PR must link ADR-P7-002/003/007 to satisfy `snapshot_regen_audit.py`. |

## Out of scope

- **Real digest values for the placeholders** — operators pin real digests as a follow-up; placeholders are clearly labeled in the YAML.
- **`gate.shell_trace.budget_s` empirical calibration** — S7-04 measures distribution; if p95 > 24 s, an ADR amendment bumps the default.
- **CLI flag wiring on `codegenie migrate`** — S5-05 owns the Click options; this story only proves the helper supports the `cli_value` kwarg.
- **Pre-warm / catalog-refresh CLI verbs** — operator follow-up (Open implementation question #6).
- **Phase 11 / Phase 13 reading these values** — out-of-phase consumers; their stories own the read sites.

## Notes for the implementer

- This story **touches** Step 2 wrappers from S2-02..S2-04. That's deliberate — the wrappers had local resolution helpers that were temporary scaffolding; consolidating into `resolve_setting` here is the correct pattern. Surface the cross-story touch in the PR description so a reviewer doesn't think you're widening Step 2's scope.
- The contract-surface snapshot regen is **mandatory** in this PR (S1-07 + S1-08). The S1-08 audit script scans the PR body for `ADR-(P\d+-\d+|0\d+)` and requires a matching ADR file modified in the same PR — but for a *yaml-only additive extension* the relevant ADRs (ADR-P7-002, ADR-P7-003, ADR-P7-007) are already in place from Step 1; only their per-phase ADR files need referencing in the PR body, not re-edited. Confirm `snapshot_regen_audit.py` accepts this pattern; if it requires a re-edit, add a one-line "no semantic change" follow-up in the ADR's Consequences section.
- Env-var naming: `gate.shell_trace.budget_s` → `CODEGENIE_GATE_SHELL_TRACE_BUDGET_S`. Document the dot-to-underscore convention in the module docstring (Rule 11 — match conventions; this matches Phase 0's existing settings posture).
- The YAML cache must invalidate on mtime change so a developer who edits `tools/digests.yaml` mid-test-run isn't fooled by a stale cache. Keyed by (path, mtime, len) is sufficient; SHA-256 is overkill here.
- Coercion: `int` values must round-trip through `int(env_str)`. A `float` value (no Step 2 setting needs it yet) would call `float(env_str)`. Pick a small typed-resolver layer rather than `eval` (Rule 12 — fail loud, don't be clever).
- Placeholder digests are a documented temporary state; the PR description should list which digests are real vs placeholder, and operators are pointed at the follow-up to pin real values. Do not deploy with placeholders silent.
- This story closes Step 2. After this lands, every Phase 7 component that depends on a Step 2 wrapper or the catalog hot view is free to start (Step 3 begins with S3-01 depending on S2-01 + S1-02).
