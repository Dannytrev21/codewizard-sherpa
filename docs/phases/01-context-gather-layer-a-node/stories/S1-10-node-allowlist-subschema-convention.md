# Story S1-10 — `node` in `ALLOWED_BINARIES` + per-probe sub-schema convention + event constants

**Step:** Step 1 — Plant shared primitives, sub-schema convention, and the three Phase-0 in-place edits
**Status:** Done — 2026-05-14 (phase-story-executor attempt 1, GREEN). All 23 ACs verified across three commits: RED `8453445`, GREEN `1e8713f`, sweep `cfb189f`. Affected-slice tests 260/260 green; full unit suite 882/883 (one pre-existing S1-05 `yaml.load(` forbidden-pattern false positive in `catalogs/__init__.py:162`, documented in prior attempts). `ruff check`/`ruff format --check`/`mypy --strict src` clean; pre-commit clean on touched files. AC-5 verified: `git grep -nE '"probe\.(parser\.cap_exceeded|memo\.hit|memo\.miss|catalog\.load)"' src/codegenie/` returns only the four `Final[str]` declarations in `logging.py`. Attempt log: [`_attempts/S1-10.md`](_attempts/S1-10.md). Implementation: [`src/codegenie/exec.py`](../../../../src/codegenie/exec.py), [`src/codegenie/logging.py`](../../../../src/codegenie/logging.py), [`src/codegenie/schema/probes/_subschema_convention.md`](../../../../src/codegenie/schema/probes/_subschema_convention.md). Sweep: [`src/codegenie/parsers/_io.py`](../../../../src/codegenie/parsers/_io.py), [`src/codegenie/parsers/_depth.py`](../../../../src/codegenie/parsers/_depth.py), [`src/codegenie/parsers/jsonc.py`](../../../../src/codegenie/parsers/jsonc.py), [`src/codegenie/coordinator/parsed_manifest_memo.py`](../../../../src/codegenie/coordinator/parsed_manifest_memo.py), [`src/codegenie/catalogs/__init__.py`](../../../../src/codegenie/catalogs/__init__.py). Tests: [`tests/unit/test_exec.py`](../../../../tests/unit/test_exec.py), [`tests/unit/test_logging.py`](../../../../tests/unit/test_logging.py), [`tests/unit/schema/test_subschema_convention_doc.py`](../../../../tests/unit/schema/test_subschema_convention_doc.py), [`tests/unit/test_no_event_literal_drift.py`](../../../../tests/unit/test_no_event_literal_drift.py). Deviations: (1) `caplog` → `structlog.testing.capture_logs()` (Rule 11 — match codebase idiom; AC intent preserved); (2) literal-drift guard regex simplified to plain substring check (zero false-negative-impact). With this story Step 1 is complete: parsers, memo, snapshot pass, raw-artifact budget, catalogs, allowlist entry, convention doc, and event constants are all on disk with a registry-pattern guard against literal drift.
**Effort:** S
**Depends on:** S1-09
**ADRs honored:** ADR-0001, ADR-0004, ADR-0007, ADR-0010

## Validation notes (2026-05-14)

Hardened by `phase-story-validator`. Report: [`_validation/S1-10-node-allowlist-subschema-convention.md`](_validation/S1-10-node-allowlist-subschema-convention.md). Verdict: **HARDENED**. Changes applied in place:

