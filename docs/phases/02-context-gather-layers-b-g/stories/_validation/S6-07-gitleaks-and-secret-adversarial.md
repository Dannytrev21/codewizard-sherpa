# Validation report — S6-07 `Gitleaks` scanner + `secret_in_source` adversarial

**Validated:** 2026-05-17
**Verdict:** **HARDENED**
**Validator:** phase-story-validator skill
**Story file:** [`S6-07-gitleaks-and-secret-adversarial.md`](../S6-07-gitleaks-and-secret-adversarial.md)

## Summary

The story's *intent* — ship the fourth Layer G scanner (`GitleaksProbe`) and the load-bearing adversarial test (`test_secret_in_source.py`) that verifies ADR-0005's "plaintext present in zero persisted files" commitment — traces cleanly to `phase-arch-design.md §"Goals" G5`, the §"Gap 4 / Gap 5" closures, the ADR pair (02-ADR-0005, 02-ADR-0010), the existing `IndexHealthProbe`-class load-bearing-test discipline, and `final-design.md §"Failure modes & recovery" row 7`. But the draft's *prescriptions* referenced the pre-Phase-2-evolution kernel shape (`_run(ctx)` synchronous, `probe_id` class attribute, `from codegenie.ids import ProbeId`, `run_external_cli("gitleaks", ..., timeout_seconds=30)`, four-kwarg `ProbeOutput`, `pytest-subprocess` `fp` fixture) and used a fingerprint format (`hexdigest()[:16]` = 16 hex chars) that does not match what S3-01 actually ships (`content_hash_bytes(...).removeprefix("blake3:")[:8]` = 8 hex chars). Twelve BLOCK-severity Consistency fixes + nine Coverage hardens + four Design-Pattern notes applied; story re-scoped from 20 ACs to 28 ACs.

This is the same family of kernel-drift fixes that S6-06 went through during its hardening pass; identical shape.

## Stage 1 — Context Brief

**Story under validation:** `docs/phases/02-context-gather-layers-b-g/stories/S6-07-gitleaks-and-secret-adversarial.md` — "Step 6: Ship Layer D + E + G probes."

**Goal (extracted from story):**
1. Ship `src/codegenie/probes/layer_g/gitleaks.py` as the fourth Layer G scanner, ≤ 200 LOC, no shared base, `@register_probe(heaviness="medium")`, 30 s timeout, `--no-banner` flag.
2. Ship `tests/adv/phase02/test_secret_in_source.py` — the load-bearing adversarial test that seeds an AWS key in a fixture repo, runs the full gather, and asserts the plaintext appears in **zero** persisted files.

**Phase exit criterion (from `phase-arch-design.md §"Goals" G5`):** "Secret findings (`gitleaks`, `semgrep p/secrets`, entropy fallback) are redacted at the writer chokepoint. Verified by: `tests/adv/phase02/test_secret_in_source.py` asserting plaintext is present in **zero** persisted files (`repo-context.yaml`, every `raw/*.json`, the cache blob, the audit anchor)." This story is the test of that exit criterion.

**Phase ADRs that constrain this story:**
- **02-ADR-0001** — gitleaks added to `ALLOWED_BINARIES`; invoked through `run_external_cli` (Layer G chokepoint).
- **02-ADR-0005** — no plaintext persistence anywhere in Phase 2. This story is the load-bearing test.
- **02-ADR-0010** — `RedactedSlice` smart constructor at the writer boundary; type-level "redactor was called." Composes with this story's structural commitment.
- **02-ADR-0003** — coordinator dispatch via `heaviness` / `runs_last` decorator kwargs (closed set).
- **02-ADR-0006** — `ScannerOutcome` variants + each variant's `reason` enum are closed sets.

**CLAUDE.md load-bearing commitments:**
- Audit anchors land in `.codegenie/context/runs/*.json` (canonical path — NOT `.codegenie/runs/*.json`).
- The CLI invocation is `python -m codegenie ...` (canonical form; `codegenie` console-script may not be on PATH).
- Newtype identifiers (`ProbeId`, `IndexName`) live under `codegenie.types.identifiers`.
- Functional core / imperative shell.
- Each probe declares `_WARNING_IDS: Final[frozenset[str]]` (this story has no warnings — `errors=[]`).

