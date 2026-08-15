# Validation report — S5-04 `PLUGINS.lock` entry + Chainguard catalog hash-fence placeholder

**Story:** `docs/phases/07-migration-task-class/stories/S5-04-plugins-lock-and-catalog-hash-placeholder.md`
**Validator run:** phase-story-validator, 2026-08-14
**Verdict:** **HARDENED** — real, fixable structural problems found and patched in place.

## Context brief (Stage 1)

- **What the story promises.** Land the first Phase-7 row in `plugins/PLUGINS.lock` for `distroless-migration--node--npm` (SHA-256 tree-digest) and plant a placeholder `tests/fence/test_phase7_chainguard_lookup_table_loads.py` that S9-02 will finalise once the catalog YAML is pinned.
- **What the phase's exit criteria demand** (`High-level-impl.md §Step 5`): (a) a `PLUGINS.lock` row for the new plugin present and CODEOWNERS-reviewed, (b) the Chainguard-lookup catalog hash-fence placeholder in place ready for Step 9 to finalise, (c) no regression on any other fence.
- **What the arch + ADRs constrain.**
  - Phase 3 ADR-0011: honest framing — the lock is integrity, not signature; CODEOWNERS is the social anchor; Sigstore deferred to Phase 11.
  - Phase 7 ADR-0009: byte-edit allowlist is a *code* fence; `plugins/PLUGINS.lock` is *data* attestation. Ownership of the exclusion decision was punted to S5-04 by the S5-01 story.
  - Phase 7 ADR-0010: Chainguard CVE-to-image catalog is a frozen YAML pinned by file hash; the file itself lands in S9-01, the hash pin in S9-02.
  - S5-01 (HARDENED, 2026-08-14) `AC-4.a` explicitly **excludes** `plugins/PLUGINS.lock` from `_LOCKED_SURFACE_GLOBS` and points at S5-04 as the owner of the exclusion. The AC-7 "pin the decision at implementation time" language in the original S5-04 draft is therefore already stale on arrival.
- **What is true on disk at validation time** (grounded, not inferred):
  - `plugins/PLUGINS.lock` is **not** `{}`. It reads `{"vulnerability-remediation--node--npm": "6b5b2b12ecba007f4329e92b2dff1209b19cbb1582312cd267e5a38d28060dfd"}` — Phase-3 S7-01 already landed the first concrete row.
  - The lockfile value format is **raw 64-lowercase-hex**, no `sha256:` prefix. This is dictated by `src/codegenie/types/parsers.py::parse_blob_digest` (regex `^[0-9a-f]{64}$`, `_hex64_match`), by `LockFile` (`RootModel[dict[PluginId, BlobDigest]]`), and by `Sha256TreeDigestVerifier`. A `"sha256:…"` value causes `LockFile.from_path` to return `Err(LockFileMalformed)`, which `load_plugins` propagates.
  - The typed error for tree-digest divergence is `IntegrityMismatch(kind="integrity_mismatch", plugin: PluginId, expected: BlobDigest, actual: BlobDigest)` — not a free-text "digest mismatch" string.
  - `plugins/distroless-migration--node--npm/` does not exist yet in `main`; its creation is scheduled for Phase-7 Step-4 (Steps S4-02 + S4-03 populate it via the alpine + distroless provenance adapters + `api.py`). S5-04 correctly depends on Step 4 having landed.
  - `.github/CODEOWNERS` already contains `plugins/PLUGINS.lock @Dannytrev21` (verified). AC-6 will report "no edit needed".

## Stage 2 — Critic findings

Four lenses were applied inline (context already loaded end-to-end during Stage 1; the story is small and every finding is high-confidence). Each finding is tagged `[block]` / `[harden]` / `[nit]` with the proposed fix.

### 2A — Coverage

| # | Finding | Severity |
|---|---|---|
| C1 | AC set does not include a **cross-plugin regression check**: after adding the second row, `load_plugins()` must still succeed for the pre-existing `vulnerability-remediation--node--npm` plugin. A JSON-formatter accident (e.g., swapping the wrong value in) could break the first plugin silently. | harden |
| C2 | AC-2 asserts `load_plugins()` succeeds but does not assert **the loaded report enumerates both plugins by id**. Weak intent — a bug that loads only one still passes. | harden |
| C3 | AC-3 amendment strings (`"Phase 7"`, `"distroless-migration--node--npm"`, `"sha256:"`) do not include a reference to `IntegrityMismatch` or the load-bearing runtime enforcement path. The README amendment should tie the new row to *why* the loader refuses on mismatch. | nit |
| C4 | No AC covers what happens if the digest is **shorter/longer than 64 hex** or contains **uppercase hex** — mutation-resistance gap that a copy-paste error could exploit. Covered defensively by `parse_blob_digest`'s Err path, but no S5-04 test asserts that path. | harden |
| C5 | AC-6 says CODEOWNERS "likely already covered" — but the check is deterministic. Grep for the exact literal string, don't hedge. (Already covered: `plugins/PLUGINS.lock @Dannytrev21`.) | nit |