- **TDD plan rewritten end-to-end.** The original red tests used `subprocess.run` + sync `run_allowlisted` + `cwd="."`. The Phase 0 implementation is `async` and routes through `asyncio.create_subprocess_exec`; env is built **by omission** (parent env never copied), not by post-hoc stripping. The new red tests mirror Phase 0's [`tests/unit/test_exec.py`](../../../../tests/unit/test_exec.py) Test 2/3 idiom — spy on `asyncio.create_subprocess_exec`, assert child env keyset ⊆ safe baseline, assert `stdin=DEVNULL`, assert `shell` kwarg absent — parametrized over `git` and `node`. *Failure mode caught:* the original test would have passed trivially against a no-op implementation because the parent env vars set by `monkeypatch.setenv` never reach the child regardless of which binary is allowlisted.
- **Test paths corrected.** Phase 0 exec tests live at `tests/unit/test_exec.py`, not `tests/unit/exec/test_allowed_binaries.py`. Story now extends the existing file (Rule 11 — match codebase conventions; Rule 3 — surgical changes).
- **AC-7 "optional sweep" disambiguated.** Replaced the OR-do-it-OR-don't choice with a deterministic rule (Rule 12 — fail loud): the sweep is **required in scope** for the three event names with existing literal call-sites (`probe.parser.cap_exceeded`, `probe.memo.hit`, `probe.memo.miss`, `probe.catalog.load`); `probe.raw_artifact.truncated` has no current call-site and lands as a constant only. A grep-discipline AC pins zero remaining literal call-sites under `src/codegenie/` outside `logging.py`.
- **Closed-set discipline for `ALLOWED_BINARIES`.** Added a negative-membership AC: `"bash"`, `"sh"`, `"python"`, `"curl"`, `"wget"`, `"ssh"` are NOT in the set. Pins the Open/Closed property of the allowlist against future drift.
- **Convention-doc canonical fragment pinned.** AC-3's test now requires the doc to contain a JSON Schema fragment with `"additionalProperties": false` as a literal substring, plus a back-pointer to the enforcing test (`tests/unit/test_sub_schemas.py`, landing in S2-01) so the doc is not load-bearing alone.
- **Design-pattern note added (Notes for implementer).** If the sweep is taken, the right structural follow-up is an adversarial AST/grep test asserting no module under `src/codegenie/` other than `logging.py` re-defines a string literal equal to one of the eleven registered event-name values. That guard is **out of scope** for this story (call-site discipline is enforced by code review here); flag for Phase 1 wrap-up (S6-03).

Original goal, scope, and ADR mapping unchanged.

## Context

The final Step 1 story bundles three small ADR-gated landings: (a) the **`node` in `ALLOWED_BINARIES`** edit — the third and last Phase-0 in-place edit Phase 1 makes, gated by ADR-0001; (b) the **per-probe sub-schema convention** markdown — the in-tree documentation that ADR-0004 + ADR-0010 demand (every Phase 1 sub-schema sets `additionalProperties: false` at its own root; slices declared optional at envelope level); (c) **event-name constants** in `codegenie/logging.py` so the literals scattered across S1-02 through S1-09 collapse to `Final[str]` references.

After this story lands, every primitive Step 1 plants has its event names lifted to constants, its convention rule documented, and its allowlist entry plumbed — Step 2 onward consumes them.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #2` — `NodeBuildSystemProbe`'s optional `node --version` call via `exec.run_allowlisted` (consumed in S2-02, not this story).
  - `../phase-arch-design.md §"Component design" #11` — per-probe sub-schemas at `src/codegenie/schema/probes/`, each strict at own root.
  - `../phase-arch-design.md §"Harness engineering" → "Logging strategy"` — names every Phase-1 event: `probe.parser.cap_exceeded`, `probe.memo.hit`, `probe.memo.miss`, `probe.catalog.load`, `probe.raw_artifact.truncated`, `parser_kind` tracing field.
  - `../phase-arch-design.md §"Edge cases"` row 6 — hostile `node` shim path; this story enables the allowlist; S2-02 uses it; S5-02 adversarial tests it.
- **Phase ADRs:**
  - `../ADRs/0001-add-node-to-allowed-binaries.md` — ADR-0001 — the allowlist edit; env-strip + `shell=False` unchanged.
  - `../ADRs/0004-per-probe-subschema-additional-properties-false.md` — ADR-0004 — the convention `_subschema_convention.md` documents.
  - `../ADRs/0010-layer-a-slices-optional-at-envelope.md` — ADR-0010 — slices declared optional at envelope; non-Node repos validate.
- **Production ADRs:**
  - `../../../production/adrs/0005-no-llm-in-gather-pipeline.md` — `fence` job continues to assert.
- **Existing code:**
  - `src/codegenie/exec.py` (Phase 0) — `ALLOWED_BINARIES: frozenset[str] = frozenset({"git"})` per Phase 0 ADR-0012; this story extends to `frozenset({"git", "node"})`.
  - `src/codegenie/logging.py` (Phase 0 S2-01) — exports six `EVENT_PROBE_*` constants; this story appends five more.
  - `src/codegenie/schema/probes/` — directory exists from Phase 0 (Phase 0 ships `language_detection.schema.json`); this story adds `_subschema_convention.md` alongside.

## Goal

Three surgical landings: (a) add `"node"` to `ALLOWED_BINARIES`; (b) ship `_subschema_convention.md` documenting ADR-0004 + ADR-0010; (c) register five new event-name `Final[str]` constants in `codegenie/logging.py`.

## Acceptance criteria

