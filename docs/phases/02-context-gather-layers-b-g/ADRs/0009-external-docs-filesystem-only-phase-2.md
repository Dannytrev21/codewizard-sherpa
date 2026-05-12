# ADR-0009: `ExternalDocsProbe` is filesystem-only in Phase 2; URL/Confluence/Notion fetch deferred

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** scope · ssrf · network-policy · phase-evolution · localv2-conformance
**Related:** [Phase 0 ADR-0006](../../00-bullet-tracer-foundations/ADRs/0006-subprocess-allowlist.md), [Phase 1 ADR-0008](../../01-context-gather-layer-a-node/ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md), ADR-0003, ADR-0006

## Context

`localv2.md §5.4 D8/D9` describes `ExternalDocsProbe` and `ExternalDocsIndexProbe` as the layer that pulls in solved-example external documentation (architecture decision documents, post-mortems, Confluence/Notion pages) for Phase 4's RAG retrieval. The configured sources include filesystem paths (e.g., `~/.codegenie/external-docs/`) *and* optional URL/Confluence/Notion integrations.

The security lens (`design-security.md §"ExternalDocsProbe"`) introduced significant infrastructure to support URL fetching safely: an SSRF guard, an IP deny list (RFC1918 + link-local + 127.0.0.0/8 + 169.254.0.0/16), an `allowlist + private_endpoint` policy, an HTML-to-Markdown converter (`markdownify`), and an out-of-process fetch sandbox. The best-practices lens included URL-list mode without the guards. The performance lens proposed `tantivy` indexing as the load-bearing path.

The critic noted (`critique.md "Cross-design observations"`): SSRF + private-IP deny + scoped fetch sandbox + Confluence credentials is a substantial security surface for a feature `localv2.md §12 Week 5` explicitly schedules as a Phase-2 *stretch* goal. Phase 2's roadmap exit criterion is "every probe layer runs against real repos" — not "external docs are pulled from the open internet." Phase 4 (LLM fallback + RAG) is the first phase that operationally needs external-docs evidence for retrieval; before then, exercising the BM25 indexer over filesystem-only sources is enough to ship the contract.

## Options considered

- **Ship filesystem + URL + Confluence/Notion in Phase 2 [B+S].** Maximum coverage; ships the SSRF-guard infrastructure; requires Confluence/Notion API credentials in the gather environment; brings outbound-network back into `codegenie/`.
- **Ship filesystem + URL list with simple allowlist [B].** Middle ground; no Confluence/Notion; SSRF guard still required because URLs can target internal IPs.
- **Filesystem-only in Phase 2 [synth].** Honors `localv2.md §12 Week 5` "stretch" placement; ships D8/D9 against filesystem sources; the BM25 indexer (D9) exercises the contract surface that Phase 4 will need; URL/Confluence/Notion deferred as a Phase-2 ADR-gated future addition.

## Decision

**Phase 2 ships `ExternalDocsProbe` and `ExternalDocsIndexProbe` against filesystem-only sources.** URL fetching, Confluence integration, Notion integration, and any other outbound-network external-docs ingestion are **deferred** to a follow-up scoped as Phase-2 v0.2 or absorbed into Phase 4 — whichever lands first.

