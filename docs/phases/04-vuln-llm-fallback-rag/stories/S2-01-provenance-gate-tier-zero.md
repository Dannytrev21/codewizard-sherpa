# Story S2-01 — ProvenanceGate as explicit tier-0 short-circuit

**Step:** Step 2 — Ship trust-boundary primitives: ProvenanceGate, FenceWrapper/CanaryGuard/PromptBuilder, LlmInvocationGuard/BudgetToken
**Status:** HARDENED
**Effort:** S
**Depends on:** S1-02 (`PlanProposal` union — supplies `Refused(reason=...)` shape consumers compose against)
**ADRs honored:** ADR-0012 (tier-0 explicit gate, this phase), ADR-0003 (path-scoped fence — module lives under `src/codegenie/fallback/`, this phase), production ADR-0038 (`vuln.provenance` primitive — the seven-variant sum type this gate dispatches over)

## Validation notes

Validated: 2026-05-21
Verdict: HARDENED
Findings addressed: 15 — 4 blocks, 8 hardens, 3 nits. No critic conflict required research.

Changes applied:
- **C1 (block)** — The draft redefined `VulnProvenanceAdapter` and `Provenance` as Phase-4-local string literals. The current codebase already ships the production ADR-0038 primitive at `codegenie.primitives.vuln_provenance`: a Pydantic discriminated union with lower-case `kind` values (`app_direct`, `app_transitive`, `app_vendored`, `base_image`, `runtime_bundled`, `both`, `unknown`) plus an existing `VulnProvenanceAdapter` port. The story now consumes that primitive and forbids local duplicate `Literal[...]` / Protocol definitions in `fallback/provenance_gate.py`.
- **C2 (block)** — The draft used `codegenie.audit.EventLog` and `event_log.emit(...)`. The actual event-sourcing surface is `codegenie.plugins.events.EventLog` with `emit_internal(...)` / `emit_spanning(...)`. `ProvenanceClassified` is now specified as a `WorkflowInternalEvent` variant in `src/codegenie/plugins/events.py`, and tests assert it appears in the discriminator mapping.
- **C3 (block)** — AC-7 depended on `LlmInvocationGuard` from later sibling S2-05 and allowed a skipped test if S2-01 landed first. A story cannot be `Done` with a skipped load-bearing AC. AC-7 now proves the zero-token invariant locally by signature/import fences: `ProvenanceGate.classify` has no `BudgetToken` parameter and `provenance_gate.py` imports no budget, leaf, prompt, RAG, or Anthropic modules. S6-01/S7-06 keep the integration event-absence proof.
- **C4 (block)** — `CveAdvisory` and `RepoContext` are not importable types in the current codebase. The gate now accepts the already-extracted typed provenance query inputs that the existing primitive consumes: `CveId`, `PackageId`, `ImageRef | None`, and `SyftSbom`. S6-01 owns extraction from its advisory/repo context before calling this primitive.
- **H1 (harden)** — Adapter failures now follow the existing primitive's fail-loud contract: catch `ProvenanceError` (including its `AdapterError` subclass) and fold to `Unknown(reason="adapter_error")`; let unrelated programming errors propagate.
- **H2 (harden)** — Table-driven tests now build real `Provenance` variant instances, not strings. This catches field-shape drift and the lower-case discriminator contract.
- **H3 (harden)** — `_APP_LAYER_PROVENANCE_KINDS` now stores lower-case discriminator values and is asserted exactly against `{"app_direct", "app_transitive", "app_vendored", "both"}`.
- **H4 (harden)** — `is_app_layer` is specified as a pure predicate over `provenance.kind`, not object membership in a frozenset of models.
- **H5 (harden)** — Event tests replay the typed log and assert exactly one `ProvenanceClassified` event per classification, including the `adapter_error` field on folded `ProvenanceError`.
- **H6 (harden)** — The TDD plan uses a hand-rolled fake classifier with typed call capture instead of `MagicMock(spec=Protocol)`, because `@runtime_checkable` Protocol checks method names only.
- **H7 (harden)** — Files-to-touch now names `src/codegenie/plugins/events.py` and `tests/unit/plugins/test_events.py`; `src/codegenie/audit.py` was removed.
- **H8 (harden)** — `EventId` generation is called out as an implementation detail with a small helper, not an ambient concern hidden in the test.
- **N1 (nit)** — Notes clarify that the local Phase-4 `ProvenanceClassifier` is a facade over the production primitive, not a second adapter family.
- **N2 (nit)** — Notes preserve the Specification-pattern seam while making the Phase-7 widening path concrete: adjust the lower-case constant and the table fixture.
- **N3 (nit)** — Refactor checklist now includes strict `__all__` exports and no `Any` in the public surface.

