# Validation report: S3-05 — `cassettes.lock` BLAKE3 manifest + CI scanner

**Validated:** 2026-05-21 19:38 EDT
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S3-05 owns ADR-0014's second and third cassette-discipline layers: a CI scanner that
fails on any sanitizer violation and a per-cassette BLAKE3 lock file that Phase 6.5 can
use as a replay-identity contract. The story's goal is sound, but the draft still assumed
S3-02 had already produced two live cassette YAML files. That contradicts S3-02's
validated handoff, which deliberately deferred live cassette bytes until after the
sanitizer, scanner, manifest, and refresh workflow exist. The story is now hardened for
the correct order: S3-05 can land with an empty initial lock, then S3-06/operator refresh
records real cassettes through the discipline stack.

Other hardening focused on executor traps: the actual hashing chokepoint is
`codegenie.hashing.content_hash(path) -> "blake3:<hex>"`, not a nonexistent
`codegenie.hashing.blake3`; a Pydantic `BaseModel` is not directly raiseable, so the
lockfile parser now specifies a frozen detail model plus a thin exception wrapper; scanner
tests must aggregate all findings rather than fail on the first cassette; and future
workflow obligations (`make refresh-cassettes`, CODEOWNERS, runbook) remain S3-06 rather
than leaking into S3-05's acceptance criteria.

## Context brief

### Story snapshot

- **Goal:** Ship `tests/cassettes/anthropic/cassettes.lock`, `tests/security/test_cassettes_clean.py`, lock drift/orphan/stale checks, and dirty fixtures proving scanner failures.
- **Non-goals:** `make refresh-cassettes`, CODEOWNERS, runbook, nightly drift job, and live cassette recording.

### Phase / arch constraints

- `phase-arch-design.md` G11 requires `tests/security/test_cassettes_clean.py` and `tests/cassettes/anthropic/cassettes.lock`.
- `phase-arch-design.md` stable contracts list the `cassettes.lock` line format for later snapshotting.
- ADR-0014 requires layered cassette discipline: sanitize at record, CI scanner, CODEOWNERS, content-addressed manifest, nightly drift job, operator refresh.
- S3-04 validated `verify_cassette(path) -> CassetteVerification` as total over the filesystem and as the scanner's reusable surface.
- S3-02 validated that no live cassette YAML is committed before S3-04/S3-05/S3-06 exist.

### Existing-code reality

- `src/codegenie/hashing.py` exports `content_hash(path) -> "blake3:<64-hex>"`; there is no `codegenie.hashing.blake3`.
- `CodegenieError` subclasses are markers-only, while structured parse failures use frozen Pydantic detail models and sometimes thin exception wrappers (`VulnParseError` + `VulnParseException` precedent).
- `.pre-commit-config.yaml`'s `forbidden-patterns` hook currently scans `*.py` and excludes `tests/`; dirty YAML fixtures are more likely to affect `gitleaks` than `forbidden-patterns`.

### Open ambiguities

None requiring user input. The story-order conflict resolves by following the newer hardened predecessor S3-02 and ADR-0014's layered order: S3-05 supports zero-cassette bootstrap; S3-06/operator workflow records real cassettes later.

## Findings by critic

### Coverage critic

- **COV1 (block)** — The draft depended on "S3-02's two cassettes exist", but S3-02 was hardened to defer live cassette bytes. A literal executor would be forced either to record cassettes too early or fail the lock generation. **Fix:** S3-05 supports an empty initial lock and locks real YAML only if it already exists.
- **COV2 (harden)** — Zero-cassette behavior was undefined. AC-1 required trailing newline with "one line per cassette", which is ambiguous for zero cassettes. **Fix:** empty file is the valid zero-cassette lock; non-empty locks require trailing newline.
- **COV3 (harden)** — Parser coverage omitted missing lockfile, unsafe relpaths, non-hex chars, blank lines, and comments. **Fix:** add `missing_lockfile`, `bad_relpath`, `bad_hex_chars`, and `trailing_garbage` cases.
- **COV4 (harden)** — Scanner ACs/TDD failed on the first cassette, masking additional dirty/drift/orphan/stale entries. **Fix:** aggregate every finding before failing once.
- **COV5 (harden)** — AC-12 asserted future `make refresh-cassettes` behavior even though that target is out of scope. **Fix:** S3-05 owns only the CLI/pre-commit primitive; S3-06 owns the Makefile workflow.
- **COV6 (nit)** — `forbidden-patterns` wording was stale because the current hook does not scan YAML fixtures. **Fix:** document the actual hook posture and handle `gitleaks` separately if it trips.

### Test-Quality critic

- **TQ1 (block)** — The scanner red test used inline assertions inside loops. That lets one failure hide others and does not prove the diagnostic contains every violation. **Fix:** pure collector helpers returning `tuple[str, ...]` plus top-level `pytest.fail("\n".join(findings))`.
- **TQ2 (harden)** — No red tests covered missing lock, malformed lock, drift + orphan + stale in one run, or the empty bootstrap. **Fix:** add helper tests over `tmp_path` for each case.
- **TQ3 (harden)** — The hash-chokepoint rule was prose only. A direct `from blake3 import blake3` implementation would pass digest tests. **Fix:** add source-scan/fence test for `content_hash` use and no direct `blake3` import.
- **TQ4 (harden)** — `--check` mode had no no-write test. **Fix:** CLI test asserts stale lock bytes are unchanged on check failure, write mode updates, second write is idempotent.
- **TQ5 (harden)** — Dirty fixtures are intentionally secret-shaped but the test plan did not verify pre-commit behavior. **Fix:** require a documented/behavioral hook check and a gitleaks negative control if an allowlist is needed.
- **TQ6 (nit)** — `load_lockfile` returning a mutable dict invites accidental mutation in scanner code. **Fix:** return immutable `MappingProxyType`.

