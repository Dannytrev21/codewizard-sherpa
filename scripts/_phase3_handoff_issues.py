"""Pure data registry for the Phase-3 handoff GitHub issues (S8-04).

This module is **pure data** — no I/O, no ``subprocess``, no ``os``. It exposes
:data:`ISSUE_SPECS`, a ``Final`` tuple of typed :class:`IssueSpec` frozen
Pydantic models consumed by :mod:`scripts.file_phase3_handoff_issues` (the
impure shell). Open/Closed: a future handoff story adds a row to the tuple;
the impure script's logic is unchanged.

Each handoff issue is a **project-board mirror** that *links* to the canonical
Phase 3 story file(s) under ``docs/phases/03-vuln-deterministic-recipe/stories/``
— the story file is the implementation prescription; the GitHub issue is the
project-board notification surface. No re-prescription.

Open-implementation-questions selection rationale (per
``docs/phases/02-context-gather-layers-b-g/stories/README.md §"Open
implementation questions"``):

# #1, #3, #6, #7, #8 are resolved by shipped stories (S1-02, S4-02/S7-02, S3-01, S7-04, S1-11); see stories/README.md §"Open implementation questions" inline citations.

Backlog issues file #2 (full-repo ``mypy --warn-unreachable`` rollout), #4
(``ExternalDocsProbe`` host-allowlist config schema), and #5
(``SkillsLoader`` per-tier signing) — the three items still open.
"""

from __future__ import annotations

from typing import Final, NewType

from pydantic import BaseModel, ConfigDict

MilestoneName = NewType("MilestoneName", str)

_PHASE3_MILESTONE: Final[MilestoneName] = MilestoneName(
    "Phase 3 — Vuln remediation: deterministic recipe path"
)
_BACKLOG_MILESTONE: Final[MilestoneName] = MilestoneName("Backlog")

_PHASE3_STORIES_PATH: Final[str] = "docs/phases/03-vuln-deterministic-recipe/stories"


class IssueSpec(BaseModel):
    """One GitHub issue payload — title, milestone, body, labels, story links.

    Frozen so the ``Final`` registry below cannot be mutated at runtime.
    ``extra="forbid"`` so a typo in a field name is a hard validation error.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str
    milestone: MilestoneName
    body: str
    labels: frozenset[str]
    phase3_stories: tuple[str, ...]


# ---------- Issue #1: Plugin Loader ----------

_ISSUE_1_BODY: Final[str] = f"""### Phase 2 context

Phase 2 ships kernel-side scaffolding only (per `ADR-0007`): the four adapter
`Protocol`s at `src/codegenie/adapters/protocols.py`, the `TCCMLoader`, the
`SkillsLoader`, and the `IndexFreshness` sum type. The Plugin Loader itself,
`plugin.yaml` parser, integrity-verified loader, and `extends:` resolver are
deliberately deferred to Phase 3 per `ADR-0031` §Consequences §1 — the first
plugin doubles as the proof the loader works.

### Phase 3 stories

This handoff issue is a project-board mirror of the canonical Phase 3 story
files (no re-prescription — implement against the story files):

- [S2-01 Plugin registry kernel]({_PHASE3_STORIES_PATH}/S2-01-plugin-registry-kernel.md)
- [S2-02 Plugin manifest Pydantic]({_PHASE3_STORIES_PATH}/S2-02-plugin-manifest-pydantic.md)
- [S2-03 Plugin loader integrity]({_PHASE3_STORIES_PATH}/S2-03-plugin-loader-integrity.md)
- [S2-04 Plugin resolver extends]({_PHASE3_STORIES_PATH}/S2-04-plugin-resolver-extends.md)

### Acceptance

