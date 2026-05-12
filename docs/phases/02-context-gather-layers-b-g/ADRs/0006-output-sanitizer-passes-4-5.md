# ADR-0006: `OutputSanitizer` Pass 4 (secret-finding fingerprinter) + Pass 5 (prompt-injection marker tagger)

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** security · sanitizer · chokepoint · secret-handling · prompt-injection · schema-defense
**Related:** [Phase 0 ADR-0008](../../00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md), [Phase 1 ADR-0007](../../01-context-gather-layer-a-node/ADRs/0007-warnings-id-pattern.md), ADR-0005, ADR-0011

## Context

Phase 0 froze `OutputSanitizer` at two passes (field-name regex; path-scrub). Phase 1 added Pass 3 (size/depth cap) under Phase 1 ADR-0008's discipline. Phase 2 introduces two new categories of hostile data that flow through `ProbeOutput`:

1. **Secret findings from `gitleaks`** (Phase 2 G6 probe). Raw matched bytes — API keys, tokens, AWS secret access keys — would otherwise hit `repo-context.yaml`, the cache blob directory, and the audit log unless explicitly transformed before chokepoint write. `--redact` at the tool boundary is one defense; sanitizer-level enforcement is the second.
2. **Prompt-injection markers in `RepoNotesProbe` and `ExternalDocsProbe` bodies.** Repo notes and markdown docs may contain `<|im_start|>`, `[INST]`, `<<SYS>>`, `ignore previous instructions`, and similar markers. Phase 8's Hierarchical Planner will eventually feed these into LLM context; uninstrumented bodies invite prompt-injection attacks at that handoff. The body itself must be preserved verbatim (so the Planner can read it through structured tool output, not inline) but downstream consumers need a metadata signal that something is in it.

The security lens proposed both passes (`design-security.md §"OutputSanitizer Pass 4"`, `§"OutputSanitizer Pass 5"`). The performance and best-practices lenses were silent on this. The critic did not attack Pass 4/5 specifically but pointed out (`critique.md "Cross-design observations"` "Things this design missed") that fingerprint-only secret storage makes diagnostic work harder and that the marker-tagger must preserve information (file, line) for false-positive review.

This ADR captures both as additions to the Phase 0 chokepoint, lifting the pass count from 2 (Phase 0) → 3 (Phase 1) → **5** (Phase 2).

## Options considered

- **Tool-boundary redaction only.** `gitleaks --redact` mandatory; rely on it. No sanitizer-side defense. If a future probe author adds a `gitleaks --no-redact` call (or some other probe captures a `matched_text` field), the raw secret reaches disk.
- **Schema-level forbiddance only.** Sub-schemas declare `additionalProperties: false` and forbid `match|raw|value`. Catches anything emitted under those fields. Doesn't catch `findings[].context` from a future probe that adds the field thinking it's harmless.
- **Sanitizer Pass 4 (fingerprinter) + Pass 5 (marker tagger) at the Phase-0 chokepoint [S].** Strongest. Belt-and-suspenders with both tool-side redaction and schema-side forbidance. One central enforcement point.

## Decision

**Phase 2 extends `src/codegenie/output_sanitizer.py` with two new method calls**:

### Pass 4: secret-finding fingerprinter

- **Field detection:** Any object key matching the regex `match|secret|finding|raw|context|value` (case-insensitive) is treated as a candidate secret carrier.
- **Transform:** Replace the string value with `{content_hash: blake3(value), entropy_band: "low"|"med"|"high", length: int}`. Original string discarded.
- **Where:** Runs *before* the cache write, *before* the audit write, *before* YAML emission. Same chokepoint discipline as Passes 1–3.
- **Schema enforcement:** Sub-schemas tag fields with `"x-secret-finding": true`; objects so tagged are required to have `content_hash`, `entropy_band`, `length` and forbidden from having `match|raw|value|secret|context`. Belt-and-suspenders; runs in the schema validator after Pass 4.
- **Idempotency:** Pass 4 on sanitized output is a no-op (Hypothesis property test asserts).
- **`entropy_band`:** Shannon entropy over the byte distribution, bucketed into three bands by configurable thresholds. The original bits aren't preserved; the band is enough to triage false positives.

### Pass 5: prompt-injection marker tagger

- **Field detection:** Long strings (> 256 chars) anywhere in a `ProbeOutput`.
- **Transform:** Scan for marker patterns (`<\|im_start\|>`, `\[INST\]`, `<<SYS>>`, `ignore previous instructions`, `as an AI language model`, `disregard the above`, …); emit `prompt_injection_marker_count: int` and `prompt_injection_markers_seen: list[str]` as **sibling metadata fields**. **The original string is preserved verbatim.**
- **Why preserve:** Phase 3's vuln-remediation and Phase 4's LLM fallback must read the body. The defense is *signal*, not *redaction* — the Planner reads markers via structured slice fields, not via inlined content.
- **Where:** Same chokepoint as Pass 4; runs after Pass 4 (so a marker inside a `match` field is replaced with a hash by Pass 4, then Pass 5 sees no string to scan there).

