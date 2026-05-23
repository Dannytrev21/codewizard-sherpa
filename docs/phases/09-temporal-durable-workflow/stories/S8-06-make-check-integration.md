# Story S8-06 — make-check integration + Phase-9 docs publication

**Step:** Step 8 — Durability test pass + adversarial sweep + CI gates
**Status:** Ready
**Effort:** M
**Depends on:** S8-04 (perf canaries + nightly bench infra), S8-05 (no-retry-loop fence), S8-03 (blast-radius adversarial sweep). Implicitly depends on every Phase-9 fence shipped in Steps 1–7: `test_workflow_determinism` (S1-07), `test_activity_payload_typing` (S4-06), `test_temporal_ui_loopback` (S2-01), `test_alembic_revision_lock` (S2-04), `test_alembic_schema_snapshot` (S2-05), `test_no_merge_activity` (S4-07), `test_alembic_owns_only_events_schema` (S2-04), `test_replay_determinism` (S5-05), `test_kill_worker_resume` (S8-01).
**ADRs honored:** P9-ADR-0004, P9-ADR-0007, P9-ADR-0008, P9-ADR-0009, P9-ADR-0015 — every load-bearing ADR's CI gate is wired in. Closes roadmap exit criteria 1, 2, 3 end-to-end via verified phrasing alignment.

## Context

This is the **Phase 9 closeout story.** Everything before it ships a piece (a fence, a test, a workflow class, a projection); this one wires the pieces into the CI fabric so a regression *anywhere* in Phase 9's scope surfaces at PR time, and so the roadmap exit-criteria phrasing actually means something a year from now. The architect named this explicitly: High-level-impl §Step 8 §Done criteria line 236 ("`make check` green end-to-end on a clean clone") + line 241 (roadmap exit-criteria phrasing verified) + line 242 (mkdocs build strict + Phase-9 page published).

Three load-bearing pieces:

1. **`make check` wiring**: every new Phase-9 fence test is reachable from `make check` (transitively via `make test` or via explicit `make fence` / `make lint-imports` targets). This is mostly a verification story — most fences land via `tests/` collection automatically — but each one needs a verification assertion so a future `testpaths` config change doesn't silently drop coverage.
2. **Nightly `make bench`** workflow: the ratchet baselines from S8-04 only matter if the workflow runs reliably. This story confirms the nightly cron is correctly wired, the artifact uploads work, the issue-opener step works, and the four canaries run as a coherent suite.
3. **`docs/development.md` + mkdocs Phase-9 page**: contributors need to know how to run `make dev-up`, troubleshoot Postgres + Temporal setup, override ports for local conflicts, read the perf canary baselines, and understand the durability soak scripts. The Phase-9 page in mkdocs is the public-facing artifact ([dannytrev21.github.io/codewizard-sherpa](https://dannytrev21.github.io/codewizard-sherpa)). `make docs` (which runs `mkdocs build --strict`) must stay green.

The "roadmap exit-criteria phrasing verified end-to-end" line is unusually load-bearing for a closeout story — the architect wanted a literal phrase-match check between the roadmap and the actual CI evidence. AC-7 below ships that as a mechanical test.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy §CI gates` (line 1033) — names every fence wired into `make check`.
  - `../phase-arch-design.md §Testing strategy §Performance canaries` (line 1049) — nightly `-m bench` requirement.
- **Stories that feed this:** every Phase-9 story that adds a CI gate (manifest §Cross-cutting concerns line 226). Read each story's "Files to touch" → if a `tests/fence/test_*.py` is added, this story confirms it runs under `make check`.
- **High-level-impl:** `../High-level-impl.md §Step 8 §Done criteria` lines 236–242; §Exit-criteria mapping table line 254.
- **Existing precedent:** Phase 0–2 docs publication (`docs/contributing.md §Structural defense tests` is the genre).
- **Roadmap exit-criteria source:** `docs/roadmap.md §Phase 9` — verbatim phrasing this story asserts against.

## Goal

Wire every Phase-9 fence + durability test into `make check`; wire every perf canary into nightly `make bench` with ratchet baselines; ship `docs/development.md` + Phase-9 mkdocs page; assert the roadmap's three exit-criteria phrasings hold mechanically end-to-end on a clean clone.

## Acceptance criteria

**`make check` integration (AC-1 through AC-3)**

- [ ] **AC-1** `tests/fence/test_make_check_includes_phase09_fences.py` exists and parses the `Makefile` `check:` target + every transitively-invoked target (`lint`, `lint-imports`, `typecheck`, `test`, `fence`). Asserts each of the following Phase-9 fence test paths is reachable from `make check`:
  - `tests/fence/test_workflow_determinism.py` (S1-07)
  - `tests/fence/test_activity_payload_typing.py` (S4-06)
  - `tests/fence/test_temporal_ui_loopback.py` (S2-01)
  - `tests/fence/test_alembic_revision_lock.py` (S2-04)
  - `tests/fence/test_alembic_schema_snapshot.py` (S2-05)
  - `tests/fence/test_no_merge_activity.py` (S4-07)
  - `tests/fence/test_alembic_owns_only_events_schema.py` (S2-04)
  - `tests/fence/test_no_retry_loops.py` (S8-05)
  - `tests/fence/test_durability_test_not_quarantined.py` (S8-01)
  - `tests/workflows/test_replay_determinism.py` (S5-05)
  - `tests/durability/test_kill_worker_resume.py` (S8-01 — must run in `make test`, not behind `@pytest.mark.e2e`).
  Implementation: reads `Makefile` + the relevant `pyproject.toml [tool.pytest.ini_options]` `testpaths` + `addopts`; constructs the union of paths CI executes; asserts each above path is in the union.
- [ ] **AC-2** Clean-clone validation: a CI workflow step (or a documented `scripts/clean-clone-check.sh`) runs `make dev-up && make check` from a fresh `git clone` checkout. Exits 0. This is the literal verification of High-level-impl §Step 8 §Done criteria line 236. Evidence (CI run URL + duration) recorded in `_attempts/S8-06.md` at GREEN.
- [ ] **AC-3** Failure-mode message clarity: if any Phase-9 fence fails, the failure surface in CI must name the owning ADR + the legitimate alternative path. A meta-test `tests/fence/test_fence_failure_messages_name_adrs.py` parses each fence test file's module docstring + raised assertion messages, asserts a non-empty substring matching `P9-ADR-\d{4}|production ADR-\d{4}|roadmap §Phase 9` is present in each. Discoverability discipline — a regression a year from now should point a contributor at the rationale, not just say "test failed".

**Nightly `make bench` wiring (AC-4)**

- [ ] **AC-4** The `.github/workflows/bench-phase09.yml` from S8-04 is confirmed running on a nightly cron (e.g., `0 7 * * *` UTC). This story:
  - Confirms one successful nightly run has executed end-to-end (artifact uploaded, no canary failed, no issue opened).
  - Adds a `make bench` Makefile target if not already present (S8-04 may have added it; verify no duplicate).
  - Documents the "what to do when a canary fails" workflow in `docs/development.md`: (a) verify machine-fingerprint match (S8-04 AC-6); (b) re-run nightly; (c) if persistent, open a phase-ADR amendment per arch §Gap analysis line 1127 (Gap-1 escape valves); (d) "bump baseline" PR is the last resort, requiring SHA+date+rationale in the JSON.

**Documentation site (AC-5 through AC-6)**

- [ ] **AC-5** `docs/development.md` covers (with code snippets where useful, not just prose):
  - `make dev-up` / `make dev-down` lifecycle; what containers come up; what ports bind (all loopback, per S2-01).
  - Port override: how to set `CODEGENIE_DURABLE_POSTGRES_PORT`, `CODEGENIE_DURABLE_TEMPORAL_PORT`, etc., for local conflicts. Uses S2-02's `DurableSettings` env-prefix.
  - Troubleshooting matrix: container won't start (port conflict, OOM, image pull), `make migrate` fails (Postgres role not ready), Temporal UI not reachable (DNS/loopback confusion).
  - Reading perf canary baselines: where they live (`tests/bench/baselines/`), how `make bench` reads them, what a regression looks like.
  - The durability soak scripts (`scripts/soak-kill-worker-resume.sh` from S8-01); when to run them locally.
  - **No "TODO" sections**: a meta-test `tests/docs/test_no_todo_in_development_doc.py` asserts `"TODO" not in docs/development.md`. A future contributor's half-written "TODO: figure out how X works" surfaces at PR time.
- [ ] **AC-6** mkdocs Phase-9 page exists at `docs/phases/09-temporal-durable-workflow/index.md` (or wherever the mkdocs site config places per-phase landing pages — read `mkdocs.yml`). Page links to: `phase-arch-design.md`, `High-level-impl.md`, the eight Step pages from the stories README, the relevant ADR docs. `make docs` (i.e., `mkdocs build --strict`) exits 0. A meta-test `tests/docs/test_mkdocs_phase09_page_present.py` asserts the page exists and is linked from `mkdocs.yml`.

**Roadmap exit-criteria phrasing verification — load-bearing (AC-7)**

- [ ] **AC-7** `tests/fence/test_phase09_roadmap_exit_criteria_phrasing.py` mechanically asserts the three roadmap exit criteria phrasings are honored end-to-end:
  - **EC-1 "Workflows survive process restarts without state loss"**:
    - Asserts `tests/durability/test_kill_worker_resume.py` exists, has no quarantine markers (delegates to S8-01 AC-1's meta-test), and is reachable from `make check` (delegates to AC-1 above).
    - Asserts `tests/durability/test_temporal_cluster_restart.py` (S8-02) exists.
  - **EC-2 "`temporal-ui` shows live workflow inspection"**:
    - Asserts `tests/fence/test_temporal_ui_loopback.py` (S2-01) exists.
    - Asserts `infra/docker-compose.dev.yml` includes a `temporalio/ui` service binding to `127.0.0.1:8233`.
    - Asserts `make dev-up` documentation references the URL (string match on `127.0.0.1:8233` in `docs/development.md`).
  - **EC-3 "All retries are framework-level — application code contains no retry loops"**:
    - Asserts the four fences from S8-05 are all in place (importlinter contract, forbidden-patterns hook rules, AST walker, known-violation fixture).
    - Asserts `src/codegenie/durable/activities/retry_policies.py` `_POLICIES` table from S4-01 exists with `>= 1` entry.
    - Asserts a live scan of `src/codegenie/durable/workflows/*.py` via S8-05's `_no_retry_fence.scan_workflows_dir` returns `[]`.
  - **Roadmap source-of-truth check**: the test reads `docs/roadmap.md`, locates §Phase 9, asserts each of the three phrasings appears verbatim (whitespace-normalized). A future roadmap edit that changes the phrasing forces a paired update to this test — drift detection.

**Closeout artifact (AC-8 through AC-10)**

- [ ] **AC-8** `_attempts/S8-06.md` ships the **Phase-9 closeout summary** as part of GREEN: every story's final status (`Done` / `BLOCKED-PARTIAL`); every ADR that landed (0001–0015 + any 0016+ from Gap-1 evidence); CI run URLs for the clean-clone validation + the first nightly bench; the per-EC verification evidence from AC-7.
- [ ] **AC-9** `ruff check`, `ruff format --check`, `mypy --strict`, `make lint-imports`, `make fence`, `make docs --strict` all clean. The full `make check` matrix passes on a clean clone.
- [ ] **AC-10** Story Status → `Done` after AC-7 + AC-2 + AC-8 land green. This is the last story of Phase 9 — when it's `Done`, the phase ships.

## Implementation outline

1. Implement `tests/fence/test_make_check_includes_phase09_fences.py` (AC-1):
   - Parse `Makefile` via a simple line-walker (no `make` subprocess — that's CI-fragile); follow target dependencies.
   - Parse `pyproject.toml [tool.pytest.ini_options]` for `testpaths`.
   - Build the union of paths CI runs; assert membership.
2. Implement `tests/fence/test_fence_failure_messages_name_adrs.py` (AC-3):
   - For each Phase-9 fence file, parse its module docstring + assertion strings; assert a regex match for an ADR reference.
3. Confirm `.github/workflows/bench-phase09.yml` (from S8-04) is running nightly; add `make bench` target if missing.
4. Author `docs/development.md` per AC-5 — code snippets, troubleshooting matrix, perf-canary how-to, soak-script how-to.
5. Author `docs/phases/09-temporal-durable-workflow/index.md` (or whichever filename `mkdocs.yml` expects); update `mkdocs.yml nav` to include the Phase-9 page if not already present.
6. Add `tests/docs/test_no_todo_in_development_doc.py` + `tests/docs/test_mkdocs_phase09_page_present.py`.
7. Implement `tests/fence/test_phase09_roadmap_exit_criteria_phrasing.py` (AC-7) — the load-bearing closeout test.
8. Run `scripts/clean-clone-check.sh` (or its CI equivalent) end-to-end; capture URL + duration; record in `_attempts/S8-06.md`.
9. Wait for one nightly `bench-phase09.yml` run to complete green; record URL.
10. Update story Status → `Done`; phase ships.

## TDD plan — red / green / refactor

**Red:** Most of the fences are already wired transitively via `testpaths = ["tests"]` — AC-1's meta-test is mostly green-on-arrival. The load-bearing red is **AC-7's exit-criteria phrasing test**: write it first against the verbatim roadmap phrasings; if the source of truth (`docs/roadmap.md` Phase 9 section) doesn't match exactly, the test is red and the roadmap (or this story's understanding of it) needs reconciling. The doc-presence tests (`test_no_todo_in_development_doc.py`, `test_mkdocs_phase09_page_present.py`) are also red until `docs/development.md` + the index page are written.

**Green:** Write `docs/development.md`; write the index page; update `mkdocs.yml`; run `make docs --strict`; iterate until strict-mode is happy. Run AC-7's test; if any verbatim phrasing fails, reconcile (either rephrase this test, or — if the roadmap phrasing is the load-bearing source — surface the drift via a paired roadmap edit + this story's `_attempts/S8-06.md`).

**Refactor:** Lift the AC-1 path-union builder into `tests/fence/_helpers/make_target_resolver.py` so a future closeout story for Phase 10 / 11 / … can reuse it without re-implementing Makefile parsing. The AC-7 roadmap-phrasing matcher likewise: extract `assert_roadmap_phrase_verbatim(roadmap_md_path, section, phrase)` for reuse.

## Files to touch

| Path | Why |
|---|---|
| `tests/fence/test_make_check_includes_phase09_fences.py` | NEW — AC-1. |
| `tests/fence/test_fence_failure_messages_name_adrs.py` | NEW — AC-3. |
| `tests/fence/test_phase09_roadmap_exit_criteria_phrasing.py` | NEW — AC-7 load-bearing closeout test. |
| `tests/fence/_helpers/__init__.py` | NEW — helper package marker. |
| `tests/fence/_helpers/make_target_resolver.py` | NEW — Makefile parser reused across phases. |
| `tests/docs/__init__.py` | NEW (if missing) — package marker. |
| `tests/docs/test_no_todo_in_development_doc.py` | NEW — AC-5 sub-check. |
| `tests/docs/test_mkdocs_phase09_page_present.py` | NEW — AC-6 sub-check. |
| `docs/development.md` | NEW or EDIT — AC-5 content. |
| `docs/phases/09-temporal-durable-workflow/index.md` | NEW — AC-6 mkdocs landing page. |
| `mkdocs.yml` | EDIT — add Phase-9 page to nav if missing. |
| `Makefile` | EDIT — confirm/add `bench` target. |
| `scripts/clean-clone-check.sh` | NEW or EDIT — wraps `make dev-up && make check` for CI/local clean-clone validation. |

## Out of scope

- **Phase-10+ test wiring** — each future phase ships its own closeout story.
- **Performance baseline retroactive tuning** — S8-04's first-night baselines stand; this story does not rebaseline anything.
- **Production-shape K8s deployment docs** — Phase 16 territory.
- **A `make phase09` umbrella target** — three named subtargets (`make check`, `make bench`, `make docs`) are cleaner than a phase-scoped umbrella; resist.
- **Cross-phase fence consolidation** — each phase's fences stay in their own `tests/fence/*` files; a future Phase 20 cleanup may consolidate naming, but not now.

## Notes for the implementer

- **AC-7 is the test that closes Phase 9.** If you ship every other AC but AC-7 is fragile (regex-matching the roadmap in a brittle way, or matching against a docstring that drifts), the closeout is fake. Read `docs/roadmap.md §Phase 9` first; whatever phrasing is there is the ground truth; this test asserts against it verbatim. If the roadmap phrasing is itself broken (typos, ambiguity), surface a paired roadmap edit in this story's PR — don't paper over it in the test.
- **`make docs --strict`** is non-negotiable. mkdocs strict mode catches broken links, missing pages, dead anchors — the kind of doc rot that turns the published site into a graveyard. The first-time-strict-green for Phase 9 is a meaningful checkpoint; record the SHA in `_attempts/S8-06.md`.
- **Avoid running `make` as a subprocess from a test.** Makefile parsing in Python (line-by-line, follow target deps) is finicky but reproducible. Subprocess `make` is environment-dependent (missing tools, Docker not running) and flakes. AC-1's path-resolver is a pure-Python parser.
- **The "discoverability discipline" of AC-3** (every fence failure message names its ADR) earns its keep two years from now when a contributor stumbles into a fence they didn't write. Without it, "test_workflow_determinism failed" is a puzzle; with it, "test_workflow_determinism failed: see P9-ADR-0004 §Consequences" is a treasure map.
- **Nightly bench (AC-4) needs one successful run before this story is `Done`.** Don't skip this; the workflow is "configured" until it runs once, then it's "working". The first-night run is also the first real-CI-environment perf measurement — surface the numbers in `_attempts/S8-06.md` so future readers see the starting point.
- **`docs/development.md` is contributor-facing copy.** Read it as if you're a new contributor on day one. If a section makes you ask "but what if my port is busy?" or "how do I tell if Postgres is healthy?", that section is incomplete. AC-5's "no TODO" meta-test is the floor, not the ceiling.
- **The clean-clone validation (AC-2) catches the entire class of "works on my machine"** bugs — missing `.env.example` defaults, undocumented apt-get dependencies, Docker daemon assumptions. Run it; record the duration (target ≤ 5 min from clone to `make check` green); if it's longer, surface as a follow-up dev-experience improvement.
- **When this story is `Done`, Phase 9 is done.** The next story will be Phase 10's S1-01. Mark the manifest README's executive-summary line accordingly (or note in `_attempts/S8-06.md` that the manifest now needs a "Phase shipped" line). The discipline of closing the loop matters — a phase that's "mostly shipped" leaks into the next phase's scope.