- [ ] **AC-1 (allowlist extension).** `src/codegenie/exec.py` — `ALLOWED_BINARIES` extends from `frozenset({"git"})` to `frozenset({"git", "node"})`. No other line in the file changes except the module-docstring sources block, which gains a one-line pointer to ADR-0001. Verified by `git diff --stat src/codegenie/exec.py` ≤ 5 lines added, 1 modified.
- [ ] **AC-2a (positive membership + closed-set equality).** `tests/unit/test_exec.py` is extended with a test that asserts (i) `"node" in ALLOWED_BINARIES`, AND (ii) `ALLOWED_BINARIES == frozenset({"git", "node"})`. The equality assertion is load-bearing — it catches a mutant that silently widens the set (e.g., adds `"bash"`).
- [ ] **AC-2b (closed-set negative discipline — Open/Closed regression).** Same test module asserts that `"bash"`, `"sh"`, `"python"`, `"curl"`, `"wget"`, `"ssh"` are NOT in `ALLOWED_BINARIES`. This pins the discipline that every future addition is ADR-gated (ADR-0001 / Phase 0 ADR-0012); a PR that "just adds" any of these six binaries will fail this test and trigger the ADR conversation.
- [ ] **AC-2c (env-omission invariant for `node` argv).** A new async test in `tests/unit/test_exec.py`, modeled on Phase 0 Test 2, asserts: with `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `AWS_SECRET_ACCESS_KEY`, `SSH_AUTH_SOCK` set in the parent environment, calling `await run_allowlisted(["node", "--version"], cwd=tmp_path, timeout_s=5.0)` produces a child env whose keyset is a subset of `{"PATH", "HOME", "LANG", "LC_ALL"}`. The spy target is `asyncio.create_subprocess_exec`; `subprocess.run` is NOT patched (the wrapper does not call it). The assertion is over the *captured* env passed to `create_subprocess_exec`, not over `os.environ`.
- [ ] **AC-2d (env_extra sensitive-key drop, `node` argv).** Same module asserts: passing `env_extra={"OPENAI_API_KEY": "leak", "GIT_SSH_COMMAND": "ssh -i /tmp/k"}` to a `node`-argv invocation drops `OPENAI_API_KEY` from the child env, keeps `GIT_SSH_COMMAND`, AND emits a `subproc.env_extra.sensitive_key_dropped` structured event with `key="OPENAI_API_KEY"`.
- [ ] **AC-2e (chokepoint invariants hold for `node` argv).** Parametrize Phase 0 Test 3's `stdin=DEVNULL` and no-`shell`-kwarg assertions over `["git", "--version"]` AND `["node", "--version"]`. Catches a mutant that special-cases the new binary by relaxing one of the six chokepoint invariants for `node` only.
- [ ] **AC-3 (convention doc — content).** `src/codegenie/schema/probes/_subschema_convention.md` exists, is ≤ 80 lines, and documents three rules with code-block examples: (i) every Phase 1 sub-schema sets `additionalProperties: false` at its own root (link to ADR-0004); (ii) every Phase 1 slice is declared optional at envelope `probes.*` level (link to ADR-0010); (iii) `warnings[]` and structured `errors[]` use the `WarningId` pattern `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` (link to ADR-0007). Doc also names where the enforcing test lives (`tests/unit/test_sub_schemas.py`, landing in S2-01) so the convention isn't load-bearing alone.
- [ ] **AC-3b (convention doc — structural assertions).** `tests/unit/schema/test_subschema_convention_doc.py` asserts: the file exists; it references the three ADR filenames verbatim (`0004-per-probe-subschema-additional-properties-false`, `0007-warnings-id-pattern`, `0010-layer-a-slices-optional-at-envelope`); it quotes the `WarningId` regex verbatim; it contains the literal substring `"additionalProperties": false` (the canonical fragment must be present, not merely described); it contains the literal substring `test_sub_schemas.py` (the back-pointer to the enforcing test).
- [ ] **AC-4 (event-name constants).** `src/codegenie/logging.py` exports five new `Final[str]` constants below the existing six `EVENT_PROBE_*` and the five `GITIGNORE_APPEND_*`. Each follows the existing naming convention `EVENT_PROBE_<UPPERCASE_UNDERSCORE>` and is added to the `__all__` tuple in alphabetical position:
  - `EVENT_PROBE_PARSER_CAP_EXCEEDED: Final[str] = "probe.parser.cap_exceeded"`
  - `EVENT_PROBE_MEMO_HIT: Final[str] = "probe.memo.hit"`
  - `EVENT_PROBE_MEMO_MISS: Final[str] = "probe.memo.miss"`
  - `EVENT_PROBE_CATALOG_LOAD: Final[str] = "probe.catalog.load"`
  - `EVENT_PROBE_RAW_ARTIFACT_TRUNCATED: Final[str] = "probe.raw_artifact.truncated"`
  Per existing convention (`logging.py` docstring), constants are plain `str`, NOT a `StrEnum` — Phase 13's cost ledger destructures via `type(x) is str`.
- [ ] **AC-4b (constants test).** `tests/unit/test_logging.py` is extended: the `EXPECTED_EVENT_NAMES` dict gains the five new (name → value) mappings; the existing closure assertion ("every `EVENT_PROBE_*` attribute on the module appears in this dict") extends to the new family without modification, so a future PR that ships a sixth `EVENT_PROBE_*` constant without adding it to the dict fails the closure check.
- [ ] **AC-5 (registry sweep — call-site discipline).** The four existing call-sites of registered event strings are flipped from literals (or module-local `_EVENT_*` copies) to imports of the new `logging` constants:
  - `src/codegenie/parsers/_io.py`, `src/codegenie/parsers/_depth.py`, `src/codegenie/parsers/jsonc.py` — replace local `_EVENT_CAP_EXCEEDED` with `from codegenie.logging import EVENT_PROBE_PARSER_CAP_EXCEEDED` (the three module-local definitions go away — single source of truth).
  - `src/codegenie/coordinator/parsed_manifest_memo.py` — flip the two raw literals `"probe.memo.hit"` / `"probe.memo.miss"` to `EVENT_PROBE_MEMO_HIT` / `EVENT_PROBE_MEMO_MISS`.
  - `src/codegenie/catalogs/__init__.py` — replace local `_EVENT_CATALOG_LOAD` with `EVENT_PROBE_CATALOG_LOAD`.
  Verified by `git grep -nE '"probe\.(parser\.cap_exceeded|memo\.hit|memo\.miss|catalog\.load)"' src/codegenie/` returning **zero** hits outside `src/codegenie/logging.py`.
  - `probe.raw_artifact.truncated` has no current call-site; the constant lands in `logging.py` only and is consumed in a later story.
- [ ] **AC-6 (no behavioral drift from the sweep).** All previously-passing tests in `tests/unit/parsers/`, `tests/unit/coordinator/`, `tests/unit/catalogs/` continue to pass without modification — the sweep is rename-only. If any test asserts on an event literal string (e.g., a structlog capture comparing `event == "probe.memo.hit"`), the test continues to pass because the string VALUE is preserved exactly.
- [ ] **AC-7 (TDD discipline).** Red tests are committed in one commit (AC-2a–e, AC-3b, AC-4b) before any green-impl changes; green-impl follows in a separate commit. The sweep (AC-5) is in a third focused commit so it can be reverted independently if it grows beyond rename-only.
- [ ] **AC-8 (CI gates).** `ruff check`, `ruff format --check`, `mypy --strict`, `pytest`, and the Phase 0 `fence` job pass on touched files. `mkdocs build --strict` still passes (the convention doc is under `src/`, not `docs/`, so mkdocs ignores it — verified.

## Implementation outline

1. Edit `src/codegenie/exec.py` — one-line addition to `ALLOWED_BINARIES`.
2. Extend `tests/unit/exec/test_allowed_binaries.py` with the `node`-membership assertion and the env-strip matrix.
3. Create `src/codegenie/schema/probes/_subschema_convention.md` — ≤ 80-line in-tree note covering the three rules (root-strict, envelope-optional, WarningId pattern) with code-blocks showing the canonical JSON Schema fragment.
4. Append five `Final[str]` constants to `src/codegenie/logging.py` in the same block-style as the Phase 0 six constants.
5. Extend `tests/unit/test_logging.py` with the new-constant assertions.
6. (Optional sweep) Replace literal event strings in `safe_json.py`, `safe_yaml.py`, `jsonc.py`, `catalogs/__init__.py`, `parsed_manifest_memo.py`, and the raw-artifact-budget writer with the new constants.

## TDD plan — red / green / refactor

> **TDD note (load-bearing).** Phase 0's `run_allowlisted` is `async` and routes
> through `asyncio.create_subprocess_exec`. The wrapper builds the child env **by
> omission** (only `PATH`/`HOME`/`LANG`/`LC_ALL` copied from the parent) — it does
> NOT post-hoc strip parent-env keys. Tests therefore spy on
> `asyncio.create_subprocess_exec` and assert over the captured env passed to the
> spawn, not over `os.environ`. See [`tests/unit/test_exec.py`](../../../../tests/unit/test_exec.py)
> Tests 2 and 3 for the canonical idiom.

### Red — failing tests first (one commit)

```python
# tests/unit/test_exec.py — extension to the Phase 0 file
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest import mock