### Consistency critic

- **CON1 (block)** — Story dependency line contradicted S3-02's validation notes: S3-02 is cassette-ready only and records no live cassettes. **Fix:** dependency now says S3-02 provides scenario markers; real bytes deferred until S3-06.
- **CON2 (block)** — Existing code reference named `codegenie.hashing.blake3`, which does not exist. **Fix:** reference `content_hash(path).removeprefix("blake3:")`.
- **CON3 (harden)** — "Pydantic error class" plus "raises `LockfileMalformed`" is internally inconsistent if interpreted as raising a `BaseModel`. **Fix:** `LockfileMalformedDetail` Pydantic payload plus `LockfileMalformed(Exception)` wrapper with convenience properties.
- **CON4 (harden)** — AC-12 required behavior for an out-of-scope S3-06 Makefile target. **Fix:** AC-12 now pins the CLI message S3-06 will call.
- **CON5 (nit)** — Files-to-touch said the lock is generated from S3-02 cassettes. **Fix:** row now permits empty initial lock.

### Design-Patterns critic

- **DP1 (harden)** — The scanner shape was pure-impure tangled: loop, collect, and fail all inline. **Fix:** functional core (`_collect_*_findings`) with a thin pytest shell.
- **DP2 (harden)** — Unsafe relpaths in the lock file make illegal states representable and can make stale checks resolve outside the cassette directory. **Fix:** reject bad relpaths at parse time.
- **DP3 (harden)** — Lockfile view should be immutable once parsed. **Fix:** public `load_lockfile` returns `MappingProxyType`.
- **DP4 (harden)** — Hashing must remain behind the Phase-0 chokepoint; this is an adapter-pattern issue around a crypto dependency. **Fix:** mandate `content_hash` and source-scan against direct imports.
- **DP5 (nit)** — No registry/factory is needed for one cassette vendor. Keep the path `tests/cassettes/anthropic/` explicit; future vendors can add sibling directories behind the same helper shape.

## Research briefs

None. All findings resolved from repository context and existing phase documents; no external research was needed.

## Conflict resolutions

- **Empty lock vs "one line per cassette".** Consistency with S3-02 and ADR-0014's layering wins. An empty file is the only sane initial lock when no cassette YAML exists yet; non-empty locks keep the stable two-space line format.
- **Pydantic detail vs exception class.** The repo's structured-error precedent wins over the draft wording. A frozen Pydantic model carries the typed payload; a thin `Exception` wrapper is raised.
- **Dirty fixture literal vs pre-commit firewall.** Coverage wants a real `sk-ant-` fixture; pre-commit must not be weakened broadly. Resolution: do not add a `forbidden-patterns` carve-out; if `gitleaks` trips, allowlist only the dirty-fixture path and prove an outside negative control still fails.
- **Design-pattern advice vs YAGNI.** No plugin registry for cassette vendors in S3-05. The helper shape is enough; a future second vendor can add a sibling lock directory without editing a registry today.

## Edits applied

1. Header `Status: Ready -> HARDENED`; dependency line corrected to S3-02 scenario markers, not real cassette bytes.
2. Added `Validation notes` block summarizing the story-order, hashing, error-model, scanner-diagnostic, and future-workflow fixes.
3. Context and goal updated to include the zero-cassette bootstrap.
4. Existing-code reference corrected from nonexistent `codegenie.hashing.blake3` to `content_hash(path).removeprefix("blake3:")`.
5. AC-1 hardened for empty file, relpath safety, sorted non-empty lines, trailing newline, and no blank/comment lines.
6. AC-2 hardened for unprefixed digest behavior, immutable lock mappings, empty rebuild output, recursive YAML walk, and no direct BLAKE3 imports.
7. AC-3 rewritten as `LockfileMalformedDetail` + thin `LockfileMalformed(Exception)` wrapper with a closed reason taxonomy.
8. AC-4 expanded to include `--check`, no-write drift behavior, and sanitizer refusal in both modes.
9. AC-5 through AC-8 hardened for aggregate diagnostics and missing/malformed lock reporting.
10. AC-11 rewritten to match the actual `forbidden-patterns` scope and to handle `gitleaks` narrowly if needed.
11. AC-12 demoted from future Makefile workflow to the S3-05 CLI primitive consumed by S3-06.
12. AC-14 updated to document empty lock semantics.
13. Added AC-19 through AC-23 for pure scanner collectors, hash chokepoint fence, bad-relpath rejection, empty bootstrap coverage, and CLI no-write tests.
14. Implementation outline, TDD plan, files-to-touch, out-of-scope, and implementer notes updated accordingly.

## Verdict rationale

**HARDENED.** The story should proceed to executor after these edits. The blockers were real but fixable in place: story-order contradiction with S3-02, nonexistent hashing helper, and a test plan that could hide multiple scanner failures. The hardened story now preserves ADR-0014's layered order, keeps hashing behind the existing chokepoint, makes lockfile parse failures typed, and gives the executor mutation-resistant tests for empty bootstrap, drift, orphan, stale, malformed, and dirty-cassette cases.

## Recommended next step

`phase-story-executor` can implement S3-05 after S3-04 is available. Start with `manifest.py` and its unit tests, then wire the scanner helpers and CLI `--check`. Commit an empty `tests/cassettes/anthropic/cassettes.lock` if no cassette YAML exists yet; do not record live cassettes in this story.
