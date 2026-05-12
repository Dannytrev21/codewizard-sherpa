# Story S4-01 — `LockfilePolicyScanner` + typed violations + `--allow-policy-violations` graded escape

**Step:** Step 4 — Ship `LockfilePolicyScanner` (graded escape) and the single-profile `ValidationGate` (install/test/build + signal-escalate)
**Status:** Ready
**Effort:** M
**Depends on:** S3-09
**ADRs honored:** ADR-0007 (graded escape valve), ADR-0001 (Transform/Validator surface), ADR-0010 (audit chain event types)

## Context

Phase 3's pre-transform validation refuses lockfiles with known-hostile structural patterns *before* `npm ci` runs against attacker-controlled bytes (`design-security.md §Threat model #2`). Security-first proposed a hard-non-retryable scanner with "escalate to human" as the only recourse; the critic dismantled this as a false-positive trap on legitimate corporate repos (GitHub-tarball deps, private `publishConfig.registry`). The synth ships the scanner as a **fact-emitter** with a typed-violation surface and a graded `--allow-policy-violations` operator opt-in; widening-retry is deferred to Phase 5 (ADR-0007).

This is the Phase 3 substrate for Phase 5's three-retry widening — the scanner produces structured `Violation` records; the orchestrator (S5-03) interprets them; Phase 5 wraps with retry policy. The closed-enum violation type set is load-bearing — adding a violation type later requires ADR amendment + coordination with Phase 5's widening logic.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #10 LockfilePolicyScanner` — interface, violation types, internal design, performance envelope.
  - `../phase-arch-design.md §"Goals" #11` — "fact-emitting validator with graded escape valve" goal statement.
  - `../phase-arch-design.md §"Edge cases"` row #2 — RegistryRedirect happens-path + graded escape flow.
- **Phase ADRs:**
  - `../ADRs/0007-lockfile-policy-scanner-graded-allow-policy-violations.md` — ADR-0007 — full decision; typed Violation models; `--allow-policy-violations` closed-enum flag; exit 7 + `escalation.policy_violation` audit event; widening retry deferred to Phase 5.
  - `../ADRs/0010-audit-chain-extension-cache-replay-event.md` — ADR-0010 — `lockfile.scanned` + `lockfile.policy_violation` audit event payload shape.
- **Production ADRs:**
  - `../../../production/adrs/0009-humans-always-merge.md` — human-review semantics at PR-merge, not at policy gate; informs why exit 7 (not block-and-route) is the right Phase-3 shape.
- **Source design:**
  - `../final-design.md §"Components" #6 LockfilePolicyScanner` — fact-emitting role.
  - `../final-design.md §Synthesis ledger row "Lockfile policy"` — winner: retryable-with-widening (Phase 5) + `--allow-policy-violations` escape in P3.
  - `../final-design.md §"Goals" §"Trust & safety goals"` #10.
- **Existing code:**
  - `src/codegenie/transforms/contract.py` (from S1-02) — `TransformOutput`, `Confidence`.
  - `src/codegenie/transforms/cve/contract.py` (from S2-01) — for cross-ref of `additionalProperties: false` discipline.
  - `src/codegenie/audit/events.py` (from S1-07) — `lockfile.scanned`, `lockfile.policy_violation` event types and Pydantic payloads.
  - `src/codegenie/errors.py` (from S1-01) — extend with `LockfileMalformed`.
  - `src/codegenie/cli/__init__.py` (from S1-10) — `codegenie remediate` is the click group hosting `--allow-policy-violations`.

## Goal

Implement `src/codegenie/transforms/validation/lockfile_policy.py` exposing `LockfilePolicyScanner.scan(lockfile_path, *, allowed_registries, allowed_violations) -> LockfileScanResult` with a typed closed-enum Pydantic violation model set; emit `lockfile.scanned` audit events; raise `LockfileMalformed` (loud, not a violation) on schema-malformed input; refuse oversized lockfiles at a 50 MB hard cap.

## Acceptance criteria

