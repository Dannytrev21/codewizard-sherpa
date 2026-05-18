# Phase 6 — Best-practices design

## Design principles

1. **Functional core, imperative shell.** Transition reducers stay pure; graph runners do I/O.
2. **Stable contracts at phase boundaries.** Phase 6.5 depends on `VulnRemediationSut`, not on `build_vuln_loop`.
3. **Plugin-local behavior, shared ports.** Graph topology is owned by the vuln-remediation plugin; reusable services stay under `src/codegenie/`.
4. **Illegal states are unrepresentable.** Ledger state, node outcomes, and resume inputs use Pydantic discriminated unions.
5. **Tests mirror the graph.** Unit tests cover reducers and transition tables; integration tests cover kill/resume and HITL interruption.

## Proposed public surface

```python
class VulnRemediationSut(Protocol):
    async def run_case(self, request: VulnRemediationCase) -> VulnRemediationResult: ...
    def digest(self) -> SutDigest: ...
```

`run_case` is the stable harness-facing operation. The default implementation may wrap a LangGraph builder, but that builder is private to Phase 6.

## Why this fits the repo

- Mirrors the decorator/registry patterns already used by probes and task classes.
- Keeps new behavior additive under the narrowed extension-by-addition rule from production ADR-0039.
- Gives Phase 6.5 a real contract to test against before Phase 7 adds a second task class.