Full audit log: docs/phases/04-vuln-llm-fallback-rag/stories/_validation/S2-01-provenance-gate-tier-zero.md

## Context

ADR-0012 lifts production ADR-0038's `vuln.provenance` refuse-mode from "implicit Phase 3 return path" to an **explicit tier-0 step** that runs before any LLM tokens are spent, any RAG record is queried, or any recipe is matched. S2-01 ships the Phase-4 consumer: `ProvenanceGate.classify(...) -> Provenance`, a pure `is_app_layer(provenance) -> bool` predicate, and one typed `ProvenanceClassified` workflow-internal event per classification.

The current codebase already contains the production ADR-0038 provenance primitive under `src/codegenie/primitives/vuln_provenance/`. That is the source of truth for `Provenance`, the seven variant classes, `SyftSbom`, and adapter errors. This story must not fork it under `src/codegenie/fallback/`. The Phase-4 gate is a small facade that consumes a classifier over already-extracted typed inputs (`CveId`, `PackageId`, `ImageRef | None`, `SyftSbom`) and leaves extraction from advisory/repo context to S6-01's `FallbackTier`.

Phase 7 can broaden app-layer handling for distroless/base-image work by amending `_APP_LAYER_PROVENANCE_KINDS` and its exhaustive table. Until that phase amendment, only `app_direct`, `app_transitive`, `app_vendored`, and `both` are actionable by Phase 4; `base_image`, `runtime_bundled`, and `unknown` refuse before spend.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 6 — ProvenanceGate` — public interface, internal structure, performance envelope, failure behavior.
  - `../phase-arch-design.md §Goals — G7` — "zero LLM tokens spent on non-app-layer CVEs" event-absence proof.
  - `../phase-arch-design.md §Scenarios — Scenario 3` — sequence diagram of the gate refuse path.
  - `../phase-arch-design.md §Edge cases row 1` — `Unknown` / base-image glibc-on-Node case.
  - `../phase-arch-design.md §Decision points` row 1 — `ProvenanceGate.classify` is the first decision point.
- **Phase ADRs:**
  - `../ADRs/0012-provenance-gate-explicit-tier-zero.md` — tier-0 commitment; Specification-pattern fit; `_APP_LAYER_PROVENANCE_KINDS` seam; reversibility `Low`.
  - `../ADRs/0003-path-scoped-fence-amendment.md` — `src/codegenie/fallback/` admitted; new module lives inside that path.
- **Production ADRs:**
  - `../../../production/adrs/0038-vulnerability-provenance-attribution.md` — seven-variant `Provenance` primitive and refuse-mode semantics.
- **Source design:**
  - `../final-design.md §Component 6 — ProvenanceGate`.
- **Existing code (read before writing):**
  - `src/codegenie/primitives/vuln_provenance/types.py` — `Provenance` discriminated union; lower-case `kind` values; real variant fields.
  - `src/codegenie/primitives/vuln_provenance/protocols.py` — existing `VulnProvenanceAdapter` Protocol. Do not redefine this name in `fallback/`.
  - `src/codegenie/primitives/vuln_provenance/assembly.py` — `assemble_provenance(cve_id, package_id, image_ref, sbom, ...) -> Provenance`; current dispatch/failure precedent.
  - `src/codegenie/primitives/vuln_provenance/errors.py` — `ProvenanceError` / `AdapterError`; the only failures this gate folds to `Unknown`.
  - `src/codegenie/primitives/vuln_provenance/syft_reader.py` — `SyftSbom` test fixture can be `SyftSbom()`.
  - `src/codegenie/plugins/events.py` — actual `EventLog` API, `WorkflowInternalEvent` union, and `emit_internal(...)` convention.
  - `tests/unit/plugins/test_events.py` — adjacent event-union tests and `EventLog.replay()` assertion style.
  - `tests/unit/primitives/vuln_provenance/test_assembly.py` — variant fixtures and typed provenance test idioms.

## Goal

Ship `src/codegenie/fallback/provenance_gate.py` with `ProvenanceGate.classify(cve_id, package_id, image_ref, sbom) -> Provenance` plus `is_app_layer(provenance) -> bool` over `_APP_LAYER_PROVENANCE_KINDS = frozenset({"app_direct", "app_transitive", "app_vendored", "both"})`, table-driven coverage over all seven real `Provenance` variants, and a typed `ProvenanceClassified` `WorkflowInternalEvent` emitted on every classification. S6-01 can then call this gate first and project any non-app-layer result to `Refused(reason=PROVENANCE_NOT_APP_LAYER)` with zero token-spend surface available.

## Acceptance criteria

- [ ] **AC-1 — Module location & path-scoped fence.** `src/codegenie/fallback/provenance_gate.py` exists. It imports only stdlib plus `codegenie.*` symbols. It imports no `anthropic`, `chromadb`, `fastembed`, `onnxruntime`, `keyring`, `httpx`, `requests`, `openai`, `langchain`, `langgraph`, `transformers`, `torch`, or `sentence_transformers`.
- [ ] **AC-2 — Consume the existing provenance primitive; do not fork it.** `provenance_gate.py` imports `Provenance`, `AppDirect`, `AppTransitive`, `AppVendored`, `BaseImage`, `RuntimeBundled`, `Both`, `Unknown`, `SyftSbom`, and `ProvenanceError` / `AdapterError` from `codegenie.primitives.vuln_provenance`. It does **not** define a local `Provenance = Literal[...]` alias and does **not** define a local `VulnProvenanceAdapter` Protocol. A local `ProvenanceClassifier` Protocol is allowed only as the Phase-4 facade over `assemble_provenance` / plugin wiring:
  `def classify(self, cve_id: CveId, package_id: PackageId, image_ref: ImageRef | None, sbom: SyftSbom) -> Provenance: ...`.
- [ ] **AC-3 — `_APP_LAYER_PROVENANCE_KINDS` is exact and immutable.** `_APP_LAYER_PROVENANCE_KINDS: Final[frozenset[str]] = frozenset({"app_direct", "app_transitive", "app_vendored", "both"})`. A unit test asserts exact equality. Adding `"base_image"` or `"runtime_bundled"` fails loudly.
- [ ] **AC-4 — `is_app_layer(provenance) -> bool` predicate.** Pure function; returns `True` for `AppDirect`, `AppTransitive`, `AppVendored`, and `Both`; returns `False` for `BaseImage`, `RuntimeBundled`, and `Unknown`. The test parametrizes real Pydantic variant instances and asserts against `provenance.kind`, not against strings masquerading as variants.
- [ ] **AC-5 — `ProvenanceClassified` event is a typed internal event.** `src/codegenie/plugins/events.py` defines `ProvenanceClassified` with `model_config = ConfigDict(frozen=True, extra="forbid")`, `event_type: Literal["provenance_classified"] = "provenance_classified"`, `event_id: EventId`, `workflow_id: WorkflowId`, `timestamp: datetime`, `provenance_kind: Literal["app_direct", "app_transitive", "app_vendored", "base_image", "runtime_bundled", "both", "unknown"]`, and `adapter_error: str | None = None`. It is included in `WorkflowInternalEvent` and exported in `__all__`.
- [ ] **AC-6 — `ProvenanceGate.classify` dispatches and emits.** `ProvenanceGate(classifier: ProvenanceClassifier, event_log: EventLog).classify(cve_id, package_id, image_ref, sbom)` delegates exactly once to `classifier.classify(...)`, emits exactly one `ProvenanceClassified(provenance_kind=<result.kind>)` via `event_log.emit_internal(...)`, and returns the same `Provenance` object. A table-driven test covers all seven variants and replays the event log to assert exactly one event.
- [ ] **AC-7 — Adapter-domain failure folds to `Unknown`; programming errors fail loud.** If `classifier.classify(...)` raises `ProvenanceError` (including `AdapterError`), the gate emits `ProvenanceClassified(provenance_kind="unknown", adapter_error=<str>)` and returns `Unknown(reason="adapter_error", details={"error": <str>})`. If the classifier raises an unrelated exception such as `TypeError` or `AssertionError`, the gate does **not** swallow it. Tests cover both paths.
- [ ] **AC-8 — Zero-token / zero-budget invariant at the primitive boundary.** `ProvenanceGate.classify` has no `BudgetToken` parameter and `provenance_gate.py` imports no `codegenie.fallback.budget`, `LlmInvocationGuard`, `BudgetToken`, `LeafLlm`, `PromptBuilder`, `SolvedExampleRetriever`, `rag`, or `leaf` symbols. `tests/fence/test_provenance_gate_zero_spend_boundary.py` AST-walks imports and the method signature. S6-01/S7-06 prove the integration-level event absence; this story proves the primitive cannot spend.
- [ ] **AC-9 — Event-kind registration cannot silently drift.** `tests/unit/plugins/test_events.py` (or a new `tests/fence/test_event_kinds_complete.py` if the suite already has that convention by implementation time) asserts `TypeAdapter(WorkflowInternalEvent).json_schema()["discriminator"]["mapping"]` contains `"provenance_classified"` and that `ProvenanceClassified` constructs with typed payload fields. A typo such as `"provenanceClassified"` or class-not-in-union fails.
- [ ] **AC-10 — Strict typing and lint.** `ruff check`, `ruff format --check`, and `mypy --strict` are clean for `src/codegenie/fallback/provenance_gate.py`, the touched event module, and the new tests. Public signatures contain no `Any`, and no new `# type: ignore` is introduced outside test-only mypy-negative snippets.