import pytest


def test_node_in_allowed_binaries() -> None:
    # ADR-0001: Phase 1 extends from {"git"} to {"git", "node"}.
    from codegenie.exec import ALLOWED_BINARIES

    assert "node" in ALLOWED_BINARIES
    # Equality assertion catches a mutant that silently widens the set.
    assert ALLOWED_BINARIES == frozenset({"git", "node"})


@pytest.mark.parametrize(
    "denied",
    ["bash", "sh", "python", "curl", "wget", "ssh"],
)
def test_allowed_binaries_closed_set_regression(denied: str) -> None:
    """A PR that adds any of these MUST land a Phase ADR first (ADR-0012,
    ADR-0001). This test is the structural guard."""
    from codegenie.exec import ALLOWED_BINARIES

    assert denied not in ALLOWED_BINARIES


async def test_node_invocation_env_keyset_subset_of_safe_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The five sensitive parent-env keys are structurally absent from the
    child env for a `node`-argv invocation — the env-by-omission invariant
    holds across allowlist extensions, not just for `git`."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-not-real")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-real")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp-not-real")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "AKIA-not-real")
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/x")

    from codegenie.exec import run_allowlisted

    fake_proc = mock.MagicMock()
    fake_proc.pid = 99997
    fake_proc.returncode = 0
    fake_proc.communicate = mock.AsyncMock(return_value=(b"v20.11.1\n", b""))
    spy = mock.AsyncMock(return_value=fake_proc)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)

    await run_allowlisted(["node", "--version"], cwd=tmp_path, timeout_s=5.0)

    captured_env = spy.await_args.kwargs["env"]
    allowed_baseline = {"PATH", "HOME", "LANG", "LC_ALL"}
    leaked = set(captured_env) - allowed_baseline
    assert not leaked, f"leaked keys for node argv: {leaked}"