**Sibling-story precedent applied:**
- **S6-06** (validation pass shipped the kernel-drift family of fixes): `_run(ctx)` → `async run(self, repo, ctx)`; `probe_id` → dual-form (`name: str` + `_PROBE_ID: Final[ProbeId]`); imports relocated (`codegenie.types.identifiers`, `codegenie.errors`); `run_external_cli` async + `cwd=`/`timeout_s=` kwargs; six-field `ProbeOutput`; `applies_to_*: list[str]`; `_make_repo()`/`_make_ctx()` fixtures replace `ProbeContext.for_test(...)`; `monkeypatch.setattr` mock pattern replaces `pytest-subprocess`.
- **S3-01** (the redactor itself): fingerprint format is `content_hash_bytes(...).removeprefix("blake3:")[:8]` = 8 lowercase hex chars; marker is `<REDACTED:fingerprint=<8hex>>`; dedupe at fingerprint-level (same cleartext twice → `findings_count == 2`, `len(fingerprints) == 1`).
- **S3-03** (writer signature tightening): `Writer.write(envelope: RedactedSlice, raw_artifacts: list[tuple[str, bytes]], output_dir: Path) -> None`; emits `event="envelope.written"` with `secrets_redacted_count` field; envelope redactor walks the **dict envelope** — NOT `raw_artifacts` bytes.

**Critical tension surfaced at brief time:** S6-06 AC-W1 (two-file write split — typed slice + raw scanner bytes) vs. ADR-0005 (zero plaintext anywhere). Gitleaks raw stdout JSON contains the cleartext in the `"Secret"` field. The envelope-level `_seam_redact_envelope` walks dicts, not bytes. The Writer's `raw_artifacts` parameter is `list[tuple[str, bytes]]` and is persisted verbatim. **Without intervention, gitleaks' raw bytes would land on disk with cleartext.** This is the load-bearing Design-Pattern decision the story must pin (it does not, in the draft).

## Stage 2 — Critic findings

Four critics ran (sequentially, owing to file-permission constraints on the `**/*secret*` path that forced single-thread access). Findings tagged `block` / `harden` / `nit` per skill spec.

### Consistency critic

**Twelve BLOCK-severity findings — all kernel-drift identical in shape to the S6-06 hardening pass:**

| ID | Finding | Fix |
|---|---|---|
| B1 | Draft uses `_run(self, ctx) -> ProbeOutput` (sync, one-arg). Frozen Phase-0 ABC requires `async def run(self, repo, ctx) -> ProbeOutput`. | Implementation outline + TDD plan + prescribed code rewritten to async two-arg form. |
| B2 | Draft uses `probe_id = ProbeId("gitleaks")` (class attr). Repo precedent: dual-form (`name: str = "gitleaks"` + module-level `_PROBE_ID: Final[ProbeId]`). | AC-3 + AC-N1 (new) pin both forms. |
| B3 | Draft: `from codegenie.ids import ProbeId` + `from codegenie.exec import ToolMissingError`. Master: `from codegenie.types.identifiers import ProbeId` + `from codegenie.errors import ToolMissingError`. | All imports relocated. |
| B4 | Draft: `run_external_cli("gitleaks", [...], timeout_seconds=30)` (sync, binary string first). Master: `await run_external_cli(_PROBE_ID, argv, cwd=..., timeout_s=30.0)`. | AC-4 + prescribed code rewritten. |
| B5 | Draft: `ProbeOutput(probe_id=..., confidence=..., schema_slice=..., errors=[])` (4 wrong kwargs). Master: six-field constructor. | `_wrap` helper rewritten. |
| B6 | Draft: `applies_to_*: tuple[str, ...]`. ABC: `list[str]`. | AC-3 reworded. |
| B7 | Draft uses `ProbeContext.for_test(repo_root=...)` — phantom. | Replaced with `_make_repo()` / `_make_ctx()` conftest fixtures. |
| B8 | Draft uses `pytest-subprocess` `fp` fixture; not in `pyproject.toml`'s dev deps. | TDD plan rewritten with `monkeypatch.setattr(<module>, "run_external_cli", _spy)` + `AsyncMock`. |
| B9 | **CRITICAL: fingerprint format mismatch.** Draft: `blake3(SEED.encode()).hexdigest()[:16]` (16 hex chars). S3-01 AC-13/AC-14: 8 hex chars via `content_hash_bytes(...).removeprefix("blake3:")[:8]`. The 16-char marker would NEVER match the 8-char marker the redactor emits — AC-13 would fail at every gather. | AC-5, AC-13, `GitleaksFinding`, `_parse`, prescribed code, test fingerprint expectation all rewritten to 8-hex via the chokepoint helper. |
| B10 | Draft imports `from blake3 import blake3` directly. Phase-0 ADR-0001 declares `codegenie.hashing.content_hash_bytes` as the single chokepoint. | Probe imports `from codegenie.hashing import content_hash_bytes`; `blake3` PyPI package not imported in `gitleaks.py`. |
| B11 | Draft test walks `.codegenie/runs/*.json`. CLAUDE.md: `.codegenie/context/runs/*.json`. | AC-15 + audit anchor test rewritten. |
| B12 | Draft uses `subprocess.run(["codegenie", "gather", ...])`. Canonical: `[sys.executable, "-m", "codegenie", "gather", ...]`. | TDD plan rewritten — every subprocess call uses `sys.executable -m codegenie`. |

