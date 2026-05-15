# Validation report — S1-05 `IndexId / SkillId / TaskClassId / IndexName / ProbeId` newtypes

**Story:** [`../S1-05-identifiers-newtypes.md`](../S1-05-identifiers-newtypes.md)
**Validated:** 2026-05-15
**Validator:** phase-story-validator (scheduled task: `story-validation-corrector`)
**Verdict:** **HARDENED with remediation queue**

## Summary

The story implements `codegenie.types` — four kernel-tier `NewType` identifiers (`IndexId`, `SkillId`, `TaskClassId`, `IndexName`) and a re-exported `PackageManager` (Phase 1 ADR-0013) — and merged GREEN on 2026-05-15 (commit `83b9425`) while validation was in progress. The original 9 ACs all PASS as merged.

Validation found **two block-tier gaps** plus **eleven harden-tier gaps** the original ACs and the GREEN merge both missed. The block-tier gaps:

1. **`ProbeId` is missing.** S1-04 (hardened 2026-05-15) imports `ProbeId` from `codegenie.types.identifiers` (S1-04 lines 51, 78, 656). The hardened-S1-04 doc explicitly routes the addition through S1-05. `grep -rn "ProbeId" src/` returns zero hits at validation time. When S1-04 executes, `ImportError`. **The original story's Out-of-scope text falsely claimed `ProbeId` already existed in Phase 0** — it does not. Remediation AC-1b lands `ProbeId = NewType("ProbeId", str)` in `identifiers.py`, the package `__all__`, and the test set.
2. **AC-6's mypy nominal-discrimination is unverified.** The original test file (`tests/unit/types/test_identifiers_typecheck.py`) keeps the cross-type swap lines **commented out** as prose-documentation. **No CI step uncomments and runs them.** The single load-bearing property of the entire story — that mypy `--strict` rejects cross-NewType assignment — is asserted by comments, not by code. Remediation AC-6a adds a subprocess meta-test (`test_identifiers_mypy_negative.py`) that writes a temp file with the swap **executable**, subprocess-invokes `mypy --strict`, and asserts non-zero exit + expected error substrings.

The harden-tier gaps are family-symmetric closures that S1-01 / S1-03 / S1-04 already established and S1-05 omitted: exact-set `__all__` (not ⊇), pairwise NewType distinctness, `NewType.__name__` pinning, AST-based source-scan (not regex), identity passthrough through `__init__`, removed `try/except ImportError` layout-drift fallback, module-purity invariant, `isinstance` footgun pin, `type(val) is str` strict identity, and per-tool AC-9 split.

The merged implementation is not retracted; the original 9 ACs stay marked PASS. The remediation queue (AC-1b / 3a / 3b / 4a / 5b / 6a / 7a / 8a / 9a–d) is appended to the story as a single XS follow-up commit. Stage 3 research skipped (no `NEEDS RESEARCH` findings — every gap was answerable from arch + production ADR-0033 + S1-01/S1-03/S1-04 precedent + verified repo state).

## Context Brief (Stage 1)

- **Goal as written (pre-validation):** Implement `src/codegenie/types/__init__.py` and `src/codegenie/types/identifiers.py` declaring four `NewType`s + a re-exported `PackageManager`, asserting via tests that the import location hasn't silently drifted.
- **Goal as hardened (post-validation):** **Five** `NewType`s (add `ProbeId`) + the re-export; assert (a) import-location stability, (b) pairwise distinctness + `__name__` pinning, (c) `mypy --strict` rejects cross-type swap **executed in CI**, (d) module-purity invariant on `identifiers.py`.
- **Phase 2 exit criteria touched:** Plugin scaffolding ships as documentation-as-code (kernel-only); every other Phase 2 Step 1 story (S1-01 freshness, S1-03 adapter protocols, S1-04 TCCM) consumes this story's types. S1-05 is the load-bearing kernel.
- **Load-bearing commitments touched:**
  - `CLAUDE.md §"Extension by addition"` — open `NewType` for registry keys (`IndexName`, `SkillId`, `TaskClassId`, `ProbeId`) is the right choice; closed `Literal` would freeze the registry set.
  - Production ADR-0033 §1 — newtype-per-domain-primitive is the binding discipline.
  - Production ADR-0033 §3 — primitive-obsession is a review-blocker.
  - Phase 1 ADR-0013 — `PackageManager` is owned at `codegenie.probes.node_build_system`; re-export-by-import only.
  - 02-ADR-0006 — `IndexName` is the registry key for `@register_index_freshness_check`.