- [ ] `src/codegenie/transforms/validation/__init__.py` exists (empty namespace marker) so `validation/` is an importable sub-package under `transforms/`.
- [ ] `LockfilePolicyScanner.scan(lockfile_path: Path, *, allowed_registries: Sequence[str] = ("registry.npmjs.org",), allowed_violations: frozenset[ViolationType] = frozenset()) -> LockfileScanResult` is defined and importable from `codegenie.transforms.validation.lockfile_policy`.
- [ ] Five Pydantic violation models are defined, each with `model_config = ConfigDict(extra="forbid")` and `schema_version: Literal["v1"] = "v1"`: `RegistryRedirect(package, version, resolved_url, host)`, `MissingIntegrity(package, version)`, `LifecycleScriptDeclared(package, version, hooks: list[Literal["preinstall","install","postinstall"]])`, `PublishConfigOverride(declared_registry, allowed_registries: tuple[str, ...])`, `ResolutionsRedirect(spec, redirected_to, host)`. The discriminated union is `Violation = Annotated[Union[...], Field(discriminator="kind")]`; each model carries a `kind: Literal[...]` tag.
- [ ] `LockfileScanResult(violations: list[Violation], allowed_violations: frozenset[ViolationType], lockfile_size_bytes: int, schema_version: Literal["v1"])` is the public return shape; `extra="forbid"` at every nesting level.
- [ ] Hard size cap: `lockfile_path.stat().st_size > 50 * 1024 * 1024` → raises `LockfileOversize` (loud; not a violation; not exit 7). The cap is a `Final[int]` module constant `MAX_LOCKFILE_BYTES`.
- [ ] Schema-malformed lockfile (cannot JSON-parse or missing required top-level keys per npm v3 schema) → raises `LockfileMalformed` with `detail` field pinning the parse failure (loud, not a violation).
- [ ] Each violation type has detection logic per `phase-arch-design.md §"Component design" #10` table:
  - `RegistryRedirect` — any `packages.*.resolved` URL whose host ∉ `allowed_registries`.
  - `MissingIntegrity` — any `packages.*` entry lacking `integrity` (excluding workspace-internal and `link:` entries).
  - `LifecycleScriptDeclared` — top-level `package.json` OR any `node_modules/*/package.json` declares `scripts.{preinstall,install,postinstall}`.
  - `PublishConfigOverride` — top-level `package.json#publishConfig.registry` differs from `allowed_registries`.
  - `ResolutionsRedirect` — top-level `package.json#{overrides,resolutions}` redirect to a host ∉ `allowed_registries`.
- [ ] `allowed_violations` filters violations by `kind`: violations whose `kind` ∈ `allowed_violations` are still emitted in `LockfileScanResult.violations` (facts, not judgments) AND recorded in `allowed_violations` field; the *orchestrator* (S5-03) reads both to decide exit 0 vs exit 7.
- [ ] On every invocation, the scanner emits exactly one `lockfile.scanned` audit event with payload `{violation_count, allowed_violations: list[str], lockfile_size_bytes}` (per ADR-0010 schema). On any unfiltered violation, additionally emits one `lockfile.policy_violation` event per violation with `{violation_type, package, range}`.
- [ ] CLI `--allow-policy-violations` is wired into `codegenie remediate` (extends S1-10 surface) as a click `MultipleChoice` over the closed enum `{RegistryRedirect, MissingIntegrity, LifecycleScriptDeclared, PublishConfigOverride, ResolutionsRedirect}`; comma-separated; typos like `registry-redirect` are rejected by click before the command body runs.
- [ ] `tests/unit/transforms/validation/test_lockfile_policy.py` ships 7 tests: one happy path (no violations) + one per violation type (5) + `--allow-policy-violations` filtering path; plus `tests/unit/transforms/validation/test_lockfile_policy_caps.py` ships 2 tests: oversize → `LockfileOversize`; malformed → `LockfileMalformed`.
- [ ] `additionalProperties: false` extra-field-rejection unit test pins the schema discipline (per cross-cutting concern in `stories/README.md`).
- [ ] The TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Write the failing tests under `tests/unit/transforms/validation/test_lockfile_policy.py` and `tests/unit/transforms/validation/test_lockfile_policy_caps.py`. Hand-author small lockfile fixtures inline as multi-line strings (5–20 lines each); keep them realistic but minimal.
2. Add `LockfileMalformed`, `LockfileOversize` to `src/codegenie/errors.py` extending the S1-01 error tree (`LockfileError` base optional; flat is fine if no shared shape needed).
3. Create `src/codegenie/transforms/validation/__init__.py` (empty); create `src/codegenie/transforms/validation/lockfile_policy.py`.
4. Define `ViolationType = Literal["RegistryRedirect", "MissingIntegrity", "LifecycleScriptDeclared", "PublishConfigOverride", "ResolutionsRedirect"]` at module top.
5. Define the five Pydantic violation models with `model_config = ConfigDict(extra="forbid")` and the discriminated `Violation` union via `Annotated[Union[...], Field(discriminator="kind")]`.
6. Define `LockfileScanResult` Pydantic model.
7. Implement `LockfilePolicyScanner.scan`:
   - Stat-check size; over cap → raise `LockfileOversize`.
   - Read bytes; `json.loads`; on `JSONDecodeError` → raise `LockfileMalformed(detail=str(e))`.
   - Validate top-level shape (`lockfileVersion`, `packages` keys present); missing → `LockfileMalformed`.
   - Walk `packages.*` for `RegistryRedirect` + `MissingIntegrity`.
   - Walk top-level `package.json` body for `LifecycleScriptDeclared` (top-level only is fine for v1; sub-package lifecycle requires walking `node_modules/*/package.json` — emit per the detection table).
   - Top-level `publishConfig.registry` for `PublishConfigOverride`.
   - Top-level `overrides`/`resolutions` for `ResolutionsRedirect`.
   - Construct typed violation models; collect into `violations: list[Violation]`.
   - Emit `lockfile.scanned` audit event (always); per-violation `lockfile.policy_violation` events for each violation whose `kind` ∉ `allowed_violations`.
   - Return `LockfileScanResult(violations=..., allowed_violations=allowed_violations, lockfile_size_bytes=stat.st_size, schema_version="v1")`.