async def test_node_invocation_env_extra_drops_sensitive_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """env_extra is the only caller-driven path into the child env; a node
    invocation that passes a sensitive key MUST have it dropped AND logged
    so future callers can grep the audit trail."""
    from codegenie.exec import run_allowlisted

    fake_proc = mock.MagicMock()
    fake_proc.pid = 99996
    fake_proc.returncode = 0
    fake_proc.communicate = mock.AsyncMock(return_value=(b"v20.11.1\n", b""))
    spy = mock.AsyncMock(return_value=fake_proc)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)

    await run_allowlisted(
        ["node", "--version"],
        cwd=tmp_path,
        timeout_s=5.0,
        env_extra={"OPENAI_API_KEY": "leak", "NODE_OPTIONS": "--no-warnings"},
    )

    captured_env = spy.await_args.kwargs["env"]
    assert "OPENAI_API_KEY" not in captured_env
    assert captured_env.get("NODE_OPTIONS") == "--no-warnings"
    # The chokepoint logs a structured drop event — caught by structlog's
    # caplog integration in tests/conftest.py.
    assert any(
        "subproc.env_extra.sensitive_key_dropped" in rec.message
        or rec.args.get("key") == "OPENAI_API_KEY"
        for rec in caplog.records
    )


@pytest.mark.parametrize(
    "argv",
    [["git", "--version"], ["node", "--version"]],
)
async def test_spawn_kwargs_pin_stdin_devnull_and_no_shell_for_each_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, argv: list[str]
) -> None:
    """The six chokepoint invariants (Phase 0 ADR-0012) hold for both
    binaries — no special-casing for the new entry."""
    from codegenie.exec import run_allowlisted

    fake_proc = mock.MagicMock()
    fake_proc.pid = 88888
    fake_proc.returncode = 0
    fake_proc.communicate = mock.AsyncMock(return_value=(b"", b""))
    spy = mock.AsyncMock(return_value=fake_proc)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)

    await run_allowlisted(argv, cwd=tmp_path, timeout_s=10.0)

    kwargs = spy.await_args.kwargs
    assert kwargs["stdin"] is asyncio.subprocess.DEVNULL
    assert "shell" not in kwargs
```

```python
# tests/unit/test_logging.py — extension to EXPECTED_EVENT_NAMES
# The existing closure check ("every EVENT_PROBE_* module attr is in the dict")
# extends without code-change; only the dict grows.

