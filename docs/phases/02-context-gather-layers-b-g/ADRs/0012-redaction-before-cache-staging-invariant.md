# ADR-0012: Raw-artifact byte redaction is a writer-boundary invariant, not a per-probe responsibility

**Status:** Accepted
**Date:** 2026-05-19
**Tags:** security · secrets · redaction · chokepoint · structural-defense · raw-artifacts
**Related:** 02-ADR-0005, 02-ADR-0010, ADR-0008 (Phase 0 sanitizer chokepoint), ADR-0011 (atomic writer)

## Context

02-ADR-0005 commits Phase 2 to **zero plaintext secrets in any persisted file**. The mechanism described there is `redact_secrets` (named-pattern + Shannon-entropy fallback) walking `ProbeOutput.schema_slice` before the writer publishes `repo-context.yaml`. 02-ADR-0010 closes the type-system bypass by making the writer accept only `RedactedSlice`. Together the two ADRs cover the **structured** payload — every string leaf inside the slice tree gets the redactor.

They do **not** cover `ProbeOutput.raw_artifacts` — the opaque byte payloads probes write to `.codegenie/context/raw/`. The `redact_secrets` walker is defined over `JSONValue` and stops at the slice. The CLI marshalling step (`cli.py:618`) reads each `raw_path` back as bytes, applies the soft truncation budget (S1-09), and hands the bytes to `Writer.write` — which atomic-replaces them onto disk without ever touching the contents.

The Phase 2 `gitleaks` probe is the existing partial fix (`layer_g/gitleaks.py:138-191` — `_redact_raw_bytes`): because the tool's stdout JSON literally contains the `Secret` field as cleartext, `gitleaks` redacts its own raw bytes inside the probe before persistence (AC-RP1 per S6-07). That single inline mitigation is described in the docstring as "ADR-0010 one rung earlier."

F-03 — surfaced by `phase-shakedown` on 2026-05-19 — demonstrates the gap. `scip-typescript` (B1, S4-03) emits a binary SCIP protobuf that embeds the indexed **source text** alongside symbol info. When the analyzed repo contains a secret in source (the fixture seeds `AKIA1234567890ABCDEF` into `src/config.ts`), the secret rides verbatim into `.codegenie/context/raw/scip-index.scip`. The two load-bearing adversarial tests fail deterministically on both cold and warm-cache lanes:

```
tests/adv/phase02/test_secret_in_source.py::test_gather_produces_zero_plaintext_in_any_persisted_file
tests/adv/phase02/test_secret_in_source.py::test_warm_cache_lane_still_zero_plaintext
```

The leak is silent because Phase 2 has no consumer of `scip-index.scip` (it is "Phase-3-opaque" per `scip_index.py:21-28`); B2 reads only the `scip.json` sidecar. Operators don't see the bytes. But the invariant promised by 02-ADR-0005 — *zero plaintext anywhere* — is broken, and every future probe that writes a binary or text artifact inherits the same silent failure mode unless we close the gap structurally.

## Options considered

- **Option A — Drop source text from the SCIP blob via `scip-typescript` flags / post-processing.** **Pattern:** Per-tool mitigation. Cheapest if it works. Fails on three counts: (1) scip-typescript exposes no documented flag to elide `Document.text`; (2) Phase 3's planned `ScipAdapter` (production-side) will likely need source positions / token text for `RefsTo` / `ConsumersOf` queries, so eliding text now bakes in a Phase-3 regression we cannot foresee yet; (3) the fix solves *one* probe — every future probe that emits a binary blob (LSIF, semgrep --json with code snippets, dependency-graph dumps with embedded README excerpts, etc.) re-opens the same hole. Punts the problem; doesn't compose.

