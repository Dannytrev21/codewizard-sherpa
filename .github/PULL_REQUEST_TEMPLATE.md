# Pull request

## Summary

<!-- One paragraph: what this PR changes and why. Link the story / ADR / issue. -->

## How verified

<!-- Concrete: ran `make check`, opened the docs build at /contributing, etc. -->

## ADRs honored

<!-- e.g. ADR-0002 (LLM-in-gather fence), ADR-0007 (probe contract snapshot), ADR-0006 (pyproject extras shape) -->

## Contract-frozen checklist

The set of paths below is governed by `.github/CODEOWNERS` and reviewed
strictly. If your PR touches **any** of them, also link the relevant
ADR amendment issue (template: `.github/ISSUE_TEMPLATE/adr-amendment.md`):

- `src/codegenie/probes/base.py`
- `tests/snapshots/probe_contract.v1.json`
- `tests/unit/test_pyproject_fence.py`
- `localv2.md`
- `docs/production/adrs/`

See [ADR-0007](docs/production/adrs/) for the drift-resolution policy and the
`adr-amendment` issue / PR-template workflow.

## CI matrix

The six required CI jobs (run on `ubuntu-24.04` × Python `3.11` and `3.12`):
`lint`, `typecheck`, `test`, `security`, `docs`, `fence`. All six must be
green on `main`'s HEAD before this PR is mergeable.

## Author checklist

- [ ] I have read `docs/contributing.md` and confirm this PR honors the conventions there (coverage ratchet, `[project.optional-dependencies]` extras shape, probe-version-bump rules).
- [ ] If this PR touches any contract-frozen path above, I have either (a) filed an ADR amendment issue and linked it here, or (b) confirmed the change is mechanically derived from a runtime change documented in an existing accepted ADR.
- [ ] The CI matrix below is green: `lint`, `typecheck`, `test`, `security`, `docs`, `fence` on Python 3.11 and 3.12.
