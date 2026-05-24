# Validation report: S3-05 — `stage6_validate.yaml` + `stage6_validate_loose.yaml` populated + digest-pinned `sandbox-policy.yaml`

**Validated:** 2026-05-23
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Validator agent run:** automated (story-validation-corrector scheduled task)

## Summary

S3-05 populates two stage-6 gate catalog YAMLs (`stage6_validate.yaml` strict + `stage6_validate_loose.yaml` dev-mode loose), commits the codegenie-owned `tools/policy/sandbox-policy.yaml` per ADR-0013, and flips `tools/digests.yaml#sandbox.policy_yaml` from S1-07's `"TBD"` placeholder to a real BLAKE3-128 hex digest. It also stubs `src/codegenie/sandbox/signals/policy.py` (`POLICY_PATH` constant + ADR-0013 docstring) so the S4-03 collector has a place to land later and so the adversarial test from ADR-0013 can lock in the not-repo-resident invariant at this stage.

The draft correctly identified the deliverables and traced cleanly to ADR-0013 / ADR-0014 / ADR-0015 + Open Q4 (ship both catalogs), but contained **three block-tier cross-story contradictions** an executor following the draft literally would have hit on first `pytest` invocation, plus ~15 coverage and test-quality gaps that would silently let a wrong implementation pass. The most consequential:

1. **BLAKE3 length contradiction between the draft and S1-07 HARDENED.** Draft pins BLAKE3-128 (`hexdigest(length=16)` → 32 hex chars) per arch §Data model lines 654/774-775 + S3-01 AC-HASH-FORMAT-1. S1-07 HARDENED already shipped `_BLAKE3_DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")` in `tests/schema/test_digests_yaml.py` — 64 hex chars (BLAKE3-256). Writing a 32-char hex into `tools/digests.yaml#sandbox.policy_yaml` would fail S1-07's fence test. Per Rule 7 (Surface conflicts, don't average them), the source of truth is the arch design — **BLAKE3-128 wins**. The S1-07 regex is the bug. Resolution: S3-05 owns a one-line forward-fix to S1-07's regex (`{64}` → `{32}`) — Group E (AC-DG-FIX-1..-3).
2. **`GateCatalogLoader` does not exist.** Draft TDD: `from codegenie.gates.catalog_loader import GateCatalogLoader; loader = GateCatalogLoader(catalog_dir=CATALOG); loader.load_all()`. S1-06 HARDENED ships only module-level `load` / `load_all` functions plus the `CatalogEntry` Pydantic class — `__all__ == {"CatalogEntry", "load", "load_all"}`. Tests rewritten to call `load_all(CATALOG)` directly + assert both gate entries materialize as `CatalogEntry` instances (also exercises ADR-0014 `extra="forbid"` transitively).
3. **`sandbox.base_image_node` key cannot exist in `tools/digests.yaml`.** Draft told the executor to "pull the actual base-image digest from `tools/digests.yaml#sandbox.base_image_node` (added if absent — placeholder `sha256:0000...` is OK)". S1-07 AC-DG-2 + arch §Data model line 306 pin exactly four `sandbox.*` keys (`firecracker`, `vmlinux`, `rootfs`, `policy_yaml`); the placeholder shape (`sha256:0000...`) also violates S1-07 AC-DG-5 (values must match `"TBD"` or hex — neither permits the `sha256:` prefix). Surgical fix (Rule 3): inline the placeholder `cgr.dev/chainguard/node@sha256:` + 64 zero hex chars directly into `stage6_validate.yaml#sandbox.base_image` (S1-06's `_schema.json` accepts this shape via its `^cgr\.dev/chainguard/[a-z]+@sha256:[a-f0-9]{64}$` regex). Real Chainguard digest swap is owned by S3-07's integration test.

Resolution: ~35 numbered ACs across 12 groups (Groups A–L) (was 11 unnumbered checkboxes), a **five-test-file TDD plan** (catalogs strict + loose / policy values / digest cross-check / in-repo-policy adversarial stub / `test_digests_yaml.py` regex forward-fix) with planted-positive companions across every walker per Phase 5 convention (S1-07 AC-PP-* idiom), two golden-template byte-equality tests applying the S3-01 sidecar pattern to YAML, and three file-stability invariants (LF, no CRLF, no BOM) that the original digest-equality test alone could not enforce.

## Findings by critic

### Coverage critic — NEEDS-HARDENING

| Severity | Finding | Resolution |
|---|---|---|
| block | F-COV-1 — BLAKE3 length contradiction with S1-07 (`{64}` vs `{32}`) | Group E (AC-DG-FIX-1..-3): one-line regex fix + comment update; arch + S3-01 = source of truth. |
| block | F-COV-2 — `sandbox.base_image_node` cannot be added (S1-07 four-key constraint) | Group A AC-STRICT-7 inlines literal `cgr.dev/chainguard/node@sha256:` + 64 zeros; S3-07 swaps to real digest. |
| block | F-COV-3 — strict catalog ACs only assert ~3 of ~15 arch-pinned fields | Group A AC-STRICT-1..-14 itemize every arch-pinned field (max_attempts, retryable_failures, attempt_overrides[2], time_budget, memory, pids, env_allowlist, both phases entries with `network`/`enable_trace`/`egress_allowlist`/`cmd`). |
| block | F-COV-4 — no AC asserts loose catalog loads through `catalog_loader.load_all` with `TransitionId.STAGE6_VALIDATE_LOOSE` | Group F AC-LOAD-1..-4. |
| harden | F-COV-5 — policy YAML byte-for-byte AC doesn't pin ADR-0015 asymmetric values | Group C AC-POL-1..-7 (with explicit AC-POL-7 calling out ADR-0015 invariant). |
| harden | F-COV-6 — banned-substring list re-declared instead of imported | Group H AC-BS-1..-3 (import canonical from S1-03 `_introspection.BANNED_SUBSTRINGS`; add the constant if S1-03 didn't export). |
| harden | F-COV-7 — no AC pins digest regex independently of file-bytes equality | Group D AC-DG-2: `re.fullmatch(r"^[a-f0-9]{32}$", value)` standalone. |
| harden | F-COV-8 — no AC asserts trailing-LF / no-CRLF / no-BOM | Group J AC-STAB-1..-3. |
| harden | F-COV-9 — no AC asserts `policy_yaml` value is no longer `"TBD"` | Group D AC-DG-3. |
| nit | F-COV-10 — adversarial stub path-component check too lenient | Group G AC-ADV-2..-3 + AC-PP-5. |

### Test-Quality critic — NEEDS-RESCUE (rewrite TDD plan; goal preserved)

| Severity | Finding | Resolution |
|---|---|---|
| block | F-TQ-1 — `GateCatalogLoader` import would `ImportError` at collection time | TDD plan rewritten to import `load_all` + `CatalogEntry` (Group F). |
| block | F-TQ-2 — `set(required_signals) == {...}` silently accepts list reorder; canonical-JSON spec hashing depends on order | Group A AC-STRICT-1 pins exact list + order; AC-PP-4 planted-positive proves the assertion fires on a reorder. |
| block | F-TQ-3 — digest test is tautological (recomputes via the same recipe both sides) | Group K AC-PP-1 planted-positive with a known-wrong fixture; Group D AC-DG-2 separately pins the regex shape so a hash-fn mutation (BLAKE3-128 → BLAKE3-256 on both sides) breaks the length check. |
| block | F-TQ-4 — banned-substring set re-declared locally forks ADR-0014's trust anchor | Group H AC-BS-1 imports canonical from S1-03; AC-BS-2 byte-equality sync test. |
| block | F-TQ-5 — no planted-positive companions; Phase 5 convention violated | Group K AC-PP-1..-5 (digest mismatch, banned-substring walker, loader extra-property, list-order, traversal path). |
| harden | F-TQ-6 — `".codegenie" not in str(POLICY_PATH)` bypassable by traversal | Group G AC-ADV-2 uses `.resolve().parts`; AC-PP-5 planted-positive. |
| harden | F-TQ-7 — no byte-equality test for "byte-for-byte" arch-spec claim | Group I AC-GOLDEN-1..-3 commits golden templates with `<pinned>` substitution. |
| harden | F-TQ-8 — loose catalog test doesn't assert `non_retryable_failures == []` or `max_attempts == 3` | Group B AC-LOOSE-1..-7 enumerated. |
| harden | F-TQ-9 — no test invokes `load_all` and asserts return type | Group F AC-LOAD-1..-4. |

### Consistency critic — NEEDS-RESCUE (three block-tier contradictions resolved)

| Severity | Finding | Resolution |
|---|---|---|
| block | F-CON-1 — BLAKE3-128 vs S1-07 `{64}` regex | Group E AC-DG-FIX-1..-3. Arch + S3-01 = source of truth. |
| block | F-CON-2 — `GateCatalogLoader` non-existence | TDD plan + Group F use module functions. |
| block | F-CON-3 — `sandbox.base_image_node` violates S1-07 four-key constraint | Inline literal in catalog YAML (AC-STRICT-7); S3-07 owns real digest. |
| block | F-CON-4 — `sha256:0000...` placeholder violates S1-07 regex anyway | Subsumed by F-CON-3 resolution. |
| harden | F-CON-5 — ADR-0015 asymmetric values not pinned verbatim | AC-POL-7 calls out the ADR explicitly. |
| harden | F-CON-6 — banned-substring set re-declaration forks ADR-0014 | AC-BS-1..-3. |
| nit | F-CON-7 — `TransitionId.STAGE6_VALIDATE_LOOSE` confirmed present in S1-04 | AC-LOAD-4 makes the enum-identity assertion explicit. |
| nit | F-CON-8 — YAML-anchors policy surface as AC | AC-LOOSE-10. |

### Design-Patterns critic — NEEDS-NUDGE

| Severity | Finding | Resolution |
|---|---|---|
| nit | F-PAT-1 — `POLICY_PATH: Path` as plain Path is fine | Leave as-is per Rule 2; Notes §5 documents the decision. |
| harden | F-PAT-2 — `digest_for(name)` reader rule-of-three reached but S3-06 owns the kernel | Notes §1 documents the deferral. |
| nit | F-PAT-3 — anchor vs duplicate decision | AC-LOOSE-10 + Notes §4. |
| nit | F-PAT-4 — inline `blake3()` in test is fine vs promoting from S3-01 | Different input domains (canonical-JSON vs raw bytes); leave inline. |
| harden | F-PAT-5 — `PLACEHOLDER_BASE_IMAGE_DIGEST` typed sentinel | Notes §2 punts to S3-06 (`SandboxHealthProbe` startup check is the natural owner). |
| nit | F-PAT-6 — per-policy-file digest registry decorator | YAGNI; YAML key set is the registry. |

## Edits applied (summary)

- Added `## Validation notes` block at the head documenting all 12 changes with rationale.
- Restructured ACs from 11 unnumbered checkboxes into 12 numbered groups (A–L) covering ~35 ACs.
- Rewrote the TDD plan into five test files with explicit imports, helpers, and assertion bodies (no `GateCatalogLoader`).
- Added five planted-positive companion tests (Group K) per Phase 5 convention.
- Added golden-template byte-equality tests (Group I) applying the S3-01 sidecar idiom to YAML.
- Added file-stability invariants (Group J — LF, no CRLF, no BOM).
- Added S1-07 regex forward-fix as Group E with code-comment justification (arch + S3-01 = source of truth).
- Updated Files-to-touch table from 7 rows to 13 rows (added golden templates, regex forward-fix, `_introspection.py` conditional edit, three test files, adversarial stub).
- Added six "Notes for the implementer" paragraphs (was four loose bullets), four sourced from design-pattern critic findings.
- Added explicit "Out of scope" rows for `digest_for()` helper, `PLACEHOLDER_BASE_IMAGE_DIGEST` sentinel, and `sandbox.base_image_node` widening — closing the door on three goal-creep paths the executor could have taken.

## Stage 3 — Research

Not invoked: no critic finding tagged `NEEDS RESEARCH`. All canonical patterns were available in-codebase (S1-07 planted-positive convention, S3-01 golden-sidecar convention, S1-03 introspection set, S1-06 module-function loader API). Stage 3 skip is correct.

## Open questions surfaced (not blocking)

- **Q-OPEN-1**: If S1-03 has not yet exported `BANNED_SUBSTRINGS` (verify with `grep -n "BANNED_SUBSTRINGS" src/codegenie/sandbox/signals/_introspection.py` before starting), this story exports it as a one-line additive constant. The validator did not verify S1-03's current export shape because Phase 5 has not yet GREEN-shipped any code (all stories `HARDENED`-only); the executor verifies at start.
- **Q-OPEN-2**: The S1-07 regex forward-fix in this story implicitly amends S1-07 (HARDENED). A pedantic reading would re-run `phase-story-validator` against S1-07 to update its `_validation/` report. Pragmatic call (Rule 3): keep the change surgical to S3-05; document the cross-story link in the commit message + S3-05's Validation note 1; S1-07's `_validation/` report stays historically accurate. If the team prefers, re-validate S1-07 in a follow-up.

## Verdict

**HARDENED.** Three block-tier contradictions resolved by aligning with the canonical source of truth (arch + S3-01 + S1-06 + S1-07). Goal preserved verbatim (populate two YAMLs + commit policy YAML + flip digest). Story is ready for `phase-story-executor`.