### Coverage critic

**Nine harden-severity gaps:**

| ID | Gap | Fix |
|---|---|---|
| C1 | `GitleaksSlice` is anaemic — only `outcome` + `findings_count`. Loses per-finding rule_id/file/line. Per S6-06 AC-9, rich per-scanner detail must live on the SLICE as `findings_detail`. | AC-6 reworded — `findings_detail: list[GitleaksFinding]`. AC-12 reworded to inspect the slice rather than raw. |
| C2 | **CRITICAL: raw-artifact persistence policy unpinned.** Gitleaks' raw bytes contain cleartext in `"Secret"`. The envelope redactor walks dicts only. Without policy, gitleaks-raw.json would persist cleartext, breaking ADR-0005. | Pinned as **gitleaks-only carve-out from S6-06 AC-W1**: probe redacts cleartext in raw bytes BEFORE adding to `raw_artifacts`. AC-RP1 + AC-RP2 (new). Structural defense one rung earlier than ADR-0010. |
| C3 | Eight ABC class attributes not all pinned. A `layer = "F"` typo would slip past `mypy --strict`. | AC-B1 (new) — all eight (plus `cache_strategy` and `version`) asserted. |
| C4 | `@register_probe` kwargs incomplete — `runs_last=False` unpinned. | AC-3 reworded to include `runs_last=False`; AC-R1 (new) — registry-membership smoke. |
| C5 | `declared_inputs` + `cache_strategy` unspecified — cache-key derivation underdefined. | AC-B1 pins `declared_inputs: list[str] = ["**/*"]` + `cache_strategy: Literal["content"] = "content"`. |
| C6 | Timeout path missing (`ProbeTimeoutError` handling). | AC-T1 (new) — timeout → `ScannerFailed(exit_code=124, stderr_tail="gitleaks.timeout")`. |
| C7 | Non-zero exit (≥ 2) → `ScannerFailed` not adversarial-tested. | AC-EX (new) — exit_code 2 path. |
| C8 | Malformed JSON missing required keys (`RuleID` / `File` / `StartLine` / `Secret`) not covered. | AC-12b (new) — `ScannerFailed(reason="invalid_json")`. |
| C9 | Fixture README contains literal seed → self-contamination (gitleaks scans README too). | AC-9 reworded — README uses placeholder pattern only; literal lives in `src/config.ts` + `docs/internal-notes.md`. |
| C10 | AC-15 walks wrong audit-anchor path. | Subsumed by B11. |

### Test-quality critic

**Six harden-severity findings (the BLOCK shape on the fingerprint format was promoted to B9 above):**

