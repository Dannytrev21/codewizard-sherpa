# Story S6-06 — Phase 5 contract snapshot test (failure means Phase 5 cannot ship)

**Step:** Step 6 — RemediationOrchestrator, TrustScorer, two-stream EventLog, SubgraphNode Protocol, end-to-end happy path
**Status:** HARDENED (validated 2026-05-19 — see [`_validation/S6-06-phase5-contract-snapshot.md`](_validation/S6-06-phase5-contract-snapshot.md))
**Effort:** M
**Depends on:** S5-01 (`RecipeEngine` Protocol home), S5-05 (`RemediationReport` + co-located `TrustSignal`/`TrustOutcome` per its Option A), S6-01 (EventLog — orchestrator constructor-injection), S6-02 (`TrustScorer` + `StageOutcome` TypeAlias), S6-03 (`SubgraphNode` Protocol — orchestrator's 5-node sequence), S6-04 (`RemediationOrchestrator` — the wrap-target)
**ADRs honored:** ADR-0001 (ship the Phase-5 contract surface; the snapshot test is the CI-gating handshake; §Consequences row 1 mandates re-export from `codegenie.transforms`; row 2 mandates this test); ADR-0007 (Phase 3 runs `_validate_stage6` inside `SubprocessJail`; Phase 5 wraps the retry envelope); ADR-0010 (every contract symbol is a typed Pydantic / dataclass / Protocol with `extra="forbid"`; §Decision (3) discriminated-union narrowing; Amendment 2026-05-18 single-canonical-declaration-site discipline — S5-05's Option A co-locates `TrustSignal`/`TrustOutcome` in `outcomes.py`); ADR-0011 (honest framing — the snapshot is a structural pin, not a behavioural contract)

## Validation notes (2026-05-19)

This story was hardened against shipped reality at HEAD `ecfff74` and the latest hardened states of its six dependency stories (all `HARDENED`, none `GREEN` yet at validation time). Edits in this pass:

1. **Status** flipped to `HARDENED` with link to validation report.
2. **Depends on** expanded from `S6-04` only to the full chain (S5-01, S5-05, S6-01, S6-02, S6-03, S6-04). Reason: the test imports symbols owned by all six; without GREEN deps it cannot land. Executor should re-check each dep is GREEN before opening.
3. **ADRs honored** extended with ADR-0010 Amendment 2026-05-18 (single-canonical-declaration-site) and ADR-0011 (honest framing).
4. **TDD-plan imports rewritten** to use the canonical `from codegenie.transforms import ...` re-export path for every named symbol — `TrustSignal`/`TrustOutcome`/`StageOutcome`/`AttemptSummary`/`RemediationReport`/`RecipeEngine` included. The original story mixed deep-imports (`codegenie.transforms.trust_scorer`, `codegenie.transforms.report`, `codegenie.transforms.apply_context`) that either don't exist (S5-05 Option A co-located in `outcomes.py`) or violate the test's own AC about importing via re-export. Re-export-identity check (`pkg.RecipeEngine is plugins.protocols.RecipeEngine`) added so a duplicate Protocol declaration cannot pass.
5. **`StageOutcome` added to the snapshot list** as the 7th symbol (per S6-04 validation C-F2, Phase-5 reads the alias name; the alias resolves to `TrustOutcome`). New AC pins both the alias name and the target.
6. **Classifier rules elevated to a registry** (Design-Patterns rule-of-three: class-method, Pydantic-field, Protocol-method, `model_config`, decorator-presence, discriminator — six rule families, well past the abstraction threshold). New AC requires `@register_delta_rule(SnapshotKind)` so adding a 7th breaking-delta category is one new module + one decorator call, never an edit to the diff walker.
7. **Snapshotter dispatch elevated to a registry** (Strategy + Registry, same rule-of-three: `class`, `abc`, `protocol`, `pydantic_model`, `type_alias` — five kinds today). New AC requires `@register_snapshot_kind(SnapshotKind)`.
8. **Six new breaking-delta meta-test cases** added: discriminated-union variant removal, `extra="forbid"` → `extra="allow"`, `frozen=True` → `frozen=False`, `@runtime_checkable` removal, required-field type-narrowing, Protocol-method removal. Each was named in Notes but lacked a corresponding meta-test assertion — exactly the bug that lets a buggy classifier ship silently.
9. **Determinism property test** added: same source → byte-identical snapshot across 10 invocations in the same process. Catches non-stable dict ordering in `model_json_schema()` output.
10. **No-silent-rewrite fence** added: without the env var, the test MUST NOT write to `GOLDEN_PATH`. Asserted by patching `Path.write_text` on the golden path. Catches the failure mode where a refactor silently inverts the env-var check.
11. **Directive-message format test** added: the failure message MUST contain the literal `PHASE 5 CANNOT SHIP`, the symbol name, the before/after signature, and a reference to ADR-0001 §Consequences row 2. A future implementer cannot regress the operator UX without a red test.
12. **Functional-core fence** added: `snapshot_symbol`, `diff_snapshots`, `format_breaking_delta_message` are AST-walk-asserted to be pure (no `os.environ`, no `read_text` / `write_text`, no module-level side effects). Catches the failure mode where a "small helper" reads from disk mid-snapshot and silently shadows the golden.
13. **`should_update_golden(env: Mapping[str, str]) -> bool` factored out** so the env-var decision is testable without monkeypatching `os.environ`.
14. **Pydantic-version pin** AC added: `pyproject.toml` carries `pydantic == X.Y.*`; the golden encodes the exact Pydantic JSON-schema-emitter output. A Pydantic minor-version bump that changes the schema emitter is a contract event, not a transparent dep bump.

## Context

ADR-0001 commits Phase 3 to shipping six named contract symbols (`RemediationOrchestrator`, `TrustScorer`, `Transform` ABC, `ApplyContext`, `RecipeEngine`, `remediation-report.yaml`) that Phase 5 wraps additively. The ADR's §Consequences row 2 names a **CI-gating contract snapshot test** as the mechanism that prevents drift: *"`tests/integration/test_phase5_contract_snapshot.py` is CI-required; failure blocks Phase 3 merges."*

This story lands that test. The test reads the public surfaces of the six symbols, canonicalizes their shape (Pydantic JSON schema for models, `inspect.signature` for methods, `inspect.getmembers` for classes), and compares to a golden file under `tests/golden/phase5-contract/`. Failure means **Phase 5 cannot ship** because Phase 5's `GateRunner.run(transition=stage6_validate, ctx=GateContext(...))` decorates symbols by name + signature; any drift means Phase 5's wrap doesn't compose.

**Critical distinction** (per `High-level-impl.md §Implementation-level risks #4`): the test allows **additive** deltas (a new optional field with `default_factory`, a new method on a class, a new variant on a discriminated union) but rejects **breaking** deltas (rename, remove, required-add, signature-change). Breaking deltas require an explicit **ADR amendment + golden refresh** in the same PR. Encoding this distinction in the test (not in reviewer judgment) is the explicit risk-mitigation strategy from High-level-impl.

The six symbols and what their snapshot captures:

| Symbol | Snapshot content |
|---|---|
| `RemediationOrchestrator` | `inspect.signature(__init__)`, `inspect.signature(run)`, `inspect.signature(_validate_stage6)`; class MRO |
| `TrustScorer` | `inspect.signature(__init__)`, `inspect.signature(score)`; `TrustSignal` + `TrustOutcome` JSON schemas |
| `Transform` (ABC) | abstract method names + signatures; concrete subclass list (sealed hierarchy snapshot) |
| `ApplyContext` | Pydantic JSON schema; `AttemptSummary` JSON schema; `prior_attempts` default-factory shape |
| `RecipeEngine` (Protocol) | Protocol method signatures; `@runtime_checkable` decorator presence |
| `remediation-report.yaml` schema | Pydantic JSON schema of `RemediationReport` (from S5-05) |

The architecture spec's §Testing strategy lists this test explicitly: *"`tests/integration/test_phase5_contract_snapshot.py` — the Phase-5 contract handshake; failure means Phase 5 cannot ship."*

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy — CI gates (required jobs)` — names this test as a CI-required job.
  - `../phase-arch-design.md §Component design C1–C5` — the public interfaces of the six symbols. The snapshot freezes these.
  - `../phase-arch-design.md §Path to production end state — Deferred ADRs this phase makes resolvable` — names P3-001 (Phase-5 contract surface) as the ADR this snapshot enforces.
- **Phase ADRs:**
  - `../ADRs/0001-ship-phase5-contract-surface-by-name.md` — full read. §Decision names the six symbols; §Consequences mandates this test; §Reversibility (Low) is the reason brittleness is acceptable.
  - `../ADRs/0007-run-npm-install-and-npm-test-in-phase3-jail.md` §Consequences — `_validate_stage6` signature is fixed by ADR-0001 contract snapshot.
- **Cross-phase contract:**
  - `../../05-sandbox-trust-gates/final-design.md §Component design — GateRunner` — the call site whose composition with `_validate_stage6` this snapshot protects.
  - `../../05-sandbox-trust-gates/ADRs/0001-two-chokepoint-sandbox-seam.md` — names `RemediationOrchestrator._validate_stage6` as the Stage-6 callsite swap point.
  - `../../05-sandbox-trust-gates/ADRs/0002-additive-prior-attempts-kwarg.md` — `ApplyContext.prior_attempts` is the additive amendment; the snapshot must permit it.
  - `../../05-sandbox-trust-gates/ADRs/0003-trustscorer-extension-via-signal-kind-registry.md` — `@register_signal_kind` is the additive extension; the snapshot must permit new kinds.
- **High-level-impl risk callout:**
  - `../High-level-impl.md §Implementation-level risks #4` — the explicit additive-vs-breaking distinction this test must encode.
- **Existing snapshot test precedent:**
  - `tests/unit/test_probe_contract.py` (Phase 0) — already snapshots the `Probe` ABC byte-for-byte against `docs/localv2.md §4`. Same pattern, different scope.
  - `tests/unit/probes/test_repo_context_envelope_extra.py` (Phase 1) — JSON-schema-based snapshot precedent.
- **This phase, parallel stories:**
  - S6-04 — the `RemediationOrchestrator` whose three signatures this test pins.
  - S6-02 — the `TrustScorer` whose constructor-injection shape this test pins.
  - S5-05 — the `RemediationReport` Pydantic model whose JSON schema is part of the snapshot.
  - S1-04 — the `Transform` ABC + `ApplyContext` Pydantic.
  - S5-01 — the `RecipeEngine` Protocol.

## Goal

Land `tests/integration/test_phase5_contract_snapshot.py` and a golden file under `tests/golden/phase5-contract/` that, together, freeze the public surface of the six ADR-0001 named symbols. The test allows **additive** deltas (optional fields with defaults, new discriminated-union variants, new methods on classes) and rejects **breaking** deltas (rename, remove, required-add, signature-change); failure is CI-gating; the failure message explicitly tells the reader to either revert the breaking change or land an ADR amendment + golden refresh in the same PR.

## Acceptance criteria

### Files + collection

- [ ] **AC-1.** `tests/integration/test_phase5_contract_snapshot.py` exists and is collected by `pytest tests/integration/`.
- [ ] **AC-2.** `tests/integration/test_phase5_contract_snapshot_meta.py` exists and is collected (meta-test for the classifier).
- [ ] **AC-3.** `tests/integration/_phase5_contract_helpers.py` exists (helpers; underscore-prefix → not collected as a test).
- [ ] **AC-4.** `tests/golden/phase5-contract/snapshot.json` lives in the repo; on first commit captures the green state of S5-01, S5-05, S6-01 through S6-04.

### Canonical symbol set (7 named symbols — ADR-0001's 6 plus `StageOutcome`)

- [ ] **AC-5.** The test snapshots exactly these symbols, imported via the canonical re-export path `from codegenie.transforms import …` (ADR-0001 §Consequences row 1):
  - `RemediationOrchestrator` — `inspect.signature(__init__)`, `.run`, `._validate_stage6`; class MRO.
  - `TrustScorer` — `inspect.signature(__init__)`, `.score`; `TrustSignal` + `TrustOutcome` Pydantic JSON schemas.
  - `Transform` (ABC) — abstract method names + signatures; **sorted set** of concrete subclass qualified names (additive on grow; breaking on remove).
  - `ApplyContext` Pydantic JSON schema + `AttemptSummary` Pydantic JSON schema.
  - `RecipeEngine` (Protocol) — method signatures + `@runtime_checkable` decorator presence.
  - `RemediationReport` (from S5-05) — Pydantic JSON schema, **including field declaration order** (per S5-05 AC-Surface-3).
  - `StageOutcome` — TypeAlias name + the qualified name of its target (must resolve to `TrustOutcome` per S6-04 validation C-F2).
- [ ] **AC-6.** **Re-export identity check.** For every symbol in the named set, `getattr(codegenie.transforms, name) is <deep-module>.<name>` is asserted — a duplicate Protocol or shadowed re-export fails loud. The deep-module map (`RecipeEngine` → `codegenie.plugins.protocols`, etc.) is declared once at the top of the test file.
- [ ] **AC-7.** **Deep-import rejection.** The test file imports ONLY `from codegenie.transforms import …` for the seven named symbols. A static AST scan inside the test (or a sibling fence test) asserts no `from codegenie.transforms.<submodule> import …` line exists in either `test_phase5_contract_snapshot.py` or `test_phase5_contract_snapshot_meta.py`. (`tests/integration/_phase5_contract_helpers.py` may deep-import only for its own internal `_DEEP_MODULE_MAP`.)

### Determinism + canonical encoding

- [ ] **AC-8.** **Snapshot determinism**: `snapshot_symbol(name, obj)` invoked twice in the same process on the same symbol returns byte-identical JSON. Asserted across all seven symbols via property test (10 runs each).
- [ ] **AC-9.** **Canonical encoding**: the snapshot is JSON-serialized with `json.dumps(..., indent=2, sort_keys=True, ensure_ascii=True)`. `sort_keys` recursively sorts nested dicts (verified — stdlib behaviour). Pydantic JSON schemas are obtained via `Model.model_json_schema(mode="serialization")`, then walked once to canonically sort `properties`, `required`, and `$defs` keys.
- [ ] **AC-10.** **Cross-platform stability**: the snapshot is asserted byte-identical on Linux + macOS CI (no `os.linesep`, no `pathlib.PurePath` repr — only stable Python primitives in the schema).
- [ ] **AC-11.** **Pydantic version pin**: `pyproject.toml` carries `pydantic == X.Y.*` (exact minor). A Pydantic minor-version bump that perturbs `model_json_schema` output triggers AC-8 → CI red → ADR amendment + golden refresh in the same PR. The exact pin string is recorded in the snapshot's top-level metadata (`{"_pydantic_version": "..."}`) so a future reader can correlate.

### Additive vs breaking classifier

- [ ] **AC-12.** **Additive deltas pass (do NOT fail the test, MAY update the golden if env var set):**
  - new optional Pydantic field with `default` or `default_factory`,
  - new method on a class (existing methods unchanged),
  - new discriminated-union variant (existing variants unchanged),
  - new abstract subclass of `Transform`,
  - new optional kwarg (kw-only, with default),
  - new `SignalKind` registry entry surfaced via additive Literal expansion,
  - new entry in `transforms.__all__` (export added).
- [ ] **AC-13.** **Breaking deltas fail (and the failure prints the AC-19 directive message):**
  - rename of any class / Pydantic field / Protocol method / TypeAlias / `__all__` entry,
  - removal of any class / Pydantic field / Protocol method / discriminated-union variant / `__all__` entry,
  - signature change to an existing method (positional-arg insertion, return-type change, kwarg-default removal),
  - **required-field add** (new field without `default` / `default_factory`),
  - **required-field type narrowing** (e.g., `int | str` → `int` removes a shape consumers were allowed to send),
  - `model_config["extra"]` change (`"forbid"` → `"allow"` or vice-versa),
  - `model_config["frozen"]` change (`True` → `False` or vice-versa),
  - **`@runtime_checkable` decorator removal** from a Protocol,
  - **`Field(discriminator="kind")` removal** or rename of the discriminator key,
  - `Annotated` discriminator metadata replaced with a plain `Union` (breaks Phase 5's static `match` narrowing per ADR-0010 §Decision (3)),
  - re-export identity change (`codegenie.transforms.X is not <canonical-home>.X` — a fresh duplicate class shadowing the canonical one).
- [ ] **AC-14.** **Each AC-12 and AC-13 case has at least one corresponding meta-test parametric case** in `test_phase5_contract_snapshot_meta.py`. The meta-test is the safety net for the classifier; extending the classifier without extending the meta-test is forbidden (asserted by a meta-meta count test that compares the count of registered delta rules to the count of meta-test cases).

### Update-golden mode (safety + opt-in)

- [ ] **AC-15.** The test exposes `--update-golden` via the env var `PHASE5_CONTRACT_UPDATE_GOLDEN=1` (NOT a pytest CLI flag — collision risk with other plugins per Notes). The decision is factored into a pure function `should_update_golden(env: Mapping[str, str]) -> bool` so it can be tested without monkeypatching `os.environ`.
- [ ] **AC-16.** **No-silent-rewrite fence**: when the env var is unset, the test does NOT call `GOLDEN_PATH.write_text` or `GOLDEN_PATH.write_bytes`. Asserted by patching `Path.write_text` / `write_bytes` to raise on the golden path during the normal-mode test run.
- [ ] **AC-17.** **CI-strict mode**: in CI (`os.environ.get("CI") == "true"`), the env-var opt-in is IGNORED and the test always compares to the on-disk golden. A developer cannot accidentally regenerate the golden in CI; the regen path is local-only.
- [ ] **AC-18.** **Additive-stale-golden behaviour**: additive deltas detected against the on-disk golden fail the test with a distinct message asking the developer to rerun with `PHASE5_CONTRACT_UPDATE_GOLDEN=1` and commit the regenerated golden. The test does NOT silently pass — drift even of the additive kind must surface in PR diffs (per Notes: golden lives in the repo).

### Directive message UX

- [ ] **AC-19.** **Failure message format**: on breaking deltas the test prints a multi-line message produced by `format_breaking_delta_message(delta)` that contains, in order, all of:
  - The literal sentinel string `PHASE 5 CONTRACT SNAPSHOT MISMATCH — BREAKING CHANGE DETECTED`,
  - `Symbol: <fully-qualified-name>`,
  - `Before: <stringified-shape>` and `After: <stringified-shape>`,
  - The literal `Phase 5 cannot ship.` directive,
  - A 4-step ADR-amendment + golden-refresh procedure referencing `docs/phases/03-vuln-deterministic-recipe/ADRs/` and the matching Phase 5 ADR,
  - `See ADR-0001 §Consequences row 2.`
- [ ] **AC-20.** The directive-message format has a structural test in the meta-test file that asserts each substring above is present (string-contains, not regex — robust to wording polish).

### Classifier + snapshotter extension points (rule-of-three)

- [ ] **AC-21.** **Snapshotter is registry-dispatched.** `snapshot_symbol(name, obj)` dispatches via a `@register_snapshot_kind(SnapshotKind)` registry, one entry per kind: `class`, `abc`, `protocol`, `pydantic_model`, `type_alias`. Adding a sixth kind (e.g., `Enum`) is one new module-local function + one decorator call, no edits to `snapshot_symbol`. (Mirrors the codebase's `@register_probe`, `@register_dep_graph_strategy`, `@register_index_freshness_check` precedents — CLAUDE.md §"Open/Closed seams".)
- [ ] **AC-22.** **Classifier is registry-dispatched.** `diff_snapshots(before, after)` dispatches each delta to a `@register_delta_rule(SnapshotKind)`-registered classifier. Today's rule families (class-method, Pydantic-field, Protocol-method, `model_config`, decorator-presence, discriminator) each own a module; adding a 7th breaking-delta category is one new module + one decorator call, no edits to the walker.
- [ ] **AC-23.** **`SnapshotKind` is a `StrEnum`** (single canonical home in `_phase5_contract_helpers.py`); both registries key off it. A typo in the kind string is a `KeyError` at registration, not at first failing test.

### Functional-core / purity fences

- [ ] **AC-24.** `snapshot_symbol`, `diff_snapshots`, and `format_breaking_delta_message` are **pure** (no `os.environ` reads, no `Path.read_text` / `write_text`, no logging, no module-level side effects after import). Enforced by an AST-walk fence test (`tests/fence/test_phase5_contract_helpers_purity.py`) that scans the helper module and rejects any of the above call names. (CLAUDE.md §"Functional core / imperative shell".)
- [ ] **AC-25.** The `Delta` algebra is a frozen tagged union (`@dataclass(frozen=True)` `Additive` and `Breaking`, both carrying a `kind: Literal[...]` discriminator); every dispatch site uses `match` + `assert_never` (ADR-0010 §Decision (3)).

### Documentation + CI wiring

- [ ] **AC-26.** The test docstring quotes ADR-0001 §Consequences row 2 verbatim and explains: *"Failure of this test means Phase 5 cannot ship. Treat snapshot mismatches as load-bearing."*
- [ ] **AC-27.** The test runs under `make check`. If `make check` does not currently invoke `tests/integration/`, the story extends it to do so AND the change is reflected in `Makefile` + CI YAML.
- [ ] **AC-28.** **Module location**: helpers live at `tests/integration/_phase5_contract_helpers.py`. The story does NOT introduce a `tests/helpers/` shared module (Rule 2 — premature abstraction; the helpers are scoped to this one test pair).

### Bar

- [ ] **AC-29.** TDD red test exists, committed, green.
- [ ] **AC-30.** `ruff format`, `ruff check`, `mypy --strict` clean.
- [ ] **AC-31.** `make fence` clean (the new helpers-purity fence is part of `make fence`).

## Implementation outline

1. **Scaffold `_phase5_contract_helpers.py`** with the typed surface (no logic yet) — `SnapshotKind` StrEnum, `Delta` tagged-union (`Additive | Breaking` `@dataclass(frozen=True)`), the two empty registries, and the `should_update_golden(env)` pure-function stub. Commit; this lets the meta-test typecheck while still red.
2. **Write the meta-test first** (`test_phase5_contract_snapshot_meta.py`, red) — parametric over every AC-12 (additive) and AC-13 (breaking) case, plus the directive-message format test (AC-19/20) and the meta-meta count check (AC-14). Each case uses a locally-defined synthetic class / Pydantic model / Protocol fixture (NOT a module under `src/codegenie/`) so it can be intentionally broken without affecting production code.
3. **Implement the snapshotter registry** (AC-21/23): one module-local function per `SnapshotKind`, each registered via `@register_snapshot_kind(...)`. `snapshot_symbol(name, obj)` resolves kind by ABC / Protocol / `BaseModel` / `inspect.isabstract` / `typing.get_origin` checks; calls into the registered snapshotter; returns a canonical dict.
4. **Implement the classifier registry** (AC-22): one module-local rule per delta category (class-method, Pydantic-field, Protocol-method, `model_config`, decorator, discriminator). Each rule is a pure function `(before_value, after_value, path) -> Iterable[Delta]`. `diff_snapshots` walks the snapshot dict recursively and dispatches each key/value pair.
5. **Implement `format_breaking_delta_message`** as a pure `@dataclass`-keyed dispatch over `Delta.kind`, producing the multi-line string asserted by AC-19. Single source of truth for the message format — the meta-test's AC-20 assertion is the regression net.
6. **Run the meta-test until green** — at this point the classifier is proven correct against synthetic fixtures, with zero dependency on S6-01..S6-05 actually existing yet.
7. **Write the main test** (`test_phase5_contract_snapshot.py`, red). Imports use the canonical re-export path (AC-5/6/7):
   ```python
   from codegenie.transforms import (
       RemediationOrchestrator, TrustScorer, Transform, ApplyContext,
       AttemptSummary, RecipeEngine, RemediationReport,
       TrustSignal, TrustOutcome, StageOutcome,
   )
   ```
   No deep-import paths. The `_DEEP_MODULE_MAP` for the re-export-identity check (AC-6) lives in `_phase5_contract_helpers.py` (the only place deep imports are permitted).
8. **First-run golden bootstrap**: with all six dep stories GREEN on the executor branch, run `PHASE5_CONTRACT_UPDATE_GOLDEN=1 pytest tests/integration/test_phase5_contract_snapshot.py` to populate `snapshot.json`. Commit golden in the same PR.
9. **Add the helpers-purity fence** (`tests/fence/test_phase5_contract_helpers_purity.py`, AC-24) — AST-walks `_phase5_contract_helpers.py` and rejects any of `os.environ`, `Path.read_text`, `Path.write_text`, `logging.getLogger`, `subprocess.*`. Mirrors the existing `tests/fence/test_transforms_module_purity.py` pattern.
10. **Wire CI**: ensure `make check` invokes `pytest tests/integration/test_phase5_contract_snapshot.py` and `tests/integration/test_phase5_contract_snapshot_meta.py`. If `tests/integration/` is not yet in `make check`, extend the `Makefile`; surface the change in the PR description.
11. Run `ruff format`, `ruff check`, `mypy --strict`, `make fence`, full `make check`.

## TDD plan — red / green / refactor

### Red — write the failing tests first

#### Meta-test (the classifier safety net — proves AC-12/13/14/19/20)

```python
# tests/integration/test_phase5_contract_snapshot_meta.py
"""Meta-test: prove the snapshot diff classifier distinguishes additive vs breaking.

Fixtures are locally-defined synthetic classes / Pydantic models / Protocols,
NOT modules under src/codegenie/. This is the same isolation discipline as
Phase 0 ADR-0002's per-test registry.
"""
from __future__ import annotations

from typing import Annotated, Literal, Protocol, runtime_checkable

import pytest
from pydantic import BaseModel, ConfigDict, Field

from tests.integration._phase5_contract_helpers import (
    Additive,
    Breaking,
    SnapshotKind,
    diff_snapshots,
    format_breaking_delta_message,
    snapshot_symbol,
    DELTA_RULE_REGISTRY,
    SNAPSHOTTER_REGISTRY,
)


# ---------------------------------------------------------------------------
# Class-method deltas
# ---------------------------------------------------------------------------

def _cls_v1():
    class S:
        def method_a(self, x: int) -> str: ...
    return S


def _cls_plus_method_b():
    class S:
        def method_a(self, x: int) -> str: ...
        def method_b(self, y: int) -> str: ...
    return S


def _cls_renamed():
    class S:
        def method_z(self, x: int) -> str: ...
    return S


def _cls_method_removed():
    class S:
        pass
    return S


def _cls_required_arg_added():
    class S:
        def method_a(self, x: int, y: int) -> str: ...
    return S


def _cls_optional_kwarg():
    class S:
        def method_a(self, x: int, *, z: int = 0) -> str: ...
    return S


def _cls_return_type_changed():
    class S:
        def method_a(self, x: int) -> bytes: ...
    return S


@pytest.mark.parametrize(
    "builder,is_additive,delta_kind",
    [
        (_cls_plus_method_b,        True,  "method_added"),
        (_cls_optional_kwarg,       True,  "kwarg_added_with_default"),
        (_cls_renamed,              False, "method_renamed"),
        (_cls_method_removed,       False, "method_removed"),
        (_cls_required_arg_added,   False, "required_arg_added"),
        (_cls_return_type_changed,  False, "return_type_changed"),
    ],
)
def test_class_method_delta_classification(builder, is_additive, delta_kind):
    before = snapshot_symbol("S", _cls_v1())
    after = snapshot_symbol("S", builder())
    deltas = diff_snapshots(before, after)
    if is_additive:
        assert deltas and all(isinstance(d, Additive) for d in deltas)
    else:
        assert any(isinstance(d, Breaking) and d.kind == delta_kind for d in deltas)


# ---------------------------------------------------------------------------
# Pydantic field deltas + model_config + discriminated unions
# ---------------------------------------------------------------------------

def _model_v1():
    class M(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")
        a: int
    return M


def _model_plus_optional():
    class M(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")
        a: int
        b: list[str] = Field(default_factory=list)
    return M


def _model_plus_required():
    class M(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")
        a: int
        b: int
    return M


def _model_extra_flipped_to_allow():
    class M(BaseModel):
        model_config = ConfigDict(frozen=True, extra="allow")
        a: int
    return M


def _model_frozen_flipped_off():
    class M(BaseModel):
        model_config = ConfigDict(frozen=False, extra="forbid")
        a: int
    return M


def _model_field_type_narrowed():
    # before: a: int | str   →   after: a: int   (consumers were allowed to send str)
    class MBefore(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")
        a: int | str
    return MBefore


def _model_field_type_narrowed_after():
    class MAfter(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")
        a: int
    return MAfter


@pytest.mark.parametrize(
    "builder,is_additive,delta_kind",
    [
        (_model_plus_optional,            True,  "field_added_with_default"),
        (_model_plus_required,            False, "required_field_added"),
        (_model_extra_flipped_to_allow,   False, "model_config_extra_changed"),
        (_model_frozen_flipped_off,       False, "model_config_frozen_changed"),
    ],
)
def test_pydantic_field_delta_classification(builder, is_additive, delta_kind):
    before = snapshot_symbol("M", _model_v1())
    after = snapshot_symbol("M", builder())
    deltas = diff_snapshots(before, after)
    if is_additive:
        assert deltas and all(isinstance(d, Additive) for d in deltas)
    else:
        assert any(isinstance(d, Breaking) and d.kind == delta_kind for d in deltas)


def test_pydantic_field_type_narrowing_is_breaking():
    before = snapshot_symbol("M", _model_field_type_narrowed())
    after = snapshot_symbol("M", _model_field_type_narrowed_after())
    deltas = diff_snapshots(before, after)
    assert any(isinstance(d, Breaking) and d.kind == "field_type_narrowed" for d in deltas)


# ---------------------------------------------------------------------------
# Discriminated-union deltas
# ---------------------------------------------------------------------------

class _VarA(BaseModel):
    kind: Literal["a"] = "a"


class _VarB(BaseModel):
    kind: Literal["b"] = "b"


class _VarC(BaseModel):
    kind: Literal["c"] = "c"


def _union_v1():
    class Holder(BaseModel):
        u: Annotated[_VarA | _VarB, Field(discriminator="kind")]
    return Holder


def _union_plus_variant():
    class Holder(BaseModel):
        u: Annotated[_VarA | _VarB | _VarC, Field(discriminator="kind")]
    return Holder


def _union_minus_variant():
    class Holder(BaseModel):
        u: Annotated[_VarA, Field(discriminator="kind")]
    return Holder


def _union_lost_discriminator():
    class Holder(BaseModel):
        u: _VarA | _VarB   # plain Union; breaks static `match` narrowing
    return Holder


@pytest.mark.parametrize(
    "builder,is_additive,delta_kind",
    [
        (_union_plus_variant,        True,  "union_variant_added"),
        (_union_minus_variant,       False, "union_variant_removed"),
        (_union_lost_discriminator,  False, "discriminator_removed"),
    ],
)
def test_discriminated_union_classification(builder, is_additive, delta_kind):
    before = snapshot_symbol("Holder", _union_v1())
    after = snapshot_symbol("Holder", builder())
    deltas = diff_snapshots(before, after)
    if is_additive:
        assert deltas and all(isinstance(d, Additive) for d in deltas)
    else:
        assert any(isinstance(d, Breaking) and d.kind == delta_kind for d in deltas)


# ---------------------------------------------------------------------------
# Protocol deltas (runtime_checkable + method removal)
# ---------------------------------------------------------------------------

def _proto_v1():
    @runtime_checkable
    class P(Protocol):
        def m(self, x: int) -> str: ...
    return P


def _proto_method_removed():
    @runtime_checkable
    class P(Protocol):
        pass
    return P


def _proto_runtime_checkable_removed():
    class P(Protocol):
        def m(self, x: int) -> str: ...
    return P


def test_protocol_method_removal_is_breaking():
    before = snapshot_symbol("P", _proto_v1())
    after = snapshot_symbol("P", _proto_method_removed())
    deltas = diff_snapshots(before, after)
    assert any(isinstance(d, Breaking) and d.kind == "protocol_method_removed" for d in deltas)


def test_protocol_runtime_checkable_removal_is_breaking():
    before = snapshot_symbol("P", _proto_v1())
    after = snapshot_symbol("P", _proto_runtime_checkable_removed())
    deltas = diff_snapshots(before, after)
    assert any(isinstance(d, Breaking) and d.kind == "runtime_checkable_removed" for d in deltas)


# ---------------------------------------------------------------------------
# Directive message format (AC-19 / AC-20)
# ---------------------------------------------------------------------------

def test_directive_message_contains_required_sections():
    delta = Breaking(
        kind="method_signature_changed",
        symbol="RemediationOrchestrator._validate_stage6",
        before="(self, transform: Transform, ctx: ApplyContext) -> StageOutcome",
        after="(self, transform: Transform, ctx: ApplyContext, *, retry: int = 0) -> StageOutcome",
    )
    msg = format_breaking_delta_message(delta)
    # AC-19: each substring must be present.
    assert "PHASE 5 CONTRACT SNAPSHOT MISMATCH — BREAKING CHANGE DETECTED" in msg
    assert "Symbol: RemediationOrchestrator._validate_stage6" in msg
    assert "Before: (self, transform: Transform, ctx: ApplyContext) -> StageOutcome" in msg
    assert "After:  (self, transform: Transform, ctx: ApplyContext, *, retry: int = 0) -> StageOutcome" in msg
    assert "Phase 5 cannot ship." in msg
    assert "docs/phases/03-vuln-deterministic-recipe/ADRs/" in msg
    assert "See ADR-0001 §Consequences row 2." in msg


# ---------------------------------------------------------------------------
# AC-14: classifier rules vs. meta-test cases (meta-meta count assertion)
# ---------------------------------------------------------------------------

def test_every_registered_delta_rule_has_meta_test_coverage():
    """
    The classifier registry MUST NOT outgrow the meta-test parametrization.
    If you add a new delta-kind, add a meta-test case in the same PR.
    """
    registered_kinds = set(DELTA_RULE_REGISTRY.all_breaking_kinds())
    covered_kinds = set(_BREAKING_KINDS_COVERED_BY_THIS_FILE)
    missing = registered_kinds - covered_kinds
    assert not missing, f"breaking kinds without meta-test coverage: {sorted(missing)}"


_BREAKING_KINDS_COVERED_BY_THIS_FILE = frozenset(
    {
        "method_renamed", "method_removed", "required_arg_added", "return_type_changed",
        "required_field_added", "model_config_extra_changed", "model_config_frozen_changed",
        "field_type_narrowed", "union_variant_removed", "discriminator_removed",
        "protocol_method_removed", "runtime_checkable_removed",
        "method_signature_changed",
    }
)


# ---------------------------------------------------------------------------
# AC-21/22: registry shape (Strategy + Open/Closed)
# ---------------------------------------------------------------------------

def test_snapshotter_registry_covers_every_snapshot_kind():
    for kind in SnapshotKind:
        assert SNAPSHOTTER_REGISTRY.get(kind) is not None, f"missing snapshotter: {kind}"


def test_classifier_registry_covers_every_snapshot_kind():
    for kind in SnapshotKind:
        assert DELTA_RULE_REGISTRY.has_rule_for(kind), f"missing delta rule: {kind}"
```

#### Main test (AC-1, 5, 6, 7, 26)

```python
# tests/integration/test_phase5_contract_snapshot.py
"""
Phase 5 contract snapshot test (ADR-0001 §Consequences row 2).
FAILURE OF THIS TEST MEANS PHASE 5 CANNOT SHIP.

Additive deltas permitted; breaking deltas (rename, remove, required-add,
signature change, model_config / discriminator / runtime_checkable changes,
field type narrowing) fail CI and require ADR amendment + golden refresh
in the same PR. See ADR-0001 §Consequences row 2.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# Import EVERY named symbol via the canonical re-export path (AC-5/6/7).
from codegenie.transforms import (
    ApplyContext, AttemptSummary, RecipeEngine, RemediationOrchestrator,
    RemediationReport, StageOutcome, Transform, TrustOutcome, TrustScorer,
    TrustSignal,
)

from tests.integration._phase5_contract_helpers import (
    Additive,
    Breaking,
    diff_snapshots,
    format_breaking_delta_message,
    re_export_identity_violations,
    should_update_golden,
    snapshot_symbol,
)

GOLDEN_PATH = Path(__file__).parent.parent / "golden" / "phase5-contract" / "snapshot.json"

SYMBOLS = {
    "RemediationOrchestrator": RemediationOrchestrator,
    "TrustScorer":             TrustScorer,
    "TrustSignal":             TrustSignal,
    "TrustOutcome":            TrustOutcome,
    "StageOutcome":            StageOutcome,
    "Transform":               Transform,
    "ApplyContext":            ApplyContext,
    "AttemptSummary":          AttemptSummary,
    "RecipeEngine":            RecipeEngine,
    "RemediationReport":       RemediationReport,
}


def _build_actual_snapshot() -> dict[str, object]:
    return {n: snapshot_symbol(n, obj) for n, obj in SYMBOLS.items()}


def test_phase5_contract_snapshot_matches_golden(monkeypatch: pytest.MonkeyPatch) -> None:
    # AC-16 — outside update-mode, the test MUST NOT write the golden.
    if not should_update_golden(os.environ):
        _orig_write_text = Path.write_text

        def _no_silent_rewrite(self: Path, *a: object, **kw: object) -> int:
            if self == GOLDEN_PATH:
                pytest.fail(
                    "AC-16 violation: golden was rewritten without "
                    "PHASE5_CONTRACT_UPDATE_GOLDEN=1 set"
                )
            return _orig_write_text(self, *a, **kw)  # type: ignore[arg-type]

        monkeypatch.setattr(Path, "write_text", _no_silent_rewrite)

    actual = _build_actual_snapshot()

    if should_update_golden(os.environ):
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_PATH.write_text(
            json.dumps(actual, indent=2, sort_keys=True, ensure_ascii=True)
        )
        pytest.skip("golden refreshed; rerun without the env var to verify")

    assert GOLDEN_PATH.exists(), (
        f"Golden missing at {GOLDEN_PATH}. "
        "First-run: PHASE5_CONTRACT_UPDATE_GOLDEN=1 pytest <this file>"
    )
    golden = json.loads(GOLDEN_PATH.read_text())
    deltas = diff_snapshots(golden, actual)

    breaking = [d for d in deltas if isinstance(d, Breaking)]
    if breaking:
        msg = "\n\n".join(format_breaking_delta_message(d) for d in breaking)
        pytest.fail(msg)  # AC-19 message already self-contained.

    additive = [d for d in deltas if isinstance(d, Additive)]
    if additive:
        # AC-18 — additive drift is not silently accepted.
        pytest.fail(
            "Additive deltas detected against on-disk golden:\n"
            + "\n".join(f"  - {d.kind} @ {d.symbol}" for d in additive)
            + "\nRerun with PHASE5_CONTRACT_UPDATE_GOLDEN=1 and commit the updated golden."
        )


def test_phase5_named_symbols_re_exported_from_transforms_package() -> None:
    """AC-6 — identity, not just attribute presence."""
    violations = re_export_identity_violations(SYMBOLS)
    assert not violations, "re-export identity check failed:\n" + "\n".join(violations)


def test_phase5_contract_snapshot_is_deterministic() -> None:
    """AC-8 — same source → byte-identical bytes across 10 invocations."""
    canonical = json.dumps(_build_actual_snapshot(), indent=2, sort_keys=True, ensure_ascii=True)
    for _ in range(9):
        again = json.dumps(_build_actual_snapshot(), indent=2, sort_keys=True, ensure_ascii=True)
        assert again == canonical, "snapshot drifted across invocations"


@pytest.mark.skipif(os.environ.get("CI") != "true", reason="CI-strict mode (AC-17)")
def test_ci_ignores_update_golden_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-17 — in CI the env-var opt-in is ignored."""
    monkeypatch.setenv("PHASE5_CONTRACT_UPDATE_GOLDEN", "1")
    monkeypatch.setenv("CI", "true")
    assert should_update_golden(dict(os.environ)) is False
```

Run; confirm `ImportError` (helpers + re-exports + StageOutcome alias) until S5-01..S6-04 land their re-exports, then `AssertionError` (golden absence) on first real run.

### Green — make it pass

- `SnapshotKind = StrEnum("SnapshotKind", "class abc protocol pydantic_model type_alias")` is the single canonical key.
- `@register_snapshot_kind(SnapshotKind.PYDANTIC_MODEL)` decorates a pure function `(name, obj) -> dict[str, Any]` that calls `obj.model_json_schema(mode="serialization")`, canonicalizes nested dict ordering, captures `model_config` keys (`extra`, `frozen`, `populate_by_name`), and records the `discriminator` on any `Annotated[..., Field(discriminator=...)]` field.
- Each snapshotter is registered once at module import; `snapshot_symbol(name, obj)` dispatches via `match _resolve_kind(obj):` with `assert_never` on the wildcard.
- `@register_delta_rule(SnapshotKind.PYDANTIC_MODEL)` decorates a pure `(before_value, after_value, path) -> Iterable[Delta]` rule per category. `diff_snapshots` walks the snapshot tree recursively and dispatches each key/value pair through the registry.
- `format_breaking_delta_message` is a pure `match delta.kind:` block producing the multi-line string asserted by AC-19/20. The string is a single source of truth — there is no logging-side branch.
- First run with `PHASE5_CONTRACT_UPDATE_GOLDEN=1` populates the golden; commit it (AC-4).

### Refactor — clean up

- Extract `should_update_golden(env: Mapping[str, str]) -> bool` so AC-15/17 are testable without `monkeypatch.setenv`.
- Confirm the helpers-purity fence (AC-24) is in `tests/fence/` and runs under `make fence`.
- Confirm `make check` invokes the integration test (AC-27); extend the `Makefile` if it does not.
- Move any meta-test fixture-helper duplication into module-private helpers; do NOT extract to `tests/helpers/` (Rule 2 — premature abstraction).
- Verify the `Pydantic` minor-version pin in `pyproject.toml` matches the version recorded in the snapshot metadata (`_pydantic_version`); update if stale (AC-11).

## Files to touch

| Path | Why | Covers AC |
|---|---|---|
| `tests/integration/test_phase5_contract_snapshot.py` | Main snapshot test — re-export imports, golden compare, no-silent-rewrite fence, determinism property, CI-strict mode | 1, 5, 6, 7, 8, 16, 17, 18, 26 |
| `tests/integration/test_phase5_contract_snapshot_meta.py` | Meta-test — every additive + breaking classifier case + directive-message format + meta-meta registry count check | 2, 12, 13, 14, 19, 20, 21, 22 |
| `tests/integration/_phase5_contract_helpers.py` | `SnapshotKind` StrEnum, `Delta` tagged union, registries, `snapshot_symbol`, `diff_snapshots`, `format_breaking_delta_message`, `should_update_golden`, `re_export_identity_violations`, `_DEEP_MODULE_MAP` | 3, 9, 15, 21, 22, 23, 25 |
| `tests/golden/phase5-contract/snapshot.json` | Frozen golden snapshot — first generated by `PHASE5_CONTRACT_UPDATE_GOLDEN=1`, then committed | 4 |
| `tests/fence/test_phase5_contract_helpers_purity.py` | AST-walk fence — `snapshot_symbol`, `diff_snapshots`, `format_breaking_delta_message` are pure | 24, 31 |
| `Makefile` (extend if not already wired) | Ensure `make check` invokes `pytest tests/integration/` | 27 |
| `pyproject.toml` (verify pin) | `pydantic == X.Y.*` exact-minor pin; snapshot records `_pydantic_version` | 11 |

## Out of scope

- **Modifying any of the six symbols** — they ship in S6-01..S6-05 and S1-03/S1-04/S5-01/S5-05; this story only freezes them.
- **A snapshot of `EventLog`** — `EventLog` is NOT one of the six ADR-0001 named symbols (Phase 5 does not depend on it directly; it depends on `TrustScorer` which constructor-injects an `EventLog`). The internal events taxonomy is gated by ADR-0005, not ADR-0001.
- **A snapshot of `SubgraphNode` Protocol** — internal to Phase 3's orchestrator (S6-03); Phase 6's LangGraph migration wraps it but that's not Phase 5's concern.
- **Cross-language snapshot (e.g., JSON-schema-of-JSON-schema)** — JSON schemas dumped at `indent=2, sort_keys=True` is enough; no canonicalization library.
- **Per-platform snapshot variations** — the test runs on Linux + macOS CI; the snapshot must be platform-independent.
- **Snapshot of recipe registrations** — recipes are open-for-extension; per-plugin registries are out of scope (ADR-0001 contract is the kernel, not the plugins).
- **`remediation-report.yaml` content (not schema) snapshot** — that's golden-file territory under `tests/golden/remediation-reports/`, owned by S8-02.

## Notes for the implementer

### Operational

- **This is the most load-bearing test in Phase 3.** A passing snapshot is necessary-but-not-sufficient for Phase 5; a failing snapshot is *sufficient* to block Phase 5. Treat every CI failure as P0.
- **The additive-vs-breaking classifier is the heart of the story.** False-positive breaking → developers dismiss the test; false-positive additive → Phase 5 silently breaks. The meta-test is the safety net; AC-14's meta-meta count check makes "added classifier rule, forgot the meta-test case" a red test in the same PR.
- **The directive message in the failure output is intentional UX.** A future dev hitting this in CI is confused by default — they touched an unrelated file. The message must answer in one screen: (a) what changed, (b) why it's blocking, (c) the exact resolution procedure. AC-19/20 pin the format; do not log around it (AC-24 forbids it).
- **The golden file lives in the repo, not CI cache.** Committing makes drift visible in PR diffs (`git log -p tests/golden/phase5-contract/snapshot.json`).
- **`PHASE5_CONTRACT_UPDATE_GOLDEN=1` is an env var, not a CLI flag** — pytest's `--update-golden` may collide with other plugins. AC-15 factors the decision into `should_update_golden(env)` so it's testable without monkeypatching `os.environ`.
- **CI-strict mode (AC-17)** prevents accidental in-CI golden regeneration. The env-var path is local-only.
- **First-run setup**: golden absent → test fails with the directive; run `PHASE5_CONTRACT_UPDATE_GOLDEN=1 pytest <file>`, commit golden in same PR, PR description references ADR-0001 + the S6-06 landing.

### Imports + re-export contract (corrected from original)

- **Every named symbol is imported via `from codegenie.transforms import …`** — see AC-5/7. The original draft imported from deep modules (`codegenie.transforms.trust_scorer`, `codegenie.transforms.report`, `codegenie.transforms.apply_context`), which either don't exist (S5-05's Option A co-locates `TrustSignal`/`TrustOutcome` in `outcomes.py`) or violate the test's own re-export-contract AC. The deep-module map for the identity check (AC-6) lives ONLY in `_phase5_contract_helpers.py`, where one centralized declaration is acceptable.
- **`StageOutcome` is the 7th symbol** (per S6-04 validation report C-F2). It is a `TypeAlias = TrustOutcome` declared at S6-02's canonical site and re-exported from `codegenie.transforms.__init__`. The snapshot records both the alias name and the qualified name of its target — renaming the alias OR redirecting the target is a breaking delta. Phase 5 reads the alias name.
- **`TrustSignal` + `TrustOutcome` live in `codegenie.transforms.outcomes`** (S5-05 Option A — single canonical declaration site per ADR-0010 Amendment 2026-05-18). S6-02's `trust_scorer.py` re-exports both; `codegenie.transforms.__init__` re-exports them again. The identity check (AC-6) verifies they are the same class object across all three import paths.
- **The re-export identity check (AC-6) is NOT just `hasattr`** — it asserts `getattr(codegenie.transforms, name) is <deep-module>.<name>`. A duplicate Protocol declaration (`class RecipeEngine(Protocol): ...` re-defined in `transforms/__init__.py`) would pass `hasattr` but break Phase 5's `isinstance(obj, RecipeEngine)` against the deep-imported class. `is` catches it; `hasattr` does not.

### Classifier semantics

- **`extra="forbid"` → `extra="allow"` is BREAKING** (AC-13). Phase 5 tests assume `extra="forbid"`; flipping it changes Pydantic's rejection semantics for unknown fields.
- **`frozen=True` → `frozen=False` is BREAKING** (AC-13). Phase 5's retry envelope uses `model_copy(update=...)` which depends on frozen-instance semantics; flipping breaks the contract.
- **`@runtime_checkable` removal is BREAKING** (AC-13). Phase 5 uses `isinstance(obj, RecipeEngine)` at gate-runner time; removing the decorator turns that into a `TypeError`.
- **Discriminated-union variant additions are ADDITIVE** (per ADR-0001 §Tradeoffs row 5 + Phase 5 ADR-0003). A new `RecipeOutcome` variant from Phase 4 does not break Phase 5; `case _:` fallthroughs handle it.
- **Discriminated-union variant *removal* is BREAKING** — a Phase-5 `match` arm references the variant by name; removing it breaks the arm. AC-14 + meta-test cover.
- **Discriminator removal (`Annotated[..., Field(discriminator="kind")]` → plain `Union`) is BREAKING** (AC-13). Plain `Union` loses static `match` narrowing — Phase 5's `assert_never` exhaustiveness arms regress to runtime errors. ADR-0010 §Decision (3).
- **Required-field type narrowing is BREAKING** (AC-13). Widening `int` → `int | str` is also breaking for consumers using `int`-only operations, but the asymmetry favors consumer safety: narrowing the producer is the harder breakage. The meta-test covers narrowing; widening can be folded in later if it bites.

### Design patterns (the heart of "easy to maintain + extend")

- **Snapshotter is registry-dispatched** (AC-21). The kernel knows nothing about specific kinds. Adding `Enum` snapshot support (likely in Phase 4 for `SignalKind` Literals → real Enum) is one new module-local function + `@register_snapshot_kind(SnapshotKind.ENUM)`. Mirrors `@register_probe` (Phase 0), `@register_index_freshness_check` (Phase 2), `@register_dep_graph_strategy` (Phase 3). CLAUDE.md §"Open/Closed seams".
- **Classifier is registry-dispatched** (AC-22). Same rationale — each delta-rule family is its own module. The seven rule families today (class-method, Pydantic-field, Protocol-method, `model_config`, decorator-presence, discriminator, type-narrowing) put the seam well above the rule-of-three threshold.
- **`Delta` is a tagged union** (AC-25). `Additive` and `Breaking` are `@dataclass(frozen=True)` with a `kind: Literal[...]` discriminator. Every dispatch over `Delta` uses `match` + `assert_never` (ADR-0010 §Decision (3)). The `kind` literal of `Breaking` is the **single canonical name** for the breaking-delta family; meta-test parametrization references the same literal; AC-14's meta-meta count check joins the two.
- **`format_breaking_delta_message` is a `match` over `delta.kind`** — single source of truth for the operator UX. AC-19/20 pin the substrings; a future PR that adds a new breaking kind MUST extend the message dispatch and the meta-test simultaneously.
- **Functional core / imperative shell** (AC-24). The three core helpers are pure; AST-walk fence keeps them that way. Only the main test reads/writes the golden file. CLAUDE.md §"Functional core / imperative shell".
- **Smart-constructor for env-var decision** (AC-15) — `should_update_golden(env: Mapping[str, str]) -> bool` is testable without `monkeypatch`. Pass `os.environ` at the call site; do not read inside the helper.

### Snapshot reproducibility

- **Pydantic-version pin (AC-11)** is load-bearing. A Pydantic minor-version bump that changes `model_json_schema` output (Pydantic does this between minors) silently invalidates the snapshot for the wrong reason — it looks like a Phase 3 contract drift. Recording `_pydantic_version` in the snapshot makes the cause visible. Future contract-snapshot stories (Phase 5 has its own, Phase 6.5 will have one for eval rubrics) MAY copy this pattern.
- **`sort_keys=True` is recursive in stdlib `json`** (verify in the implementer's local docs; codebase precedent: `tests/unit/test_probe_contract.py` uses the same pattern). No third-party canonical-JSON library needed.
- **`model_json_schema(mode="serialization")`** — pick one mode and stick with it. Mixed modes across symbols would create drift between symbols that *should* have identical shape.
- **Cross-platform stability (AC-10)** — never include `os.linesep`, `pathlib.PurePath` repr, or anything else that varies across Linux/macOS. The snapshot must be pure Python primitives.

### What the snapshot does NOT catch (and why that's OK)

- **Behavioural changes within the same signature** — `_validate_stage6` returning `Validated(passed=True)` when it should return `Validated(passed=False)` is a behavioural bug, caught by `tests/unit/transforms/test_orchestrator.py` (S6-04) and `tests/unit/transforms/test_trust_scorer.py` (S6-02), NOT here. The snapshot is structural pinning only — ADR-0011 (honest framing).
- **Docstring drift** — intentionally not snapshotted. Docstrings change for prose reasons; pinning them would generate noise.
- **Type-annotation alias collapse** — `list[int]` vs `List[int]` are equivalent; the snapshotter normalizes via `inspect.formatannotation` or `typing.get_type_hints(include_extras=True)`. Pin the choice in the helper module's module docstring.

### Out-of-scope reminders

- **No snapshot of `EventLog`, `SubgraphNode`, recipe registrations** — see Out of scope below. Adding them is a contract expansion that needs an ADR-0001 amendment.
- **The re-export check is a separate test from the snapshot.** A symbol renamed *only in the re-export* (not in the source module) would pass the snapshot (imported via `codegenie.transforms`) but break Phase 5 consumers using the deep-import path. AC-6's identity check covers both directions.
- **`_validate_stage6` is in the snapshot despite the underscore prefix** (ADR-0001 §Tradeoffs load-bearing-but-private-looking). Renaming → breaking → caught.
- **Meta-test fixtures use locally-defined classes**, NOT modules under `src/codegenie/` — so they can be intentionally broken without affecting real code (same isolation as Phase 0 ADR-0002's per-test registry discipline).