- **Sibling-family lineage:** Fourth kernel-tier domain-modeling story in Phase 2 Step 1 (after S1-01 IndexFreshness, S1-03 Adapter protocols + AdapterConfidence, S1-04 TCCM). Symmetric discipline carries forward: exact-set `__all__`, AST source-scan, module-purity AST, sibling-precedent compile-fail tests (mypy subprocess), pairwise distinctness for any closed nominal-type family.
- **Prior validation history:** S1-04 report cross-references S1-05 explicitly — "S1-05 owns the identifiers module; S1-04's precondition is that `ProbeId = NewType("ProbeId", str)` lands in `src/codegenie/types/identifiers.py` either before or simultaneously with this story. If the implementer encounters a missing `ProbeId` at green-stage time, the correct fix is to extend `S1-05`'s deliverable to add `ProbeId` — **not** to declare a local `ProbeId = str` alias in `tccm/model.py`."
- **Open ambiguities resolved before Stage 2:**
  - **Phase 1 `PackageManager` location.** Verified flat (`src/codegenie/probes/node_build_system.py:115`); no `layer_a/` subpackage exists. `try/except ImportError` hedge is therefore branch-on-noop. Remediation removes the hedge.
  - **`ProbeId` existence.** Verified absent from `src/`. S1-04 hard-requires it from S1-05. Remediation AC-1b is the canonical home.
  - **`TaskClass` vs `TaskClassId` naming.** Phase 2 chose `TaskClassId` for naming-symmetry; production ADR-0033 §1 has `TaskClass`. Resolution: deliberate Phase 2 deviation, documented in Notes-for-implementer; reconciliation is a future production-ADR amendment.
- **Implementation-already-shipped consideration:** The story merged GREEN on 2026-05-15 (commit `83b9425`) while validation was in progress. Validator does not retract a GREEN merge; it appends a remediation AC queue and keeps the original ACs marked as PASS. The remediation pass is a surgical follow-up. Sibling story validations (S1-01, S1-03, S1-04) all ran pre-execution; S1-05 is the first post-execution validation. The pattern is correct — validation findings drive a follow-up commit, not a revert.

## Stage 2 — critic reports

### Coverage (verdict: COVERAGE-HARDEN — 10 findings, one block)

| ID | Sev | Finding | Closure |
|----|----|---|---|
| F1 | harden | `__name__` of each NewType not pinned; typo `NewType("Indeex_id", str)` lies in mypy errors | AC-1b adds `nt.__name__ == name` |
| F2 | harden | Independent-NewType invariant unasserted — `IndexId = SkillId = NewType("Id", str)` aliasing slips past | AC-1b pairwise `is not` over 10 pairs |
| F3 | harden | `__all__` checked with ⊇; stowaway exports slip past | AC-3a/3b exact equality |
| F4 | harden | Same-object identity guard exists for `PackageManager` but not for the four NewTypes through `__init__` | AC-5b identity passthrough |
| F5 | **block** | AC-6 mypy negative-path is comment-prose; no CI step runs it | AC-6a subprocess meta-test |
| F6 | harden | AC-5 `try/except ImportError` masks layout drift; both Phase 1 paths permitted | AC-5b removes fallback |
| F7 | harden | AC-4 regex source-scan permits annotation-form rebinding and breaks on multi-line imports | AC-4a AST walk |
| F8 | nit | AC-7 uses `isinstance(val, str)` which a `str` subclass passes | AC-7a `type(val) is str` |
| F9 | nit | AC-9 conflates four tools; failure attribution impossible | AC-9a/9b/9c/9d split |
| F10 | harden | `isinstance(x, IndexId)` runtime `TypeError` undocumented as enforced | AC-8a `pytest.raises(TypeError)` |

### Test Quality (verdict: TESTS-HARDEN — 6 findings, one block; mutation analysis)

Mutation table (selected — full set in critic output):