| ID | Finding | Fix |
|---|---|---|
| T1 | `fp` fixture (`pytest-subprocess`) not in dev deps. | Subsumed by B8 (Consistency). |
| T2 | `test_warm_cache_lane_still_zero_plaintext` is mutation-thin — the second gather might serve pre-redacted bytes from the first gather's redacted cache, masking a cache-lane-bypass bug. | AC-14 strengthened — delete `repo-context.yaml` between the two gathers, forcing re-write from cache-served probe outputs. |
| T3 | `test_secrets_redacted_count_log_field_positive` asserts `>= 1`. The fixture has two seed instances at distinct paths (`config.ts` + `internal-notes.md`), so per S3-01 AC-26 dedupe the count must be `>= 2`. A `set`-based finding-level dedupe would mask the bug at the `>= 1` threshold. | AC-20 reworded — `secrets_redacted_count >= 2`. |
| T4 | Argv-pinning test only checks `--no-banner` + `--no-git`. Need full flag enumeration including `--exit-code 0`, `--report-format=json`, `--report-path=-`, `--source <path>`, and the dual-form `_PROBE_ID` first-positional. | TDD plan rewritten — single `test_argv_pins_all_hardening_flags` enumerates every flag. |
| T5 | `test_gitleaks_actually_found_the_seed` reads from `raw_dir.glob("gitleaks*.json")` and parses a top-level `.findings` key. The actual gitleaks raw payload is a top-level JSON array, not a dict; and per the AC-RP1 carve-out, the raw bytes are already redacted (no cleartext in the rule_id field anyway). Better: read the gitleaks slice from `repo-context.yaml` (post-redactor — `findings_detail` is what downstream consumers see). | AC-12 reworded — inspect `envelope["probes"]["gitleaks"]["findings_detail"]` via `yaml.safe_load`. |
| T6 | AC-19 determinism is hand-waved ("two consecutive gathers"); the test needs a concrete recipe that strips `generated_at` + any UUID field and asserts byte-identity. | TDD plan adds `test_two_gathers_byte_identical_modulo_generated_at` with explicit recipe. |

### Design-pattern critic

**Four design-pattern observations:**

| ID | Observation | Decision |
|---|---|---|
| DP1 | `Fingerprint = NewType("Fingerprint", str)` — rule-of-three threshold crossed (probe → slice → writer → CLI summary → gitleaks finding = six consumer surfaces). Production ADR-0033 §3 names primitive obsession as a review-blocker. | **Defer to S8-02** (the natural concurrent-landing site with the fourth consumer in the CLI summary). Pinned in Notes-for-implementer #13. |
| DP2 | `_parse` returns `tuple[...] | str` — non-idiomatic Result. Closer to repo precedent: `tuple[...] | ScannerFailed` so the caller `isinstance`-pattern-matches on a closed sum type. | Promoted to prescribed code rewrite. |
| DP3 | Pure / impure split. `_parse`, `_fingerprint`, `_redact_raw_bytes`, `_stderr_tail` all pure; only `run()` impure. Functional core / imperative shell preserved. | Pinned in Notes-for-implementer #16. No code change; the pattern naturally holds. |
| DP4 | `_PASSES` registry for byte-redaction (speculative). Rule of three NOT crossed (single pass); the pure function is the right shape. | Refused. Note #14 documents the refusal so a future contributor doesn't speculatively introduce it. |

## Stage 3 — Research

**Skipped.** No `NEEDS RESEARCH` findings. Every gap was answerable from:
- `phase-arch-design.md §"Goals" G5` + §"Gap 4" + §"Gap 5" (line 1075–1090)
- 02-ADR-0005 (no plaintext persistence) + 02-ADR-0010 (`RedactedSlice`)
- CLAUDE.md (canonical paths, CLI invocation form)
- Sibling-story validation logs: `_validation/S6-06-layer-g-curated-scanners.md` (kernel-drift family), `_validation/S3-01-secret-redactor.md` (fingerprint format), `_validation/S3-03-writer-signature-sanitizer-composition.md` (envelope-redactor composition site)