- **Option B — Extend the redactor to walk raw-artifact bytes at the CLI marshalling boundary.** **Pattern:** Structural defense at the chokepoint (same shape as 02-ADR-0010). Add `redact_raw_artifact_bytes(payload: bytes, probe_name: ProbeId) -> tuple[bytes, list[SecretFinding]]` to `codegenie.output.sanitizer`. Wire it into `cli.py` right after the `apply_raw_artifact_truncation` call, before bytes flow into `raw_artifacts: list[tuple[str, bytes]]` for `Writer.write`. The function applies the existing named patterns from `_PATTERNS` (now also compiled in `bytes` form), emits `SecretFinding` records into the existing audit-trail list, and returns the redacted bytes. Entropy fallback is **deliberately skipped** for opaque binary blobs (Shannon entropy over arbitrary protobuf bytes is meaningless and would corrupt unrelated structure); the named-pattern set covers every credential class 02-ADR-0005 enumerates (AWS / GitHub / JWT / RSA / npm / Anthropic). Idempotent against `gitleaks`-style probes that already pre-redact (re-applying patterns to already-redacted bytes is a no-op because the cleartext is gone).

- **Option C — Mirror `gitleaks`: each probe pre-redacts its own raw bytes.** **Pattern:** Per-probe responsibility. Same trap as Option A but distributed: every new probe author must remember to call `_redact_raw_bytes` and we have no structural enforcement. Scales linearly with probe count; the next contributor who forgets re-introduces F-03 under a different probe. The smart-constructor failure mode named in 02-ADR-0010 — "every caller has to remember; they won't" — applied to raw bytes.

## Decision

Adopt **Option B**. The invariant "no plaintext secret persists in any byte the writer publishes" lives at the writer-marshalling boundary, not in any individual probe.

Concretely:

1. `src/codegenie/output/sanitizer.py` gains `redact_raw_artifact_bytes(payload: bytes, probe_name: ProbeId) -> tuple[bytes, list[SecretFinding]]`. It compiles `_PATTERNS_BYTES` (the existing `_PATTERNS` table re-compiled with `bytes` regex objects) once at module import. Each match emits a `SecretFinding` (probe_name, BLAKE3-8-hex fingerprint, pattern_class, cleartext_len) and substitutes `<REDACTED:fingerprint=<8hex>>` bytes inline. The entropy fallback does NOT run against bytes — see Tradeoffs.

2. `src/codegenie/cli.py` (`_seam_coordinator_gather` callsite, `cli.py:618-663`) calls `redact_raw_artifact_bytes` after `apply_raw_artifact_truncation` returns. The resulting redacted bytes flow into `raw_artifacts: list[tuple[str, bytes]]`. Raw-artifact findings are **not** merged into the existing `_emit_phase2_summary` stdout count or the `envelope.written` structlog event's `secrets_redacted_count` field — both surfaces continue to report only envelope-redactor (slice-side) findings, preserving the `stdout_count == event.secrets_redacted_count` invariant tested by `tests/integration/cli/test_summary_count_matches_event.py`. Instead the marshalling step emits a dedicated structlog event `raw_artifacts.redacted` carrying `count` + sorted unique `fingerprints` when any raw-origin redaction occurred, so the audit trail stays grep-able without coupling to the slice-side count contract. This mirrors the `gitleaks` precedent (probe-side redaction is invisible to the envelope count). Surfacing raw-origin findings into the operator-facing stdout block is amendment territory per §Reversibility.

3. The existing `gitleaks._redact_raw_bytes` stays in place. It is now defense-in-depth — the cleartext is gone by the time the marshalling step sees the bytes — but removing it would silently widen the in-process window during which gitleaks' parsed `Secret` field exists in memory. Keep the rung; document that the marshalling-step redactor is the load-bearing invariant.

4. A new adversarial test in `tests/adv/phase02/test_secret_in_source.py` (or a sibling file) walks every probe with a non-empty `raw_artifacts` list and plants the same `AKIA...` seed into a fixture each probe would index, asserting the seed appears in zero persisted bytes. Future probes that add `raw_artifacts` inherit the invariant via this test, not via the new probe author remembering an ADR.

**Pattern: Chokepoint structural defense + parametric extension at the I/O boundary.**

## Tradeoffs