## Implementation outline

1. Read `src/codegenie/primitives/vuln_provenance/types.py`, `protocols.py`, `assembly.py`, `errors.py`, `syft_reader.py`, and `src/codegenie/plugins/events.py` before writing. Match current conventions; do not fork the provenance primitive or event log.
2. Create `src/codegenie/fallback/__init__.py` if absent. Export `ProvenanceGate`, `ProvenanceClassifier`, `_APP_LAYER_PROVENANCE_KINDS`, and `is_app_layer`.
3. Create `src/codegenie/fallback/provenance_gate.py`:
   - `from __future__ import annotations`
   - imports: `dataclasses.dataclass`, `typing.Final`, `typing.Protocol`, `typing.runtime_checkable`, `uuid`; `codegenie.primitives.vuln_provenance` types/errors; `codegenie.plugins.events.EventLog`, `ProvenanceClassified`; `codegenie.types.identifiers.{CveId, EventId, ImageRef, PackageId}`.
   - Define `ProvenanceClassifier` as the local facade Protocol with the four already-extracted provenance inputs. This is not a second adapter family; it is the Phase-4 gate's dependency-inverted port.
   - Define `_APP_LAYER_PROVENANCE_KINDS` exactly as AC-3.
   - Define `is_app_layer(provenance: Provenance) -> bool` as `return provenance.kind in _APP_LAYER_PROVENANCE_KINDS`.
   - Define `ProvenanceGate` as `@dataclass(frozen=True, slots=True)` with `classifier: ProvenanceClassifier` and `event_log: EventLog`.
   - Define a private `_new_event_id() -> EventId` helper. Use a simple deterministic-shape ULID-like prefix, for example `EventId("01HPRV" + uuid.uuid4().hex[:20].upper())`; tests need only assert the event exists, not pin the generated id.
   - In `classify`, delegate once, catch only `ProvenanceError` (which includes `AdapterError`), fold to `Unknown(reason="adapter_error", details={"error": str(exc)})`, emit `ProvenanceClassified(event_id=_new_event_id(), workflow_id=self.event_log.workflow_id, provenance_kind=result.kind, adapter_error=...)` through `emit_internal`, then return the result.
