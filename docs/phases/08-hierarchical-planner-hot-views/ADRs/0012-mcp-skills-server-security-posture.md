# ADR-0012: MCP Skills server — read-only tools and contract-snapshot, no OS-level confinement

**Status:** Accepted
**Date:** 2026-05-21
**Tags:** Smart constructor / contract snapshot · Newtype pattern · anti-decision: no speculative subsystem
**Related:** ADR-0010, [production ADR-0023](../../../production/adrs/0023-mcp-server-topology.md), [production ADR-0031](../../../production/adrs/0031-plugin-architecture.md)

## Context

Phase 8 ships the first concrete MCP server — `SkillsMcpServer`, a local stdio child process serving Skill manifests to the planner. It is the first worked example of the eventual MCP topology ([production ADR-0023](../../../production/adrs/0023-mcp-server-topology.md), `Deferred`). Phase 8 must decide the server's *security posture*.

[critique.md §Cross-design observations](../critique.md#where-do-the-three-disagree) shows the lenses split: performance ships stdio with no auth; security ships `seccomp-bpf` + read-only bind-mounts + `no_new_privileges` + zero-net OS confinement. The security mechanism is undeployable: per [critique.md §hidden assumptions](../critique.md#hidden-assumptions-1), "seccomp is Linux-only and the documented dev substrate is macOS — the design's signature isolation control does not run on the platform the project develops on." OS-level process confinement requires the deployment substrate Phase 9 introduces. But "no hardening at all" is also wrong — an MCP tool surface is a contract, and a `get_skill` tool that takes a skill ID is a path-traversal vector if the ID is unvalidated.

## Options considered

- **Option A — Full OS-level confinement: `seccomp-bpf` + read-only bind-mount + `no_new_privileges` + zero-net.** **Pattern:** Capability / sandboxing — but `seccomp` is Linux-only; undeployable on the macOS dev substrate; requires Phase-9 deployment infrastructure. A *speculative subsystem* (toolkit "flag on sight") for a phase away.
- **Option B — Stdio server, no hardening — no ID validation, no contract test.** **Pattern:** none — a `get_skill("../../etc/passwd")` traversal vector; tool-surface drift undetected; "the roadmap puts the Skills server *in* Phase 8" so a naked server is a deliverable gap, not a deferral.
- **Option C — Stdio + two read-only tools + newtype-ID smart-constructor validation + `MCP_SKILLS_CONTRACT` snapshot test; OS confinement deferred to Phase 9.** **Pattern:** Smart constructor / contract snapshot + Newtype pattern — the security controls that *are* deployable on the actual substrate, plus an explicit deferral of the ones that are not.

## Decision

`SkillsMcpServer` exposes exactly **two read-only MCP tools** (`list_skills`, `get_skill`) — **no write tool, no exec tool, no filesystem-path tool**. `SkillId` is a **newtype validated by a regex smart constructor** — a traversal-shaped ID (`../../etc/passwd`) fails the constructor before any filesystem touch. The tool surface is pinned as `MCP_SKILLS_CONTRACT` (a `Final`) and **snapshot-tested** against the live server. Tools return *manifests* (id, frontmatter, `body_offset`/`body_size`), never inlined skill bodies (progressive disclosure). **OS-level confinement (seccomp, bind-mounts, `no_new_privileges`) is explicitly deferred to Phase 9** — it is undeployable on the macOS dev substrate. The in-memory index is built once in an explicit `start()`, not at import.

## Tradeoffs

| Gain | Cost |
|---|---|
| Every security control shipped *runs on the actual substrate* (macOS dev) — no undeployable signature control | A compromised MCP process is not kernel-confined in Phase 8 — process-level confinement only |
| Two read-only tools — no write/exec — minimize the attack surface structurally | If a future Skills *write* path is needed, it is a new tool + a new ADR — not a Phase-8 capability |
| `SkillId` smart constructor rejects path traversal before any filesystem touch (edge case 12) | A regex smart constructor must be kept correct — an over-permissive regex re-opens the traversal vector |
| `MCP_SKILLS_CONTRACT` snapshot makes any tool-surface drift a loud CI failure | The young `mcp` SDK's stdio/tool-advertisement API must match the contract's assumptions — a deliberate version pin and a drift-guarding snapshot |
| The process *boundary itself* is the Phase-8 security gain — it forces the Skills interface to be an explicit, contract-tested Port now | OS-level confinement is a real deferred risk; Phase 9's deployment substrate owns it |

## Pattern fit

The toolkit's "Smart constructor" entry: "a factory that validates inputs and refuses to construct invalid instances… the raw constructor is private." The `SkillId` newtype with a regex smart constructor is exactly that — a traversal-shaped ID cannot become a `SkillId`. The `MCP_SKILLS_CONTRACT` snapshot is the "contract + snapshot test" idiom (the ADR-0007 probe-ABC pattern) — the tool surface is a contract; drift is a reviewable diff. Rejecting Option A is an **anti-decision**: the tempting pattern was the Capability/sandboxing pattern (OS-level confinement), and the anti-pattern it would have created is the toolkit's "speculative subsystem" — "infrastructure for zero-current-use threats whose enabling phase has not arrived," and in this case literally non-runnable on the dev OS.

## Consequences

- `SkillsMcpServer` exposes two read-only tools; there is no write, exec, or filesystem-path tool.
- `SkillId` is a newtype with a regex smart constructor; a traversal-shaped ID is rejected with a typed error before any filesystem access (edge case 12; adversarial-tested).
- `MCP_SKILLS_CONTRACT` is a `Final` snapshot-tested against the live server — tool-surface drift fails CI.
- Tools return manifests, not skill bodies — progressive disclosure (commitment §7).
- The in-memory index is built in an explicit `start()` — no side effects at import or in the constructor.
- OS-level confinement (seccomp, bind-mounts, `no_new_privileges`) is **not** in Phase 8 — Phase 9's deployment substrate owns it; this ADR is the record of that deferral.
- If the MCP stdio process dies, leaf skill lookups fall through to a direct `SkillsLoader` read (same data); Phase 9's Temporal envelope owns process supervision.
- The `mcp` SDK version is pinned in `pyproject.toml`; the snapshot test guards drift (Open Question 8).

## Reversibility

**Medium.** The read-only-tools + contract-snapshot + newtype-ID posture is cheap to *extend* (Phase 9 can add OS confinement additively — it is a deployment-layer concern, not a code-shape change). The deferral of OS confinement is a deliberate, recorded gap, not a permanent stance. Reversing the *read-only* constraint (adding a write tool) would be a real expansion of the attack surface and would need its own ADR. The `MCP_SKILLS_CONTRACT` shape is frozen-by-snapshot — changing it is a loud, reviewed diff.

## Reversibility note — the anti-decision

This ADR records that OS-level confinement was **deliberately not** built in Phase 8. The tempting pattern — sandboxing the MCP child with seccomp/bind-mounts — is correct *eventually*, but in Phase 8 it would be a speculative subsystem that does not even run on the project's macOS dev substrate. A future engineer adding deployment hardening should treat this as the seam: Phase 9's deployment substrate is where OS confinement lands, additively.

## Evidence / sources

- ../phase-arch-design.md §C6 — SkillsMcpServer
- ../phase-arch-design.md §Non-goals — "OS-level confinement of the MCP process"
- ../phase-arch-design.md §Edge case 12 — Skills-ID path traversal
- ../final-design.md §Synthesis ledger — Conflict-resolution row "MCP server hardening"
- ../critique.md §Attacks on the security-first design, hidden assumption 2 — seccomp is Linux-only
- ../../../production/adrs/0023-mcp-server-topology.md — `Deferred`
- ../../../production/adrs/0031-plugin-architecture.md
- `design-patterns-toolkit.md` §Smart constructor; §Anti-patterns — "Speculative subsystem"
