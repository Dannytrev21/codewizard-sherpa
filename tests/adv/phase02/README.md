# `tests/adv/phase02/` — Phase 2 adversarial corpus

Adversarial / boundary tests for the Phase 2 ("Layer B–G probes")
work. Each file targets a load-bearing risk the
[`docs/phases/02-context-gather-layers-b-g/phase-arch-design.md`](../../../docs/phases/02-context-gather-layers-b-g/phase-arch-design.md)
"Implementation risks" section calls out. They all run inside the
`adv-phase02` CI job (wired in S8-03) as part of the load-bearing
gate — a failure here blocks merge.

The full set:

| File | Story | Defends |
|---|---|---|
| [`test_stale_scip_fixture.py`](test_stale_scip_fixture.py) | S4-02 | `IndexHealthProbe` + SCIP staleness signal — the single most important probe per the design docs. |
| [`test_adversarial_dockerfile.py`](test_adversarial_dockerfile.py) | S5-06 | Layer C marker / Dockerfile robustness against generated / multi-stage / non-canonical Dockerfiles. |
| [`test_image_digest_drift.py`](test_image_digest_drift.py) | S5-05 | Image-digest resolver + runtime-trace freshness invariants. |
| [`test_secret_in_source.py`](test_secret_in_source.py) | S6-07 | **Behavioural** secret-leak defense — secret in source code is detected by the gitleaks probe and the output is fully redacted (no plaintext lands in `repo-context.yaml`). |
| [`test_hostile_skills_yaml.py`](test_hostile_skills_yaml.py) | S7-04 | `SkillsLoader` resilience against `!!python/object` RCE, deep nesting, alias-chain bombs, malformed frontmatter, non-UTF8 input, schema violations, and symlink escape (`O_NOFOLLOW`). |
| [`test_concurrent_gather_race.py`](test_concurrent_gather_race.py) | S7-04 | Phase-0 `O_APPEND` + atomic-`os.replace` cache contract under two concurrent `codegenie gather` processes (ADR-0009 — no `pytest-xdist`). |
| [`test_no_inmemory_secret_leak.py`](test_no_inmemory_secret_leak.py) | S7-04 | **Structural** redactor invariants: `RedactedSlice` construction restricted to the two documented sites; `Writer.write` accepts only `RedactedSlice`; `Writer.write` called only from the documented CLI seam; `model_construct` banned under `src/codegenie/output/`. |
| [`test_phase3_handoff_smoke.py`](test_phase3_handoff_smoke.py) | S7-04 | Phase-3 adapter-Protocol drift trip-wire — landed **skipped**, unskipped by Phase 3's author at the entry-gate review (`grep -r "enabled when Phase 3 plugin lands" tests/`). |

## Conventions

- **Two-process concurrency uses `subprocess.Popen`**, not
  `pytest-xdist` and not `asyncio.gather` — `O_APPEND` kernel atomicity
  only fires under real OS processes (02-ADR-0009).
- **Hostile fixtures are minimal** (under `fixtures/<test-name>/`).
  Cases that cannot be safely committed to git (symlinks, NUL-byte
  filenames, raw non-UTF8 names) are constructed at test time.
- **No `mock.patch`.** The tests exercise the real production code
  paths — loaders, the `O_APPEND` cache contract, the AST of the
  production tree, the four S1-03 Protocols. Mocks would mask the
  regressions these tests are designed to catch.
- **Structural tests prefer `ast` over `inspect.getsource` regex.**
  An AST walker resolves aliased imports correctly (see
  `test_no_inmemory_secret_leak.py::test_walker_resolves_aliased_imports`).

## When a test fails

Each test's failure message names the file + line of the offending
construct + the relevant ADR. Read the failure first; the fix is
almost always either (a) the named ADR amendment, or (b) reverting
the change that broke the invariant. Adding a `@pytest.mark.flaky`
or `xfail` is **never** the right response — these tests guard
non-negotiable correctness properties.
