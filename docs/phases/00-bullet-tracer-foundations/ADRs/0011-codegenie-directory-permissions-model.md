# ADR-0011: `.codegenie/` permissions model — 0700/0600 with post-CI-cache-restore re-chmod

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** security · ci · permissions · cross-platform
**Related:** [ADR-0008](0008-output-sanitizer-two-pass-chokepoint.md)

## Context

The `.codegenie/` directory holds cache blobs, raw probe artifacts, audit run-records, and the canonical `repo-context.yaml`. The security lens proposed `0700` directory mode / `0600` file mode to ensure no other user on the host can read cached secrets or audit records.

`../critique.md §6.4` flags a shared blind spot across all three lens designs: the performance and best-practices lenses both ship `actions/cache` for `.codegenie/cache/` restoration in CI. GitHub Actions runners restore cached files with `umask 0022` — files come back as `0644` and directories as `0755`. The security design's `0700`/`0600` mode-bit assertions would fail in CI under the cache-restore path. None of the three lens designs reconciles the on-disk permission model with the CI cache model.

The collision is structural: same code, two different runtime environments, contradictory mode expectations.

## Options considered

- **`0700`/`0600` everywhere, fail in CI on restore.** Strict mode bits but `actions/cache` integration is broken. Either CI fails on every restore or the mode-check is `if not in_ci`-gated, which means CI silently doesn't enforce the security property at all.
- **`0755`/`0644` everywhere, no enforcement.** Cross-platform but offers no protection on a multi-user dev host. Rejected.
- **Skip `actions/cache` entirely.** Cold caches on every CI run. Walltime budget blowout. Defeats the purpose of having a cache.
- **`0700`/`0600` after every write, with `os.chmod` re-applied post-restore (synth).** Writer always sets target modes; mode-bit-check tests assert post-`gather` state, not post-restore state. The cache restore creates a transient `0755` window but the next write fixes it. Cross-platform safe.

## Decision

**Files in `.codegenie/` are written `0600`; directories `0700`. The Writer re-applies these modes via `os.chmod` after every write, including the post-`actions/cache`-restore path.** Mode-bit-check tests assert post-`gather` permissions, not post-cache-restore permissions. The `~/.codegenie/.tool-cache.json` (and `~/.codegenie/.cache-key` if introduced in Phase 14) follows the same `0600` policy.

## Tradeoffs

| Gain | Cost |
|---|---|
| `.codegenie/` cache and audit records have process-owner-only readability on multi-user dev hosts | Transient `0755`/`0644` window exists between `actions/cache` restore and the first write — sub-second on CI but real |
| `actions/cache` integration works — CI cache restore is supported without abandoning the perm model | The "re-chmod after every write" discipline must live in the Writer; one missed call leaks back to default umask |
| Tests assert the right invariant — "after `codegenie gather` finishes, all files in `.codegenie/` are 0600" — not "files were 0600 between restore and first write" | The test surface must include the post-gather mode assertion as a separate gate from the during-gather assertion |
| Cross-platform: macOS and Linux behave identically; Windows file mode bits are advisory but the call is idempotent | No defense against an attacker who can read the disk in the transient window — out of scope per the Phase 0 threat model |
| Phase 14's webhook-driven gather inherits the model — same re-chmod after every write | The transient window grows in webhook-driven gather if many gathers race; addressed in Phase 14 with explicit per-gather subdirectories |

## Consequences

- `src/codegenie/output/writer.py` calls `os.chmod` on every file and directory it creates, after the atomic `os.replace`. The chmod call is idempotent.
- The `CacheStore` shares the convention — `0700` on `.codegenie/cache/` directory + sharded blob dirs; `0600` on every blob file and on `index.jsonl`.
- The `AuditWriter` writes `runs/<utc-iso>-<short>.json` at `0600`.
- The `.gitignore` mutation routine ([ADR-0006](0006-pyproject-toml-extras-shape.md)) doesn't fall under `.codegenie/` — it touches the analyzed repo's `.gitignore`, which keeps its existing mode.
- Mode-bit-check unit tests in `tests/unit/test_output_writer.py` assert: after a `gather`, every file under `.codegenie/` is `0600`; every directory is `0700`. The tests do NOT assert state during a gather or immediately after a `actions/cache` restore.
- A `weekly-drift` job could spot a transient-window issue (the cache restore creates `0755`, but if no write follows, the next `gather` would catch it). Not a current concern.
- Documentation in `docs/contributing.md` notes the model so contributors don't `chmod -R 644 .codegenie/` "to fix permissions."

## Reversibility

**Low.** The chmod-after-write discipline is mechanically a few lines spread across the Writer, CacheStore, AuditWriter. Removing it would create a security regression on multi-user dev hosts but no functional break. Reversing the mode targets (e.g., to `0644`/`0755`) is configurable, but the security-by-default direction has been chosen explicitly. Tests gate the invariant.

## Evidence / sources

- `../final-design.md §2.7` (Cache layer permissions)
- `../final-design.md §2.8` (Writer re-applies modes post-restore)
- `../final-design.md §L4 row 4` (Shared blind spot resolution: permissions under CI cache restore)
- `../critique.md §6.4` (Shared blind spot — umask collision)
- `../phase-arch-design.md §Physical view` (Dev / CI runner mode-bit difference)
- `../phase-arch-design.md §Edge cases` (Edge case #6 — cache restore mode mismatch)
