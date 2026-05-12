# Story S8-03 — Seeded-staleness three fixtures + `--strict` integration + BuildGraph static-vs-resolved

**Step:** Step 8 — Adversarial corpus + integration end-to-end + seeded-staleness + goldens + CI gates + Phase 3 handoff
**Status:** Ready
**Effort:** M
**Depends on:** S8-02
**ADRs honored:** ADR-0007 (`BuildGraphProbe` `--ignore-scripts` + `resolution_status` parity), ADR-0011 (B2 advisory budget + `--strict` exit-code 3 semantics), ADR-0013 (`SCIPIndexProbe` honors `node_modules` if present; this story pre-builds the SCIP for the stale fixture)

## Context

This story pins **roadmap exit criterion #2** — `IndexHealthProbe` surfaces **≥ 3 real staleness cases** in CI, exceeding the roadmap's "at least one" floor. The Phase 2 design (`final-design.md §"Synthesis ledger row 2"`) explicitly raised the bar from one to three to demonstrate B2 catches staleness across multiple independent domains, not just one rigged scenario.

Three committed fixtures, each surfacing `confidence: low` on its own B2 domain:

- `tests/fixtures/stale_scip_repo/` — commit a pre-built `.codegenie/index/scip-index.scip` produced from an **older commit** in the same repo's history; the current `HEAD` is N commits ahead; `IndexHealthProbe` reports `scip.confidence: low`.
- `tests/fixtures/stale_sbom_repo/` — commit a prior `SBOM` JSON (`.codegenie/context/raw/sbom.json`) produced from an **older `Dockerfile`** (base image bumped between SBOM and HEAD); `IndexHealthProbe` reports `sbom.confidence: low`.
- `tests/fixtures/stale_semgrep_rulepack_repo/` — pin the semgrep rule-pack version in `.codegenie/cache/semgrep/` to a **deprecated version** (older than the version in `tools/digests.yaml`); `IndexHealthProbe` reports `semgrep.confidence: low`.