4. Add `ProvenanceClassified` to `src/codegenie/plugins/events.py` beside `AdapterDegraded` / `StageOutcome`, include it in `WorkflowInternalEvent`, `_INTERNAL_CLASSES`, and `__all__`. Keep it workflow-internal, not spanning.
5. Write `tests/unit/fallback/test_provenance_gate.py` first. Use hand-rolled typed fakes, not `MagicMock(spec=Protocol)`.
6. Extend `tests/unit/plugins/test_events.py` for `ProvenanceClassified` union membership and construction.
7. Add `tests/fence/test_provenance_gate_zero_spend_boundary.py` for the AST import/signature guard.
8. Run `mypy --strict src/codegenie/fallback/provenance_gate.py src/codegenie/plugins/events.py tests/unit/fallback/test_provenance_gate.py tests/unit/plugins/test_events.py tests/fence/test_provenance_gate_zero_spend_boundary.py`, then `ruff check` and `ruff format --check`.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file path: `tests/unit/fallback/test_provenance_gate.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from codegenie.fallback.provenance_gate import (
    ProvenanceGate,
    _APP_LAYER_PROVENANCE_KINDS,
    is_app_layer,
)
from codegenie.plugins.events import EventLog, ProvenanceClassified
from codegenie.primitives.vuln_provenance import (
    AdapterConfidence,
    AdapterError,
    AppDirect,
    AppTransitive,
    AppVendored,
    BaseImage,
    Both,
    DistroPackage,
    Provenance,
    RuntimeBundled,
    SyftSbom,
    Unknown,
)
from codegenie.types.identifiers import CveId, ImageRef, PackageId, WorkflowId
from codegenie.types.parsers import (
    parse_docker_stage_name,
    parse_image_digest,
    parse_layer_digest,
    parse_runtime_id,
)


def _cve() -> CveId:
    return CveId("CVE-2025-12345")


def _package() -> PackageId:
    return PackageId("lodash@4.17.21")


def _image() -> ImageRef:
    return ImageRef("docker.io/example/app:1.2.3")


def _sbom() -> SyftSbom:
    return SyftSbom()


def _app_direct() -> AppDirect:
    return AppDirect(
        manifest_path=Path("package.json"),
        package=_package(),
        confidence=AdapterConfidence.HIGH,
    )


def _app_transitive() -> AppTransitive:
    pkg = _package()
    return AppTransitive(
        manifest_path=Path("package.json"),
        package=pkg,
        chain=(PackageId("express@5.0.0"), pkg),
        confidence=AdapterConfidence.HIGH,
    )


def _app_vendored() -> AppVendored:
    return AppVendored(
        vendored_path=Path("vendor/lodash"),
        package=_package(),
        confidence=AdapterConfidence.DEGRADED,
    )


def _base_image() -> BaseImage:
    return BaseImage(
        image_digest=parse_image_digest("sha256:" + "a" * 64).unwrap(),
        layer_digest=parse_layer_digest("sha256:" + "b" * 64).unwrap(),
        distro_pkg=DistroPackage(name="openssl", version="3.0.0", distro="alpine"),
        stage=parse_docker_stage_name("runtime").unwrap(),
        confidence=AdapterConfidence.HIGH,
    )


def _runtime_bundled() -> RuntimeBundled:
    return RuntimeBundled(
        runtime=parse_runtime_id("node20").unwrap(),
        bundled_path=Path("lib/node/npm"),
        package=_package(),
        confidence=AdapterConfidence.DEGRADED,
    )


def _both() -> Both:
    return Both(app_record=_app_direct(), base_record=_base_image())


def _unknown() -> Unknown:
    return Unknown(reason="no_adapter_resolved")


_PROVENANCE_CASES: tuple[tuple[Provenance, bool], ...] = (
    (_app_direct(), True),
    (_app_transitive(), True),
    (_app_vendored(), True),
    (_both(), True),
    (_base_image(), False),
    (_runtime_bundled(), False),
    (_unknown(), False),
)


@dataclass
class ReturningClassifier:
    result: Provenance
    calls: list[tuple[CveId, PackageId, ImageRef | None, SyftSbom]] = field(default_factory=list)

    def classify(
        self,
        cve_id: CveId,
        package_id: PackageId,
        image_ref: ImageRef | None,
        sbom: SyftSbom,
    ) -> Provenance:
        self.calls.append((cve_id, package_id, image_ref, sbom))
        return self.result


class FailingClassifier:
    def classify(
        self,
        cve_id: CveId,
        package_id: PackageId,
        image_ref: ImageRef | None,
        sbom: SyftSbom,
    ) -> Provenance:
        raise AdapterError("npm registry timeout")


class BuggyClassifier:
    def classify(
        self,
        cve_id: CveId,
        package_id: PackageId,
        image_ref: ImageRef | None,
        sbom: SyftSbom,
    ) -> Provenance:
        raise TypeError("programming bug")


def _events(log: EventLog) -> list[ProvenanceClassified]:
    return [e for e in log.replay() if isinstance(e, ProvenanceClassified)]


def test_app_layer_kinds_are_exact_lowercase_values() -> None:
    assert _APP_LAYER_PROVENANCE_KINDS == frozenset(
        {"app_direct", "app_transitive", "app_vendored", "both"}
    )


@pytest.mark.parametrize(("provenance", "expected"), _PROVENANCE_CASES)
def test_is_app_layer_table(provenance: Provenance, expected: bool) -> None:
    assert is_app_layer(provenance) is expected


@pytest.mark.parametrize(("provenance", "_expected"), _PROVENANCE_CASES)
def test_classify_delegates_once_and_emits_event(
    tmp_path: Path, provenance: Provenance, _expected: bool
) -> None:
    classifier = ReturningClassifier(provenance)
    log = EventLog(root=tmp_path, workflow_id=WorkflowId("01HWF00000000000000000000"))
    gate = ProvenanceGate(classifier=classifier, event_log=log)

    result = gate.classify(_cve(), _package(), _image(), _sbom())

    assert result == provenance
    assert classifier.calls == [(_cve(), _package(), _image(), _sbom())]
    events = _events(log)
    assert len(events) == 1
    assert events[0].provenance_kind == provenance.kind
    assert events[0].adapter_error is None


def test_adapter_error_returns_unknown_and_emits_structured_event(tmp_path: Path) -> None:
    log = EventLog(root=tmp_path, workflow_id=WorkflowId("01HWF00000000000000000000"))
    gate = ProvenanceGate(classifier=FailingClassifier(), event_log=log)

    result = gate.classify(_cve(), _package(), _image(), _sbom())

    assert isinstance(result, Unknown)
    assert result.reason == "adapter_error"
    assert result.details == {"error": "npm registry timeout"}
    events = _events(log)
    assert len(events) == 1
    assert events[0].provenance_kind == "unknown"
    assert events[0].adapter_error == "npm registry timeout"


def test_non_provenance_exception_is_not_swallowed(tmp_path: Path) -> None:
    log = EventLog(root=tmp_path, workflow_id=WorkflowId("01HWF00000000000000000000"))
    gate = ProvenanceGate(classifier=BuggyClassifier(), event_log=log)

    with pytest.raises(TypeError, match="programming bug"):
        gate.classify(_cve(), _package(), _image(), _sbom())
```