### Ordering and naming

- Pass 1 (field-name regex, Phase 0) → Pass 2 (path-scrub, Phase 0) → Pass 3 (size/depth cap, Phase 1) → **Pass 4 (secret fingerprinter, Phase 2)** → **Pass 5 (prompt-injection marker tagger, Phase 2)** → schema validator (Pass 4's `x-secret-finding` enforcement) → YAML write + audit write.

## Tradeoffs

| Gain | Cost |
|---|---|
| Raw matched secret bytes never reach `repo-context.yaml`, audit log, or any cache blob — single chokepoint, central enforcement | Diagnostic work on a false-positive secret finding loses raw text; the `entropy_band` + `length` + `file/line/rule_id` set is the diagnostic surface |
| Belt-and-suspenders: tool-side `--redact` + sanitizer Pass 4 + schema `x-secret-finding` tag — three independent defenses | Three places to maintain; a future probe that emits a `matched_text` field but doesn't trigger Pass 4's regex slips through if the schema doesn't tag the field |
| Prompt-injection markers are detected once at the chokepoint, not per-consumer — Phase 3 / 4 / 8 consumers all see the same metadata | Marker patterns are a closed list; an adversary can craft a novel marker that escapes detection; the chokepoint's value is averaged across known patterns |
| Bodies are preserved verbatim — Phase 4's RAG flow consumes them through structured slice fields, not inlined into prompts | Storage cost: marker counts and seen-patterns lists add ~100 bytes per long-string field; immaterial |
| Pass 4 is idempotent (Hypothesis property test asserts) — re-running the sanitizer on sanitized data is safe | Idempotency is an invariant the implementation must maintain across future passes; ADR notes this explicitly |
| Pass count lifts to 5 in a linear, documented sequence; no parallel passes, no late-write reflection on prior pass output | Linear is slower than a fused pass; immaterial at Phase 2 byte volumes (per `final-design.md "Resource & cost profile"`) |

## Consequences

- `src/codegenie/output_sanitizer.py` gains two methods: `pass4_fingerprint_secrets(output: ProbeOutput) -> ProbeOutput` and `pass5_tag_prompt_injection(output: ProbeOutput) -> ProbeOutput`. The coordinator's per-probe sanitize sequence becomes a 5-step linear pipeline.
- `tests/unit/output_sanitizer/test_pass4_fingerprint_secrets.py` and `test_pass5_prompt_injection_tagger.py` ship.
- `tests/adv/test_gitleaks_redaction_invariant.py` asserts: planted `AKIAFAKE0000000000` byte sequence appears nowhere in `.codegenie/` after gather — Pass 4 + tool-side redaction together (`final-design.md "Test plan" Adversarial tests`).
- `tests/adv/test_repo_note_prompt_injection.py` asserts: planted `<|im_start|>` marker in `.codegenie/notes/poison.md` produces `prompt_injection_marker_count ≥ 1` in `repo_notes` slice; body **not inlined** in YAML; body file at mode `0600`.
- `tests/adv/test_external_doc_prompt_injection.py` parallels the above for `external_docs`.
- Schema sub-files for `gitleaks`, `semgrep`, and any future findings-emitting probe declare `x-secret-finding: true` on candidate fields.
- Future probes whose outputs may contain secret-shaped or prompt-injection-shaped data inherit the chokepoint defense; no per-probe defensive code needed.
- The `entropy_band` bucketing thresholds live in a small `src/codegenie/output_sanitizer/entropy_bands.yaml` (catalog) so they can be tuned without touching the sanitizer's regex logic.
- Phase 8's Hierarchical Planner consumes `prompt_injection_marker_count` and `prompt_injection_markers_seen` from each slice when assembling LLM context.

## Reversibility

**Medium.** Removing Pass 4 or Pass 5 is a method deletion plus removal of the call from the sanitize pipeline. The schema `x-secret-finding` tag and the test corpus would remain, becoming dead defenses. The *capability* (preventing raw secret bytes from reaching disk; signaling prompt-injection markers) cannot be removed without re-introducing a known security regression; future Phases that need either capability would have to add a replacement, not relitigate this one.

## Evidence / sources

- `../final-design.md "Goals (concrete, measurable)"` OutputSanitizer-Pass-4/5 bullet
- `../final-design.md "Components" #9 OutputSanitizer — Pass 4 + Pass 5`
- `../final-design.md "Conflict-resolution table" D15` — the resolution
- `../final-design.md "Failure modes & recovery"` gitleaks rows; repo-notes adversarial row
- `../phase-arch-design.md "4+1 architectural views" "Logical view"` — OutputSanitizer class diagram
- `../phase-arch-design.md "Goals" #4` — adversarial fixtures including prompt-injection
- `../critique.md "Attacks on the security-first design"` "Things this design missed" — fingerprint-only debugging cost
- [Phase 0 ADR-0008](../../00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md) — the chokepoint this extends
