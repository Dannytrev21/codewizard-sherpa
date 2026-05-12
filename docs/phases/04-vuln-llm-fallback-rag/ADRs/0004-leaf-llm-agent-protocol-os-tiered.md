# ADR-0004: `LeafLlmAgent` Protocol with OS-tiered implementations (in-process on macOS, bwrap+uid jailed on Linux)

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** trust-boundary · protocol · process-isolation · phase-5-handoff · synthesizer-departure
**Related:** [ADR-0013](0013-api-key-store-env-var-refused.md), [ADR-0014](0014-langgraph-leaf-agent-node-minimal-wrap.md), [production ADR-0012](../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md), [production ADR-0020](../../../production/adrs/0020-leaf-agents-sdk.md)

## Context

Anthropic's SDK runs *somewhere*. The three lens designs disagreed on where: in-process (performance, best-practices) or in a `bwrap` jail with an egress proxy holding the key (security). The critic (`critique.md §security.2`) flagged that the security-lens file-IO-mediated jail contract does *not* map cleanly to Phase 5's microVM contract (vsock-mediated), so the "Phase 5 swap is a transport change" claim was too strong. The synthesizer's compromise: ship the `LeafLlmAgent` Protocol *now* with two concrete implementations (in-process for macOS dev; jailed for Linux production-ish) so Phase 5's `MicroVmLeafLlmAgent` is a third sibling rather than a contract rewrite ([production ADR-0020](../../../production/adrs/0020-leaf-agents-sdk.md) compatibility).

The OS split is intentional. macOS engineers run dev cycles that need the orchestrator's address space (Keychain access, Quick debug iteration); they pay a thinner trust boundary, surfaced loud via `audit.warning(leaf_in_process_on_linux)` if `--leaf=in_process` is set on Linux. Production-ish Linux runs go through `bwrap --unshare-all --uid <agent-uid>` with the API key resident only in a separate `EgressProxy` daemon. Phase 5 swaps `JailedLeafLlmAgent` for `MicroVmLeafLlmAgent` without touching `RagLlmEngine`.

## Options considered

- **In-process only.** Performance and best-practices position. Cheapest. Means the SDK shares the orchestrator's address space — full access to `RepoContext`, audit chain, `~/.ssh`, working tree. Phase 5 must retrofit isolation everywhere.
- **bwrap + uid jail + egress proxy on every OS.** Security-lens. Same Linux mechanism on Mac requires Docker-for-Mac or similar; cost ~150ms/run + significant operational burden for dev cycles that don't justify it.
- **OS-tiered: in-process on macOS, jailed on Linux.** Synth pick. Two implementations of one Protocol. Audit warning on the mismatch (`--leaf=in_process` on Linux). Phase 5 adds a third implementation; the contract stays put.
- **microVM (firecracker / Hyper-V) now.** Phase 5's actual target. Deferred per [production ADR-0012](../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md); too much infrastructure for a phase whose primary goal is the planning tier.

## Decision

Define a `LeafLlmAgent(Protocol)` in `src/codegenie/llm/contract.py` with `available() -> bool` and `invoke(LlmRequest) -> LlmResponse`. Ship two concrete implementations: `InProcessLeafLlmAgent` (macOS default, dev opt-in on Linux with audit warning) reads the API key from the platform keystore and calls `anthropic.Anthropic` directly; `JailedLeafLlmAgent` (Linux default) spawns a subprocess under `bwrap --unshare-all --uid <agent-uid>` with only `/agent-jail/<run-id>/{in,out}` writable and only `unix:/jail/egress.sock` reachable. The `EgressProxy` daemon (separate process) holds the API key; its allowlist is exactly `POST /v1/messages` + `POST /v1/messages/count_tokens`. Phase 5's `MicroVmLeafLlmAgent` is a third implementation; `RagLlmEngine` and `LlmRequest`/`LlmResponse` shapes do not change.

## Tradeoffs

