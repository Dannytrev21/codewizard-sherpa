# Story S9-03 — Catalog refresh process documentation + Sigstore-deferral cross-reference

**Step:** Step 9 — CVE-to-image catalog YAML + loader + file-hash fence
**Status:** Ready
**Effort:** S
**Depends on:** S9-01 (the catalog YAML + loader whose refresh workflow this doc describes; the doc references the file path, the loader's contract, and the seeded-row precedent S9-01 ships).
**ADRs honored:** Phase 7 ADR-0010 (CVE-to-image lookup ships as plugin-internal frozen YAML; CODEOWNERS-reviewed PR is the named refresh workflow; Sigstore upgrade is deferred — this doc is the deferral's documented home); Phase 7 ADR-0011 (no Chainguard credential class — operators pulling for verification use public-registry endpoints; the doc explicitly does NOT introduce a credential workflow); Phase 3 ADR-0011 (honest framing — the doc explicitly disclaims cryptographic-signature properties); Phase 7 ADR-0009 (the doc names the two CODEOWNERS-gated files an operator touches in a refresh PR: the YAML + the fence's pinned-hash line).

## Context

S9-01 lands the YAML. S9-02 pins the file-hash fence with the real sha256. This story closes the operator-facing loop: write `docs/phases/07-migration-task-class/catalog-refresh-process.md` — the human-readable runbook an operator follows when a new Chainguard distroless image becomes available, when a CVE-to-image mapping needs updating, or when a stale entry needs removing. The doc is the canonical answer to the question "I want to add a new row to the catalog — what do I do?" It names the two files to edit (the YAML and the fence's pinned-hash line), the CODEOWNERS gate, the verification one-liner, the PR template checklist, and the explicit deferral of cryptographic-signature properties to a future ADR.

This is a **doc-only story.** There is no Python code change, no test code change (S9-02's fence is the executable counterpart; this doc is the human counterpart). The story's "test" is a smoke verification that the doc exists at the canonical path, references the right ADRs by number, and contains the expected sections (intro, who can publish, how-to-update workflow, verification step, CODEOWNERS gating, future Sigstore upgrade path). The story is intentionally small; the load-bearing work is precision of wording — over-claim the integrity property and you violate Phase 3 ADR-0011, under-document the workflow and you make S9-02's fence harder to use in practice.

**Why a doc instead of a runbook in the test docstring.** Operator-facing process documentation is consumed by humans (likely on the road, on a phone, looking at the GitHub UI before opening the refresh PR). Burying it in a Python module's docstring locks it to engineers with checkouts. The doc lives under `docs/phases/07-migration-task-class/` so it ships with mkdocs and surfaces in the documentation site. The fence file's module docstring (S9-02) links to this doc, not the other way around — one source of truth, one canonical home.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Edge cases row 9` — "CVE-to-image YAML signature poisoned (file edited outside CODEOWNERS PR)" — the threat model this refresh process operationalizes.
  - `../phase-arch-design.md §Tradeoffs (consolidated) row "Frozen YAML CVE-to-image lookup"` — names "operator-side tamper detection via file-hash fence" + the deferred Sigstore upgrade.
- **Phase ADRs:**
  - `../ADRs/0010-chainguard-cve-image-lookup-frozen-yaml.md` — read cover-to-cover. §Decision names the refresh PR workflow; §Consequences names the two-file PR (YAML + pinned hash); §Reversibility names the deferred Sigstore upgrade path. This doc is the operator-facing translation of that ADR.
  - `../ADRs/0011-no-chainguard-credential-class.md` — read §Decision + §Consequences. The doc explicitly does NOT add a credential workflow; pulls for verification are unauthenticated.
  - `../ADRs/0009-phase-7-byte-edit-allowlist-fence.md` — the byte-edit allowlist; the doc names that the catalog YAML and the fence file are CODEOWNERS-gated (not part of the 10-row code allowlist), so legitimate refreshes pass the fence.
- **Sibling stories:**
  - `S9-01-chainguard-catalog-and-loader.md` — the YAML's location, schema, and Pydantic loader; the doc cites these by path.
  - `S9-02-chainguard-catalog-file-hash-fence.md` — the fence file whose pinned-hash line the operator updates; the doc's "how to update" section names this file by path and the constant name `_CATALOG_SHA256_PINNED`.
  - `S5-04-plugins-lock-and-catalog-hash-placeholder.md` — the precedent. Phase 3's `plugins/PLUGINS.lock.README.md` is the parallel doc for the directory-attestation fence; mirror its voice, structure, and honest-framing wording.
- **Production precedent (READ BEFORE WRITING — Rule 8):**
  - `plugins/PLUGINS.lock.README.md` — the canonical "integrity-attestation doc" voice for this repo. Mirror its structure: short intro, honest-framing section, regeneration command, CODEOWNERS gating, deferred-Sigstore note, future-upgrade path. Do NOT invent a different shape; the parallel is intentional and helps future readers context-switch between the two integrity-attestation regimes.
  - `docs/contributing.md` (if present, for repo doc voice) — match the prose voice.
- **Production ADRs:**
  - `../../../production/design.md §2.6 — Organizational uniqueness as data, not prompts` — the parent rule. Catalog is data; refresh is a PR; humans review.
  - `../../../production/design.md §2.8 — Humans always merge` — the parent rule for the CODEOWNERS gate.
- **Existing code (READ BEFORE REFERENCING):**
  - `.github/CODEOWNERS` — verify the catalog YAML path is covered; the doc cites the actual rule by line if it exists. If S5-04 + S9-01 already wired CODEOWNERS coverage (likely), reference; if not, the doc names the missing rule as a precondition.

## Goal

Land `docs/phases/07-migration-task-class/catalog-refresh-process.md` — a precise, honest, operator-facing runbook for refreshing the Chainguard CVE-to-image catalog. The doc names the two files an operator edits (catalog YAML + fence pinned-hash), the verification one-liner, the CODEOWNERS gate, the PR template checklist, and the explicit deferral of cryptographic-signature properties to a future ADR (the Phase 7 ADR-0010 §Reversibility path). The doc is structured to be readable end-to-end in under 5 minutes and copy-pasteable for the verification commands.

## Acceptance criteria

### Doc existence + canonical location

- [ ] AC-1 — `docs/phases/07-migration-task-class/catalog-refresh-process.md` exists. The path matches the pointer S9-02's fence module docstring uses (verify by grepping S9-02's file for the path; the strings must match exactly).
- [ ] AC-2 — The doc is written in Markdown, UTF-8, LF line endings, ends with a single trailing newline, contains no tab characters, and renders correctly under `mkdocs build --strict` (verified by running `make docs` and confirming exit 0).
- [ ] AC-3 — The doc is added to the mkdocs navigation (`mkdocs.yml`) under the Phase 7 documentation section if Phase 7 has a nav entry; if Phase 7's docs are auto-collected by mkdocs config (`docs_dir` glob), the file is auto-picked up — verify by checking `make docs` lists the new page in the built site index.

### Required sections (presence + ordering)

The doc has the following H2 sections in this order. A smoke test (AC-13) verifies the headings literally appear:

- [ ] AC-4 — `## Purpose` — 2–3 sentences naming the catalog YAML, the threat model (operator-side tamper detection), the integrity-attestation framing, and the explicit non-claim of cryptographic-signature properties.
- [ ] AC-5 — `## Who can publish` — names the CODEOWNERS group(s) that gate the catalog YAML path. Names that any contributor can OPEN a refresh PR; only CODEOWNERS-listed reviewers can APPROVE the merge. Cross-references `.github/CODEOWNERS` by relative path.
- [ ] AC-6 — `## When to refresh` — names the operational triggers: (a) a new Chainguard distroless image becomes available for a known CVE; (b) an existing recommendation's `image_digest` is rotated by Chainguard (advisory-driven); (c) a stale entry is removed because the upstream advisory is withdrawn. Names the cadence (weekly-ish per Phase 7 ADR-0010 §Tradeoffs) and the explicit non-cadence (not driven by a clock; driven by Chainguard advisories or operator discovery).
- [ ] AC-7 — `## How to update — step-by-step` — the mechanical recipe. Numbered list, copy-pasteable. The steps are exactly:
  1. Edit `plugins/distroless-migration--node--npm/data/chainguard_image_recommendation_table.yaml` — add / amend / remove the entry. Schema fields named verbatim per S9-01's loader: `cve_id`, `recommended_chainguard_image`, `image_digest`, `notes`. `image_digest` MUST be `sha256:<64-hex>` (the smart constructor rejects anything else).
  2. Recompute the file's sha256: `python -c "import hashlib, pathlib; print('sha256:' + hashlib.sha256(pathlib.Path('plugins/distroless-migration--node--npm/data/chainguard_image_recommendation_table.yaml').read_bytes()).hexdigest())"` (single one-liner; copy-pasteable).
  3. Update `tests/fence/test_phase7_chainguard_lookup_table_loads.py::_CATALOG_SHA256_PINNED` to the new value. Update the inline `# Pinned against catalog YAML at git <short-sha>` comment to the new git short-sha if convenient (informational only).
  4. Run `pytest tests/fence/test_phase7_chainguard_lookup_table_loads.py` locally — all three tests green.
  5. Run `make check` — green; no regressions.
  6. Open a PR touching exactly two files: the catalog YAML and the fence file. CODEOWNERS auto-requests review from the gating group; merge gated on approval + green CI.
- [ ] AC-8 — `## CODEOWNERS gating` — names the gate explicitly: the `.github/CODEOWNERS` rule(s) covering the catalog YAML path and the fence file's path. Names what happens if a refresh PR touches additional files outside the two-file scope (CODEOWNERS may request other reviewers; the PR template's "this is a catalog refresh" checkbox is the operator's signal). Names the failure mode: an edit to the catalog YAML without an accompanying fence update fails CI on `test_catalog_hash_matches_pinned`; an edit to the fence's pinned hash without a corresponding YAML byte change also fails (same test, different mismatch direction).
- [ ] AC-9 — `## Verification` — restates the local-verification one-liner from AC-7 step 4, plus the loader round-trip command (`pytest tests/unit/plugins/distroless_migration_node_npm/test_catalog_loader.py`). Names that CI runs both on every PR; local verification is a pre-PR sanity check, not a substitute.
- [ ] AC-10 — `## Honest framing — what this process attests` — explicit Phase 3 ADR-0011 carry-forward section. Verbatim states: "This refresh process is integrity attestation, NOT cryptographic signature." Names the social anchor (CODEOWNERS-reviewed PR) and the cryptographic non-anchor (no Sigstore, no GPG, no operator identity). Names the threat-model boundary: accidental corruption + partial-merge errors + unreviewed file changes are detected; a determined adversary with merge rights on `main` defeats the process trivially. Mirrors the `plugins/PLUGINS.lock.README.md §"Honest framing"` voice.
- [ ] AC-11 — `## Future upgrade — Sigstore-bundled signed artifact (deferred)` — names the Phase 7 ADR-0010 §Reversibility upgrade path: a future ADR may bundle the catalog with a Sigstore signature; the loader grows to verify a `.sigstore` companion file; CODEOWNERS-gating remains as the social anchor while cryptographic verification is added as the additional defense. Names that this upgrade is **deferred, not committed** — opening it requires a fresh ADR with a documented threat model that justifies the additional infrastructure cost. Cites Phase 7 ADR-0010 §Reversibility by anchor link.
- [ ] AC-12 — `## Related ADRs and stories` — bulleted list with relative paths and one-line descriptions for: Phase 7 ADR-0010, Phase 7 ADR-0011, Phase 7 ADR-0009, Phase 3 ADR-0011 (honest framing), S9-01, S9-02, S5-04. Each reference is a clickable markdown link from the doc's location.

### Smoke verification ("test" for a doc-only story)

- [ ] AC-13 — A doc-shape smoke test lives at `tests/unit/docs/test_catalog_refresh_process_doc.py` (create the `tests/unit/docs/` directory if it does not exist; mirror existing doc-shape tests if any precedent — search for `tests/.*doc.*` first to avoid duplicating an existing pattern). The test asserts:
  - **AC-13.a** The file `docs/phases/07-migration-task-class/catalog-refresh-process.md` exists.
  - **AC-13.b** The file contains all eight required H2 headings in order (`## Purpose`, `## Who can publish`, `## When to refresh`, `## How to update — step-by-step`, `## CODEOWNERS gating`, `## Verification`, `## Honest framing — what this process attests`, `## Future upgrade — Sigstore-bundled signed artifact (deferred)`, `## Related ADRs and stories`).
  - **AC-13.c** The file contains literal-string references to all required ADRs by number: `ADR-0010`, `ADR-0011`, `ADR-0009` (Phase 7), and `ADR-0011` (Phase 3 — must be disambiguated either by path or by saying "Phase 3 ADR-0011").
  - **AC-13.d** The file contains literal-string references to the file paths the operator edits: `plugins/distroless-migration--node--npm/data/chainguard_image_recommendation_table.yaml` and `tests/fence/test_phase7_chainguard_lookup_table_loads.py`.
  - **AC-13.e** The file contains the literal string `_CATALOG_SHA256_PINNED` (the constant name an operator updates).
  - **AC-13.f** The file contains the literal phrase `integrity attestation` and does NOT contain the words `cryptographic signature`, `digitally signed`, `tamper-proof`, or `non-repudiable` (the honest-framing discipline — over-claim detection).
- [ ] AC-14 — The doc-shape smoke test runs under `pytest tests/unit/docs/` and is fast (< 100 ms; pure file read + string search). It is collected under `make check`.

### Cross-references stay valid

- [ ] AC-15 — Every relative-path link in the doc resolves to an existing file. A `pytest` smoke check (part of AC-13's test file) walks the doc's relative links and asserts each target exists. If a sibling story is not yet written when this doc lands (unlikely — only S9-02 is a hard dep, and the doc may forward-reference Steps 10–12), gate forward references behind a "see also" framing rather than a hard link.
- [ ] AC-16 — The doc does NOT link to any URL outside the repo (no `https://chainguard.dev/...`, no `https://github.com/sigstore/...`). External links go stale and erode trust in the doc; if Chainguard-specific reference is needed, name the canonical project doc + cite the version, but do not link out. (If a future ADR ratifies external linking conventions, this rule loosens; for Phase 7, conservative.)

### Mkdocs + voice + format

- [ ] AC-17 — `make docs` green (`mkdocs build --strict` exits 0; no broken links per mkdocs' strict mode; no unrecognized headings).
- [ ] AC-18 — The doc's prose voice matches the repo's existing documentation voice. Read `plugins/PLUGINS.lock.README.md` and Phase 7 ADR-0010 first; the doc's voice should be recognizable as the same author-pool. Plain English; no marketing language; no hedging; no over-claim; no jargon unless cross-referenced.
- [ ] AC-19 — `ruff format`, `ruff check`, `mypy --strict` on the smoke-test file clean. The smoke test imports only `pathlib`, `re`, and `pytest`; no other dependencies.

## Implementation outline

1. **Read the precedents.** `plugins/PLUGINS.lock.README.md` is the parallel doc for the directory-attestation regime; this story's doc is its catalog-file-attestation counterpart. Read Phase 7 ADR-0010 + ADR-0011 + ADR-0009 + Phase 3 ADR-0011 cover-to-cover. Note the canonical phrases ("integrity attestation, not cryptographic signature"; "CODEOWNERS social anchor"; "deferred Sigstore upgrade").
2. **Verify dependencies landed.** S9-01's catalog YAML exists; S9-02's fence file exists with `_CATALOG_SHA256_PINNED`. If either is missing, this story is blocked — surface immediately.
3. **Draft the doc.** Eight H2 sections in the AC-4 → AC-12 order. Aim for ~150–250 lines of Markdown total (under 5 minutes to read end-to-end). Each H2 is 2–6 paragraphs; the "How to update" section is a 6-step numbered list with copy-pasteable command blocks.
4. **Mirror the honest-framing voice verbatim where appropriate.** Cite Phase 3 ADR-0011 as the canonical source; quote the "integrity attestation, not cryptographic signature" framing in §Honest framing.
5. **Wire the relative-path links.** Every ADR + sibling-story reference is a relative-path markdown link. Verify each link resolves on the local filesystem before committing.
6. **Add the mkdocs nav entry (AC-3) if needed.** Inspect `mkdocs.yml`; if Phase 7's docs are auto-collected by glob, no edit needed. If explicit nav is required, add one line under the Phase 7 section.
7. **Write the doc-shape smoke test.** `tests/unit/docs/test_catalog_refresh_process_doc.py`. Pure file read + string + regex checks; ~30–50 LOC. Cover AC-13.a → AC-13.f + AC-15.
8. **Run `make docs` — green.** Run `pytest tests/unit/docs/test_catalog_refresh_process_doc.py` — green.
9. **Run `make check` — green.** Story done.

## TDD plan — red / green / refactor

### Red — failing test first

Write `tests/unit/docs/test_catalog_refresh_process_doc.py` BEFORE the doc exists:

```python
"""Smoke test for the Phase 7 catalog refresh process doc (S9-03)."""
from pathlib import Path
import re
import pytest

_DOC_PATH = Path("docs/phases/07-migration-task-class/catalog-refresh-process.md")

_REQUIRED_HEADINGS_IN_ORDER: tuple[str, ...] = (
    "## Purpose",
    "## Who can publish",
    "## When to refresh",
    "## How to update — step-by-step",
    "## CODEOWNERS gating",
    "## Verification",
    "## Honest framing — what this process attests",
    "## Future upgrade — Sigstore-bundled signed artifact (deferred)",
    "## Related ADRs and stories",
)

_REQUIRED_LITERALS: tuple[str, ...] = (
    "ADR-0010",
    "ADR-0011",
    "ADR-0009",
    "Phase 3 ADR-0011",
    "plugins/distroless-migration--node--npm/data/chainguard_image_recommendation_table.yaml",
    "tests/fence/test_phase7_chainguard_lookup_table_loads.py",
    "_CATALOG_SHA256_PINNED",
    "integrity attestation",
)

_FORBIDDEN_OVERCLAIM_LITERALS: tuple[str, ...] = (
    "cryptographic signature",
    "digitally signed",
    "tamper-proof",
    "non-repudiable",
)

def test_catalog_refresh_process_doc_exists() -> None:
    assert _DOC_PATH.exists(), f"Catalog refresh process doc missing at {_DOC_PATH}"

def test_required_headings_present_and_ordered() -> None:
    text = _DOC_PATH.read_text()
    last_idx = -1
    for heading in _REQUIRED_HEADINGS_IN_ORDER:
        idx = text.find(heading)
        assert idx != -1, f"Required heading missing: {heading}"
        assert idx > last_idx, f"Heading out of order: {heading}"
        last_idx = idx

def test_required_literals_present() -> None:
    text = _DOC_PATH.read_text()
    for literal in _REQUIRED_LITERALS:
        assert literal in text, f"Required literal missing: {literal}"

def test_no_overclaim_wording() -> None:
    text = _DOC_PATH.read_text()
    for forbidden in _FORBIDDEN_OVERCLAIM_LITERALS:
        assert forbidden not in text, (
            f"Honest-framing violation — forbidden over-claim wording present: "
            f"{forbidden!r}. Phase 3 ADR-0011 wording is canonical; rewrite using "
            f"'integrity attestation' framing."
        )
```

Run: `pytest tests/unit/docs/test_catalog_refresh_process_doc.py -x` — expect `FileNotFoundError` / `AssertionError` (doc does not exist). This is the red bar.

### Green — minimum impl

Write the doc per the eight-section structure. Verify each section satisfies its corresponding AC. Re-run the smoke test. Iterate until green. Run `make docs` — green.

### Refactor — clean up

- Confirm prose voice matches `plugins/PLUGINS.lock.README.md` — no marketing language, no hedging, no over-claim. Read both docs side-by-side; if the new doc reads as a different author, rewrite.
- Confirm every relative-path link resolves. The doc lives at `docs/phases/07-migration-task-class/catalog-refresh-process.md`; ADR links are `./ADRs/<file>.md`; story links are `./stories/<file>.md`; production ADR links are `../../production/adrs/<file>.md`.
- Confirm the "How to update" section's command blocks are copy-pasteable in full — no `<placeholder>` text the operator has to mentally substitute except the literal sha256 value and the optional git short-sha.
- Strip any words from the forbidden-literals list (AC-13.f). The smoke test enforces this; if it fires during refactor, the wording fix is the right move.

## Files to touch

| Path | Why |
|---|---|
| `docs/phases/07-migration-task-class/catalog-refresh-process.md` | The doc this story creates. Eight H2 sections; ~150–250 lines; mkdocs-strict compliant; honest-framing voice. |
| `tests/unit/docs/test_catalog_refresh_process_doc.py` | Doc-shape smoke test. Verifies existence + heading presence + literal references + over-claim wording absence. |
| `tests/unit/docs/__init__.py` | Empty package marker if the directory does not already exist. |
| `mkdocs.yml` | One additive nav entry under the Phase 7 section IF Phase 7's docs are NOT auto-collected by glob. Inspect first; edit only if needed. |

**No other files edited.** This story does NOT touch the catalog YAML (S9-01), the loader (S9-01), the fence file (S9-02), the `.github/CODEOWNERS` file (S5-04 + S9-01 own that), or any ADR (the ADRs are read; they are not amended).

## Out of scope

- **The catalog YAML content.** S9-01's territory. The doc names the file by path; it does not enumerate the seeded rows or recommend specific CVE-to-image mappings (data-collection work is operator-side, not doc-side).
- **The fence file's pinned hash.** S9-02's territory. The doc names the constant `_CATALOG_SHA256_PINNED` and the file path; it does not duplicate the value (which is git-tracked and dynamic per refresh).
- **The Sigstore upgrade itself.** Phase 7 ADR-0010 §Reversibility is the upgrade path; this doc names that path as deferred and points at the ADR. Writing the actual Sigstore-loader code, designing the `.sigstore` companion format, defining the operator identity, etc. — all out of scope. The doc's §Future upgrade section is a one-paragraph forward pointer, not a design.
- **A Chainguard credential workflow.** Phase 7 ADR-0011 rules this out entirely. The doc explicitly does NOT add a "publishing operator authenticates to Chainguard" step; pulls for verification are unauthenticated against `cgr.dev/chainguard/*`.
- **Automated catalog-refresh tooling (`codegenie catalog refresh <cve>`).** Manual `hashlib.sha256(...)` + paste-into-constant is the documented Phase 7 mechanism. Automated tooling is Phase 11 territory; the doc names the manual workflow only.
- **Cross-language catalog (Python, Java, etc.).** Phase 7's catalog is Node-and-npm-scoped per S9-01's plugin tree (`plugins/distroless-migration--node--npm/`). Phase 8+ adds new language/ecosystem plugins; each gets its own catalog and its own refresh process doc by precedent. This doc is Phase 7's; future docs are Phase 8+'s job.
- **Operator on-call rotation / SLA for refresh response.** Out of scope — this doc names the mechanical workflow; the human process around it (who's on-call, how fast advisories get triaged) is an organizational concern documented elsewhere.

## Notes for the implementer

- **Read `plugins/PLUGINS.lock.README.md` first.** That is the canonical voice for an integrity-attestation doc in this repo. The new doc's eight-section structure is intentionally parallel to it; readers context-switching between the two regimes (directory-attestation vs. single-file-attestation) get cognitive continuity. Diverge from that voice only with explicit Rule 7 justification.
- **Honest framing is non-negotiable.** Phase 3 ADR-0011 is the canonical source. The forbidden-literals list in the smoke test (`cryptographic signature`, `digitally signed`, `tamper-proof`, `non-repudiable`) is the enforcement mechanism — if the test fires during refactor, the wording fix is the right move, not loosening the test. Surface conflicts via Rule 7; do not silently average the over-claim and honest-framing patterns.
- **Don't pre-shape the Sigstore upgrade.** Phase 7 ADR-0010 §Reversibility names the upgrade as deferred; the doc's §Future upgrade is a one-paragraph forward pointer, not a design. If you find yourself sketching the `.sigstore` companion format, the loader's verification logic, or the operator's identity workflow, stop — that's a future ADR's job. Rule 2: cheapest abstraction; the cheapest is the one not shipped.
- **Copy-pasteable commands.** The §How to update section's command blocks must be runnable verbatim from any modern shell with `python3` + `pytest` + `make` in `PATH`. Test the commands locally before landing the doc; a doc with a broken command erodes operator trust faster than a missing doc.
- **The smoke test is the load-bearing verification.** A doc-only story without an executable assertion is a story that drifts. AC-13's literal-string + heading-order checks are the minimum bar; the over-claim-wording check (AC-13.f) is the integrity property an automated test can enforce that prose review may miss. Do not skip the smoke test; do not weaken it.
- **No external URLs.** AC-16. External links go stale; they erode trust in the doc; they encourage operators to chase links instead of running the documented commands. If a Chainguard-specific reference is needed, name the project + the version in prose without a URL. Phase 8+ may revisit if external linking conventions are ratified by ADR.
- **One canonical home.** S9-02's fence file's module docstring points at THIS doc by relative path. If the doc's filename or location changes during refactor, update S9-02's docstring in lockstep — but the canonical filename is `catalog-refresh-process.md` at `docs/phases/07-migration-task-class/`; changes to that pair are an ADR-level conversation, not a quiet rename.
- **Read AC-13's forbidden-literals list before drafting.** The list is short: `cryptographic signature`, `digitally signed`, `tamper-proof`, `non-repudiable`. Drafting prose with those words and then having to revise wastes effort; draft using the honest-framing vocabulary from the start (`integrity attestation`, `CODEOWNERS-gated`, `tamper-detection`, `social anchor`, `deferred Sigstore upgrade`). The canonical phrases are in `plugins/PLUGINS.lock.README.md` and Phase 3 ADR-0011 — mine them.