| Gain | Cost |
|---|---|
| One redaction surface for every probe's raw bytes — F-03 closes for `scip_index` and every future probe that writes a raw artifact inherits the same defense automatically (the test enumerates probes, not patterns). | Adds one walk through every raw-artifact payload at marshalling time. The SCIP blob can be tens of MB; running the six named regexes against tens of MB is millisecond-scale per gather and runs after the soft truncation cap, so the bound is `min(file_size, raw_artifact_truncate_mb * 1_048_576)`. No new IO. |
| The audit trail surfaces raw-origin findings on a dedicated structlog event (`raw_artifacts.redacted`) carrying `count` + sorted unique `fingerprints`. The slice-side count surface (stdout summary + `envelope.written.secrets_redacted_count`) stays unchanged, so the `stdout == event` contract that `tests/integration/cli/test_summary_count_matches_event.py` enforces still holds. Operators audit raw-origin redactions by grepping the new event id. | Operators reading only the stdout summary block will not see raw-origin counts; they have to consume the structured log. Acceptable trade given the existing slice-side count contract; promoting raw counts into the stdout block is amendment territory per §Reversibility. |
| Composes with 02-ADR-0010's `RedactedSlice` smart constructor — same structural-defense shape (the value type proves the cleanup ran), just at the bytes boundary. The forbidden-patterns net can grow to forbid raw-bytes-into-Writer.write call sites that bypass the new function, mirroring the existing `model_construct` ban under `src/codegenie/output/**`. | The new function does NOT return a smart-constructor wrapper around the bytes (a `RedactedBytes` type) — a `bytes` payload is harder to nominate via Pydantic than a `dict`. The structural defense lives in (a) the cli.py wiring being the single producer of `raw_artifacts: list[tuple[str, bytes]]` (already true; `Writer.write` is the single consumer) plus (b) the test invariant. A Phase 3+ amendment can promote this to a `RedactedBytes` smart-constructor wrapper if the bytes contract surface grows. |
| Idempotent against pre-redacting probes (`gitleaks`) — re-applying named patterns to already-redacted bytes is a no-op because the cleartext is gone. No probe needs to change to land this fix. | We knowingly skip the Shannon-entropy fallback for raw-artifact bytes. Entropy over arbitrary protobuf / binary bytes is statistically meaningless (it's not entropy-of-a-string-leaf) and a positive match would corrupt unrelated structural bytes, breaking the artifact. **Concrete consequence:** an opaque-format secret class that doesn't match any of the six named patterns (e.g., a future TOKEN scheme) would slip through this layer until its pattern joins `_PATTERNS`. The ADR amendment workflow (per 02-ADR-0005 §"Reversibility") is the named door — adding a seventh pattern class is the same shape as adding it for slice redaction today. |
| The SCIP blob remains structurally a SCIP protobuf — the byte-level substitution replaces only matched cleartext bytes with a shorter marker, so any consumer (Phase 3's planned ScipAdapter) that uses byte offsets into `Document.text` will see corruption at the redacted regions only. Symbol queries (name + range) are unaffected because the redaction does not touch symbol info or position tables. | Phase 3's `ScipAdapter` cannot rely on cleartext source-text projection inside redacted regions. The scip_index docstring already notes the blob is "Phase-3-opaque" for Phase 2's purposes; Phase 3's design must engage with this. This is an explicit, documented constraint — not a hidden one. |
| Writer-boundary placement preserves the existing chokepoint discipline. The Writer signature stays the same; the marshalling step is the single producer; the test invariant is enumerable by walking `tests/adv/phase02/`. | A new probe author who writes raw artifacts via a path OTHER than `ProbeOutput.raw_artifacts` (e.g., directly writing to `ctx.workspace` and then reading back outside the contract) escapes the invariant. The probe-context-conformance fence already forbids most of this surface; the new test asserts behavior end-to-end, not on the static call graph. |

## Pattern fit

Pattern: **Chokepoint structural defense** (`design-patterns-toolkit.md §"Chokepoint"`) at the marshalling boundary. The pattern's prescription: "if every flow must pass through one named gate, the invariant becomes a property of the gate, not of every caller." 02-ADR-0010 applies it at the `dict → RedactedSlice` boundary; this ADR applies it at the `bytes → Writer` boundary. Same toolkit, same failure-mode prevention ("contributors will forget"), one layer down.

## Consequences

- `src/codegenie/output/sanitizer.py` exports `redact_raw_artifact_bytes(payload, probe_name) -> tuple[bytes, list[SecretFinding]]` alongside the existing `redact_secrets`. The bytes-form pattern table `_PATTERNS_BYTES` is compiled once at module import from the same string sources as `_PATTERNS`, so a pattern change touches one canonical list.
- `src/codegenie/cli.py` (`cli.py:618-663`) invokes `redact_raw_artifact_bytes` after `apply_raw_artifact_truncation` and before the bytes land in `raw_artifacts: list[tuple[str, bytes]]`. The function's `list[SecretFinding]` return is **not** merged into the existing slice-side summary surface — the stdout count and the `envelope.written` event's `secrets_redacted_count` field stay scoped to envelope-redactor findings only. Raw-origin findings instead surface on a dedicated `raw_artifacts.redacted` structlog event (count + sorted unique fingerprints) emitted once per gather when any raw-origin redaction occurred.
- `tests/adv/phase02/test_secret_in_source.py` continues to assert the AKIA-seed invariant; both `test_gather_produces_zero_plaintext_in_any_persisted_file` and `test_warm_cache_lane_still_zero_plaintext` turn green.
- A new adversarial test under `tests/adv/phase02/` walks every probe with a non-empty `raw_artifacts` list and proves the same invariant holds. The test is parameterized on probe identity, so the next probe to add raw artifacts is automatically covered.
- The existing `gitleaks._redact_raw_bytes` stays in place as a defense-in-depth rung. Its in-process cleartext window is unaffected; the marshalling-step redactor only protects the on-disk persisted state.
- The entropy-fallback omission for raw-artifact bytes is a documented constraint. The ADR amendment workflow is the door for a seventh pattern class; the slice-side entropy fallback continues to cover unstructured-string surfaces.
- No probe code changes; no `Probe` ABC change; no `Writer.write` signature change. The fix is additive at the marshalling boundary.

## Reversibility

**High.** Reverting is one function deletion in `sanitizer.py` and one call-site removal in `cli.py`. The slice-side redactor (`redact_secrets`) continues to work unchanged. The reversal would re-open F-03; the structural-defense argument makes this unattractive by design — same shape as 02-ADR-0010's reversibility note.

Further-strengthening directions (Phase 3+):

- Promote `bytes` flowing into `Writer.write` to a `RedactedBytes` smart constructor (mirrors `RedactedSlice`), making "redactor was called over the bytes" type-checkable.
- Route raw-artifact writes through `ctx.workspace` and then into `output_dir` via a single mover, so the on-disk window during which unredacted bytes exist (between `scip-typescript --output=…` and the CLI marshalling step) closes. Currently the unredacted bytes exist on disk only transiently within a single gather process; the final persisted state is redacted.

## Evidence / sources

- `tests/adv/phase02/test_secret_in_source.py::test_gather_produces_zero_plaintext_in_any_persisted_file` — the failing invariant (F-03).
- `tests/adv/phase02/test_secret_in_source.py::test_warm_cache_lane_still_zero_plaintext` — the warm-cache failure mode (cache serves the on-disk blob).
- `src/codegenie/probes/layer_b/scip_index.py:127-140, 235` — the scip-typescript `--output` invocation.
- `src/codegenie/probes/layer_g/gitleaks.py:138-191` — the per-probe precedent this ADR generalizes away from.
- `src/codegenie/output/sanitizer.py:283-440` — the existing `redact_secrets` + `_PATTERNS` table this ADR extends.
- `src/codegenie/cli.py:618-663` — the marshalling boundary where the new redaction slots in.
- 02-ADR-0005 — the zero-plaintext-persistence commitment this ADR finishes enforcing.
- 02-ADR-0010 — the chokepoint structural-defense pattern this ADR mirrors at the bytes boundary.
- ADR-0008 (Phase 0) — the original two-pass sanitizer chokepoint discipline.
- ADR-0011 (Phase 0) — the atomic-writer guarantees the marshalled bytes inherit.