Each story carries its own acceptance criteria; do not duplicate them here.
Land the four stories in order (registry → manifest → loader → resolver). On
landing the four stories, verify that the four Protocols at
`src/codegenie/adapters/protocols.py` are imported unchanged (see handoff
issue #4 for the smoke-test trip-wire).
"""

_ISSUE_1 = IssueSpec(
    title="[Phase 3] Implement Plugin Loader: kernel + manifest parser + integrity loader + resolver",
    milestone=_PHASE3_MILESTONE,
    body=_ISSUE_1_BODY,
    labels=frozenset({"phase:3", "handoff:from-phase-2", "loader"}),
    phase3_stories=(
        "S2-01-plugin-registry-kernel",
        "S2-02-plugin-manifest-pydantic",
        "S2-03-plugin-loader-integrity",
        "S2-04-plugin-resolver-extends",
    ),
)

# ---------- Issue #2: First plugin + four ADR-0032 adapters ----------

_ISSUE_2_BODY: Final[str] = f"""### Phase 2 context

Per `ADR-0032`, Phase 2 ships the four adapter `Protocol`s at
`src/codegenie/adapters/protocols.py` with **zero implementations**. Phase 3's
first plugin (`plugins/vulnerability-remediation--node--npm/`) doubles as the
proof the Plugin Loader works AND ships the four ADR-0032 adapter
implementations against Node/npm.

### Phase 3 stories

- [S7-01 vuln node-npm plugin scaffold]({_PHASE3_STORIES_PATH}/S7-01-vuln-node-npm-plugin-scaffold.md)
- [S7-02 npm recipes and adapters]({_PHASE3_STORIES_PATH}/S7-02-npm-recipes-and-adapters.md)

The four adapter implementations land alongside the plugin (matched 1:1
against the Phase 2 Protocols):

- `dep_graph_npm.py` — implements `DepGraphAdapter` for `npm ls --json`.
- `import_graph_node.py` — implements `ImportGraphAdapter` for Node module
  resolution.
- `scip_node.py` — implements `ScipAdapter` for `scip-typescript` indexes.
- `test_inventory_node.py` — implements `TestInventoryAdapter` for
  `package.json` scripts.

### Acceptance

Per the story files. Re-use the Phase 2 fixtures `monorepo-pnpm` and
`minimal-ts` under `tests/fixtures/` for adapter-level integration tests; the
fixtures already exercise the manifest + dep-graph shapes the adapters target.
"""

_ISSUE_2 = IssueSpec(
    title="[Phase 3] Implement first plugin: plugins/vulnerability-remediation--node--npm + four ADR-0032 adapters",
    milestone=_PHASE3_MILESTONE,
    body=_ISSUE_2_BODY,
    labels=frozenset({"phase:3", "handoff:from-phase-2", "plugin"}),
    phase3_stories=(
        "S7-01-vuln-node-npm-plugin-scaffold",
        "S7-02-npm-recipes-and-adapters",
    ),
)

# ---------- Issue #3: Universal fallback / HITL ----------

_ISSUE_3_BODY: Final[str] = f"""### Phase 2 context

`production/design.md §"Humans always merge"` is the Phase 3 invariant the
universal `(*, *, *)` fallback plugin enforces: when no concrete plugin
matches the `(task-class, language, package-manager)` resolution triple, the
fallback fires and the workflow escalates to a human-in-the-loop (HITL)
review instead of silently doing nothing. Per `ADR-0031`, the fallback ships
in Phase 3 alongside the first concrete plugin so the loader's resolution
algorithm is exercised against both a real match and a wildcard fallback.

### Phase 3 stories

- [S7-03 universal HITL fallback plugin]({_PHASE3_STORIES_PATH}/S7-03-universal-hitl-fallback-plugin.md)

### Acceptance

Per the story file. The fallback's job is to escalate cleanly, not to do
work; its acceptance criteria pin the HITL escalation surface, not any
remediation logic.
"""

_ISSUE_3 = IssueSpec(
    title="[Phase 3] Implement universal (*, *, *) fallback plugin / HITL escalation",
    milestone=_PHASE3_MILESTONE,
    body=_ISSUE_3_BODY,
    labels=frozenset({"phase:3", "handoff:from-phase-2", "fallback"}),
    phase3_stories=("S7-03-universal-hitl-fallback-plugin",),
)

# ---------- Issue #4: LOAD-BEARING — unskip the contract trip-wire ----------

_ISSUE_4_BODY: Final[str] = """### Phase 2 context

This is the most load-bearing of the five handoff issues. Phase 2 landed
`tests/adv/phase02/test_phase3_handoff_smoke.py` (function
`test_phase3_adapter_handoff_smoke`) with `@pytest.mark.skip(reason=...)`
citing `ADR-0007` + `High-level-impl.md §Step 7`. The test asserts the four
adapter `Protocol`s at `src/codegenie/adapters/protocols.py` are imported
**unchanged** by Phase 3. Per `phase-arch-design.md §"Gap 1"`, this is the
contract trip-wire: without unskipping it at the Phase 3 entry-gate review,
Phase 3 can silently drift the Protocol shapes and Phase 2's typing guarantee
evaporates.

Any Protocol drift requires an explicit ADR amendment to 02-ADR-0006 / 02-ADR-0007 — not a silent Protocol edit.

### Phase 3 stories

This issue does NOT map to a single Phase 3 story file — it is an action
required at Phase 3's **entry-gate review**, before the loader stories
(S2-01..S2-04) merge.

### Acceptance at Phase 3 entry-gate

1. Unskip `tests/adv/phase02/test_phase3_handoff_smoke.py` —
   delete the `@pytest.mark.skip(...)` decorator on
   `test_phase3_adapter_handoff_smoke` and confirm the test passes against
   the as-of-Phase-2 Protocols (no drift).
2. Verify the four Protocols at `src/codegenie/adapters/protocols.py` are
   imported unchanged. The test asserts the signatures byte-for-byte against
   a frozen-at-Phase-2 baseline.
3. If a signature change is required (e.g., `consumers(self, pkg: PackageId,
   *, transitively: bool = False)`), file an ADR amendment to 02-ADR-0006 or
   02-ADR-0007 **before** editing the Protocol. Any Protocol drift requires
   an explicit ADR amendment to 02-ADR-0006 / 02-ADR-0007 — not a silent
   edit.
"""

_ISSUE_4 = IssueSpec(
    title="[Phase 3] Unskip test_phase3_handoff_smoke.py at Phase 3 entry-gate review",
    milestone=_PHASE3_MILESTONE,
    body=_ISSUE_4_BODY,
    labels=frozenset({"phase:3", "handoff:from-phase-2", "smoke"}),
    phase3_stories=(),
)

# ---------- Issue #5: ALLOWED_BINARIES extension ----------

_ISSUE_5_BODY: Final[str] = """### Phase 2 context

Phase 3's first plugin (Node/npm) shells out to `npm` (dependency graph,
audit) and `jq` (JSON post-processing). Neither is in Phase 2's
`ALLOWED_BINARIES: frozenset[str]` at `src/codegenie/exec/__init__.py:96` —
the `exec` package's module-init carries the frozenset, the structural
guard at the subprocess chokepoint. Documenting the discipline here is not
a substitute for the frozenset edit.

