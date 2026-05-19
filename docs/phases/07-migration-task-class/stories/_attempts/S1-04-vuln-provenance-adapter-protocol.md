# S1-04 attempt log

## 2026-05-19 — Attempt 1 — GREEN

**Implementer:** Claude (Opus 4.7) under scheduled `codewizard-executer` task.

### Outcome
**GREEN** — every AC pinned by a runtime test; gates clean.

### What shipped

- `src/codegenie/primitives/vuln_provenance/errors.py` — marker-only typed
  hierarchy: `ProvenanceError(CodegenieError)` →
  `RegistryError(ProvenanceError)`, `AdapterError(ProvenanceError)`. No
  `__init__`, no `__str__`, no class attributes (AC-11 markers-only fence
  pins this).
- `src/codegenie/primitives/vuln_provenance/protocols.py` —
  `@runtime_checkable class VulnProvenanceAdapter(Protocol)` with exactly
  two methods: `attribute(self, cve_id, package_id, image_ref, sbom) ->
  Provenance` and `confidence(self) -> AdapterConfidence`. `SyftSbom`
  ships as a bare-name forward reference under
  `from __future__ import annotations`; a `TYPE_CHECKING`-guarded
  placeholder class keeps `mypy --strict` clean today. S1-05 will replace
  the placeholder with the real `SyftSbom` import; the AC-6 forward-ref
  test carries the `# TODO(S1-05)` tightening marker.
- `src/codegenie/primitives/vuln_provenance/__init__.py` — re-exports the
  four new public names (`AdapterError`, `ProvenanceError`, `RegistryError`,
  `VulnProvenanceAdapter`); `__all__` extended in ASCII order.
- `tests/unit/primitives/vuln_provenance/test_adapter_protocol_shape.py`
  — 16 tests across AC-1, AC-2, AC-3 (bidirectional), AC-4 sub-clause
  mutual-exclusivity, AC-5 `excinfo.value`-style negative, AC-6
  forward-ref pin, AC-10 Protocol-not-ABC `__mro__` assertion, AC-11
  parametrised markers-only AST walk.
- `tests/unit/primitives/vuln_provenance/test_protocols_module_purity.py`
  — AC-8 widened from `protocols.py` to also cover `errors.py` (allowlist
  `{__future__, codegenie.errors}`). Catches relative-import drift on
  both modules.
- `tests/unit/primitives/vuln_provenance/test_types_dunder_all.py` —
  `_EXPECTED_PUBLIC_ALL` tuple extended with the four new names; sort
  invariant still pinned.

### Red → Green → Refactor

**RED.** First run of the new tests against the un-implemented modules:
`ImportError` / `ModuleNotFoundError` — exactly the expected failure
mode the story names ("missing `protocols.py` + `errors.py` + four
names").

**GREEN.** Created `errors.py` first (markers-only), `protocols.py`
second (verbatim arch shape), extended `__init__.py` third. Re-ran
the suite — 135/135 passed across
`tests/unit/primitives/vuln_provenance/`.

**REFACTOR.** Tightened the `SyftSbom` forward-reference implementation
from a quoted-string annotation (`sbom: "SyftSbom"`) to a bare-name
annotation under `from __future__ import annotations` with a
`TYPE_CHECKING`-guarded placeholder class — keeps the runtime
annotation a clean `"SyftSbom"` string and `mypy --strict` clean today.
Tightened the negative-`ProvenanceError` test to assert via
`excinfo.value` instead of catch-then-re-raise (Rule 9).

### Gates run

| Gate | Result |
|---|---|
| `pytest tests/unit/primitives/vuln_provenance/` (135 tests) | PASS |
| `pytest tests/unit tests/unit/plugins tests/unit/types tests/fence tests/unit/test_pyproject_fence.py` (1162 tests) | PASS |
| `mypy --strict src/codegenie/primitives/vuln_provenance/` | PASS |
| `ruff check` on touched files | PASS |
| `ruff format --check` on touched files | PASS |
| `lint-imports --config pyproject.toml --no-cache` | PASS (4 kept, 0 broken) |

### Out of scope (deferred to later stories)
- `_REGISTRY` dict + `@register_provenance_adapter` decorator — S2-01.
- `AdapterFactory` Protocol + DI vocabulary — S2-02.
- `SyftSbom` Pydantic model — S1-05 (this story carries a forward
  reference + `# TODO(S1-05)` test marker).
- Concrete adapter implementations — S3-02 (npm), S4-02 (alpine),
  S4-03 (distroless).
- Phase 7 LLM-SDK / no-`Any` fence — S1-06.

### Notes on environment-only failures

Five pre-existing failures surfaced when the full `tests/unit
tests/integration` run was attempted; all confirmed unrelated to
S1-04:

1. `tests/unit/test_lint_imports_canary.py` × 2 — fails because
   `lint-imports` is only on `.venv/bin/`, not the shell PATH.
   Environment issue.
2. `tests/integration/portfolio/test_portfolio_sweep.py` — fails
   locally because `scip-typescript` is installed and the
   `--infer-tsconfig` flag creates `tsconfig.json` inside the copied
   fixture tree, surfacing a `tsconfig_path: "tsconfig.json"` live
   value vs. the committed `tsconfig_path: null` golden. CI passes
   because `scip-typescript` is absent there — probe falls back to
   the `confidence: low / freshness: stale` golden values. Pre-existing
   local-only golden drift, not introduced by S1-04.
3. `tests/integration/transforms/test_sandbox_exec_hello_world.py`,
   `test_sandbox_exec_network_policy.py` — `nightly_macos`-marked
   tests that probe `sandbox-exec`; macOS sandbox-exec returncodes
   71/65 in this environment. Pre-existing.

The portfolio fixture drift is a real bug worth tracking
(SCIP probe mutates the canonical fixture tree even though the test
uses `shutil.copytree`) but it is out of scope for S1-04.