EXPECTED_EVENT_NAMES.update(
    {
        "EVENT_PROBE_PARSER_CAP_EXCEEDED": "probe.parser.cap_exceeded",
        "EVENT_PROBE_MEMO_HIT": "probe.memo.hit",
        "EVENT_PROBE_MEMO_MISS": "probe.memo.miss",
        "EVENT_PROBE_CATALOG_LOAD": "probe.catalog.load",
        "EVENT_PROBE_RAW_ARTIFACT_TRUNCATED": "probe.raw_artifact.truncated",
    }
)


def test_phase1_event_constants_exist_and_match_values() -> None:
    for name, value in [
        ("EVENT_PROBE_PARSER_CAP_EXCEEDED", "probe.parser.cap_exceeded"),
        ("EVENT_PROBE_MEMO_HIT", "probe.memo.hit"),
        ("EVENT_PROBE_MEMO_MISS", "probe.memo.miss"),
        ("EVENT_PROBE_CATALOG_LOAD", "probe.catalog.load"),
        ("EVENT_PROBE_RAW_ARTIFACT_TRUNCATED", "probe.raw_artifact.truncated"),
    ]:
        attr = getattr(cgl, name)
        assert attr == value
        # Phase 13 cost-ledger contract: plain str, not StrEnum.
        assert type(attr) is str
```

```python
# tests/unit/schema/test_subschema_convention_doc.py — new file
from __future__ import annotations

from pathlib import Path


def test_subschema_convention_doc_exists_and_links_adrs() -> None:
    doc = Path("src/codegenie/schema/probes/_subschema_convention.md")
    assert doc.exists(), "convention doc must live alongside the sub-schemas"
    text = doc.read_text(encoding="utf-8")

    # The three load-bearing ADRs are linked by filename.
    assert "0004-per-probe-subschema-additional-properties-false" in text
    assert "0007-warnings-id-pattern" in text
    assert "0010-layer-a-slices-optional-at-envelope" in text

    # The WarningId regex is quoted verbatim.
    assert "^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$" in text

    # The canonical fragment is present, not merely described.
    assert '"additionalProperties": false' in text

    # The enforcing test is named, so the doc is not load-bearing alone.
    assert "test_sub_schemas.py" in text

    # The doc stays a reference, not a tutorial.
    line_count = sum(1 for _ in text.splitlines())
    assert line_count <= 80, f"convention doc is {line_count} lines; cap is 80"
```

```python
# tests/unit/test_no_event_literal_drift.py — new file, registry discipline
"""Pin AC-5: after the sweep, no module under src/codegenie/ outside
logging.py contains a string literal equal to one of the four registered
event-name values that previously had call-sites. A fifth value
(probe.raw_artifact.truncated) has no current call-site so it is checked
to exist only at the logging.py declaration."""
from __future__ import annotations

import re
from pathlib import Path


_REGISTERED_LITERALS = {
    "probe.parser.cap_exceeded",
    "probe.memo.hit",
    "probe.memo.miss",
    "probe.catalog.load",
}


def test_no_module_redeclares_a_registered_event_literal() -> None:
    root = Path("src/codegenie")
    offenders: list[tuple[Path, str]] = []
    for py in root.rglob("*.py"):
        if py.name == "logging.py":
            continue
        text = py.read_text(encoding="utf-8")
        for lit in _REGISTERED_LITERALS:
            if re.search(rf'(?<!\.){re.escape(lit)}', text):
                # Allow docstring mentions only if not in a string-literal
                # constant context; a precise check is overkill here — the
                # sweep eliminates all of these by construction.
                if f'"{lit}"' in text or f"'{lit}'" in text:
                    offenders.append((py, lit))
    assert not offenders, (
        "registered event literals re-declared outside logging.py: " + repr(offenders)
    )