### 2B — Test Quality

| # | Finding | Severity |
|---|---|---|
| T1 | AC-1.b regex is **`^sha256:[0-9a-f]{64}$`**. Correct regex against actual codebase is **`^[0-9a-f]{64}$`** (see `_HEX64_PATTERN` in `types/parsers.py`). Applied as-written, the AC-1.b test would fail on the first `pytest` run because the real file has no `sha256:` prefix. | **block** |
| T2 | AC-1's digest-value shape (`"sha256:<64-hex-chars>"`) contradicts the format `parse_blob_digest` accepts (64-hex only). Story-authored value would make `LockFile.from_path` return `Err(LockFileMalformed)`, breaking `load_plugins()` for the *existing* plugin too. | **block** |
| T3 | AC-2.a's error assertion says "typed error naming the plugin id + 'digest mismatch'". Actual variant is `IntegrityMismatch(kind="integrity_mismatch", plugin: PluginId, expected: BlobDigest, actual: BlobDigest)`. Assert by `kind` + `plugin` (structural) — not by a string-in-message check (brittle). | harden |
| T4 | Planted-tampering test (AC-2.a) uses `tmp_path` + a synthetic lock. Good functional-core split. But no test asserts the loader also correctly **rejects** the case where the lock names a plugin whose directory is absent (`MissingPluginDirectory`) or the case where the plugin id in the lock is not itself a valid `PluginId` (`LockFileMalformed`). Optional — S5-04's scope is the happy row + one negative. Note explicitly so it's a choice, not an omission. | nit |
| T5 | AC-4's two catalog tests are `xfail(strict=True)` at S5-04 landing. This means at landing time the tests exercise **nothing at all** — they merely reserve the file and the hand-off. Story acknowledges this in AC-5.c, but the AC-4.a "verified by `pytest --collect-only ...` reporting two collected items (both xfail-strict)" is the strongest observable check S5-04 can make. Add an explicit assertion that both items are *both* collected *and* marked `xfail(strict=True)` (not just one or the other) — otherwise a future refactor that drops `strict=True` slips through. | harden |
| T6 | AC-1.c compares the on-disk digest against the pinned digest. **Mutation-resistant**: mutate any plugin file → digest changes → AC-1.c red. Correct pattern. But the assertion should compare `BlobDigest` newtype values (typed compare), not raw strings, so `mypy --strict` catches a future accidental string-substitution. | harden |
| T7 | AC-4's `_CATALOG_SHA256_PLACEHOLDER` uses a `"sha256:0000…"` prefix. This is a **different** format from `BlobDigest` (single-file file-hash vs. tree-digest); making them look alike invites confusion. Two options — pick one deliberately: **(a)** drop the prefix (`"0000…"` raw 64-hex) to mirror `BlobDigest`; **(b)** keep the prefix and add a module-level `_HASH_PREFIX_INTENT: Final[str] = "sha256:"` with a docstring explaining why this hash is prefixed while `BlobDigest` is not. Pick (b) — the catalog hash is *not* a `BlobDigest` and marking the format deliberately different documents intent. | harden |

### 2C — Consistency

| # | Finding | Severity |
|---|---|---|
| K1 | Story context "Phase 3 shipped `PLUGINS.lock` empty (`{}`) — the first concrete row was reserved for Phase 7. This story lands that first row" is **stale**. Phase 3 S7-01 landed `vulnerability-remediation--node--npm` (verified — see `plugins/PLUGINS.lock`). This story lands the **second** row, not the first. Rewrite context + Goal to say "second concrete row / first Phase-7 row". | **block** |
| K2 | AC-1 says "updated from `{}`". Not `{}` any more — updated from `{"vulnerability-remediation--node--npm": "…"}`. Rewrite to "an additive key". | **block** |
| K3 | AC-7 "pin the decision at implementation time and document in `_attempts/S5-04.md`" — already pinned by S5-01 AC-4.a HARDENED (2026-08-14): `plugins/PLUGINS.lock` is EXCLUDED from `_LOCKED_SURFACE_GLOBS`. S5-04's AC-7 should now be a **verification** ("assert `_LOCKED_SURFACE_GLOBS` from `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` does not glob-match `plugins/PLUGINS.lock`") not a decision. Removes an operational hazard: the story would otherwise re-open a settled decision at implementation time. | **block** |
| K4 | Notes-for-implementer echoes the same open-question language as AC-7 ("Pin the decision and document in `_attempts/S5-04.md`. Surface the conflict explicitly per Rule 7") — remove the "decision needed" framing; keep the historical rationale so the executor knows why the exclusion exists. | harden |
| K5 | `plugins/PLUGINS.lock.README.md` still says "The lock ships empty (`{}`) in Phase 3. The first concrete plugin lands in S7-01". Phase-3 S7-01 landed. That README wording is stale even before S5-04 opens. S5-04 owns the follow-on amendment; add an AC to also correct the stale historical wording (one-line edit: "The lock shipped empty in Phase 3; Phase-3 S7-01 landed the first concrete row (`vulnerability-remediation--node--npm`); Phase-7 S5-04 lands the second row (`distroless-migration--node--npm`)"). | harden |
| K6 | Depends-on names only S5-01. S5-04 needs the plugin **directory** to exist (Step-4 stories S4-02 + S4-03 populate it via the alpine + distroless provenance adapters + `api.py`). Add S4-02 and S4-03 to Depends-on. | harden |
| K7 | Files-to-touch does not include `_lessons.md` — every executor story updates `_lessons.md` on close per the executor skill. Not a story-file omission per se; noted for the executor. | nit |