| # | Wrong impl | Caught by original draft? | Closure |
|---|---|---|---|
| M1 | `IndexId = SkillId = TaskClassId = IndexName = NewType("Id", str)` (one NewType, four names) | No — all four `__supertype__ is str` | AC-1b pairwise `is not` |
| M2 | `IndexId = NewType("SkillId", str)` (wrong `__name__`) | No — mypy binding still works, error messages lie | AC-1b `__name__ == name` |
| M5 | Extra entry leaks into `__all__` (e.g., `"NewType"`) | No — ⊇ semantics admit extras | AC-3a/3b == |
| M7 | Forget `as PackageManager` (mypy strict implicit-reexport rejects) | No runtime test asserts it | AC-4a alias.asname pin |
| M8 | `__init__.py` rebinds `PackageManager = "pnpm"` | No — `__all__` is just names | AC-5b identity passthrough |
| M16 | Contributor uncomments the mypy swap lines and forgets to revert; suite still passes | No — comments are prose | AC-6a subprocess meta-test |
| M18 | Multi-line `from x import (\n  PackageManager,\n)` style | False-positive — single-line regex fails to find the import | AC-4a AST walk |

Verdict drivers:
- **F1 (block)** — AC-6 unverified by automation. Single highest-leverage gap.
- **F2, F3 (harden)** — `__all__` and pairwise distinctness are the family-symmetric closure (S1-04 F10 precedent).
- **F4, F5 (harden)** — `__name__` pin and identity-through-`__init__` are mechanical one-liners with categorical coverage.
- **F6 (harden)** — AST > regex for source-scan; sibling validators already converged on this (S1-04 §F4-precedent: "AST source-scan as durable enforcement").

### Consistency (verdict: CONSISTENCY-HARDEN — 7 findings, one block; 3 nits)

| ID | Sev | Finding |
|----|----|---|
| C1 | **block** | Story falsely claimed `ProbeId` exists in Phase 0; verified absent; S1-04 hard-requires it from S1-05 |
| C2 | harden | `TaskClassId` vs production ADR-0033 §1's `TaskClass` — deliberate Phase 2 deviation, document in Notes |
| C3 | harden | Module-location hedge (`<layer_a>` placeholder) — verified flat; commit to canonical path |
| C4 | nit | Story hedges PackageManager shape "(or `NewType`/`Enum`, whichever shipped)" — verified `Literal`; delete the hedge |
| C5 | nit | Notes conflates `as X` mypy contract with `__all__` runtime contract — clarify they are complementary, both required |
| C6 | nit | `types/` as new top-level package not in ADR-0006's enumeration — but ADR-0006's list was domain-packages-only; `types/` is kernel-tier (no new arch decision required) |
| C7 | accept | 9 ACs for 4 lines of impl — proportionate to load-bearing position; family discipline (S1-01 12 ACs, S1-04 22 ACs) sets precedent. Rule 2 not violated |

### Design Patterns (verdict: PATTERNS-HARDEN — 4 findings, all harden/nit)

| ID | Sev | Pattern | Finding |
|----|----|---|---|
| P1 | harden | symmetric kernel-surface | `__all__` ⊇ → ==; family closure |
| P2 | harden | sibling-family symmetric (module purity) | `identifiers.py` is kernel-most-imported; no purity AC |
| P3 | nit | same-object re-export invariant | identity passthrough through `__init__` for the four NewTypes |
| P4 | nit | intentional openness for registry-keyed plugin extension | open NewType vs closed Literal rationale missing from Notes |

Findings rejected under Rule 2 (Simplicity First):
- One-file-per-identifier — four below rule-of-three; central file is correct.
- `@register_identifier` decorator — pattern soup; reject.
- Smart-constructor `Result[IndexName, ParseError]` — already correctly out-of-scope.
- Move `PackageManager` into kernel — violates Rule 3 and Phase 1 ADR-0013; correctly chosen re-export-from-feature.
- Dataclass/Pydantic wrapping — explicit Notes warning preserved.

## Stage 3 — Researcher

**SKIPPED.** No `NEEDS RESEARCH` findings. Every gap was answerable from:
- Arch design + production ADR-0033 (canonical pattern)
- Verified repo state (`grep` for `ProbeId`, `cat` for Phase 1 PackageManager location)
- Sibling-story validation precedent (S1-04 `Result` type routing, AST scan, exact-set `__all__`)
- Standard pytest subprocess pattern for compile-fail tests (well-known; no canonical-pattern lookup needed)

## Stage 4 — Synthesizer + Editor

### Conflict resolution

No conflicts between critics. All four critics' findings converged on the same closure pattern (family-symmetric discipline). Priority order (Consistency > Coverage > Test-Quality > Design-Patterns) was not exercised — every recommendation cleared every lens.

### Edits applied

The story file was edited surgically (no rename; no removal of original content):