8. Extend `src/codegenie/cli/__init__.py` (S1-10) with `--allow-policy-violations` click option — `multiple=True` + `type=click.Choice([...closed-enum...])`. Document help string referencing this story + ADR-0007.
9. Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/transforms/validation/ tests/unit/transforms/validation/`, `pytest tests/unit/transforms/validation/`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Path: `tests/unit/transforms/validation/test_lockfile_policy.py`

```python
from pathlib import Path

import pytest

from codegenie.transforms.validation.lockfile_policy import LockfilePolicyScanner


def test_clean_lockfile_emits_no_violations(tmp_path: Path) -> None:
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text('{"lockfileVersion": 3, "packages": {"": {}}}')
    result = LockfilePolicyScanner().scan(lockfile)
    assert result.violations == []
    assert result.schema_version == "v1"


def test_registry_redirect_detected(tmp_path: Path) -> None:
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text(
        '{"lockfileVersion": 3, "packages": {"node_modules/x": '
        '{"resolved": "https://evil.example.com/x.tgz", "integrity": "sha512-AA=="}}}'
    )
    result = LockfilePolicyScanner().scan(lockfile)
    assert len(result.violations) == 1
    assert result.violations[0].kind == "RegistryRedirect"
    assert result.violations[0].host == "evil.example.com"


def test_allow_policy_violations_records_opt_in(tmp_path: Path) -> None:
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text(
        '{"lockfileVersion": 3, "packages": {"node_modules/x": '
        '{"resolved": "https://github.com/foo/bar/archive/abc.tgz", "integrity": "sha512-AA=="}}}'
    )
    result = LockfilePolicyScanner().scan(
        lockfile, allowed_violations=frozenset({"RegistryRedirect"})
    )
    # Fact-emitting: violation is still in the list
    assert len(result.violations) == 1
    # Operator opt-in is recorded
    assert "RegistryRedirect" in result.allowed_violations
```

Path: `tests/unit/transforms/validation/test_lockfile_policy_caps.py`

```python
import pytest

from codegenie.errors import LockfileMalformed, LockfileOversize
from codegenie.transforms.validation.lockfile_policy import (
    LockfilePolicyScanner, MAX_LOCKFILE_BYTES,
)


def test_oversize_raises_loudly(tmp_path):
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_bytes(b"{}" + b" " * (MAX_LOCKFILE_BYTES + 1))
    with pytest.raises(LockfileOversize):
        LockfilePolicyScanner().scan(lockfile)


def test_malformed_raises_loudly(tmp_path):
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text("{not json")
    with pytest.raises(LockfileMalformed):
        LockfilePolicyScanner().scan(lockfile)