| Gain | Cost |
|---|---|
| Single Protocol surface across macOS, Linux, microVM (Phase 5), and future SDK swaps ([production ADR-0020](../../../production/adrs/0020-leaf-agents-sdk.md)) | Two implementations in v0.4.0; Linux-only CI job to exercise `JailedLeafLlmAgent`, `EgressProxy`, and `bwrap` setup |
| macOS dev loop stays fast (no subprocess spawn, no jail setup, ~30ms keystore read amortized over process lifetime) | macOS engineers operate inside the orchestrator's address space — surfaced as a known threat-model concession; not the production trust posture |
| Linux production-ish runs have a real process boundary, egress allowlist, and an API key that never enters the agent process | `bwrap` + uid setup adds ~80–150ms per LLM call; Linux p95 wall-clock budget absorbs this within the 180s goal |
| Phase 5's microVM swap is a third sibling, not a rewrite — the contract is the Protocol, not the transport | "Identical RPC contract" claim is honest about file-IO vs vsock divergence: the Protocol is preserved; the *transport implementation* changes |
| `available()` returns False on missing API key, missing `bwrap`, or missing uid — selector falls through cleanly to `reason="no_engine"` | `EgressProxy` is a stateful daemon; one more process to lifecycle-manage on Linux |
| Egress proxy strips agent-supplied `x-api-key` headers before forwarding — closes the smuggle channel from a compromised agent (`critique.md §security.4`) | Proxy must use standard CA chain (no SPKI pin per `final-design.md §"Synthesis ledger"` row "SPKI pinning") — Anthropic's CDN-issued LE cert rotation every ~60 days would break a hard pin |

## Consequences

- `LeafLlmAgent` lives in `src/codegenie/llm/contract.py` and is one of three frozen-at-v0.4.0 contracts. Snapshot-tested in `tests/contracts/test_llm_contract_snapshot.py`.
- `anthropic` may not be imported anywhere outside `src/codegenie/llm/leaf_anthropic/*` — fence-CI enforced. `JailedLeafLlmAgent` and `InProcessLeafLlmAgent` both live there.
- `EgressProxy` allowlist is data: a hard-coded list in v0.4.0 (`POST /v1/messages`, `POST /v1/messages/count_tokens`). Phase 5 may widen it for the retry-with-context flow.
- `JailedLeafLlmAgent.invoke` is file-mediated (`req.json` → `resp.json`); Phase 5's `MicroVmLeafLlmAgent.invoke` is vsock-mediated; both satisfy the same Protocol. The transport divergence is acknowledged, not hidden.
- macOS bare `ANTHROPIC_API_KEY` in env emits `audit.warning(api_key.env_present)` but does not refuse to start. Linux bare env-var is hard-refuse. See [ADR-0013](0013-api-key-store-env-var-refused.md).
- No tool use, no file_read tool, no bash — the agent's tool surface is empty in Phase 4. Phase 5 reopens for retry-with-context.
- Per-call wall-clock budget: macOS ~8s p50; Linux jailed adds ~80–150ms process spawn + bwrap setup overhead per call.

## Reversibility

**Medium.** Collapsing to one implementation (in-process only, or jailed only) requires removing the OS-tiered logic from CLI flag parsing and engine construction, plus dropping the Linux-only CI job. The *Protocol* is durable — the rest of Phase 4 (engine, validator, prompt loader) only ever sees the Protocol type. Phase 5 explicitly relies on the Protocol existing as a swap point; reverting would require Phase 5 amendments.

## Evidence / sources

- `../phase-arch-design.md §"Component design"` #2 — `LeafLlmAgent` + implementations
- `../phase-arch-design.md §"Physical view"` — macOS / Linux split diagram
- `../final-design.md §"Synthesis ledger" §"Conflict-resolution table"` row "Agent process boundary"
- `../final-design.md §"Components"` #3 — `LeafLlmAgent` design
- `../critique.md §security.2` — file-IO vs vsock divergence
- `../critique.md §performance "Things this design missed"` — security's process boundary
- Production [ADR-0012](../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md) — microVM in Phase 5
- Production [ADR-0020](../../../production/adrs/0020-leaf-agents-sdk.md) — leaf agents SDK choice