The fixtures are committed **byte-for-byte reproducible** — pre-built SCIP, pre-built SBOM JSON, pinned-deprecated rule-pack version — never regenerated at test time (`High-level-impl.md §"Implementation-level risks"` #7). This story also lands the `--strict` exit-code 3 integration test (one of the three seeded fixtures + `--strict` ⇒ exit 3) and the `BuildGraphProbe` static-vs-resolved parity test (a pnpm-workspace fixture; static `resolution_status` ↔ resolved `resolution_status` must agree on the dependency edges).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Goals"` — exit criterion #2 verbatim: "IndexHealthProbe surfaces ≥ 3 real staleness cases."
  - `../phase-arch-design.md §"Testing strategy" → "Integration tests"` — three of the seven integration tests are this story's surface.
- **Phase ADRs:**
  - `../ADRs/0007-buildgraph-ignore-scripts-and-resolution-status.md` — `resolution_status` enum + static-vs-resolved parity is the contract this story's pnpm-workspace test pins.
  - `../ADRs/0011-index-health-advisory-budget-and-strict-flag.md` — `--strict` exits 3 on any `confidence == "low"`; `--strict-domains` is selective.
- **Source design:**
  - `../final-design.md §"Synthesis ledger row 2"` — "three real staleness cases (SCIP, SBOM, semgrep rule-pack) rather than one."
  - `../final-design.md §"Failure modes & recovery"` — B2 staleness is the canonical honesty-oracle surface.
- **Implementation plan:**
  - `../High-level-impl.md §"Step 8"` — `test_index_health_staleness_seeded.py` + 3 fixtures = roadmap exit criterion #2; `test_strict_flag_fails_on_low_confidence.py`; `test_buildgraph_static_vs_resolved.py`.
  - `../High-level-impl.md §"Implementation-level risks"` #7 — fixtures committed byte-for-byte; do **not** regenerate at test time.
- **Existing code:**
  - `src/codegenie/probes/index_health.py` (S3-01).
  - `src/codegenie/probes/build_graph.py` (S3-02).
  - `src/codegenie/cli.py` `--strict` / `--strict-domains` flags (S3-04).
  - `tests/integration/test_phase2_end_to_end_node.py` (S8-02) — the upstream this story depends on.
- **Style reference:** `../../01-context-gather-layer-a-node/stories/S5-04-fixtures-monorepo-non-node.md` (Phase 1 fixture-creation story pattern).

## Goal

Land three seeded-staleness fixtures + the `test_index_health_staleness_seeded.py` integration test that exercises all three (roadmap exit criterion #2), the `--strict` exit-code-3 integration test, and the `BuildGraphProbe` static-vs-resolved parity test — all CI-gating on `main`.

## Acceptance criteria

- [ ] `tests/fixtures/stale_scip_repo/` exists with: (a) a git history of ≥ 5 commits; (b) `.codegenie/index/scip-index.scip` committed at the repo root, built from commit `HEAD~5`; (c) a top-level `STALE.md` documenting the seeding (which commit produced the SCIP, what the current `HEAD` adds). The fixture is a stripped-down Node.js TS repo (~50 KB total including the `.scip` blob).
- [ ] `tests/fixtures/stale_sbom_repo/` exists with: (a) a `Dockerfile` whose `FROM` line has been bumped between SBOM and HEAD (e.g., `FROM node:18-alpine` previously, `FROM node:20-alpine` now); (b) `.codegenie/context/raw/sbom.json` committed, produced against the prior `FROM` line; (c) a top-level `STALE.md` documenting the seeding (prior base image, current base image, why the SBOM is stale).
- [ ] `tests/fixtures/stale_semgrep_rulepack_repo/` exists with: (a) `.codegenie/cache/semgrep/` populated with per-file findings blobs keyed against a deprecated rule-pack version; (b) the deprecated version is **older than** the version pinned in `src/codegenie/catalogs/tools/digests.yaml` (commit the version mismatch into the fixture via a top-level `STALE.md` documenting both versions); (c) the cache blobs decode cleanly under `msgpack` (the staleness is in the version, not in corruption — corruption is a separate adversarial case in S8-01).
- [ ] `tests/integration/test_index_health_staleness_seeded.py` exists; runs `codegenie gather` against each of the three fixtures; asserts (i) exit 0 on each; (ii) `stale_scip_repo` ⇒ `index_health.scip.confidence == "low"` AND other domains' confidence not low; (iii) `stale_sbom_repo` ⇒ `index_health.sbom.confidence == "low"` AND other domains' confidence not low; (iv) `stale_semgrep_rulepack_repo` ⇒ `index_health.semgrep.confidence == "low"` AND other domains' confidence not low; (v) the docstring opens with `"""Roadmap exit criterion #2: GREEN — IndexHealthProbe surfaces ≥ 3 real staleness cases."""` (PR-body grep contract).
- [ ] `tests/integration/test_strict_flag_fails_on_low_confidence.py` exists; runs gather against `stale_scip_repo/` with **`--strict`**; asserts exit code is **3**; envelope is **still written to disk** before exit (the `--strict` semantics from ADR-0011: write envelope, then exit non-zero); a second run with `--strict-domains cve` (no `cve` low domain) exits **0**; a third run with `--strict-domains scip` exits **3**.
- [ ] `tests/integration/test_buildgraph_static_vs_resolved.py` exists; uses a pnpm-workspace fixture (existing `node_monorepo_turbo` from Phase 1 or a new `tests/fixtures/pnpm_workspace_resolution_parity/`); runs gather twice — once with pnpm **on** `$PATH`, once with pnpm **off** `$PATH` (monkeypatch); asserts (i) on-path run produces `resolution_status: "resolved"`; (ii) off-path run produces `resolution_status: "static_only"`; (iii) the **declared_edges** set in both runs is identical (static parse is the floor); (iv) the **resolved_edges** in the resolved run is a superset of `declared_edges` (resolution adds hoisted/peer-dep edges).
- [ ] All three new integration tests pass on **Python 3.11 and 3.12**.
- [ ] Each fixture's `STALE.md` (a) documents the seeding mechanism, (b) names the precise file that is stale, (c) cites the originating ADR (ADR-0011 for the three staleness fixtures), (d) cites the regeneration recipe if a future PR needs to bump the seeding (e.g., the SCIP binary is regenerated by checking out `HEAD~5` and running `scip-typescript`, then committing). The `STALE.md` is the cited source when a future contributor proposes a fixture refresh.
- [ ] The three fixtures together add ≤ **200 KB** to the repo (the SCIP binary is the largest single file; if it exceeds 100 KB, use a smaller TS source tree to keep the fixture lean).

## Implementation outline

1. **Build the three fixtures.** For each:
   - Create the fixture directory under `tests/fixtures/<name>/`.
   - Initialize a small git repo (`git init`; commit a Node.js TS project with ~5 source files).
   - Apply the seeding:
     - `stale_scip_repo`: at `HEAD~5`, run `scip-typescript index --output .codegenie/index/scip-index.scip`; commit the `.scip` blob; add 5 more commits (each modifying a source file) so the current `HEAD` is materially ahead.
     - `stale_sbom_repo`: at the prior `Dockerfile` revision, run `syft <prior-image-id> -o json > .codegenie/context/raw/sbom.json`; commit the JSON; bump the `FROM` line in `Dockerfile`; commit the bump.
     - `stale_semgrep_rulepack_repo`: write a few `.msgpack` blobs under `.codegenie/cache/semgrep/by-file/` whose internal version field is a deprecated value; commit.
   - Write `STALE.md` for each.
2. **`test_index_health_staleness_seeded.py`:**
   - Parametrize on the three fixtures; each parametrize record carries the expected low-confidence domain.
   - Read `index_health.<domain>.confidence` for each domain; assert the target domain is `low` and the others are not `low`.
   - The docstring is the PR-body grep contract.
3. **`test_strict_flag_fails_on_low_confidence.py`:**
   - Run `codegenie gather --strict tests/fixtures/stale_scip_repo/`; assert exit 3.
   - Assert `<fixture>/.codegenie/context/repo-context.yaml` exists after the failed run (envelope written before non-zero exit per ADR-0011).
   - Run with `--strict-domains cve`; assert exit 0.
   - Run with `--strict-domains scip`; assert exit 3.
4. **`test_buildgraph_static_vs_resolved.py`:**
   - Build (or reuse from Phase 1) a pnpm-workspace fixture with at least 2 packages + at least one hoisted dep.
   - Run gather with pnpm on PATH (verify via `shutil.which("pnpm")`); read `build_graph.resolution_status`; assert `"resolved"`; capture `resolved_edges`.
   - Monkeypatch `$PATH` to remove pnpm (or use a `subprocess` PATH-clearing fixture); run gather; assert `"static_only"`; capture `declared_edges`.
   - Assert `set(declared_edges) <= set(resolved_edges)`.
5. **`pyproject.toml`** — confirm the `slow_integration` marker (if introduced for this test's wall-clock budget) is registered; not strictly required if all three tests stay under 30 s.

## TDD plan — red / green / refactor

### Red — write the failing test first

Start with `test_index_health_staleness_seeded.py` because it pins the roadmap exit criterion most directly.

Path: `tests/integration/test_index_health_staleness_seeded.py`

```python
"""Roadmap exit criterion #2: GREEN — IndexHealthProbe surfaces ≥ 3 real staleness cases."""
from pathlib import Path

import pytest

SEEDED = [
    ("stale_scip_repo", "scip"),
    ("stale_sbom_repo", "sbom"),
    ("stale_semgrep_rulepack_repo", "semgrep"),
]


@pytest.mark.parametrize("fixture_name,low_domain", SEEDED)
def test_seeded_staleness_surfaces_low_confidence(fixture_name, low_domain, tmp_path, run_gather):
    fixture = Path(f"tests/fixtures/{fixture_name}").resolve()
    result = run_gather(fixture, cache_dir=tmp_path / "cache")
    assert result.exit_code == 0

    health = result.context["probes"]["index_health"]
    assert health[low_domain]["confidence"] == "low", (
        f"{fixture_name}: expected {low_domain}.confidence == low, "
        f"got {health[low_domain]['confidence']}"
    )

    for domain, slice_ in health.items():
        if domain == low_domain or not isinstance(slice_, dict):
            continue
        if "confidence" in slice_:
            assert slice_["confidence"] != "low", (
                f"{fixture_name}: unexpected low confidence on {domain}"
            )
```

Path: `tests/integration/test_strict_flag_fails_on_low_confidence.py`

```python
"""ADR-0011 | --strict exits 3 on any low confidence; --strict-domains is selective."""
from pathlib import Path


def test_strict_exits_3_on_seeded_scip(tmp_path, run_gather):
    fixture = Path("tests/fixtures/stale_scip_repo").resolve()
    result = run_gather(fixture, cache_dir=tmp_path / "cache", strict=True)
    assert result.exit_code == 3
    assert (fixture / ".codegenie/context/repo-context.yaml").exists(), (
        "ADR-0011: envelope must be written before non-zero exit"
    )


def test_strict_domains_cve_does_not_fire_on_scip_stale(tmp_path, run_gather):
    fixture = Path("tests/fixtures/stale_scip_repo").resolve()
    result = run_gather(fixture, cache_dir=tmp_path / "cache", strict_domains=["cve"])
    assert result.exit_code == 0


def test_strict_domains_scip_fires(tmp_path, run_gather):
    fixture = Path("tests/fixtures/stale_scip_repo").resolve()
    result = run_gather(fixture, cache_dir=tmp_path / "cache", strict_domains=["scip"])
    assert result.exit_code == 3
```

Path: `tests/integration/test_buildgraph_static_vs_resolved.py`

```python
"""ADR-0007 | declared_edges ⊆ resolved_edges; resolution_status reflects PM presence."""
from pathlib import Path


def test_static_vs_resolved_parity(tmp_path, run_gather, pnpm_on_path, pnpm_off_path):
    fixture = Path("tests/fixtures/pnpm_workspace_resolution_parity").resolve()

    with pnpm_on_path():
        on = run_gather(fixture, cache_dir=tmp_path / "cache_on")
    assert on.context["probes"]["build_graph"]["resolution_status"] == "resolved"
    resolved_edges = set(tuple(e) for e in on.context["probes"]["build_graph"]["resolved_edges"])

    with pnpm_off_path():
        off = run_gather(fixture, cache_dir=tmp_path / "cache_off")
    assert off.context["probes"]["build_graph"]["resolution_status"] == "static_only"
    declared_edges = set(tuple(e) for e in off.context["probes"]["build_graph"]["declared_edges"])

    assert declared_edges <= resolved_edges, "static parse must be a floor for resolved parse"
```

### Green — make it pass

The seeded-staleness test passes when each fixture's pre-committed staleness artifact (SCIP at older commit, SBOM at older Dockerfile, semgrep cache at deprecated rule-pack version) is detected by `IndexHealthProbe`'s per-domain confidence rules (S3-01).

The `--strict` test passes when ADR-0011's exit-code semantics are wired in `cli.py` (S3-04). Verify the envelope is written **before** the non-zero exit — if the CLI exits before the writer flushes, the test red-fails on the `.codegenie/context/repo-context.yaml` existence check, surfacing the bug.

The static-vs-resolved test passes when `BuildGraphProbe`'s two-stage execution (S3-02) honors the `pnpm` PATH presence correctly. A common first-failure mode: the `declared_edges` set in the static run differs from the `resolved_edges` set in the resolved run by a hoisted edge that pnpm adds — that's correct (resolution adds edges); the assertion is `declared_edges <= resolved_edges`, not equality.

### Refactor — clean up

After green:

- Verify each fixture's seeding is **byte-for-byte deterministic** by re-running the test 10× locally; any flake means a probe is re-deriving the staleness signal at runtime rather than reading the committed state. Surface and patch.
- Confirm the `STALE.md` files are written and the regeneration recipes are documented.
- Confirm the fixture total disk footprint ≤ 200 KB (`du -sh tests/fixtures/stale_*`).
- Verify on Python 3.11 and 3.12.
- The `pnpm_on_path` / `pnpm_off_path` fixtures should be parametric and rebuildable across test sessions; do not leave `$PATH` manipulated after the test ends.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/stale_scip_repo/` | New — committed pre-built SCIP at older commit. |
| `tests/fixtures/stale_sbom_repo/` | New — committed pre-built SBOM at older Dockerfile. |
| `tests/fixtures/stale_semgrep_rulepack_repo/` | New — committed pinned-deprecated rule-pack cache blobs. |
| `tests/fixtures/pnpm_workspace_resolution_parity/` | New (or reuse Phase 1 `node_monorepo_turbo`) — pnpm workspace fixture. |
| `tests/integration/test_index_health_staleness_seeded.py` | New — roadmap exit criterion #2. |
| `tests/integration/test_strict_flag_fails_on_low_confidence.py` | New — ADR-0011 exit-code semantics. |
| `tests/integration/test_buildgraph_static_vs_resolved.py` | New — ADR-0007 resolution parity. |
| `tests/conftest.py` (extend) | `pnpm_on_path` / `pnpm_off_path` context-manager fixtures if not already present. |

## Out of scope

- **Adversarial corpus expansion** — handled by **S8-01**.
- **End-to-end + real-OSS integration** — handled by **S8-02** (precedes this story).
- **Per-probe goldens** — handled by **S8-04**.
- **Bench canaries** including B2 budget — handled by **S8-05**.
- **CI workflow wiring** — handled by **S8-06**.
- **Phase 5 runtime-trace seeded-staleness fixture** — explicitly out (`runtime_trace` is deferred per ADR-0002; B2's `runtime_trace` domain reports `status: "not_applicable"`, not `low`).

## Notes for the implementer

- **The three staleness fixtures must be reproducible byte-for-byte (`High-level-impl.md §"Implementation-level risks"` #7).** Commit pre-built artifacts; do **not** regenerate at test time. If the test ever needs to regenerate to pass, the test is broken or the seeding is not reproducible — surface immediately.
- **Roadmap exit criterion #2 says "≥ 1"; Phase 2 ships 3 to demonstrate the signal is real.** Do not drop to 2 or 1 even if a fixture is tricky to seed; the architecture explicitly raised the bar (`final-design.md §"Synthesis ledger row 2"`). If one fixture is genuinely impossible (e.g., the semgrep rule-pack version cannot be programmatically pinned to a deprecated value), surface in the PR body and discuss before shipping with 2.
- **The seeded SCIP must be from the *same repo's* older commit.** If you import a SCIP from a different repo, B2's staleness signal is "wrong content" not "stale" — that's a different failure mode (handled in the adversarial corpus). The staleness is "the index reflects an older state of *this* repo."
- **The `--strict` envelope-before-exit invariant is load-bearing.** A user running gather in CI with `--strict` needs the envelope on disk for the next step (e.g., uploading to a dashboard) even when exit is 3. If the CLI exits before flushing, the test red-fails — keep this assertion.
- **`build_graph.resolved_edges` is a superset, not an equal-set, of `declared_edges`.** Resolution adds hoisted + peer-dep edges that static parsing cannot infer. The assertion is `declared_edges <= resolved_edges`. Do not weaken to equality, and do not strengthen to strict subset (a trivial fixture with no hoisting yields equality, which would red-fail strict subset).
- **`pnpm_off_path` should not break the parent shell.** Use a context manager that snapshots `os.environ["PATH"]`, removes pnpm's directory, yields, then restores. If pnpm is shipped via a wrapper script in `/usr/local/bin/`, the simplest approach is `shutil.which("pnpm")` to find it and then exclude its parent dir from PATH for the test's duration.
- **The `STALE.md` per fixture is the contract.** When a future Phase 3/7 contributor wonders "why does B2 report `low` on this fixture?", the `STALE.md` answers. Without it, the fixture looks like noise. Treat the README as a first-class artifact of the story.
