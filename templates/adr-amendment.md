# ADR Amendment PR Template

> **What this is.** The PR-body template referenced by
> `tests/unit/test_probe_contract.py`'s failure messages. The companion
> *issue* form at `.github/ISSUE_TEMPLATE/adr-amendment.md` is a distinct
> artifact (lands in S5-02) and is not consolidated with this PR template.

You are landing this PR because `tests/unit/test_probe_contract.py` flagged
drift between `src/codegenie/probes/base.py` and `docs/localv2.md §4`, or
because you are *intentionally* amending the frozen probe contract.

Per **ADR-0007** the resolution direction is **one-way**: the doc is the
source of truth, code conforms — *never* the inverse.

## Required checklist

- [ ] **(a) Edit `docs/localv2.md §4`** — the *only* place a contract change
      may originate. Pure code-side fixes that re-shape the contract are
      rejected.
- [ ] **(b) Run `python scripts/regen_probe_contract_snapshot.py`** — this
      rewrites `tests/snapshots/probe_contract.v1.json` with the new
      `doc_fingerprint` and `structural_signature`. Re-run after any
      additional §4 edit; the snapshot lives in-repo for auditability.
- [ ] **(c) Update `src/codegenie/probes/base.py`** — only if structural
      drift surfaces (a new field, a renamed method, an MRO change).
      Whitespace-only fingerprint drift does NOT require a `base.py`
      edit.
- [ ] **(d) Commit the regenerated `tests/snapshots/probe_contract.v1.json`**
      alongside the doc + code changes. A snapshot bump without a doc edit
      is a red flag — review explicitly.
- [ ] **(e) Reference ADR-0007 in this PR description** — link to
      `docs/phases/00-bullet-tracer-foundations/ADRs/0007-probe-contract-frozen-snapshot.md`
      §Reversibility. Mention which §4 lines moved and why.

## What NOT to do

- Do not bypass the snapshot test with `@pytest.mark.skip` to ship a
  change "for now." ADR-0007 §Reversibility classifies that as a
  one-line politically-costly action; it directly undermines production
  ADR-0007 (POC-to-service contract preservation).
- Do not blend code-side changes with cosmetic doc edits in the same PR
  unless the doc edit *is* the contract change. Cosmetic doc drift still
  flips the `doc_fingerprint` — review them as deliberate.
- Do not introduce third-party imports into
  `src/codegenie/probes/base.py`. The stdlib-only check
  (`test_base_py_imports_are_stdlib_only`) is part of the contract surface
  (ADR-0007 + ADR-0010).

## Why this loop exists

Without it, `localv2.md §4` and `src/codegenie/probes/base.py` could drift
silently. Every probe in Phases 1–14 inherits the `Probe` ABC; a
transcription error encoded on day one becomes a permanent error inherited
by every probe ever written. Production ADR-0007 commits to preserving
this contract POC-to-service; phase ADR-0007 *enforces* that commitment
with the snapshot you are now amending.