Event-union test extension:

```python
def test_provenance_classified_is_internal_event_variant() -> None:
    from pydantic import TypeAdapter

    from codegenie.plugins.events import ProvenanceClassified, WorkflowInternalEvent
    from codegenie.types.identifiers import EventId, WorkflowId

    schema = TypeAdapter(WorkflowInternalEvent).json_schema()
    assert "provenance_classified" in schema["discriminator"]["mapping"]

    event = ProvenanceClassified(
        event_id=EventId("01HPRV000000000000000000"),
        workflow_id=WorkflowId("01HWF00000000000000000000"),
        timestamp=_now(),
        provenance_kind="base_image",
        adapter_error=None,
    )
    assert event.event_type == "provenance_classified"
```

Fence test sketch:

```python
def test_provenance_gate_classify_signature_has_no_budget_token() -> None:
    import inspect

    from codegenie.fallback.provenance_gate import ProvenanceGate

    sig = inspect.signature(ProvenanceGate.classify)
    assert "token" not in sig.parameters
    assert "budget" not in sig.parameters


def test_provenance_gate_imports_no_spend_surfaces() -> None:
    import ast
    from pathlib import Path

    tree = ast.parse(Path("src/codegenie/fallback/provenance_gate.py").read_text())
    forbidden = {
        "codegenie.fallback.budget",
        "codegenie.fallback.leaf",
        "codegenie.fallback.prompt",
        "codegenie.rag",
        "anthropic",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not any(node.module == f or node.module.startswith(f + ".") for f in forbidden)
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(alias.name == f or alias.name.startswith(f + ".") for f in forbidden)
```

