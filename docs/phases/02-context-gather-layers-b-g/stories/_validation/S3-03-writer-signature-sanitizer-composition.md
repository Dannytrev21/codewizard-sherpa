# Validation report — S3-03 (Writer signature tightening + envelope-level redactor composition + `secrets_redacted_count` log field)

**Story:** [S3-03-writer-signature-sanitizer-composition.md](../S3-03-writer-signature-sanitizer-composition.md)
**Date:** 2026-05-16
**Validator:** phase-story-validator (skill v1.x)
**Verdict:** **HARDENED**

## Summary

The story's intent traces cleanly to 02-ADR-0010 (writer-boundary smart constructor), 02-ADR-0005 (no plaintext persistence), 02-ADR-0008 (no event stream — single structured-log field allowed), and `phase-arch-design.md §"Gap 4"` + §"Logging strategy" + line 768 (merged envelope flows through the redactor). The draft's *prescriptions*, however, referenced phantom Phase-0 surfaces that do not exist on master — six BLOCK-severity inconsistencies. The structural-fix shape from S3-01/S3-02 validations applies: keep the goal, correct the call sites. Sixteen findings closed (six BLOCK, ten harden); five design-pattern notes added.

## Context Brief

**What the story promises:**
1. Writer's public signature narrows from `dict` to `RedactedSlice`; mypy `--strict` catches a raw `dict` at the writer.
2. The sanitizer composition is documented + verified by a mock-spy ordering test.
3. `secrets_redacted_count` is emitted at the writer chokepoint as a single structured-log field on the writer-completion event.

**What the phase's exit criteria demand:**
- G5 (`phase-arch-design.md §"Goals"`): secret findings are redacted at the writer chokepoint; plaintext is in zero persisted files (verified by `test_secret_in_source.py` in S6-07).
- Gap 4: type-level "redactor was called" via `RedactedSlice` smart-constructor at the writer boundary.

**What the arch + ADRs constrain:**
- 02-ADR-0010: writer signature change is a contract-surface shift requiring a coordinated edit across all callers — on master that single caller is `_seam_write_envelope` in `cli.py`.
- 02-ADR-0005: composition is "field-name regex (Phase 0) → `JSONValue` tree walk (Phase 0) → `redact_secrets` (Phase 2). One chokepoint." But `phase-arch-design.md` line 768 clarifies: "**Merged** envelope flows through `OutputSanitizer.scrub` → `SecretRedactor.redact_secrets` → writer." This places the Phase 2 redactor at the **envelope-merge** layer, not inside per-probe `scrub`.
- 02-ADR-0008: a single new structured-log field — not an event stream.

## Source-of-truth verifications (grep against master)

| Reference in draft | Master surface | Verdict |
|---|---|---|
| `write_envelope(slice_: dict[str, JSONValue], ...) -> Path` | `Writer.write(envelope: dict[str, Any], raw_artifacts: list[tuple[str, bytes]], output_dir: Path) -> None` at `src/codegenie/output/writer.py:142` | **PHANTOM** — function name + parameter name + return type all wrong |
| `OutputSanitizer.scrub(slice_: dict[str, JSONValue], probe_name: ProbeId)` | `OutputSanitizer.scrub(output: ProbeOutput, repo_root: Path) -> SanitizedProbeOutput` at `src/codegenie/output/sanitizer.py:158` | **PHANTOM** — per-probe, not envelope-level |
| `_PASSES = [_field_name_regex_pass, _json_value_tree_walk_pass, redact_secrets]` | Actual passes: `_walk_pass1_keys` (key-name **rejection** that raises, not regex-replacement) + `_scrub_container` (absolute-path scrubbing, not a JSONValue depth-walk) | **PHANTOM** — named passes do not exist |
| `event="envelope.written"` "already emitted" by Phase 0 | `grep -rn '_log\.info\|logger\.info' src/codegenie/output/writer.py` returns zero hits | **PHANTOM** — no such event exists |
| `reveal_type(write_envelope.__annotations__["slice_"])` runtime check | `reveal_type` is a mypy directive, not a runtime callable | **INVALID MECHANISM** |
| `redact_secrets(...)`'s `probe_name` parameter at envelope-merge layer | The merged envelope has no single probe; `probe_name` carries the per-finding attribution | **AMBIGUOUS** — needs sentinel convention |

## Critic reports

### Coverage critic — HARDEN