## Stage 4 — Synthesizer + Editor

### Conflict resolutions

1. **S6-06 AC-W1 (two-file write split) vs. ADR-0005 (zero plaintext anywhere).** Resolution per priority order (Consistency > Coverage): ADR-0005 wins. S6-06 AC-W1 is the *generic* rule for Layer G scanners; gitleaks is a *named exception* because its raw bytes inherently contain cleartext. Carve-out pinned via AC-RP1 + AC-RP2. The "no shared `ScannerRunner`" discipline (final-design row 7) makes this carve-out natural — each scanner already has its own per-probe shape; gitleaks adds one more shape (raw-redaction-at-source) without needing an abstraction.

2. **Coverage critic wants `secrets_redacted_count >= 2` (T3); Test-quality critic worries this couples to fixture details.** Resolution: Coverage wins, T3 framing accepted. The fixture has two seed instances at distinct paths; this is a deliberate property of the fixture (the second instance is what proves the entropy-fallback / two-pathway coverage per Notes #5). The fixture's two-seed shape is a structural property of AC-9; tying AC-20's threshold to it is just AC consistency.

3. **DP1 (Fingerprint newtype rule-of-three crossed) vs. Rule 2 (premature abstraction is worse than three similar lines).** Resolution: Consistency wins. The pattern is principled (S3-01, S3-02, S3-03 validation logs all defer to the natural cross-cutting landing site — S8-02). This story uses `str` deliberately; the format invariant is enforced by validator in S3-02's `RedactedSlice.fingerprints` Pydantic field. No premature introduction.

### Edits applied

- **Story header:** Status `Ready` → `HARDENED`. New "Validation notes" block appended (the by-finding summary of edits, machine-readable).
- **Acceptance criteria:** 20 → 28 ACs. 8 new (AC-N1, AC-B1, AC-R1, AC-T1, AC-EX, AC-RP1, AC-RP2, AC-12b). 12 reworded (AC-1, AC-3, AC-4, AC-5, AC-6, AC-7, AC-9, AC-10, AC-11, AC-12, AC-13, AC-14, AC-15, AC-16, AC-19, AC-20). 8 preserved as-is (AC-2 LOC ceiling, AC-8 CI lane, AC-17 mypy, AC-18 CI gate, plus four others by intent).
- **Implementation outline:** rewritten to specify async `run(self, repo, ctx)`, dual-form identity, pure-helpers split (`_fingerprint`, `_parse`, `_redact_raw_bytes`, `_stderr_tail`), six-field `ProbeOutput`, raw-bytes carve-out flow, conftest fixtures, `sys.executable -m codegenie` CLI form.
- **TDD plan — Red:** Unit-tests block fully rewritten — 7 tests covering argv-pinning + fingerprint/raw-redaction + timeout + exit-2 + malformed-JSON + tool-missing + registry/ABC, all via `monkeypatch.setattr(<module>, "run_external_cli", _spy)` + `AsyncMock` pattern. Adversarial-tests block fully rewritten — 8 tests including the AC-19 determinism check and the AC-20 `secrets_redacted_count >= 2` lane.
- **TDD plan — Green:** Prescribed `gitleaks.py` skeleton fully rewritten with the chokepoint-derived 8-hex fingerprint helper, the `_redact_raw_bytes` pure pass, the closed sum-type Result shape on `_parse`, async `run`, six-field `_wrap`, full eight-attribute ABC declaration.
- **TDD plan — Refactor:** "do not extract" guidance retained; row 7 of design-patterns table cited.
- **Files-to-touch:** four new rows (`conftest.py`, `probes/__init__.py` import line, sub-schema deferral note, README placeholder annotation).
- **Out-of-scope:** unchanged.
- **Notes-for-implementer:** 10 → 17 entries. 12 hardened (fingerprint contract, raw-artifact carve-out, cleartext lifetime, `--no-git` rationale, `--exit-code 0` rationale, `sys.executable -m codegenie` form, README self-contamination guard, AC-19 determinism recipe, `adv-phase02` no-flake discipline, 100%-grep-walk shape). 5 new (Fingerprint newtype deferral with rule-of-three trace; `_PASSES` registry refusal; `ParseResult` ADT refusal; pure/impure split documentation; freshness-registry deferral to S6-08).

### Verdict

**HARDENED.** All twelve BLOCK findings closed. All nine Coverage gaps closed. All six Test-quality gaps closed. Four Design-pattern observations resolved (two pinned in Notes, two refused with documented reasoning). The story is now executor-ready: every AC has at least one TDD-plan test that would fail if a wrong implementation were swapped in (mutation-resistance verified by walking the mutation hints in each AC against the corresponding test). No RESCUE conditions — the goal, scope, and structural intent were sound; the prescriptions just needed to track the post-S6-06 kernel.

## Mutation table (sample)

For executor Validator-pass reference, the following mutations would be caught by the hardened TDD plan:

| Mutation | Test that catches it | AC |
|---|---|---|
| `[:16]` slice instead of `[:8]` on the fingerprint | `test_finding_carries_8hex_fingerprint_and_raw_bytes_redacted` | AC-5 |
| `from blake3 import blake3` direct (bypassing chokepoint) | same — fingerprint would diverge from chokepoint-derived expected | AC-5 |
| Drop `--no-banner` (ANSI banner breaks JSON parse) | `test_argv_pins_all_hardening_flags` | AC-4 |
| Drop `--no-git` (history scanning) | same | AC-4 |
| `runs_last=True` (registry drift) | `test_registry_membership_and_abc_attributes` | AC-3/AC-R1 |
| `layer = "F"` typo | same — `mypy --strict` doesn't catch class-attr value drift | AC-B1 |
| Raw bytes persisted without redaction | `test_finding_carries_8hex_fingerprint_and_raw_bytes_redacted` (assertion on `raw_artifacts[0][1]`) + adversarial walk catches at integration time | AC-RP1/AC-RP2 |
| `set`-based finding-level dedupe (mask `secrets_redacted_count` to 1) | `test_secrets_redacted_count_field_on_envelope_written` (asserts `>= 2`) | AC-20 |
| Timeout escapes past probe boundary | `test_timeout_yields_scanner_failed` | AC-T1 |
| Default-treat-non-zero-as-empty-findings convention | `test_real_crash_exit_2_yields_scanner_failed` | AC-EX |
| Silent `KeyError` swallow on malformed JSON | `test_malformed_json_missing_required_keys` | AC-12b |
| Wrong audit-anchor path (`.codegenie/runs/` instead of `.codegenie/context/runs/`) | `test_audit_anchor_contains_no_plaintext` | AC-15 |
| `["codegenie", "gather", ...]` instead of `[sys.executable, "-m", ...]` | Test would fail with FileNotFoundError on environments without console-script on PATH (fail loud) | AC-10 |
| README contains literal seed → gitleaks scans it → AC-20 count would be 3 not 2 | `test_seed_is_present_in_fixture_input` (asserts `SEED not in README.md`) | AC-11/AC-9 |
| `findings_detail` dropped from slice — only `findings_count` persisted | `test_gitleaks_actually_found_the_seed` (would fail to find `findings_detail` key) | AC-6/AC-12 |

## References

- Story: [`S6-07-gitleaks-and-secret-adversarial.md`](../S6-07-gitleaks-and-secret-adversarial.md)
- Phase arch: [`../../phase-arch-design.md`](../../phase-arch-design.md) §Goals G5, §Gap 4, §Gap 5, §Design patterns applied row 7
- ADRs honored: [02-ADR-0001](../../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md), [02-ADR-0005](../../ADRs/0005-secret-findings-no-plaintext-persistence.md), [02-ADR-0010](../../ADRs/0010-redacted-slice-smart-constructor-at-writer-boundary.md)
- Sibling-story precedent: [`_validation/S6-06-layer-g-curated-scanners.md`](S6-06-layer-g-curated-scanners.md), [`_validation/S3-01-secret-redactor.md`](S3-01-secret-redactor.md), [`_validation/S3-03-writer-signature-sanitizer-composition.md`](S3-03-writer-signature-sanitizer-composition.md)