```

Run; confirm failures (all six tests red — `node` not in set, env-keyset
test references `await run_allowlisted` on the new argv, convention doc
absent, new constants absent, sweep not yet done). Commit as red.

### Green — minimal impl (commit #2)

- `src/codegenie/exec.py`: change `ALLOWED_BINARIES = frozenset({"git"})` → `ALLOWED_BINARIES = frozenset({"git", "node"})`. Append one line to the module docstring's Sources block pointing at ADR-0001. **Nothing else.**
- `src/codegenie/logging.py`: append five `Final[str]` constants below the existing six `EVENT_PROBE_*`. Order: parser, memo.hit, memo.miss, catalog.load, raw_artifact.truncated. Extend `__all__` in alphabetical position.
- `src/codegenie/schema/probes/_subschema_convention.md`: write the convention doc. Required structure:
  - Heading + one-line summary.
  - Rule 1: `additionalProperties: false` at root (link to ADR-0004).
  - Rule 2: Slices optional at envelope `probes.*` (link to ADR-0010).
  - Rule 3: `warnings[]` and structured `errors[]` use `WarningId` pattern (link to ADR-0007); quote the regex `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` verbatim.
  - Canonical example: a JSON Schema fragment (≤ 25 lines) for a fictional probe demonstrating root-strict + pattern-constrained warnings, containing the literal `"additionalProperties": false`.
  - Back-pointer paragraph: "The structural enforcement of these rules lives in `tests/unit/test_sub_schemas.py` (landing in S2-01). This doc is the human-facing rationale; the test is the load-bearing guard."

### Registry sweep — call-site discipline (commit #3, separable)

In one focused commit so it reverts cleanly if review pushes back:

- `src/codegenie/parsers/_io.py`, `_depth.py`, `jsonc.py`: drop the three module-local `_EVENT_CAP_EXCEEDED: Final[str] = "probe.parser.cap_exceeded"` lines and emit using `from codegenie.logging import EVENT_PROBE_PARSER_CAP_EXCEEDED` directly. Update any docstring references.
- `src/codegenie/coordinator/parsed_manifest_memo.py`: flip the two raw literals `"probe.memo.hit"` / `"probe.memo.miss"` (logger.info args) to the new constants.
- `src/codegenie/catalogs/__init__.py`: drop `_EVENT_CATALOG_LOAD` local; use `EVENT_PROBE_CATALOG_LOAD`.
- Run `git grep -nE '"probe\.(parser\.cap_exceeded|memo\.hit|memo\.miss|catalog\.load)"' src/codegenie/` — must return zero hits outside `logging.py`. The new `tests/unit/test_no_event_literal_drift.py` enforces this in CI.
- Re-run the full test suite — the sweep is rename-only; no test behavior should change.

### Refactor — clean up

- Module docstring in `exec.py` already names ADR-0012; append a one-line note that Phase 1 extends with `node` per ADR-0001.
- `logging.py` constants block: confirm `ruff format` does not reflow the new entries (Phase 0 S2-01 already handled this for the first family).
- Convention doc: keep ≤ 80 lines (enforced by AC-3b).
- The structural literal-drift guard (`tests/unit/test_no_event_literal_drift.py`) is intentionally lightweight (Path.rglob + regex). If false positives arise in Phase 2+ (e.g., a probe legitimately needs the literal in test fixtures), upgrade to an AST scan in S6-03's adversarial sweep; do not weaken the test in this story.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/exec.py` | Add `"node"` to `ALLOWED_BINARIES`; one-line docstring source pointer |
| `src/codegenie/logging.py` | Add five `Final[str]` Phase-1 event-name constants; extend `__all__` |
| `src/codegenie/schema/probes/_subschema_convention.md` | Document ADR-0004 + ADR-0007 + ADR-0010 conventions |
| `tests/unit/test_exec.py` | Extend with `node`-membership, closed-set negative regression, env-keyset, env_extra drop, parametrized chokepoint kwargs |
| `tests/unit/test_logging.py` | Extend `EXPECTED_EVENT_NAMES` + targeted new-constant assertions |
| `tests/unit/schema/test_subschema_convention_doc.py` | New — convention-doc structural smoke test |
| `tests/unit/test_no_event_literal_drift.py` | New — pins AC-5 sweep discipline (registry-pattern enforcement) |
| `src/codegenie/parsers/_io.py` | Sweep — drop module-local `_EVENT_CAP_EXCEEDED`, import from `logging` |
| `src/codegenie/parsers/_depth.py` | Sweep — same |
| `src/codegenie/parsers/jsonc.py` | Sweep — same |
| `src/codegenie/coordinator/parsed_manifest_memo.py` | Sweep — flip two raw literals to constants |
| `src/codegenie/catalogs/__init__.py` | Sweep — drop `_EVENT_CATALOG_LOAD`, import from `logging` |

Note: `src/codegenie/parsers/safe_json.py` and `safe_yaml.py` route through `_io.py`/`_depth.py`, so the sweep there is transitive — they themselves don't need edits.

## Out of scope

