# ADR-0008: Output sanitizer is the single path from `ProbeOutput` to disk — two-pass, no synchronous gitleaks

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** security · chokepoint · privacy · provenance
**Related:** [ADR-0010](0010-pydantic-probe-output-validator.md), [production ADR-0006](../../../production/adrs/0006-continuous-deterministic-gather.md)

## Context

Phase 11 commits `.codegenie/` artifacts (including `repo-context.yaml`) into a real repo as part of a PR-opening bundle. That artifact will be reviewed by humans across the org. If it leaks developer home paths (`/Users/dannytrevino/...`), embedded credentials, or secret-shaped fields, the leak compounds across the portfolio.

The security lens proposed a **three-pass** sanitizer: (1) field-name regex, (2) absolute → relative path scrubbing, (3) `gitleaks` synchronous scan. `../critique.md §2.1.2` rejected pass 3: at Phase 2's hundreds-of-KB artifacts and Phase 14's continuous-gather model, `gitleaks` in the synchronous write path becomes a multi-second subprocess on the hot loop — incompatible with [production ADR-0006](../../../production/adrs/0006-continuous-deterministic-gather.md)'s "cheap to run every hour" commitment.

The performance and best-practices lenses had **zero** sanitization — `yaml.CSafeDumper` directly writing to disk. `../critique.md §1.3` and `§3.3` both name this as the load-bearing omission: Phase 11's PR will commit whatever path the writer wrote.

A sanitizer is mandatory; `gitleaks` synchronously is too expensive; the load-bearing defenses must be structural.

## Options considered

- **No sanitizer (`[P]`, `[B]`).** `yaml.CSafeDumper` directly. Fast; leaks paths and any field name the probe happens to emit. Phase 11 commits the leak.
- **Field-name regex only.** Catches obvious secret-shaped fields (`github_token`, `api_key`). Doesn't rewrite paths; doesn't catch values that aren't keys.
- **Three-pass: field-name + path-scrub + synchronous gitleaks (`[S]`).** Belt-and-suspenders-and-belt. Multi-second cost at Phase 2+ scale; breaks the continuous-gather model.
- **Two-pass: field-name + path-scrub; gitleaks at pre-commit and CI but not synchronous (synth).** Structural defenses carry the load: `_ProbeOutputValidator`'s `JSONValue` recursive type + field-name regex ([ADR-0010](0010-pydantic-probe-output-validator.md)) is the first line; path scrubbing is the Phase-11-specific defense; gitleaks runs over `codewizard-sherpa`'s own source at pre-commit time and over the analyzed repo's PR at Phase 11 — belt-and-suspenders at the boundaries where the cost is amortized, not in the gather hot path.

## Decision

**`OutputSanitizer.scrub(output, repo_root) -> SanitizedProbeOutput` is the only path from a `ProbeOutput` to a persisted byte. Two passes in fixed order:**

1. **Field-name regex filter** — defense in depth. `_ProbeOutputValidator` ran the same check in the coordinator before this point; the sanitizer's repeat-pass is the second wall in case a future bug routes around the validator.
2. **Absolute → relative path scrubbing** — any string matching `^(/Users/|/home/|/root/|<analyzed-repo-abs>/)` is rewritten relative to the analyzed-repo root. Load-bearing for Phase 11's PR commits.

**No synchronous `gitleaks` in the write path.** `gitleaks` runs as a pre-commit hook over `codewizard-sherpa`'s source and as a CI step; at Phase 11 it runs over the analyzed repo's PR. The structural defenses (`_ProbeOutputValidator`'s `JSONValue` recursive type, field-name regex, path scrubber) carry the load-bearing weight.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 11's PR commits never leak `/Users/<contributor>/` — the path scrubber is the structural defense | Two passes per `ProbeOutput` instead of three; if a probe's *value* (not field name) contains a credential of a format gitleaks would catch but the field-name regex doesn't, it slips through to commit time |
| The continuous-gather cost model (per [production ADR-0006](../../../production/adrs/0006-continuous-deterministic-gather.md)) holds — Phase 14 webhook fan-out doesn't spawn `gitleaks` subprocesses per gather | gitleaks-shaped attacks (an internal credential format gitleaks knows but the field-name regex doesn't) are caught at PR-time, not gather-time |
| The sanitizer is one chokepoint, one module, one test file — Phase 11 adding new output paths means *extending the chokepoint*, not adding a second writer | Probe authors must trust the sanitizer's path detection; the regex set is enumerated, not heuristic, so unusual mount points (`/mnt/...`) aren't covered until added |
| Defense in depth: the field-name regex runs *twice* — once in `_ProbeOutputValidator`, once in `OutputSanitizer` — closing the bypass-the-validator hole | Two passes of the same check; trivial cost (~ < 1 ms) |
| Writer is `yaml.CSafeDumper` (banned: `yaml.Dumper`, `yaml.load(...)` without `Loader=`); refusal to overwrite a symlink target (exit 5) | `pyyaml`'s C extension must be available; fallback to pure-Python `yaml.SafeDumper` logs a warning |

## Consequences

- `src/codegenie/output/sanitizer.py` is the single import-target for the path. The `Writer.write` method takes a `SanitizedProbeOutput`, not a `ProbeOutput` — typed enforcement that the sanitizer ran.
- Path-scrub regex is `^(/Users/|/home/|/root/|<analyzed-repo-abs>/)`. The `<analyzed-repo-abs>` is the runtime-resolved absolute path; new prefixes (e.g., `/mnt/work/`) require a one-line PR and a test.
- Output files written `0600`; directories `0700` (see [ADR-0011](0011-codegenie-directory-permissions-model.md) for the CI-cache-restore interaction). The permissions model is a separate ADR.
- `gitleaks` is wired at three places **outside the gather hot path**: (a) pre-commit hook on the contributor's machine, (b) `security` CI job over `uv.lock` and `src/`, (c) Phase 11's PR-opening stage over the analyzed-repo PR. None of these are in `codegenie gather`.
- The sanitizer's two-pass contract is a Phase 0 frozen interface — Phase 1+ adds new probe outputs; the sanitizer's *passes* don't change without an ADR amendment.
- `LeakedSecretError` is reserved for a deferred-Phase synchronous-gitleaks call (Phase 11 PR-opening, plausibly Phase 14 for inbound webhook payloads); not raised in Phase 0.

## Reversibility

**Medium.** Adding synchronous `gitleaks` back to the sanitizer is mechanically cheap (one subprocess call, one pre-import of the binary) but reintroduces the cost the synthesis explicitly rejected. The "two-pass" contract is what Phase 11+ assumes; widening to three-pass requires a coordinated update to consumer phases and a CI walltime budget revision. Reversing the *direction* (removing path scrubbing) is breaks-Phase-11 territory and requires both an ADR amendment and a Phase 11 redesign.

## Evidence / sources

- `../final-design.md §2.8` (Output writer + sanitizer)
- `../final-design.md §L3 row 7` (gitleaks-in-write-path: pre-commit+CI wins 12 vs every-gather's 4)
- `../critique.md §2.1.2` (Critic rejects synchronous gitleaks on cost grounds)
- `../critique.md §1.3` / `§3.3` (Critic flags `[P]` / `[B]` lacking any sanitizer)
- `../phase-arch-design.md §Component design / Output writer + sanitizer`
- [production ADR-0006](../../../production/adrs/0006-continuous-deterministic-gather.md) — cost model the synchronous gitleaks rejection serves
- [ADR-0010](0010-pydantic-probe-output-validator.md) — the structural defense the sanitizer is layered on top of
