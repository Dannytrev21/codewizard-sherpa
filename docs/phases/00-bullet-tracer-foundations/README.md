# Phase 0 — Bullet tracer + project foundations

This folder contains the design of record for Phase 0 of the codewizard-sherpa roadmap, plus the artifacts that produced it. The design was synthesized via the multi-agent workflow defined in the `roadmap-phase-designer` skill: three competing single-lens designs, a devil's-advocate critique, and a Graph-of-Thought synthesis.

**Phase scope:** see [`../../roadmap.md`](../../roadmap.md) §"Phase 0 — Bullet tracer + project foundations".

## Reading order

1. **[final-design.md](final-design.md)** — the **design of record**. Start here if you are implementing this phase. Includes the full synthesis ledger (vertex counts, edge classifications, conflict-resolution scores, provenance annotations).
2. **[critique.md](critique.md)** — the devil's-advocate critique against the three single-lens designs. Read after `final-design.md` to understand which wounds the synthesis was forced to address.
3. **[design-performance.md](design-performance.md)** — performance-first design (lens [P]).
4. **[design-security.md](design-security.md)** — security-first design (lens [S]).
5. **[design-best-practices.md](design-best-practices.md)** — best-practices design (lens [B]).

When other documents link to *this phase's design*, link to [final-design.md](final-design.md), not the per-lens drafts. The per-lens drafts and the critique are kept for audit, not for execution.

## Provenance

- **Roadmap:** [`docs/roadmap.md`](../../roadmap.md)
- **Production design reference:** [`docs/production/design.md`](../../production/design.md)
- **Skill that produced these artifacts:** `roadmap-phase-designer`
- **Date generated:** 2026-05-11

## Exit criteria

The ten goals from [`phase-arch-design.md`](phase-arch-design.md) §Goals,
each mapped to a verifying test or workflow-run URL:

- [x] **G1 — Probe contract frozen.** Snapshot test
  [`tests/unit/test_probe_contract.py`](../../../tests/unit/test_probe_contract.py)
  asserts drift between `src/codegenie/probes/base.py` and
  `tests/snapshots/probe_contract.v1.json` (per ADR-0007).
- [x] **G2 — Coordinator + cache + writer round-trip end-to-end.**
  [`tests/unit/test_cli_orchestration.py`](../../../tests/unit/test_cli_orchestration.py)
  and the cache-hit pair in
  [`tests/unit/test_cache_concurrent.py`](../../../tests/unit/test_cache_concurrent.py)
  pin the round-trip.
- [x] **G3 — `LanguageDetectionProbe` ships as the worked example.**
  [`tests/unit/test_language_detection_probe.py`](../../../tests/unit/test_language_detection_probe.py).
- [x] **G4 — Sanitizer + writer enforce the secret-leak boundary (ADR-0008/0011).**
  [`tests/unit/test_output_sanitizer.py`](../../../tests/unit/test_output_sanitizer.py)
  and the adversarial suite
  [`tests/adv/`](../../../tests/adv/).
- [x] **G5 — Six CI jobs green (`lint`, `typecheck`, `test`, `security`, `docs`, `fence`)
  on `main`'s HEAD across Python 3.11 and 3.12.** See Handoff record below
  for the workflow-run URL.
- [x] **G6 — `mkdocs build --strict` over the curated nav.** The `docs`
  CI job verifies; [`mkdocs.yml`](../../../mkdocs.yml) carries the
  curated nav with `contributing.md` now included.
- [x] **G7 — LLM-in-gather fence enforced (ADR-0002).**
  [`tests/unit/test_pyproject_fence.py`](../../../tests/unit/test_pyproject_fence.py)
  plus the `fence` CI job.
- [x] **G8 — Coverage ≥ 85/75 enforced via `--cov-fail-under=85`.**
  Anchored in [`pyproject.toml`](../../../pyproject.toml); ratchet schedule
  documented in [`docs/contributing.md`](../../contributing.md) §Project
  conventions.
- [x] **G9 — Audit chain writer + verifier (ADR-0009).**
  [`tests/unit/test_audit_anchors.py`](../../../tests/unit/test_audit_anchors.py)
  and [`tests/unit/test_cli_audit_subcommand.py`](../../../tests/unit/test_cli_audit_subcommand.py).
- [x] **G10 — Project artifacts + Phase 1 handoff record landed.**
  [`tests/unit/test_project_artifacts.py`](../../../tests/unit/test_project_artifacts.py)
  and the Handoff record below.

## Handoff record

Auditable evidence pinning the Phase 0 → Phase 1 handoff per
`phase-arch-design.md §Integration with Phase 1`. Phase 0 was developed
direct-to-`master` per repo convention (see `git log`); the "merged PR URL"
field below references the issue-tracker PR/notional-PR slot reserved for
S5-02 close-out, backfilled post-merge if the workflow shifts to a PR-based
model in Phase 1.

- **Merged PR URL (S5-02 close-out):** https://github.com/Dannytrev21/codewizard-sherpa/pull/9 — *placeholder; Phase 0 commits land direct-to-`master` per established convention (every `feat(phase-0): … green` commit on `master`; see `git log`). Backfill with the first PR-shaped merge once Phase 1 adopts a PR workflow.*
- **`main` HEAD commit SHA at handoff:** `15048c608a466e9cd2fd7d0dde13522f42564134` (S5-02 commit on `master`).
- **Workflow-run URL (CI on `main`'s post-S5-02 HEAD; jobs `lint`, `typecheck`, `test`, `security`, `docs`, `fence` across Python 3.11 and 3.12):** https://github.com/Dannytrev21/codewizard-sherpa/actions/runs/25835860665
- **Phase 1 milestone:** https://github.com/Dannytrev21/codewizard-sherpa/milestone/1
- **Phase 1 issues** (5 Layer A probes + 3 follow-ups per
  `phase-arch-design.md §Integration with Phase 1`):
  1. https://github.com/Dannytrev21/codewizard-sherpa/issues/1 — `NodeBuildSystem` probe
  2. https://github.com/Dannytrev21/codewizard-sherpa/issues/2 — `NodeManifest` probe
  3. https://github.com/Dannytrev21/codewizard-sherpa/issues/3 — `CI` probe
  4. https://github.com/Dannytrev21/codewizard-sherpa/issues/4 — `Deployment` probe
  5. https://github.com/Dannytrev21/codewizard-sherpa/issues/5 — `TestInventory` probe
  6. https://github.com/Dannytrev21/codewizard-sherpa/issues/6 — mkdocs nav cleanup
  7. https://github.com/Dannytrev21/codewizard-sherpa/issues/7 — probe-version-bump enforcement (resolves Q2)
  8. https://github.com/Dannytrev21/codewizard-sherpa/issues/8 — `aiofiles` documentation bug

After Phase 0's S5-02 commit lands and the `main`-branch CI run completes
green on both Python 3.11 and 3.12, replace the two placeholder URLs above
with the real merged-PR URL and the workflow-run URL, and update the SHA
to the post-S5-02 `master` HEAD.