- **Consuming the `node` allowlist entry** — S2-02 (`NodeBuildSystemProbe.run` calls `exec.run_allowlisted(["node", "--version"], ...)`).
- **Adversarial test for the hostile `node` shim** — S5-02 (`test_planted_node_on_path_ignored.py`).
- **Per-probe sub-schema files themselves** — S2-01 (extension), S2-02, S3-05, S4-01, S4-02, S4-03 ship the actual sub-schema JSONs. This story only documents the convention they all follow.
- **Tool-readiness check in the CLI for `node`** — Phase 0's tool-readiness check (S4-02) walks `ALLOWED_BINARIES`. Once `"node"` is in the set, the CLI's `WARN` on absent `node` follows automatically. No additional code in this story.

## Notes for the implementer

- **Three landings, three commits.** Total LOC: roughly 2 (exec.py) + 8 (logging.py) + 70 (convention doc) + ~120 (new + extended tests) + ~20 (sweep). Keep the boundary at: commit #1 red tests, commit #2 green impl (exec.py + logging.py + convention doc), commit #3 sweep (parsers + memo + catalogs). The three-commit shape means the sweep is revertible if review pushes back on coupling.
- **`run_allowlisted` is async.** The Phase 0 impl uses `asyncio.create_subprocess_exec`. Tests use `pytest-asyncio` (Phase 0 sets `asyncio_mode = "auto"` in `pyproject.toml`; check before writing tests). Do NOT patch `subprocess.run`.
- **Env-by-omission, not env-strip.** The wrapper never copies the parent's `os.environ`; it builds a four-key safe baseline (`PATH`/`HOME`/`LANG`/`LC_ALL`) plus a sanitized `env_extra`. So sensitive parent-env keys are **structurally absent** from the child, not "stripped". Test assertions should mirror Phase 0 Test 2's pattern (`set(captured_env) - safe_baseline == set()`), not assert `"OPENAI_API_KEY" not in env` after seeding it in the parent (which would pass trivially against a no-op implementation).
- **`ALLOWED_BINARIES` is `frozenset`.** Adding an element produces a new frozenset literal — there is no `.add()`. This is the Phase 0 contract and intentionally so. The Open/Closed property of the allowlist is enforced by AC-2b's negative regression — the closed set is closed *against six specific binaries* that an unwary future PR might add.
- **The convention doc is in `src/`, not in `docs/`.** Phase 0 placed schema sources under `src/codegenie/schema/`; this convention note lives alongside. `mkdocs build --strict` walks `docs_dir: docs` only (verified — see `mkdocs.yml`). The doc is for engineer eyes, navigable inside the source tree.
- **Per Rule 11 (Match conventions):** the existing event-name constants in `logging.py` use `EVENT_PROBE_<UPPERCASE_UNDERSCORE>` naming. Follow exactly:
  - `EVENT_PROBE_PARSER_CAP_EXCEEDED` (not `EVENT_PROBE_CAP_EXCEEDED` — the `parser` segment is structural and reflects the event-string namespace).
  - `EVENT_PROBE_MEMO_HIT` / `EVENT_PROBE_MEMO_MISS` (two separate constants — they're separate event strings).
  - **Plain `Final[str]`, NOT `StrEnum`.** Phase 13's cost ledger destructures via `type(x) is str`. The `logging.py` docstring states this load-bearing constraint; do not "improve" it.
- **Registry pattern + extension-by-addition (the design lens).** The five new constants formalize what was previously a scattered set of module-local `_EVENT_*: Final[str]` definitions across three parser modules and two raw-literal call-sites in `parsed_manifest_memo.py`. Centralizing in `logging.py` makes the event-name vocabulary a single-source-of-truth registry; the sweep AC + `test_no_event_literal_drift.py` enforce **Open/Closed at the file boundary** — adding a sixth event in Phase 2 is one file edit (`logging.py`) plus the new call-site, never a coordinated multi-file rename.
- **`shell=False` is the Phase 0 contract.** Don't touch it. Don't add new env-strip rules — Phase 0's omission model is intentional and already covers the secrets adversarial test (S5-02) needs.
- **This story closes Step 1.** After it merges, Step 2 (`LanguageDetectionProbe` extension + `NodeBuildSystemProbe`) starts from a complete primitives surface: parsers, memo, snapshot pass, raw-artifact budget, catalogs, allowlist entry, convention doc, event constants — all on disk, with a registry-pattern guard against literal drift.
- **Future-work flag (not in scope here).** A stronger structural guard would be a pre-commit `forbidden-patterns` hook that matches the four registered literals outside `logging.py`. AST-precision matters more there than in a unit test; defer to S6-03's adversarial sweep / Phase 1 wrap-up.