### 2D — Design Patterns

| # | Finding | Severity |
|---|---|---|
| D1 | The AC-4 catalog-hash mechanism is a **single-file file-hash pin**. Rule of three not met — there is currently only one catalog file in scope. Rule 2 (Simplicity First) wins over introducing a `@register_catalog_hash_pin` registry. Note explicitly in Notes so the executor doesn't invent premature abstraction. | harden |
| D2 | `compute_plugin_tree_digest` is already the single source of truth for tree hashing (functional-core / imperative-shell split — see loader `_collect_plugin_files` + `tree_digest_of_files`). Story correctly reuses it (AC-1.a). Note explicitly that a one-off `hashlib.sha256` MUST NOT be substituted (would diverge from the loader's walk order). Story already says this in Notes — good. | nit |
| D3 | Loader/verifier separation is already hexagonal: `PluginVerifier` Protocol, `Sha256TreeDigestVerifier` default, Phase 11 substitutes `SigstoreVerifier` at the same seam. S5-04 does not need to add any new abstraction here. Note explicitly (so the executor doesn't try to be clever). | nit |
| D4 | Consider a `@dataclass(frozen=True) class PluginLockRow` for the (id, digest) pair as domain vocabulary. **Reject** — `dict[PluginId, BlobDigest]` already carries typed identifiers via the `LockFile` `RootModel`; a wrapper adds indirection without narrowing behaviour. Rule 2 wins. | nit (rejected) |
| D5 | Cross-cutting extension seam for "additional data-attestation files" (catalog YAML today, others tomorrow) — the mechanism is fine as inline `Final[str]` today, but future rows will echo the same shape. Not the rule-of-three threshold yet. Elevate to a note ("if a third similar hash-pin lands, extract"). | harden (as a note, not an AC) |

**Nothing tagged `NEEDS RESEARCH`** — Stage 3 skipped (research without a question is token-burn).

## Stage 4 — Synthesizer resolution

Conflict priority `Consistency > Coverage > Test-Quality > Design-Patterns` produced no cross-critic contradictions. All findings translated into concrete story edits. Applying in order:

**Blockers (must-fix before executor):**
1. T1 + T2 + K1 + K2 + K3 all resolved by (a) rewriting Context to name the second-row reality, (b) removing the `sha256:` prefix from every digest value + regex, (c) rewriting AC-7 as a verification of S5-01's already-landed exclusion.

**Hardenings:**
2. C1 + C2 — AC-2 gains an explicit `LoadReport` two-plugin enumeration + a positive assertion the *existing* plugin still loads.
3. C4 — AC-1.b regex tightened to lowercase-hex-only (matches `_HEX64_PATTERN` verbatim).
4. C5 — AC-6 collapsed from "likely covered" to "verified covered by rule `plugins/PLUGINS.lock @Dannytrev21`".
5. T3 — AC-2.a asserts on `IntegrityMismatch` kind + plugin field, not string.
6. T5 — AC-4.a gains a "both items collected AND both marked xfail(strict=True)" check.
7. T6 — AC-1.c typed compare on `BlobDigest`.
8. T7 — Prefix kept, documented as deliberate. Added `_HASH_PREFIX_INTENT` sentinel with rationale docstring.
9. K5 — AC-3 gains a bullet: also correct the stale "Phase 3 ships empty" wording in README.
10. K6 — Depends-on adds S4-02 + S4-03.

**Design notes (added to Notes-for-implementer):**
11. D1 + D5 — Do NOT introduce a `@register_catalog_hash_pin` registry; if a third similar hash-pin ever lands, that's the moment to extract.
12. D3 — Do NOT modify `PluginVerifier`; the Sigstore substitution seam is already correct.

## Files edited

- `docs/phases/07-migration-task-class/stories/S5-04-plugins-lock-and-catalog-hash-placeholder.md` — Status flip to HARDENED; front-matter, Context, Goal, ACs 1-8, Implementation outline, TDD plan, Files to touch, Notes for implementer all touched. Full before/after per finding above; the story file's `## Validation notes` block records the summary.

## Verdict

**HARDENED.** No structural rescue needed; the story's shape is right — plant a `PLUGINS.lock` row + a catalog hash-fence placeholder + the CODEOWNERS + README plumbing. Three blockers (all `sha256:` prefix and stale "empty lock" claim) were surface issues induced by writing the story against Phase-3-past state rather than current-`main` state; they are fully corrected.

**Ready for phase-story-executor.**
