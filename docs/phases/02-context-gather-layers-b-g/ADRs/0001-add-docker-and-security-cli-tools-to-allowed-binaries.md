# ADR-0001: Add `docker`, `strace`, and security/SBOM CLIs to `exec.ALLOWED_BINARIES`

**Status:** Accepted
**Date:** 2026-05-14
**Tags:** registry · tool-use · security · allowlist · supply-chain · localv2-conformance
**Related:** [Phase 0 ADR-0006](../../00-bullet-tracer-foundations/ADRs/0006-pyproject-toml-extras-shape.md), [Phase 1 ADR-0001](../../01-context-gather-layer-a-node/ADRs/0001-add-node-to-allowed-binaries.md), 02-ADR-0002, 02-ADR-0005, [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md)

## Context

Phase 2 lands Layer B/C/G probes that fundamentally cannot be implemented in-process: `scip-typescript` is a Node binary that emits a binary SCIP index; `syft` and `grype` are Go binaries that build SBOMs and CVE diffs against built images; `semgrep` runs rule packs over the source tree; `gitleaks` walks `.git/` history for credential patterns; `docker` builds the analyzed-repo's container and `strace` (Linux) attaches to it for `RuntimeTraceProbe`. Each is named by `localv2.md §5.2–5.6` as the canonical tool for its layer (`phase-arch-design.md §"Tool-readiness extended"`; `final-design.md §"Resource & cost profile"`).

Phase 0 froze `codegenie.exec.run_allowlisted` as **the** subprocess chokepoint and `ALLOWED_BINARIES` as the auditable list of binaries any probe may invoke (Phase 0 §"Chokepoints"). The list grows by addition: Phase 1 added `node` for the `--version` cross-check via [Phase 1 ADR-0001](../../01-context-gather-layer-a-node/ADRs/0001-add-node-to-allowed-binaries.md), and that precedent is now invoked seven more times. The synthesis (`final-design.md §"External CLI runtime additions to ALLOWED_BINARIES"`) explicitly enumerates the set; the architect (`phase-arch-design.md §"Path to production end state" row 1`) names this as ADR-worthy because each addition is a new structural attack surface.

The decision is not *whether* to add these binaries — every input lens agrees we must — but *how*: one omnibus ADR that records the policy and lists the additions, vs. seven separate ADRs (one per binary), vs. silent expansion of `ALLOWED_BINARIES` with a code comment. The critic flagged silent expansion as the exact "Phase 0 chokepoint edit" Phase 0 said it would refuse without governance.

## Options considered

- **Option A — silent extension of `ALLOWED_BINARIES`.** Drop the names into the constant; rely on PR review to catch new entries. **Pattern:** none — anti-pattern (registry-without-record). Fast to land; the audit trail is git-blame; the policy ("when is a new binary acceptable?") is undocumented and grows by accretion.
- **Option B — one ADR per binary.** Mirror [Phase 1 ADR-0001](../../01-context-gather-layer-a-node/ADRs/0001-add-node-to-allowed-binaries.md)'s shape — `0001-add-docker.md`, `0002-add-strace.md`, … Maximum traceability per binary; eight ADRs in one phase is ceremony given the additions share a single rationale (Layer B/C/G probes need them) and a single set of mitigations.
- **Option C — one omnibus ADR for the Phase 2 batch + the policy ("a binary added to `ALLOWED_BINARIES` requires an ADR; Phase-2 batch counts as one because all entries are Layer B/C/G probe requirements named in `localv2.md`").** **Pattern:** Registry pattern — `ALLOWED_BINARIES` is the kernel-side registry; this ADR is its load-time governance gate.

## Decision

Adopt **Option C — one Phase-2 omnibus ADR**. `exec.ALLOWED_BINARIES` is extended additively with **eight new entries**: `docker`, `strace`, `semgrep`, `syft`, `grype`, `gitleaks`, `scip-typescript`, `tree-sitter`. Each entry is justified by exactly one Layer B/C/G probe named in `localv2.md §5.2–5.6`; each entry's binary runs only through Phase 0's `run_allowlisted` chokepoint, wrapped by Phase 2's `run_external_cli` for Layer B/G or invoked directly with explicit hardening flags for Layer C (per 02-ADR-0003's scheduling layer and 02-ADR-0005's persistence policy). **Pattern: Registry — kernel-side allowlist as a data-driven extension primitive.** Future binaries land via the same pattern: one ADR per phase batch, additions justified by named-trigger probes, the chokepoint surface (`run_allowlisted`'s signature) untouched.

## Tradeoffs