1. **Title** — appended `, ProbeId` to the newtype list.
2. **Status line** — appended "HARDENED 2026-05-15 (validator); AC-1b/3a/3b/4a/5b/6a/7a/8a/9a remediation required" with a pointer to this report and to `_attempts/S1-05.md`.
3. **New section: `Validation notes (2026-05-15)`** — between Status and Evidence; summarizes the 13 findings (2 block + 11 harden/nit) with one-line each.
4. **New section: `Hardening remediation`** — 12 additive ACs (AC-1b / 3a / 3b / 4a / 5b / 6a / 7a / 8a / 9a / 9b / 9c / 9d). Each is queued for an XS follow-up commit; none retroactively invalidate the 9 original ACs.
5. **Updated section: `References — where to look`** — added cross-references to S1-04's hard ProbeId requirement (lines 51 / 78 / 656); pinned the verified-current Phase 1 path; pinned the verified-current `ProbeId` absence; added production ADR-0033 file-name correction (`0033-domain-modeling-discipline.md`, not `0033-typed-identifiers.md` which was the original story's stale name); added the production ADR-0033 §1 `TaskClass` vs `TaskClassId` naming-deviation note.
6. **Updated section: `Goal`** — restated to five newtypes + the four assertions (a) location, (b) distinctness/`__name__`, (c) executed-CI mypy gate, (d) module-purity.
7. **Original ACs (AC-1 through AC-9)** — kept verbatim but marked `[x]` (all PASS as merged) with appended one-line remediation pointers (e.g., AC-3 "⊇; remediation AC-3a/3b tightens to ==").
8. **Updated section: `Implementation outline`** — added step 6 ("Remediation pass") describing the surgical follow-up.
9. **Updated section: `TDD plan`** — kept original tests verbatim for historical context; added a "Remediation tests" subsection with the full AC-1b/3a/3b/4a/5b/7a/8a/9a unit-test code and a "New file" subsection with the AC-6a subprocess meta-test in full.
10. **Updated section: `Files to touch`** — added `tests/unit/types/test_identifiers_mypy_negative.py` row.
11. **Updated section: `Out of scope`** — removed the false claim that `ProbeId` exists in Phase 0; added the Phase 3+ identifier enumeration (`AdapterId`, `RecipeId`, …) with extension-by-addition guidance; added the `Closing IndexName/SkillId/TaskClassId/ProbeId to Literal` rejection-with-rationale.
12. **Updated section: `Notes for the implementer`** — expanded with: production ADR-0033 `TaskClass` deviation note; open-NewType-vs-closed-Literal rationale for registry-keyed identifiers; AST source-scan rationale; subprocess mypy meta-test as the load-bearing CI gate; cross-story dependency on S1-04 explicit.

### Edits NOT applied (rejected)

- **Retract the GREEN merge / mark Status: Ready.** The 9 original ACs all PASS as merged. The remediation queue is additive. Retraction would hide work, violate Rule 12 (Fail loud — by erasing what shipped), and create a misleading audit trail. Status stays "Done (GREEN ...) — HARDENED (validator); remediation required".
- **Add a `@register_identifier` decorator.** Pattern soup; Rule 2 rejects. Documented in Patterns critic findings as rejected.
- **Move `PackageManager` into the kernel.** Violates Rule 3 + Phase 1 ADR-0013. Re-export-from-feature is the correct direction.
- **Smart-constructor `Result[IndexName, ParseError]`.** Correctly out-of-scope; production ADR-0033 §2 lives at parser boundaries, not at `NewType` declaration sites.
- **Hypothesis property-based tests.** Mutation space is categorical, not value-space. Unit-test set is exhaustive. Documented in Notes as deliberate rejection.

## Verdict — HARDENED with remediation queue

The story file is now ready to serve as the canonical spec for the remediation pass. The remediation commit is XS-sized (~80 LOC of new test code, ~3 LOC of new src code for `ProbeId`, one new file `test_identifiers_mypy_negative.py`, surgical edits to `__init__.py` and `identifiers.py`). After remediation lands:

- S1-04 will be able to `from codegenie.types.identifiers import ProbeId` without `ImportError`.
- The story's load-bearing claim — that mypy `--strict` rejects cross-NewType assignment — will be CI-enforced, not prose-documented.
- The family-symmetric discipline (exact `__all__`, AST source-scan, module-purity, identity-through-`__init__`, pairwise distinctness, `__name__` pinning) will parity with S1-01 / S1-03 / S1-04.

Story is now ready for `phase-story-executor` (remediation pass) or — given the existing GREEN — a direct surgical commit by the executor on the queued AC list.