- **Configured sources.** A config-declared list of local paths under `.codegenie/notes/` and a configured external-docs root (e.g., `~/.codegenie/external-docs/`).
- **D8 (`ExternalDocsProbe`).** Iterates configured paths; copies markdown into `.codegenie/context/raw/external-docs/` at mode `0600`; **scans each body with the prompt-injection marker tagger (Pass 5, ADR-0006)**; records `prompt_injection_marker_count` per document. **Body is never inlined into `repo-context.yaml`.**
- **D9 (`ExternalDocsIndexProbe`).** Builds BM25 index over the filesystem corpus. **Default engine: ripgrep** (~50 ms per query at Stage 3 time, sufficient for Phase 2). **`tantivy` is opt-in** via `pip install codegenie[search]` (ADR-0011).
- **No outbound network from `codegenie/`.** Phase 2's `fence` CI job extends Phase 0's no-`httpx`/no-`requests`/no-`socket` ban under `src/codegenie/` (`final-design.md "Goals" #12`).
- **The SSRF-guard infrastructure is documented as the gating prerequisite for any future URL fetcher** (this ADR; future-amendment surface).
- **Test:** `tests/integration/test_phase2_external_docs_disabled_by_default.py` asserts: gather with no `external_docs` config; filesystem-only mode; no URL fetcher launches; no network access by any probe.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 2 ships the D8/D9 contract surface — Phase 4's RAG flow has a stable schema to bind against today | URL/Confluence/Notion users must wait until a follow-up to retrieve from those sources; documented deferral |
| `codegenie/`'s outbound-network ban (Phase 0 `fence`) extends unchanged; no SSRF surface introduced in Phase 2 | The SSRF-guard work (private-IP deny, allowlist + private_endpoint, fetch sandbox) is queued for the follow-up — must be designed before any URL fetch lands |
| The BM25 indexer's contract (ripgrep default, tantivy opt-in) is exercised in Phase 2 CI against filesystem fixtures — Phase 4 can rely on the shape | Filesystem-only means the indexer's scale ceiling is "however much markdown you put on disk"; portfolio-scale doc retrieval lands later |
| Pass 5 prompt-injection tagger (ADR-0006) is exercised against `RepoNotesProbe` and `ExternalDocsProbe` bodies — the defense matures in Phase 2, not Phase 4 | Tagger maturity is limited to the marker patterns known in Phase 2; future Phase-4 LLM-side findings may extend the pattern set |
| The follow-up scope is reviewable in isolation — no Phase-2 review must understand "and also Confluence integration" | Two PRs to land the full D8/D9 surface; the deferred chunk needs its own ADR (which will reference this one) |
| `localv2.md §12 Week 5` "stretch" framing is honored — Phase 2 ships what's scheduled, defers what's labeled stretch | Some readers may interpret "Phase 2 ships D8/D9" as URL-fetching too; this ADR is the place to point them |

## Consequences

- `src/codegenie/probes/external_docs.py` and `external_docs_index.py` ship with filesystem-only logic.
- The config schema for `external_docs.sources` accepts only filesystem paths in Phase 2; URL/Confluence/Notion schema entries are reserved (recognized for forward compatibility but reject-with-error in Phase 2).
- The BM25 indexer uses ripgrep by default; `tantivy` is opt-in (ADR-0011).
- `tests/integration/test_phase2_external_docs_disabled_by_default.py` is CI-gating.
- `tests/adv/test_external_doc_zip_slip.py` covers filesystem-path traversal; `test_huge_external_doc.py` covers size-cap.
- The follow-up ADR (anticipated as ADR-0XXX or a Phase-4 ADR) must include:
  - SSRF guard design (private-IP deny list; allowlist mechanism).
  - URL fetch sandbox profile (likely `network="scoped"` per-fetch with per-host allowlist).
  - Confluence/Notion credential-management policy (out-of-band; not in `codegenie/` env).
  - HTML-to-Markdown conversion pipeline (likely `markdownify` with Phase 1's adversarial-corpus shape).
- Phase 4's RAG flow consumes D9's BM25 output via the same slice shape regardless of when URL/Confluence/Notion lands.

## Reversibility

**High.** Adding URL/Confluence/Notion fetching in a follow-up is mechanically additive — the filesystem-only path stays; new code adds the network-egress path. The deferred ADR is the future-amendment surface. The decision to *defer* is not high-cost to reverse if a Phase-2 hotfix actually needs URL-fetch (we'd land the follow-up ADR with SSRF guard). The cost of reversal is the *security work*, not the *codepath edit*.

## Evidence / sources

- `../final-design.md "Components" §5.4 ExternalDocsProbe + ExternalDocsIndexProbe — filesystem-only in Phase 2`
- `../final-design.md "Conflict-resolution table" D17` — the resolution
- `../final-design.md "Goals" no-outbound-network bullet`
- `../phase-arch-design.md "Non-goals" #10` — explicit URL-fetcher deferral
- `localv2.md §12 Week 5` — the "stretch" framing this ADR honors
- `../critique.md "Attacks on the security-first design"` — SSRF infrastructure as deferred work
- [Phase 0 ADR-0006](../../00-bullet-tracer-foundations/ADRs/0006-subprocess-allowlist.md) — the no-outbound-network base
- ADR-0006 — the Pass 5 tagger this ADR's D8 exercises