| Gain | Cost |
|---|---|
| Audit-trail is one document instead of eight; the policy ("when is a new binary acceptable?") is stated once, in one place | Per-binary justification is terser than [Phase 1 ADR-0001](../../01-context-gather-layer-a-node/ADRs/0001-add-node-to-allowed-binaries.md)'s shape; a future reader looking up "why `gitleaks`" finds it in a table row, not in a dedicated ADR |
| Phase 0's chokepoint surface (`run_allowlisted` signature, `ALLOWED_BINARIES` location) survives unchanged — extension by addition (commitment §2.5) | Eight new CVE feeds to follow (`docker`, `syft`, `grype`, `gitleaks`, `semgrep`, `scip-typescript`, `tree-sitter`, `strace`); `pip-audit` does not cover non-PyPI binaries — host-hygiene concern delegated to OS package managers |
| Each binary is invoked with explicit hardening flags constructed at the call site (`docker run --network=none --cap-drop=ALL --security-opt=no-new-privileges`; `semgrep --metrics=off`; `gitleaks --no-banner`) — the chokepoint stays a value-typed argv, no string interpolation | Hardening flags are author-supplied at the call site; a probe author who forgets `--network=none` ships a less-isolated tool. Mitigated by `tests/adv/phase02/test_adversarial_dockerfile.py` exercising the cap-drop path |
| The "must be invoked via `run_allowlisted` or `run_external_cli`" rule is structurally enforceable — Phase 0's `forbidden-patterns` pre-commit can be extended to ban direct `subprocess.run` / `asyncio.create_subprocess_exec` repo-wide if it isn't already | The forbidden-patterns net for Phase 2 grows; one more category to maintain |
| Cost stays at $0/run — these tools have local-binary deployment shapes; no SaaS, no API keys, no token cost | Wall-clock cost is real: `semgrep` ~200 MB RSS + 8 s on a 5k-file repo; `docker build` 30–60 s cold; `strace -f` adds ~5–10 % overhead to traced binaries |
| Layer C tools (`docker`, `strace`) **do not** route through `run_external_cli` — they use `run_allowlisted` directly with hardening flags inline (final-design §3 tradeoffs accepted) | Two subprocess pathways exist in Phase 2 by design: `run_external_cli` for B/G families, `run_allowlisted("docker", …)` for C. Auditing "where do we shell out" is now `grep "run_external_cli\|run_allowlisted"` — two patterns, not one |

## Pattern fit

Pattern: **Registry — kernel-side allowlist as a data-driven extension primitive** (`design-patterns-toolkit.md §"Registry pattern"`). The toolkit's prescription is "a registry is a dict; the decorator is `def register(name): …`. Stay that simple." `ALLOWED_BINARIES` is the simplest possible shape — a `frozenset[str]` — and this ADR is its governance gate. The pattern's failure mode the toolkit warns against ("a registry that does more than registration — eager validation, side effects, cross-references at registration time") is avoided: the binaries are validated on use (Phase 0 tool-readiness check at CLI startup), not at registration time. The omnibus-ADR shape is the "register at import time" analogue for governance — one record per phase batch, not per entry.

## Consequences

- `src/codegenie/exec.py` line listing `ALLOWED_BINARIES` grows by the eight named entries. The constant remains a literal frozenset; no dynamic discovery, no env-var overrides.
- The CLI tool-readiness check (`src/codegenie/cli.py`) gains eight new entries with the install commands from `localv2.md §6` printed when a mandatory tool is missing. Optional tools (`strace` on macOS, `bubblewrap` on any host) print a one-line startup warning and continue.
- `run_external_cli` (Phase 2 new module function; see 02-ADR-0003 for its place in the registry/scheduling story) wraps `run_allowlisted` for the seven Layer B/G binaries; `RuntimeTraceProbe` calls `run_allowlisted("docker", …)` directly with the documented hardening flags.
- `pyproject.toml`'s `gather` extras (per [Phase 0 ADR-0006](../../00-bullet-tracer-foundations/ADRs/0006-pyproject-toml-extras-shape.md)) gains **one** new Python dep (`py-tree-sitter`, see 02-ADR-0002) — not eight. The other seven binaries ship as system tools, not as PyPI packages; `gitleaks-python`, `scip-python`, `tree-sitter-python` (bindings beyond what `py-tree-sitter` provides) are explicitly rejected per `final-design.md "Resource & cost profile"`.
- A future binary addition triggers an ADR amendment to this one OR a new phase-level ADR following the same shape: name the named-trigger probe in `localv2.md`, list the hardening flags, accept the CVE-feed cost. No silent additions.
- `docker` added to `ALLOWED_BINARIES` is the named upgrade door for [production ADR-0012](../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md) — Phase 5's microVM substitution is "amend the probe module, not the chokepoint signature." The forward path is preserved without speculative `_run_in_container` indirection (refused per `final-design.md §"Patterns rejected" #3`).

## Reversibility

**High.** Each entry is a one-line edit to a frozenset and a deletion of the probe that uses it. The CVE-feed-watching commitment is operational hygiene, not code; dropping a binary is dropping its tool-readiness check and the probe call site. The chokepoint surface is untouched, so no consumer-side reshaping is needed if (e.g.) `gitleaks` is replaced by `trufflehog` in a later phase — that's a one-row addition to this ADR's table and a probe rewrite, not a contract change.

## Evidence / sources

- `../final-design.md §"External CLI runtime additions to ALLOWED_BINARIES"` — the enumerated list and its `localv2.md §6` install commands
- `../final-design.md §"Components" §3 _run_external_cli` — chokepoint composition rationale
- `../phase-arch-design.md §"Component design" §3 run_external_cli` and `§"Component summary table"` rows 5, 6
- `../phase-arch-design.md §"Path to production end state" row 1` — the named ADR slot this fills
- `../critique.md §"Attacks on the security-first design" §"Hidden assumptions" #1` — `bubblewrap` availability framing applied here as "binary is hardening, not contract"
- [Phase 0 ADR-0006](../../00-bullet-tracer-foundations/ADRs/0006-pyproject-toml-extras-shape.md) — the `gather` extras shape this composes with
- [Phase 1 ADR-0001](../../01-context-gather-layer-a-node/ADRs/0001-add-node-to-allowed-binaries.md) — the precedent for ADR-gated `ALLOWED_BINARIES` additions
- [Production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md) — composes with: every binary added here is deterministic, no LLM cost
- [Production ADR-0012](../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md) — Phase 5 microVM is the named upgrade door for `docker`'s call sites