Precedent: `02-ADR-0001` is the omnibus Phase 2 amendment that landed the
ten Layer B/C/G binaries; Phase 3 follows the same pattern — one ADR
amendment, two new entries.

### Phase 3 stories

This is a Phase 3 mechanical change wrapped in an ADR amendment; no
dedicated story file. The amendment lands alongside S7-02 (the story that
first invokes `npm`).

### Acceptance

1. File an ADR amendment to 02-ADR-0001 (or a new Phase-3 ADR if cleaner)
   adding **exactly two binaries**: `npm` and `jq`. No "while we're at it"
   additions (no `yarn`, no `pnpm`, no `node`, no `jq`-adjacent tools).
   "While we're at it" binaries are forbidden by this issue's scope.
2. Update `src/codegenie/exec/__init__.py`'s `ALLOWED_BINARIES` frozenset
   with the two entries.
3. Confirm the `pyproject-fence` CI job stays green — `subprocess` invocations
   for `npm` and `jq` must route through `run_allowlisted` or
   `run_external_cli`, not direct `subprocess.run`.
"""

_ISSUE_5 = IssueSpec(
    title="[Phase 3] Extend ALLOWED_BINARIES for npm + jq via ADR amendment",
    milestone=_PHASE3_MILESTONE,
    body=_ISSUE_5_BODY,
    labels=frozenset({"phase:3", "handoff:from-phase-2", "allowlist"}),
    phase3_stories=(),
)

# ---------- Issue #6: Backlog — full-repo mypy --warn-unreachable ----------

_ISSUE_6_BODY: Final[str] = """### Context

Per `docs/phases/02-context-gather-layers-b-g/stories/README.md §"Open
implementation questions"` #2, Phase 2 enables `mypy --warn-unreachable` at
the global level (`pyproject.toml:172` — `warn_unreachable = true`) but
relies on per-module overrides for a handful of named modules where
unreachable code is intentional (e.g., `tests/*` runs under relaxed typing).

### Why deferred

A full-repo audit of every per-module `[[tool.mypy.overrides]]` block — to
confirm none accidentally silence `warn_unreachable` on production code — is
mechanical but tedious; it is not on the Phase 3 critical path. Phase 2's
S1-11 closed the load-bearing modules (`confidence_section.py` and the
`IndexFreshness` consumer surface).

### Acceptance