```

Run; confirm `ImportError`/`AttributeError`. Commit as red marker.

### Green — smallest impl shape

- `lockfile_policy.py` ships `MAX_LOCKFILE_BYTES: Final[int] = 50 * 1024 * 1024`.
- Pydantic violation models tagged via `kind: Literal[...]`.
- `scan()` body: size-check → parse → schema-shape-check → five detection walks → audit emit → return.
- Use `urllib.parse.urlsplit(resolved_url).hostname` for host extraction; treat empty host as `RegistryRedirect`.

### Refactor — bounded

- Extract each per-violation detection into a small `_detect_<kind>(parsed) -> list[Violation]` helper for readability; do not over-decompose.
- Move violation `kind` discriminator constants into a module-level `_KINDS: Final[tuple[str, ...]]` tuple, single-source-of-truth referenced by the click `--allow-policy-violations` choice list.
- Audit-emit helper `_emit(event_name, payload)` wraps the `audit_writer` import to keep tests simple to mock.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/validation/__init__.py` | New (empty namespace marker) |
| `src/codegenie/transforms/validation/lockfile_policy.py` | New — `LockfilePolicyScanner` + violation models + `LockfileScanResult` |
| `src/codegenie/errors.py` | Add `LockfileMalformed`, `LockfileOversize` |
| `src/codegenie/cli/__init__.py` | Extend `codegenie remediate` with `--allow-policy-violations` closed-enum click option |
| `tests/unit/transforms/validation/test_lockfile_policy.py` | New — 7 tests (clean + 5 violation types + opt-in path) |
| `tests/unit/transforms/validation/test_lockfile_policy_caps.py` | New — oversize + malformed |
| `tests/unit/transforms/validation/test_lockfile_policy_schema.py` | New — `additionalProperties: false` extra-field rejection |

## Out of scope

- **Orchestrator response (exit 7 vs continue)** — handled by S5-03 (`coordinator.remediate`).
- **`escalation.policy_violation` audit event emission** — orchestrator-side; handled by S5-03.
- **Integration tests for the blocked + allowed paths** — `test_remediate_lockfile_policy_violation_blocked.py` + `test_remediate_lockfile_policy_violation_allowed.py` ship in S5-05.
- **Phase 5 widening retry policy** — explicit ADR-0007 deferral; this story only ships the substrate.
- **Sub-package lifecycle script detection via `node_modules/*/package.json` walking** — top-level `package.json` is required for v1; the contract is the closed `Violation` union; if Phase 5 needs deeper walk, ADR amendment.
- **Per-repo `.codegenie/config.yaml` precedence over `--allow-policy-violations`** — defer to S5-02/S5-03 if surfaces.

## Notes for the implementer

- **Facts, not judgments.** The scanner *never* decides "exit 7" — it returns a `LockfileScanResult`. The orchestrator (S5-03) interprets. Resist the urge to add a `should_block: bool` property to `LockfileScanResult` even if it looks convenient.
- **Closed-enum violation types.** `ViolationType` is a `Literal[...]` union — adding a new violation type later requires ADR amendment + Phase 5 widening logic update + this file + the click choice list. The cross-cutting `additionalProperties: false` discipline pins this.
- **`allowed_violations` is `frozenset`, not `list`.** Two reasons: (a) order doesn't matter — it's set membership; (b) mypy enforces immutability. Phase 2 ADR-0008 made this convention for `parsers/` arguments — carry it forward.
- **Click `MultipleChoice` over a closed enum** is the typo guardrail. `--allow-policy-violations registry-redirect` must fail with a clear click error message, not silently allow nothing. The risk note in `High-level-impl.md §Step 4` calls this out.
- **Audit event emission happens inside `scan()`**, not at the call site. The reason: the scanner is invoked from multiple places (S5-03 orchestrator path; Phase 5 retry-widening path) and we want every invocation logged. If you defer emission to the caller, Phase 5 will inevitably forget.
- **`LockfileMalformed` is loud, not a violation.** Per Rule 12 (Fail loud): a lockfile we can't even parse is not the same threat surface as a lockfile with a `RegistryRedirect`. Mixing them under the same `Violation` umbrella muddles the signal Phase 4 reads.
- **Hard cap is `50 MB`, matching Phase 2's parser caps.** Don't tighten it without a parser-DoS data point. Don't loosen it without surfacing the tradeoff in an ADR amendment.