Run; expect `ModuleNotFoundError: codegenie.fallback.provenance_gate` and missing `ProvenanceClassified`.

### Green — make it pass

Implement `provenance_gate.py` and the additive `plugins.events` variant per the outline. Keep the gate thin: no cache, no retry policy, no RAG query, no leaf call, no budget object. It classifies, emits, and returns.

### Refactor — clean up

- Keep `is_app_layer` as one pure expression over `provenance.kind`.
- Keep `ProvenanceClassifier` as a small Protocol facade; do not reintroduce a second `VulnProvenanceAdapter`.
- Export a strict `__all__` from `provenance_gate.py` and update `fallback/__init__.py`.
- Ensure tests use real `Provenance` variants and no `type: ignore`.
- If adding `ProvenanceClassified` makes event variant counts in `tests/unit/plugins/test_events.py` stale, update the expected count and exact set in the same commit.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/fallback/__init__.py` | Export the Phase-4 gate surface. |
| `src/codegenie/fallback/provenance_gate.py` | The gate primitive — `ProvenanceClassifier`, `_APP_LAYER_PROVENANCE_KINDS`, `is_app_layer`, `ProvenanceGate`. |
| `src/codegenie/plugins/events.py` | Add the `ProvenanceClassified` workflow-internal event variant and union registration. |
| `tests/unit/fallback/__init__.py` | Test package init (new if absent). |
| `tests/unit/fallback/test_provenance_gate.py` | Gate behavior, real-variant table, error-folding, event emission. |
| `tests/unit/plugins/test_events.py` | Event-union membership and typed construction for `ProvenanceClassified`. |
| `tests/fence/test_provenance_gate_zero_spend_boundary.py` | AC-8 import/signature fence proving no spend surface is reachable. |

## Out of scope

- Extracting `CveId` / `PackageId` / `ImageRef` / `SyftSbom` from `FallbackTier`'s advisory/repo context — owned by S6-01.
- The real NPM provenance adapter generalization or plugin registration — owned by S7-03 / the production `vuln.provenance` primitive family.
- Wiring into `FallbackTier.run` — owned by S6-01.
- Phase-7 base-image adapters and admitting `base_image` as actionable for distroless migrations — owned by Phase 7 and requires a phase amendment.
- The E2E event-absence test (`tests/integration/test_phase4_provenance_short_circuits.py`) — owned by S7-06.
- Any caching of classification results — not in ADR-0012's contract.

## Notes for the implementer

- **Specification-pattern naming.** `is_app_layer` is the named rule. Do not inline the membership check into `ProvenanceGate.classify`; S6-01 calls the same predicate when projecting `Provenance` to `Refused(PROVENANCE_NOT_APP_LAYER)`.
- **Facade over the production primitive.** `ProvenanceClassifier` is only a Phase-4 facade over `assemble_provenance` / plugin wiring. The actual hexagonal adapter port is already `codegenie.primitives.vuln_provenance.VulnProvenanceAdapter`; do not duplicate that family under `fallback/`.
- **Lower-case discriminator values are the contract.** The class names are `AppDirect`, `BaseImage`, etc.; the discriminating runtime value is `provenance.kind == "app_direct"` / `"base_image"` / etc. Events and `_APP_LAYER_PROVENANCE_KINDS` use the lower-case values.
- **Error discipline.** Only `ProvenanceError` (including `AdapterError`) is folded to `Unknown(reason="adapter_error")`. A raw `TypeError`, `AssertionError`, or `ValueError` from a bad implementation should propagate so the executor fixes the bug instead of masking it as a provenance unknown.
- **Event stream choice.** `ProvenanceClassified` is workflow-internal. It describes one workflow's decision point and is replayed with the workflow. It is not a spanning ledger event.
- **No spend surface.** The gate does not accept or import `BudgetToken`, `LlmInvocationGuard`, `LeafLlm`, `PromptBuilder`, a retriever, or any RAG store. That is the local proof that this step cannot spend tokens; later integration stories prove ordering by event absence.
- **No state beyond collaborators.** `ProvenanceGate` has no fields beyond `classifier` and `event_log`. No counters, no caches, no retry state.