1. Enumerate every `[[tool.mypy.overrides]]` block in `pyproject.toml`.
2. Confirm none silences `warn_unreachable` on `src/codegenie/**`.
3. If any does, file a follow-up ticket to either narrow the override or
   land an inline `# type: ignore[unreachable]` with a comment justifying.
"""

_ISSUE_6 = IssueSpec(
    title="[Backlog] Full-repo mypy --warn-unreachable rollout",
    milestone=_BACKLOG_MILESTONE,
    body=_ISSUE_6_BODY,
    labels=frozenset({"backlog", "mypy"}),
    phase3_stories=(),
)

# ---------- Issue #7: Backlog — ExternalDocsProbe host-allowlist ----------

_ISSUE_7_BODY: Final[str] = """### Context

Per `docs/phases/02-context-gather-layers-b-g/stories/README.md §"Open
implementation questions"` #4, the `ExternalDocsProbe` (Layer G6) ships in
Phase 2 with `enabled_by_default = False` and a skip-cleanly path; the
host-allowlist config schema (what hosts are permitted, who maintains the
allowlist, how an org adds an entry) is deferred until a real user opts in.

### Why deferred

The schema's shape is unknowable without a real opt-in workload; designing
it speculatively risks designing it wrong. Phase-4-or-later is the right
horizon — when the first user enables `ExternalDocsProbe`, file a schema
based on the actual hosts they need.

### Acceptance

1. First real opt-in: capture the host list they need.
2. Draft a host-allowlist config schema (likely YAML under
   `.codegenie/config/external-docs-hosts.yaml`).
3. Validate against the user's host list; iterate.
"""

_ISSUE_7 = IssueSpec(
    title="[Backlog] ExternalDocsProbe host-allowlist config schema",
    milestone=_BACKLOG_MILESTONE,
    body=_ISSUE_7_BODY,
    labels=frozenset({"backlog", "external-docs"}),
    phase3_stories=(),
)

# ---------- Issue #8: Backlog — SkillsLoader per-tier signing ----------

_ISSUE_8_BODY: Final[str] = """### Context

Per `docs/phases/02-context-gather-layers-b-g/stories/README.md §"Open
implementation questions"` #5, the `SkillsLoader` ships in Phase 2 with the
three-tier merge contract (first-tier-wins + loud `skill_shadowed` warning).
Per-tier signing (Sigstore-style) is a Phase 14 multi-tenant concern — when
an org-shared tier is consumed by other orgs, the consumers need
cryptographic provenance over the tier contents.

### Why deferred

Phase 2/3/4 are single-tenant or single-org; per-tier signing is
infrastructure overhead with no consumer until Phase 14's multi-tenant
agentic recipe authoring lands. Filed here so the seam (tier-level signing
verification slot in `SkillsLoader`) is visible at Phase 14 design time.

### Acceptance

1. At Phase 14 design time, revisit `SkillsLoader` to slot in a tier-level
   signature-verification step (Sigstore-style — cosign verify against a
   trusted-keys policy).
2. Document the signing policy (key custody, rotation cadence) per tier.
3. Add a CI gate that refuses to load an unsigned org-shared tier when the
   multi-tenant mode is enabled.
"""

_ISSUE_8 = IssueSpec(
    title="[Backlog] SkillsLoader per-tier signing (Sigstore-style)",
    milestone=_BACKLOG_MILESTONE,
    body=_ISSUE_8_BODY,
    labels=frozenset({"backlog", "skills"}),
    phase3_stories=(),
)


ISSUE_SPECS: Final[tuple[IssueSpec, ...]] = (
    _ISSUE_1,
    _ISSUE_2,
    _ISSUE_3,
    _ISSUE_4,
    _ISSUE_5,
    _ISSUE_6,
    _ISSUE_7,
    _ISSUE_8,
)


def milestones_needed(existing: frozenset[str], registry: tuple[IssueSpec, ...]) -> frozenset[str]:
    """Return the milestones in ``registry`` not present in ``existing``.

    Pure helper for the impure script's pre-flight: feed it the set of
    milestone names already on the repo (from ``gh api .../milestones``) and
    it returns the set the script must create. Idempotent: a second
    invocation with the same ``existing`` set returns the same answer; a
    second invocation after the missing milestones are created returns the
    empty set.
    """
    required: frozenset[str] = frozenset(str(spec.milestone) for spec in registry)
    return required - existing


__all__ = [
    "ISSUE_SPECS",
    "IssueSpec",
    "MilestoneName",
    "milestones_needed",
]