Eight findings (F1–F8 in the story's Validation notes block). Highlights:
- **F1 (AC-2 mypy invocation under-specified):** original "subprocess `mypy --strict`" was too loose. Mirror S1-11 AC-2 hardening: pin `python -m mypy --strict <fixture_path>`, pin both substrings (`"incompatible type"` AND `'expected "RedactedSlice"'`), add a positive-control fixture (AC-2b) so the harness itself is verified.
- **F5 (unit-vs-integration conflation in AC-9/AC-10):** original "gather a fixture repo" implies full pipeline, but this story is unit-level. Rewrote to construct `RedactedSlice` directly via `redact_secrets({}, ProbeId("__envelope__"))` and call `Writer.write` with `capture_logs()`.
- **F8 (cross-story integration with S3-01 + S3-02 unasserted):** added AC-15 parametrized over the four canonical shapes (zero / one / three-distinct / same-fingerprint-twice), mirrors S3-02 AC-15b.

### Test-quality critic — HARDEN

Mutation table for plausibly-wrong implementations that would have slipped past the original TDD plan:

| Plausibly-wrong implementation | Original TDD plan catches it? | After hardening |
|---|---|---|
| `Writer.write` accepts both `dict` and `RedactedSlice` (no `isinstance` guard; `mypy` ignored) | ❌ No (AC-3 says "passing raw dict raises TypeError" but doesn't pin mechanism) | ✅ AC-3 + AC-3b (source-level regex + runtime `TypeError`) |
| Inline composition (no `_PASSES` indirection) | ❌ No (mock-spy can't intercept direct calls in same module) | ✅ AC-5 pins `_PASSES` tuple + mock-spy via `record: list[str]` |
| Threading `SecretFinding` data into the envelope (so YAML carries fingerprints + pattern_class) | ❌ No (AC-12 says "no findings persist" without verifying mechanism) | ✅ AC-12 substring-asserts against `"pattern_class"`, `"cleartext_len"` in the YAML bytes |
| Log emission using string literals instead of named constants (typo on second emission silently breaks downstream grep) | ❌ No (AC-8 says "no string literal" without pinning a regex check) | ✅ AC-8 source-level regex check against both literals |

### Consistency critic — BLOCK (six findings, all resolved)

Six BLOCK findings (B1–B6 in the story's Validation notes). Highlights:
- **B1:** `write_envelope` does not exist; the surface is `Writer.write` (method on `class Writer`).
- **B2:** Composition site is wrong; `OutputSanitizer.scrub` is per-probe, and the named passes don't match master. The arch doc line 768 places the redactor at the **envelope-merge layer**, post-merge / pre-validate.
- **B3:** `event="envelope.written"` does not exist on Phase 0; this story introduces the event.
- **B4:** `reveal_type(...)` is a mypy directive, not a runtime callable — AC-1 mechanism is invalid as written; corrected to `typing.get_type_hints(...)["envelope"] is RedactedSlice`.
- **B5:** AC-13's "verify against the actual snapshot file at implementation time" can't be statically validated. Added a programmatic enumeration recipe.
- **B6:** `redact_secrets`'s `probe_name` parameter has no envelope-level meaning. Sentinel convention introduced: `ProbeId("__envelope__")`.

### Design-pattern critic — five notes (DP1–DP5)

- **DP1 — `_PASSES` registry: rule-of-three reached but stays a literal tuple.** Promote to `@register_sanitizer_pass` decorator when the fourth *content* pass arrives in Phase 4+ (RAG-scrubber, per-task-class redactor). Today's literal tuple is correct per Rule 2.
- **DP2 — `SanitizerPass` Protocol.** Recommended for the three pass members, with a sibling Protocol for the closure pass (different return type). Makes DP1 promotion mechanical.
- **DP3 — `Fingerprint` newtype rule-of-three reached at S3-03 (third consumer).** Deferred to S8-02 (CLI summary, fourth consumer) so the cross-cutting refactor lands concurrently — Rule 3 "surgical changes" favors one-PR-for-four-consumers over now-plus-one-rewrite.
- **DP4 — Pure module discipline.** `envelope_redactor.py` is pure (no I/O, no logging); the seam in `cli.py` is the imperative shell. Mirrors S3-02's DP3 for `redacted_slice.py`.
- **DP5 — Smart-constructor + chokepoint ladder closed at three rungs.** S3-01 (runtime) → S3-02 (type-system) → S3-03 (chokepoint) → S7-04 (source-level). Document the four-rung ladder in module docstring + PR description.

## Stage 3 research

**Skipped.** No `NEEDS RESEARCH` findings. Every gap was answerable from:
- arch design (`phase-arch-design.md §"Gap 4"`, §"Logging strategy" line ~783, line 768 envelope-merge clarification);
- ADRs 02-ADR-0005, 02-ADR-0008, 02-ADR-0010;
- verified live source (`src/codegenie/output/writer.py:142`, `src/codegenie/output/sanitizer.py:158`, `src/codegenie/cli.py:344`, `src/codegenie/cli.py:308`);
- S3-01 and S3-02 sibling validation precedent (mypy contract, hypothesis property tests, cross-story integration shape).

## Edits applied

Sixteen content-changing edits to the story:

| AC | Original | After hardening |
|---|---|---|
| Story header | `Writer signature tightening + sanitizer composition + ...` | `Writer signature tightening + envelope-level redactor composition + ...` |
| Goal | Three goals around `write_envelope` + `OutputSanitizer.scrub` composition | Five goals around `Writer.write` + `_seam_write_envelope` + `envelope_redactor.py` + two log constants + mypy fixture pair |
| References | Mostly correct doc references, wrong source-code references | Verified source-code references with line numbers; explicit phantom-surface negation |
| AC-1 | `reveal_type` + `write_envelope.__annotations__["slice_"]` | `typing.get_type_hints(Writer.write)["envelope"] is RedactedSlice` AND lock-step seam check |
| AC-2 | "runs mypy --strict ... contains `incompatible type` and `expected RedactedSlice`" | Pinned subprocess invocation; `python -m mypy --strict <fixture>`; AND substring contract; explicit fixture path |
| AC-2b (new) | — | Positive control: clean fixture passes mypy with exit 0 |
| AC-3 | "raises TypeError (or whatever the chosen runtime-rejection mechanism produces)" | First executable statement is `isinstance` guard; message contains `RedactedSlice` AND `02-ADR-0010` |
| AC-3b (new) | — | Source-level regex check via `inspect.getsource` for the `isinstance` guard |
| AC-4 | Docstring at `sanitizer.py` documenting composition `[field_name_regex, json_value_tree_walk, redact_secrets]` | Docstring at NEW `envelope_redactor.py` documenting `[known_patterns, entropy, build]`; assertion via `inspect.getdoc` substring matches over four references |
| AC-5 | Mock-spy with `time.monotonic_ns()` against `_PASSES` (in `sanitizer.py`) | Mock-spy with shared `record: list[str]` against `envelope_redactor._PASSES`; canonical order `["known_patterns", "entropy", "build"]` |
| AC-6 | "Mutation test asserts the non-mutated order is still verified ... under the mutation, the assertion fails" (confused) | Two paired tests: mutation changes recorded order; canonical preserves it |
| AC-7 | "scrub return type is RedactedSlice; writer call-site accepts directly" | `_redact_envelope` return type annotation is `RedactedSlice`; seam propagates to validate + write |
| AC-8 | One constant `SECRETS_REDACTED_COUNT_FIELD` | Two constants `SECRETS_REDACTED_COUNT_FIELD` AND `EVENT_ENVELOPE_WRITTEN`; source-level regex check that neither literal appears at the call site |
| AC-8b (new) | — | Both constants in `codegenie.logging.__all__` |
| AC-9 | "fixture repo with no secrets ... `structlog.testing.capture_logs()`" | Construct empty `RedactedSlice` directly; call `Writer.write` with `tmp_path`; assert event + field |
| AC-10 | "fixture repo with three seeded secrets" | Construct seeded envelope fixture; run through `_redact_envelope`; pass `RedactedSlice` to `Writer.write` |
| AC-11 | "event name preserved; field appears on writer's completion event" | Event uniqueness: exactly one `"envelope.written"` per `Writer.write`; failure-path test: zero events on `OSError` |
| AC-12 | "no `SecretFinding` data in any persisted artifact" | Substring assertions over the persisted YAML bytes for `pattern_class`, `cleartext_len`, canonical plaintexts (negative) AND `<REDACTED:fingerprint=` (positive) |
| AC-12b (new) | — | Per-probe attribution preserved: pre-scrubbed placeholder fixture + one novel envelope-level finding |
| AC-13 | "verify against the actual snapshot file at implementation time" | Programmatic enumeration recipe: `python -c "...print([n for n in dir(m) if 'SNAPSHOT' in n.upper()])"` |
| AC-14 | "no model_construct calls anywhere in src/codegenie/output/**" | Same content; explicit acknowledgment of one new public-constructor call site in `_build_redacted_slice_pass` (NOT `model_construct` — the lint rule does not ban the public constructor) |
| AC-15 (new) | — | Parametrized cross-story integration over four canonical shapes (mirrors S3-02 AC-15b) |
| AC-16 (new) | — | Placeholder-idempotence: existing `<REDACTED:fingerprint=…>` placeholder unchanged through envelope-level pass |
| Implementation outline | Edit `sanitizer.py` for `_PASSES`; edit `writer.py` signature | Create `envelope_redactor.py`; add `_seam_redact_envelope` between Steps 8 and 9 in `cli.py`; edit `Writer.write` signature + `isinstance` guard + log emission; edit `logging.py` two constants |
| Notes for the implementer | LOC budget; `findings_count` flow; `reveal_type` mechanism; runtime rejection; structural ladder | Same + unit-vs-integration split + the four design-pattern notes DP1–DP5 |

## Verdict rationale

**HARDENED.** The story's intent was sound (close the type-level + chokepoint rung of 02-ADR-0010's structural-defense ladder), but six BLOCK-severity inconsistencies with master would have stopped the executor on the first tool call (the `write_envelope` function it would have looked for to edit does not exist). After hardening:
- All BLOCK findings closed by realigning prescriptions to actual master surfaces (`Writer.write`, `_seam_write_envelope`, `OutputSanitizer.scrub` per-probe, the absence of an existing writer-completion event).
- Test-quality gaps (mock-spy mechanism, mypy contract, dataflow substring assertions) closed.
- Cross-story integration with S3-01 + S3-02 explicitly asserted.
- Design-pattern opportunities (registry promotion deferred until N=4 content passes; `Fingerprint` newtype deferred to S8-02 concurrent landing; pure-module discipline; ladder framing) surfaced in Notes-for-implementer.

Ready for [phase-story-executor](../../../../skills/phase-story-executor).
