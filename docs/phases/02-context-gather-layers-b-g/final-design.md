# Phase 02 — Context gathering — Layers B–G: Final design

**Status:** Design of record (synthesized from three competing designs + critique).
**Synthesized by:** Graph-of-Thought synthesizer subagent
**Date:** 2026-05-14
**Sources:** `design-performance.md` · `design-security.md` · `design-best-practices.md` · `critique.md`

> **Amendment note (2026-05-17 — [02-ADR-0011](ADRs/0011-tree-sitter-grammars-via-pypi-wheels.md)):** the "vendored `.so` + `tools/grammars.lock` BLAKE3 pin" model described in §"Component design #12 — `TreeSitterImportGraphProbe`" and §"Resource & cost profile" was superseded after S4-04 and S4-06 hit a per-platform build-chain blocker. Grammars now ship as PyPI wheels (`tree-sitter-typescript`, `tree-sitter-javascript`, future `tree-sitter-python` / `tree-sitter-java`) behind a `codegenie.grammars.lock.language_for(name) -> tree_sitter.Language` kernel; supply-chain pinning is `pip --require-hashes` at the wheel boundary. The named-trigger C-extension discipline (Phase 1 ADR-0009 admits `py-tree-sitter` as the one exception) carries forward unchanged — only grammar *delivery* changed. The body below records the original design-time decision and is preserved verbatim for historical context; **current truth is 02-ADR-0011**.

## Lens summary

Phase 2 lands the remaining probe layers (B–G) on top of Phase 0/1's frozen contract surface, with **`IndexHealthProbe` (B2) as the load-bearing citizen** the roadmap exit criterion names by name. The synthesis takes the best-practices skeleton (kernel-only probes, ADR-0033 sum types from line 1, no plugin loader yet — Phase 3 owns that), bolts on the security lens's writer-chokepoint redaction and `_run_external_cli` sandbox port (with cost-pruned isolation), and pulls from the performance lens **only** the cache-correctness primitives (image-digest as a *declared input*, not as a cache-key bypass) and the deliberate stale-fixture test that proves B2 catches what it's there to catch. The synthesis **rejects** the performance design's Plugin Loader (Phase-3 deliverable per roadmap + ADR-0031 §Consequences §1), **rejects** every Phase 0 ABC edit proposed by [P] and [S] (`cost_tier`, `capabilities: ProbeCapabilities`) and finds the same dispatch leverage in registry-side annotations, **rejects** the security design's cryptographic-anchor freshness ceremony (defends a non-threat against an attacker who already owns `$HOME`) and the per-repo encryption-key theatre (key + ciphertext in the same trust tier), and **rejects** the performance design's unilateral `pytest-xdist` reversal of the Phase 0 veto. The result is a smaller Phase 2 than any of the three inputs proposed: ~kernel probes + one tagged-union `IndexFreshness` + four adapter `Protocol`s (documentation as code) + the `TCCMLoader` skeleton + writer-chokepoint secret redaction + a one-function external-CLI port (`_run_external_cli`) wrapping `run_allowlisted`. Phase 3 owns the loader, the first plugin, the four adapter implementations, and the OpenRewrite recipes — as the roadmap says.

## Goals (concrete, measurable)

These are the load-bearing exits Phase 2 must hit. Each goal is annotated with provenance.

- **Every Layer B–G probe in `localv2.md` §5.2–5.6 (kernel-only — language-agnostic) ships with golden-file coverage against the 5-repo fixture portfolio.** [synth — adopts [B]'s kernel-only framing + [P]'s portfolio sizing]
- **`IndexHealthProbe` (B2) surfaces a real staleness case in CI against a deliberately-seeded `stale-scip` fixture; build FAILS if the probe does not catch it.** [roadmap exit criterion — operationalized as `tests/adv/phase02/test_stale_scip_fixture.py`] [synth]
- **`IndexFreshness = Fresh | Stale(reason: StaleReason)` is *the* sum type B2 returns.** One name, one module path (`src/codegenie/indices/freshness.py`), four `StaleReason` variants (`CommitsBehind`, `DigestMismatch`, `CoverageGap`, `IndexerError`). Every consumer pattern-matches with `assert_never`. The competing `AdapterConfidence` / `IndexConfidence` names are **not shipped** in Phase 2 (rationale below). [B] [synth — resolves critic finding #3]
- **Zero edits to Phase 0/1 frozen surfaces:** `Probe` ABC, `ProbeContext` (except an additive Phase-2-ADR-gated optional `image_digest_resolver` callable mirroring Phase 1's `parsed_manifest` precedent), `@register_probe`, `Coordinator` core, `Cache`, `OutputSanitizer`, `run_allowlisted`, `ALLOWED_BINARIES` (extended additively per Phase 0 §6.4). No new ABC fields for cost tiers, capability bundles, or any other coordinator-internal concern. Per-probe scheduling data lives **as registry annotations on the decorator**, not on the ABC. [synth — rejects [P]'s `cost_tier` and [S]'s `capabilities: ProbeCapabilities`; resolves critic finding #2]
- **Secret findings (`gitleaks` + `semgrep p/secrets` + entropy catch-all) are redacted at the writer chokepoint** in `repo-context.yaml`, raw artifacts, cache, and audit log. Plaintext **is not persisted in Phase 2** — see Component §Secret redactor. Cleartext access path is deferred to Phase 5 (microVM-sandboxed planner consumption). [synth — resolves critic finding #7]
- **One subprocess port for Layer B/G external CLIs:** `codegenie.exec.run_external_cli(probe_name, argv, *, cwd, allowlisted_egress, timeout_s) -> ProcessResult`, a wrapper around Phase 0 `run_allowlisted` that adds env strip, working-directory restriction, and (on Linux only, optional) `bubblewrap --unshare-net` when available. Phase 0's chokepoint is the single subprocess path. [synth — adopts [S]'s Command pattern but **uses the existing Phase 0 chokepoint** rather than introducing a parallel one]
- **No new C-extension parser dependencies.** Phase 1 ADR-0009 carries forward. The performance design's `msgpack`/`scip-python`/`tantivy`/`tree-sitter-python`/`gitleaks-python` ship-list is **rejected**. Phase 2 adds **only** `networkx` (pure-Python depgraph), `gitpython` (rejected in favor of shelling out to `git` via `run_allowlisted` — `git` already in `ALLOWED_BINARIES` per Phase 0 §6.4), `tree-sitter` + grammars (Phase 2 ADR amends Phase 1 ADR-0009 with the named trigger — see ADRs below). [synth — resolves critic shared blind spot #2 + best-practices open Q §4]
- **`tantivy` ships only as opt-in for `ExternalDocsIndexProbe` (D9), with a ripgrep-via-`run_allowlisted` fallback that is the *default*.** Phase 2's tested path is the fallback; tantivy lights up only when the user opts in via config. [synth — adopts [B]'s pure-Python ratio]
- **Cost target: $0/run. Tokens per gather: 0.** Phase 0 `fence` job continues to assert. [P+S+B agree, load-bearing commitment §2.1]
- **Wall-clock (1k-file fixture):** cold p50 ≤ 90 s; warm p50 ≤ 1.5 s; incremental (single .ts change) p50 ≤ 10 s. **No `pytest-xdist`** — the Phase 0 veto holds (synthesizer-recorded 10/4 in Phase 0). The performance design's portfolio-lane xdist exception is **rejected**; the portfolio tests fit within a serial CI lane of ≤ 6 minutes, validated by `tests/bench/bench_portfolio_walltime.py` (advisory). [synth — resolves critic finding #8]
- **Plugin scaffolding shipped in Phase 2 is kernel-only:** the four `Protocol` classes from ADR-0032 in `codegenie/adapters/protocols.py` (documentation as code), the `TCCMLoader` + `TCCM` Pydantic model + `DerivedQuery` discriminated union in `codegenie/tccm/`, the `SkillsLoader` + `Skill` Pydantic model in `codegenie/skills/`. **No plugin loader. No `plugin.yaml` parser. No `plugins/universal--*--*/` directory. No adapter implementations.** Phase 3 ships all of those, together, as ADR-0031 §Consequences §1 prescribes. [B + roadmap — resolves critic finding #1]
- **Phase 2 ships no event stream.** The audit anchor (`runs/<utc-iso>-<short>.json`) from Phase 0 is unchanged. Per ADR-0034 §Consequences §1, the canonical event log lands in Phase 9 (or 13). Phase 2 emits *structured slice metadata* (probes report their own `gathered_at`, `last_indexed_commit`, etc. in their slices) which Phase 9 will project — but does NOT pre-ship `.codegenie/events/` JSONL. [synth — resolves critic [S] §"missed" + [P] §8 + ADR-0034]

## Architecture

```
                              codegenie gather <path>
                                        │
                                        ▼
                       ┌────────────────────────────┐
                       │  Phase 0 CLI entry (click) │   ← unchanged
                       │  + tool readiness extended │
                       │    for B-G external CLIs   │
                       │  + ALLOWED_BINARIES adds   │
                       │    semgrep, syft, grype,   │
                       │    gitleaks, scip-typescript│
                       └──────────────┬─────────────┘
                                      │
                                      ▼
                       ┌────────────────────────────┐
                       │ Phase 0 Coordinator         │   ← unchanged ABC;
                       │  asyncio.Semaphore(         │     registry now
                       │    min(cpu_count(), 8))     │     carries optional
                       │  per-probe Task + timeout   │     annotations
                       │  failure isolation          │     (heaviness=heavy
                       │  Phase 1 parsed_manifest    │     used as a sort
                       │  memo                       │     key, not a sem-
                       └──────────────┬─────────────┘     aphore selector)
                                      │
   ┌──────────────────────────────────┼──────────────────────────────────┐
   │  Phase 1 Layer A probes (unchanged)                                  │
   │  ┌────────────────────── Phase 2 additions ──────────────────────┐  │
   │  │  Layer B  semantic_index_meta, index_health, dep_graph,       │  │
   │  │           tree_sitter_import_graph, generated_code,           │  │
   │  │           node_reflection (kernel surface; npm-specific       │  │
   │  │           refinements ship in Phase 3 plugin)                 │  │
   │  │  Layer C  dockerfile, sbom (syft), cve (grype), runtime_trace │  │
   │  │           (5-scenario harness, sequential), certificate,      │  │
   │  │           entrypoint, shell_usage                             │  │
   │  │  Layer D  skills_index, conventions, adrs, policy, exceptions,│  │
   │  │           repo_notes, repo_config, external_docs (opt-in)     │  │
   │  │  Layer E  ownership, service_topology stub, slo stub          │  │
   │  │  Layer F  empty (Phase 4+ task-specific evidence)             │  │
   │  │  Layer G  semgrep, ast_grep, ripgrep_curated, gitleaks,       │  │
   │  │           test_coverage_mapping                               │  │
   │  │                                                                │  │
   │  │  Kernel scaffolding (no implementations):                     │  │
   │  │   codegenie.adapters.protocols (ADR-0032 Protocols)           │  │
   │  │   codegenie.tccm.{loader,model,queries}  (ADR-0029)           │  │
   │  │   codegenie.skills.{loader,model}                             │  │
   │  │   codegenie.conventions.{catalog,model}                       │  │
   │  │   codegenie.indices.freshness  (IndexFreshness sum type)      │  │
   │  │   codegenie.depgraph.{builder,model}  (networkx graph;        │  │
   │  │     queries live in plugin adapters, not here)                │  │
   │  └────────────────────────────────────────────────────────────────┘  │
   └──────────────────────────────────┬──────────────────────────────────┘
                                      │
                                      ▼
                       ┌────────────────────────────┐
                       │ Phase 0 OutputSanitizer     │   ← extended with
                       │  (extended):                │     SecretRedactor
                       │   - field-name regex (P0)   │     pass (chokepoint;
                       │   - JSONValue tree (P0)     │     refuses to write
                       │   - SecretRedactor (P2)     │     plaintext on the
                       │   - PromptInjectionMarker   │     persisted path)
                       │     (P2; tag, not redact)   │
                       └──────────────┬─────────────┘
                                      │
                                      ▼
                       ┌────────────────────────────┐
                       │ Phase 0 Writer + Cache      │   ← unchanged
                       │  atomic .tmp → os.replace   │
                       │  content-addressed cache    │
                       │  declared_inputs governs    │
                       │  cache keys (unchanged)     │
                       └──────────────┬─────────────┘
                                      │
                                      ▼
                .codegenie/context/
                ├── repo-context.yaml              (envelope; redacted)
                ├── schema-version.txt
                ├── raw/                            (per-probe JSON; redacted)
                │   ├── scip-index.scip            (binary; consumed by
                │   │                                Phase 3 adapter)
                │   ├── runtime-trace-{scenario}.{strace,json}
                │   ├── syft-sbom.json, grype-cves.json
                │   ├── semgrep-findings.json (redacted),
                │   ├── gitleaks-findings.json (redacted)
                │   ├── dep-graph.json
                │   └── import-graph.json
                └── runs/<utc-iso>-<short>.json     (Phase 0 audit anchor;
                                                     unchanged)
```

Three structural lines from this diagram, each load-bearing:

1. **No new chokepoints.** The Phase 0 coordinator/cache/sanitizer/writer are not extended in structure — only the sanitizer grows a new *pass* (`SecretRedactor`) added by composition, and the writer's chokepoint property survives. The performance design's parallel `cost-tier coordinator` and the security design's parallel `_run_in_container` chokepoint are both **rejected** in favor of registry annotations + `run_allowlisted`-via-`run_external_cli` wrapping.

2. **Kernel-only probes; no language plugin code.** Probes in Phase 2 are `applies_to_languages=["*"]` (or, for Node-specific Phase-1 follow-ons like `NodeReflectionProbe` already targeted at the existing Phase 1 surface, `["javascript","typescript"]`). npm-specific behaviors (`npm audit`, `npm outdated`, peer-dep resolution) ship inside the Phase 3 plugin. Maven probes ship in Phase 8+. This is the extension-by-addition fence (commitment §2.5).

3. **Adapter Protocols ship; adapter implementations don't.** ADR-0032's four `Protocol` classes are pure types (~80 LOC total) shipped under `codegenie.adapters.protocols`. They are documentation as code. The performance design's projection-as-adapter-interface and `scip-python` reader are **rejected** for Phase 2 — the projection shape is a Phase 3 concern owned by the first plugin's adapter implementation, which can decide whether to project, mmap, or re-parse at query time. Phase 2 ships the `.scip` binary blob; Phase 3 picks the consumption shape.

## Components

### 1. `IndexHealthProbe` (B2 — the load-bearing one)

- **Provenance:** [B] structure + [S] threat-aware degradation reasons − [S]'s cryptographic-anchor ceremony.
- **Purpose:** Detect and surface index staleness for every index Phase 2 produces (SCIP, runtime trace, SBOM, semgrep, conventions, skills). Silent staleness is the worst failure mode of the entire system (`production/design.md §2.3`, `CLAUDE.md` load-bearing). This probe is *what makes the load-bearing commitment §2.3 real* in Phase 2.
- **Interface:**
  ```python
  @register_probe
  class IndexHealthProbe(Probe):
      name: ProbeId = ProbeId("index_health")
      layer: Literal["B"] = "B"
      tier: Literal["base"] = "base"
      applies_to_tasks: list[str] = ["*"]
      applies_to_languages: list[str] = ["*"]
      requires: list[ProbeId] = []   # reads other probes' OUTPUTS; the
                                     # coordinator's topological order
                                     # places B2 last by registry annotation
                                     # (`runs_last=True`)
      declared_inputs: list[str] = [".codegenie/context/raw/*.json",
                                    ".git/HEAD",
                                    "<scip-index-output>",
                                    "<image-digest-token>"]
      cache_strategy: Literal["none"] = "none"  # MUST run every gather;
                                                # caching this probe is
                                                # the same bug as caching
                                                # Date.now()
      timeout_seconds: int = 10
  ```
- **Internal design:** B2 reads the freshness metadata each upstream probe already wrote into its own slice — `last_indexed_commit`, `files_indexed`, `files_in_repo`, `indexer_errors`, `last_traced_image_digest`, `built_image_digest`, `rule_pack_version`, etc. — and the current `git HEAD` (via `run_allowlisted("git", "rev-parse", "HEAD", ...)` — no `gitpython` dep, per critic best-practices Q §4). For each index it constructs a typed `IndexFreshness` value via a smart constructor:

    ```python
    # codegenie/indices/freshness.py
    from typing import Annotated, Literal, Union
    from datetime import datetime
    from pydantic import BaseModel, ConfigDict, Field

    class CommitsBehind(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)
        kind: Literal["commits_behind"] = "commits_behind"
        n: int
        last_indexed: str   # commit sha; raw str at the IO boundary

    class DigestMismatch(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)
        kind: Literal["digest_mismatch"] = "digest_mismatch"
        expected: str
        actual: str

    class CoverageGap(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)
        kind: Literal["coverage_gap"] = "coverage_gap"
        files_indexed: int
        files_in_repo: int

    class IndexerError(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)
        kind: Literal["indexer_error"] = "indexer_error"
        message: str

    StaleReason = Annotated[
        Union[CommitsBehind, DigestMismatch, CoverageGap, IndexerError],
        Field(discriminator="kind"),
    ]

    class Fresh(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)
        kind: Literal["fresh"] = "fresh"
        indexed_at: datetime

    class Stale(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)
        kind: Literal["stale"] = "stale"
        reason: StaleReason

    IndexFreshness = Annotated[Union[Fresh, Stale], Field(discriminator="kind")]
    ```

    The slice shape follows `localv2.md §5.2 B2` verbatim for backward compatibility (every key the spec named), but each `confidence: high|medium|low` field is *derived from* the typed `IndexFreshness` value rather than written directly by the probe. The flat string is what `repo-context.yaml` carries (the human-readable rendering); the typed value is what `codegenie.indices.freshness.IndexFreshness` round-trips through Pydantic for in-process consumers (Phase 3 adapters, Phase 8 Bundle Builder, `CONTEXT_REPORT.md`).
- **Phase-2-internal consumer.** To prevent the "sum type without a consumer" anti-pattern the critic surfaced (shared blind spot #1, [B]'s own §Risks §1), **Phase 2 itself ships one consumer**: a `CONTEXT_REPORT.md` "Confidence" section renderer (`src/codegenie/report/confidence_section.py`) that pattern-matches on `IndexFreshness` for every index slice, prints the reason for `Stale` variants, and is exercised by every golden-file test. A `mypy --warn-unreachable`-clean missing `case` is a build error from Phase 2 onward.
- **Why this instead of [S]'s cryptographic anchoring.** The security design's BLAKE3-chained audit-log lookup attacks an attacker who can write to `.codegenie/cache/` — but per Phase 0 ADR-0011, `.codegenie/` is 0700/0600 in the user's own directory. An attacker with that write capability already owns the host (commitment §2 threat model excludes host compromise). The critic [S] §"hidden assumption" #3 named this directly: the chain detects bit-rot, not adversaries. We keep the **structural** freshness signals (commit-equality, image-digest-equality, coverage-ratio, indexer-error-count) and reject the cryptographic layer.
- **What this does buy vs. mtime.** B2 deliberately does NOT consult filesystem `mtime`. The freshness signal is `(scip_indexed_commit == repo.HEAD)` — an O(1) string compare against an indexer-emitted header — plus the coverage ratio and the image-digest comparison. mtime-based freshness is forbidden via a Phase-0 `forbidden-patterns` pre-commit addition (`os.path.getmtime` / `Path.stat().st_mtime` banned inside `src/codegenie/probes/index_health.py`). [S]
- **Why this choice over the alternatives:** All three input designs proposed three different sum-type names (`AdapterConfidence` / `IndexConfidence` / `IndexFreshness`) for the same concept. We ship **one** name (`IndexFreshness`), in **one** module (`codegenie.indices.freshness`), and document why the other two are not needed yet: `AdapterConfidence` is ADR-0033's prescription for ADR-0032 *adapter outputs* — those ship with Phase 3, and the Phase 3 plugin author decides whether `AdapterConfidence = Trusted | Degraded | Unavailable` is the same shape or a layered shape over `IndexFreshness`. `IndexConfidence` is a name collision with the human-readable `confidence: high|medium|low` string in `repo-context.yaml`. One name, one module, one consumer in Phase 2. [synth — resolves critic finding #3]
- **Tradeoffs accepted:** B2 must run last (`runs_last=True` registry annotation). Coupling to every other probe's slice shape is real; we accept it because the coupling is *inverted* relative to what [P] proposed — B2 reads slice metadata that is already part of the schema; it does not require sibling probes to expose a `health_check(slice) -> AdapterConfidence` Protocol (which [P] proposed, and which would have been a contract change to every probe). [S]'s alternative — B2 reads the audit-log event stream — is rejected; Phase 2 ships no event stream.

### 2. `IndexFreshness` sum type module

- **Provenance:** [B] verbatim; [synth] adds the Phase-2 consumer requirement.
- **Purpose:** One name, one module, one variant set for index freshness in Phase 2.
- **Location:** `src/codegenie/indices/freshness.py` (the *only* file in the `codegenie.indices` package for Phase 2; `__init__.py:__all__ = ["IndexFreshness", "Fresh", "Stale", "StaleReason", "CommitsBehind", "DigestMismatch", "CoverageGap", "IndexerError"]`).
- **Tradeoffs accepted:** Lives outside `codegenie.probes.index_health` so Phase 3 adapter implementations and Phase 8 Bundle Builder can import without circular dependency on the probe module. [B]
- **Why this choice over the alternatives:** Co-locating in `probes/index_health.py` (the critic's preferred boring default) is rejected only because the `CONTEXT_REPORT.md` confidence-section renderer needs to import it without pulling in the probe registry, and the renderer is the Phase-2 consumer that closes the "schema without a consumer" gap. One additional package is the smallest separation that makes the consumer real.

### 3. `_run_external_cli` — single subprocess port for Layer B/G external CLIs

- **Provenance:** [S] Command pattern adapted to [B+all]'s "use the existing Phase 0 chokepoint" discipline. **Refused [S]'s parallel `_run_external_cli` chokepoint that would have created a second subprocess pathway.**
- **Purpose:** Invoke `scip-typescript`, `syft`, `grype`, `semgrep`, `ast-grep`, `ripgrep`, `gitleaks` under a uniform, single-chokepoint pattern that wraps Phase 0's `run_allowlisted`.
- **Interface:**
  ```python
  # codegenie/exec.py (extends Phase 0 module)
  async def run_external_cli(
      probe_name: ProbeId,
      argv: list[str],
      *,
      cwd: Path,
      timeout_s: float,
      allowlisted_egress: frozenset[str] = frozenset(),  # only for tools
                                                         #  that legitimately
                                                         #  fetch (grype DB)
      max_stdout_bytes: int = 64 * 1024 * 1024,  # 64 MB
  ) -> ProcessResult: ...
  ```
- **Internal design:** Delegates to the existing `run_allowlisted(argv, ...)` with three additions on top — (a) env strip enforced to Phase 0 allowlist (`PATH`, `HOME`, `LANG`, `LC_ALL`, `TERM`, `CODEGENIE_*`); (b) on **Linux only**, *optional* `bubblewrap --unshare-net --ro-bind <repo> /work --bind <tmpdir> /tmp/probe` wrap when `bwrap` is on PATH (graceful no-op when missing — bubblewrap is hardening, not a hard requirement; the structural defenses ride on `run_allowlisted`); (c) `stdout`/`stderr` capped at `max_stdout_bytes` and tail-included in any failure. The `bubblewrap` path is documented as best-effort hardening on Linux CI; macOS dev hosts fall back to env-strip + cwd restriction with a single startup warning. [S, scaled down per critic [S] finding #1]
- **Why this choice over the alternatives:** [S] proposed `bubblewrap` as a mandatory boundary on Linux with an admitted macOS gap; we keep it as opt-in-on-availability and instead lean on Phase 0's `ALLOWED_BINARIES` (the binary itself is checksum-allowlisted at the OS package-manager layer, not at our process layer — a real-world host-hygiene concern, not a Phase 2 design concern). The critic correctly flagged that mandatory `bwrap` creates a developer/CI parity problem that delivers very little additional defense over `run_allowlisted` for the actual Phase 2 threat model (the repo author, not a malicious CLI binary). [synth — resolves critic [S] findings #1, #6]
- **Tradeoffs accepted:** Layer C (`docker build` for SBOM/CVE/runtime-trace) is **NOT** routed through `_run_external_cli`; it stays on `run_allowlisted("docker", ...)` directly with explicit `--network=none --cap-drop=ALL --security-opt=no-new-privileges` flags constructed in the `RuntimeTraceProbe` module. Phase 0 ADR allows `docker` (Phase 2 ADR `0001-add-docker-to-allowed-binaries.md`); no separate `_run_in_container` chokepoint. The microVM migration path (ADR-0012, Phase 5+) replaces this call site by amending the probe module, not by swapping a hexagonal port. [synth — resolves critic [S] finding §"Hexagonal sandbox claims that smuggle subprocess into the core"]
- **Pattern decisions:** Command pattern at the value-typed-argv level. Refused: hexagonal port-and-adapter framing (one adapter today is one function; "Port" labeling is ceremony per critic [S] §"Hexagonal applied to `_run_external_cli`"). Refused: parallel `_run_in_container` for Layer C; Layer C calls `run_allowlisted("docker", ...)` directly.

### 4. SecretRedactor (Writer-chokepoint extension)

- **Provenance:** [S] structure − the encryption-key theatre + [synth] defer-storage policy.
- **Purpose:** Intercept every string in every `ProbeOutput.schema_slice` before it lands in `repo-context.yaml`, raw artifacts, cache, or audit; replace anything that matches a secret pattern with `<REDACTED:fingerprint=BLAKE3_8>`. Phase 2 **does not persist plaintext** at all.
- **Interface:**
  ```python
  # codegenie/output_sanitizer.py (extends Phase 0 module)
  def redact_secrets(slice_: dict[str, JSONValue], probe_name: ProbeId
                     ) -> tuple[dict[str, JSONValue], list[SecretFinding]]:
      """Returns (redacted_slice, in-memory findings list).
      The findings list is discarded after the gather; Phase 2
      persists NO plaintext."""
  ```
- **Internal design:** Runs after Phase 0's field-name regex and the `JSONValue` tree walk. Patterns from `gitleaks`-equivalent defaults (AWS `AKIA[0-9A-Z]{16}`, GitHub `ghp_[A-Za-z0-9]{36}`, JWT, RSA `-----BEGIN…PRIVATE KEY-----`, NPM `npm_[A-Za-z0-9]{36}`, Anthropic `sk-ant-…`) plus Shannon-entropy ≥ 4.5 bits/char for length ≥ 32 unknowns. Each match is replaced with `<REDACTED:fingerprint=<first-8-hex-of-blake3>>`; an in-memory `SecretFinding` is collected (probe_name, fingerprint, pattern_class, file:line if available) and printed to the CLI summary at gather end, but **not** persisted.
- **Why this choice over [S]'s encryption ceremony.** [S]'s per-repo key in `~/.codegenie/keys/<repo>.key` plus ciphertext in `.codegenie/findings/secrets/<fp>.enc` was — by [S]'s own §Risks §5 admission — encrypted-with-a-key-in-the-same-trust-tier. The critic correctly flagged this as obfuscation, not security ([S] critic finding #5). We pick a structurally simpler answer: **don't persist the plaintext at all in Phase 2**. The Planner (Phase 3+) does not need cleartext access to the secret to remediate it — it needs the *fact that a secret exists* at file:line, plus the pattern class. If a later phase needs cleartext for a specific judgment (e.g., a microVM-sandboxed CVE adjudicator), it can be re-derived at that point inside the microVM (ADR-0012) with the secret pattern as input. **Phase-5 microVM escalation path:** if/when cleartext access is genuinely required for an automated remediation, Phase 5's microVM picks up the cleartext directly from the analyzed repo at that point in time, processes it inside the sandbox, and never persists it. The Phase 2 design names this as the explicit escalation door (see Open questions §1). [synth — resolves critic finding #7]
- **Tradeoffs accepted:** A human reviewer who wants to manually inspect the actual secret string must run `gitleaks` themselves against the repo at PR-review time; the PR evidence bundle carries only the fingerprint + file:line. The team's existing secret-hunting workflow is unchanged. We pay one regression: Phase 2 cannot do "secret rotation suggestions" inline; that's deferred to a Phase 4+ task class.
- **Pattern decisions:** Chain-of-responsibility composition at the sanitizer level (the existing Phase 0 sanitizer is unchanged; `redact_secrets` is a new pass that the sanitizer pipeline orchestrates). Refused: Capability pattern across the LLM boundary (critic flagged [S]'s `SecretFindingCapability` as authorization-with-a-fancier-name — the LLM never holds the token; the helper that reads-and-renders is the actual access surface). [synth]

### 5. Layer G security-CLI wrappers — `SemgrepProbe`, `SyftProbe`, `GrypeProbe`, `GitleaksProbe`

- **Provenance:** [B] structure verbatim (one file per scanner, ≤ 200 LOC each, single-responsibility, no shared `ScannerRunner` abstraction).
- **Purpose:** Run third-party security/SBOM scanners; parse JSON output into typed schema slices via Pydantic smart constructors.
- **Public interface:** Each registers `@register_probe`. Internal types use the `ScannerOutcome = ScannerRan | ScannerSkipped | ScannerFailed` discriminated union from [B] verbatim.
- **Internal design:** (a) check tool availability via Phase 0 `tool_cache`; (b) invoke via `codegenie.exec.run_external_cli` with explicit argv (no shell, no string interpolation, `--metrics=off` for `semgrep` to refuse phone-home); (c) parse JSON via Pydantic smart constructor; (d) return `ProbeOutput`. Each scanner's findings flow through the writer-chokepoint `redact_secrets` pass before persistence — `gitleaks` finds the secret; the sanitizer redacts it; the slice that lands in `repo-context.yaml` is fingerprint-only.
- **Why this choice over the alternatives:** [B]'s "four files instead of one abstraction" line — the critic's [S] lens proposed a unified `_run_external_cli(... capability_token)` chokepoint specifically as the security primitive. We accept the chokepoint at the **subprocess** layer (`run_external_cli`) but not at the **scanner-parser** layer — semgrep's rule-pack flags, syft's image-vs-SBOM input mode, grype's SBOM input, and gitleaks's repo-root scan are genuinely different *shapes*, not interchangeable strategies. Critic-survivability: the security lens did not flag [B]'s four-file decomposition as wrong; it flagged the missing chokepoint. We give it the chokepoint at the right layer. [synth — resolves critic-noted tension between [B] §"Layer G security wrappers" and [S] §"Layer B/G external-CLI sandbox runner"]
- **Tradeoffs accepted:** ~200 LOC of probe-level scaffolding duplicated four times. The duplication is the point per [B] critic §"Composition + clear naming over generic frameworks" — each probe is reviewable in one sitting; a shared abstraction would force four genuinely-different invocations through one type signature.

### 6. `RuntimeTraceProbe` (C4 — multi-scenario harness)

- **Provenance:** [B] structure, [P] cache-key against image digest.
- **Purpose:** Capture runtime behavior (syscalls, loaded libraries, network endpoints, shell invocations) of the analyzed-repo's container under 5 scenarios (`startup`, `smoke_test`, `healthcheck`, `shutdown`, `error_path`).
- **Interface:** Standard probe; reads `.codegenie/scenarios.yaml` (Pydantic-validated; smart-constructor parsed; falls back to 5 defaults). Per-scenario result is a `ScenarioResult = TraceScenarioCompleted | TraceScenarioFailed | TraceScenarioSkipped` discriminated union per [B] verbatim.
- **Internal design:** Sequential per-scenario execution (no concurrency — multiple `docker run` instances of the same image race resource and confuse trace attribution). Each scenario: `docker build` → `docker run --network=none --cap-drop=ALL --security-opt=no-new-privileges` with `strace -f` attaching from host (Linux) or `dtruss` with sudo prompt (macOS) or fail-typed `StraceUnavailable` (other). All `docker`/`strace` calls go through Phase 0 `run_allowlisted` (Phase 2 ADR `0001-add-docker-to-allowed-binaries.md` extends `ALLOWED_BINARIES`). Per-scenario timeout 120 s; aggregate timeout 600 s.
- **Cache key:** The probe's `declared_inputs` includes `Dockerfile`, `.codegenie/scenarios.yaml`, AND a **special declared-input token** `image-digest:<resolved-from-Dockerfile-FROM-and-build-context>` — the resolved local image digest is treated as a declared input, not as a cache-key bypass. This satisfies Phase 0 I1 (`declared_inputs` is the universal cache key) and resolves critic [P] finding #6. The image-digest resolver is provided via an optional `ProbeContext.image_digest_resolver: Callable[[Path], str | None] | None = None` field — a Phase-2-ADR-gated ProbeContext addition mirroring Phase 1 ADR-0002's `parsed_manifest` precedent (one optional callable, default None, defensive-check at the call site). This is the **one** ProbeContext field Phase 2 adds; it does NOT touch the `Probe` ABC. [synth — resolves critic [P] finding #6]
- **Why this choice over [P]'s image-digest-keyed cache bypass:** [P] proposed letting C-layer probes override `cache_key()` directly, deviating from the Phase 0 `declared_inputs` model. The critic flagged this as a structural deviation that future probes would copy. Image digest as a *declared input token* gives the same cache-hit behavior with no contract deviation — Phase 0's `declared_inputs` spec already permits special tokens (per `localv2.md §4`).
- **Tradeoffs accepted:** macOS `dtruss` requires sudo; we deterministically emit `TraceScenarioFailed(reason=StraceUnavailable())` on macOS rather than prompting, so the macOS path is *behaviorally distinct* and surfaces in `tests/property/test_trace_portability.py`. Cold p50 ~90 s (5 scenarios × ~15 s); image-digest cache key means a `package.json`-only change hits cache.

### 7. Adapter `Protocol` definitions (kernel side of ADR-0032 — documentation as code)

- **Provenance:** [B] verbatim. Critic-acknowledged risk: "Strategy via Protocol with zero implementations." We accept the risk because the Protocol *is* the spec Phase 3's first adapter must implement against; Phase 3's exit criterion includes "the first adapter implements the Phase 2 Protocols unchanged" — any drift is a Phase 2 amendment, not a Phase 3 quiet edit.
- **Purpose:** Define the four `Protocol` interfaces (`DepGraphAdapter`, `ImportGraphAdapter`, `ScipAdapter`, `TestInventoryAdapter`) plus `AdapterConfidence` placeholder. **No implementations** in Phase 2.
- **Where it lives:** `src/codegenie/adapters/protocols.py` (~80 LOC, pure types, stdlib + `typing`). `AdapterConfidence` lives in `codegenie.adapters.confidence` (separately, because — per critic finding #3 — its variant set is owned by Phase 3 when the first adapter ships; Phase 2 declares a placeholder sum `Trusted | Degraded(reason: str) | Unavailable(reason: str)` to give Phase 3 a typed target, marked with a docstring `# Phase 3 plugin may extend; revise at first adapter`).
- **Tradeoffs accepted:** No `NullAdapter` ships in Phase 2 (critic [B] finding #2 flagged the `NullAdapter` fixture as schema-validating-itself). The Phase 3 plugin's `vulnerability-remediation--node--npm` is the first real implementation; Phase 2's exit does not require an implementation, only the Protocols + the Phase 3 contract to consume them unchanged.

### 8. `TCCMLoader` (kernel side of ADR-0029)

- **Provenance:** [B] verbatim, scoped down by [synth] response to critic finding [B] #3.
- **Purpose:** Load and Pydantic-validate Task-Class Context Manifests. **No Bundle building** (Phase 8). **No TCCM fixture in `tests/fixtures/plugins/`** in Phase 2 (the critic flagged this as schema-validating-itself).
- **Public interface:** `TCCMLoader.load(path: Path) -> Result[TCCM, TCCMLoadError]`. `DerivedQuery` is a Pydantic discriminated union over the **five** ADR-0030 primitives (no `Unknown` variant — per [B]'s open Q §3 recommendation: ADR-amend on a sixth primitive).
- **Where it lives:** `src/codegenie/tccm/{loader.py, model.py, queries.py}`.
- **Phase-2-internal consumer.** To prevent the schema-without-consumer trap the critic flagged, **Phase 2 ships one TCCM in-tree** — `docs/phases/02-context-gather-layers-b-g/_reference-tccm/tccm.yaml` — an *illustrative* manifest for the `index-health-self-check` task class. This is **not** a plugin (no `plugin.yaml`; no probes; no subgraph); it is a deliberately-minimal reference fixture that exercises every field of the `TCCM` Pydantic model. The integration test (`tests/integration/tccm/test_reference_tccm_roundtrips.py`) loads it, asserts the schema roundtrips, and consumes one `DerivedQuery` variant per primitive via a mock dispatcher. The reference TCCM is documentation, not infrastructure — it ships in `docs/`, not in `plugins/`.
- **Tradeoffs accepted:** A small DSL surface (the five `DerivedQuery` variants) ships before any plugin needs them. The alternative — `DerivedQuery: dict[str, Any]` "for now" — directly violates ADR-0033 §1. Critic [B] finding #3 surfaced that no real consumer exists; we close that gap by shipping the reference TCCM under `docs/` (one consumer in the integration-test path, not under `plugins/` where it would imply pluggability that Phase 3 owns).

### 9. `SkillsLoader` (D2)

- **Provenance:** [B] verbatim + [S]'s `_safe_yaml_load_skill` discipline collapsed into the existing Phase 1 `safe_yaml.load` chokepoint.
- **Purpose:** Load and index YAML-frontmatter `SKILL.md` files from `~/.codegenie/skills/`, `.codegenie/skills/`, optional `~/.codegenie/skills-org/`. Validate frontmatter against a Pydantic schema. Body is byte-offset-recorded only (progressive disclosure — commitment §2.7).
- **Internal design:** YAML parsed via the **Phase 1 `codegenie.parsers.safe_yaml.load` chokepoint** — *not* a parallel `_safe_yaml_load_skill` helper. The critic correctly flagged [S]'s parallel loader as Rule 7's anti-pattern (two existing conventions blended). Phase 1's `safe_yaml.load` already wraps `yaml.CSafeLoader` with size + depth caps; we add **one** extra discipline at the Skills call site (and only there): `os.open(path, O_NOFOLLOW | O_NOCTTY)` followed by `os.fdopen` before passing to `safe_yaml.load`. The `O_NOFOLLOW` flag refuses symlinks at the OS level, which is the genuine Phase-2 attack surface — Skills are user-writable across three trust tiers, and `~/.codegenie/skills/x/SKILL.md → /etc/passwd` is in [S]'s adversarial-fixture corpus.
- **Tradeoffs accepted:** Three-tier merge (user > repo-local > org-shared) with first-tier-wins and a *loud* `skill_shadowed` warning in the CLI summary on every collision per [S]'s open Q §6. Bodies BLAKE3-hashed but not read into memory (progressive disclosure). One golden test asserts a hostile SKILL.md with `!!python/object` in frontmatter raises `SkillsLoadError` and executes no code.
- **Why this over [S]'s parallel loader:** Phase 1's existing chokepoint is sufficient; the `O_NOFOLLOW` discipline lives at the Skills-specific call site, not in a parallel YAML loader. [synth — resolves critic [S] finding #3]

### 10. `ConventionsCatalogLoader` (D5)

- **Provenance:** [B] verbatim.
- **Purpose:** Load and apply org convention catalog (`~/.codegenie/conventions/*.yaml`); emit typed `ConventionResult = Pass | Fail | NotApplicable` discriminated union per rule.
- **Internal design:** Pure functions over Pydantic-modeled rules; one `match` per pattern type with `assert_never` on the unreachable branch. Pattern types (`dockerfile_pattern`, `dockerfile_pattern_inverted`, `file_pattern`, `missing_file`) are themselves a Pydantic discriminated union.
- **Where it lives:** `src/codegenie/conventions/{catalog.py, model.py}`.
- **Tradeoffs accepted:** No rule engine. Conventions in Phase 2 are simple file/regex/Dockerfile checks; OPA/Rego ships in Phase 16 (ADR-0021) when policy engines become real.

### 11. `DepGraphProbe` (B5 — kernel skeleton with sum-typed ecosystem discriminator)

- **Provenance:** [B] structure − [B]'s string-keyed-dict deferred sum type.
- **Purpose:** Build a `networkx.DiGraph` of the repo's internal package dependencies (monorepo modules and cross-references). Ecosystem-specific resolution lives in plugin-side adapters (Phase 3+); Phase 2 only stitches Phase-1's already-parsed manifests into the graph.
- **Internal design:** Reads Layer A's `manifests` and `build_system` slices Phase 1 wrote. For each manifest path, dispatches to a per-ecosystem builder via a **`@register_dep_graph_strategy(ecosystem: PackageManager)` decorator** mirroring Phase 0's `@register_probe`. [B]'s open-coded dict (`ecosystem-detector: dict[str, Callable]`) is replaced with a decorator registry, satisfying ADR-0033's Open/Closed discipline at the file boundary. The `PackageManager` sum type already exists in the schema (`["bun", "pnpm", "yarn-classic", "yarn-berry", "npm"]` per Phase 1 ADR-0013) — Phase 2 imports it and uses it as the decorator key.
- **Why this choice over [B]'s deferred sum-type:** Critic [B] finding #5 directly attacked the "TODO sum-type after first plugin ships" comment. The decorator-registry pattern is the same Open/Closed primitive Phase 0 already ships for probes; using it here is one decorator + a typed registry, not a new abstraction. The fix is ~30 LOC; the deferral was speculation. [synth — resolves critic finding #5 against [B]]
- **Where it lives:** `src/codegenie/depgraph/{builder.py, model.py, registry.py}`.

### 12. `TreeSitterImportGraphProbe` (B3 — kernel skeleton)

- **Provenance:** [P]'s probe scoped down (no internal thread pool); [B]'s deferral overridden because B3 is in `localv2.md §5.2` as Phase-2 scope.
- **Purpose:** Extract file-level import edges from the source tree using tree-sitter grammars. Emits a `networkx.DiGraph`-serializable JSON to `raw/import-graph.json`. Forward+reverse adjacency is **not** pre-computed in Phase 2 — Phase 3's first `ImportGraphAdapter` decides whether to project, mmap, or walk at query time.
- **Internal design:** `py-tree-sitter` bindings (the **one** new C-extension dep Phase 2 accepts via amendment to Phase 1 ADR-0009; see new ADR `0002-tree-sitter-grammars-phase-2-amendment.md`). Per-file extraction is ~5 ms; for a 50k-LOC repo with 2k source files, ~10 s cold serially. **No internal `ThreadPoolExecutor`** — the critic [P] finding §"second concurrency layer" was correct that hidden parallelism inside a probe lies to the coordinator's semaphore budget. The probe is one CPU slot under the Phase 0 single semaphore; sequential extraction is the boring shape.
- **Grammar pinning:** Grammar `.so`/`.dylib` BLAKE3 pins recorded in `tools/grammars.lock` (vendored; reviewed-as-data). Load-time mismatch is a typed `GrammarLoadRefused` failure mode. Grammars are loaded **in-process** in Phase 2 (the [S] design's `_grammar_runner` out-of-process subprocess is rejected as over-engineering for the actual Phase-2 attack model — a malicious grammar would be a deliberate supply-chain compromise the pin already guards against). [synth — accepts critic [S] §"hidden assumption" #1 on bubblewrap as analogous]
- **Why we accept this C-extension dep:** Phase 1 ADR-0009's "named-trigger threshold" applies. The trigger: `localv2.md §5.2 B3` names `tree-sitter` as a *required* tool for B3; Phase 2 cannot ship B3 without it. The ADR amendment (`docs/phases/02-context-gather-layers-b-g/ADRs/0002-tree-sitter-grammars-phase-2-amendment.md`) records the trigger fired, the CVE-feed surface accepted, and the wheel-matrix cost. The performance design's `msgpack`/`scip-python`/`tantivy`/`gitleaks-python` *all remain rejected* — only `py-tree-sitter` + grammar packs are added, because only `py-tree-sitter` has a Phase 2 named consumer.

### 13. Probe registry annotations (the "cost-tier" discussion, resolved)

- **Provenance:** [synth] — overrules both [P] (`cost_tier` ABC field) and [B] (no scheduling hint at all).
- **Purpose:** Give the Phase 0 coordinator enough information to schedule expensive probes intelligently without editing the `Probe` ABC.
- **Interface:** The `@register_probe` decorator (Phase 0, frozen) is extended to accept **optional keyword arguments** that ride alongside the probe in the registry dict — they are *annotations on the registry entry*, not fields on the `Probe` class. The signature becomes:
  ```python
  def register_probe(
      *,
      heaviness: Literal["light", "medium", "heavy"] = "light",
      runs_last: bool = False,
  ) -> Callable[[type[Probe]], type[Probe]]: ...
  ```
  Probes opt in by decoration: `@register_probe(heaviness="heavy")` on `RuntimeTraceProbe` and `SCIPIndexProbe`. The coordinator reads these from the registry when sorting the topological-order chain (heavy probes start first under the single Phase 0 `Semaphore(min(cpu_count(), 8))`); `runs_last=True` reserves the slot for `IndexHealthProbe`.
- **Why this over [P]'s `cost_tier`:** [P] proposed `cost_tier: Literal[0,1,2,3]` as a new ABC field, defended as analogous to Phase 1's `parsed_manifest` addition. The critic correctly noted (finding #2) that `parsed_manifest` was added to `ProbeContext`, not to `Probe` itself; the ABC was untouched. **`cost_tier` is data the coordinator needs to dispatch, not data the probe needs to declare.** Registry-side annotations capture exactly this scheduling concern at the right layer and require zero ABC edits. The Phase-0 single semaphore is preserved (no per-tier semaphore explosion — the critic [P] finding §"hidden assumption" #2 noted GitHub-hosted runners have `cpu_count()=2` where per-tier sizing degenerates to 2-vs-2 starvation).
- **Why this over [B]'s "no scheduling hint at all":** Without `heaviness`, the coordinator runs the 84-second `RuntimeTraceProbe` last by topological accident, blocking cold-gather. The annotation is a soft sort key, not a separate semaphore; it does not change the contract surface — it changes which task starts in which order under the existing single-semaphore budget. [synth — resolves critic finding #2]
- **Tradeoffs accepted:** The coordinator's `_dispatch` extends by ~15 LOC to read the annotation and sort the ready-queue. This is a non-trivial coordinator edit; we ADR-gate it (`docs/phases/02-context-gather-layers-b-g/ADRs/0003-coordinator-heaviness-sort-annotation.md`). The edit is to the **coordinator's scheduling order**, not to the **chokepoint surface area** Phase 0 froze (`Semaphore`, `wait_for`, failure-isolation `try/except`, `ProbeOutput` flow); the chokepoint is preserved.

### 14. Multi-repo fixture portfolio + the stale-SCIP fixture (roadmap exit criterion)

- **Provenance:** [P]'s portfolio sizing + [synth] explicit exit-criterion wiring.
- **Purpose:** Five fixture repos under `tests/fixtures/portfolio/` exercising different probe surfaces. The **load-bearing one** is `tests/fixtures/portfolio/stale-scip/`: its `.codegenie/cache/` is pre-populated with a SCIP index from a known prior commit; the repo HEAD has moved. `IndexHealthProbe` MUST detect this and return `IndexFreshness.Stale(reason=CommitsBehind(n>=1, last_indexed=<prior>))`. `tests/adv/phase02/test_stale_scip_fixture.py` asserts the typed outcome; the build FAILS if the probe doesn't catch it.
- **Why this matters:** This is **exactly the roadmap exit criterion** ("IndexHealthProbe surfaces at least one real staleness case in CI (deliberately seeded fixture) — proving the probe actually catches what it's there to catch"), encoded as a CI gate. Phase 2 cannot exit without it.
- **CI lane:** Serial (no `pytest-xdist` — the Phase 0 veto holds). Estimated CI walltime growth ≤ 6 minutes; the bench canary `tests/bench/bench_portfolio_walltime.py` is advisory.

## Data flow

A representative warm-path run on a real Node.js repo (~5k files, TypeScript, pnpm, GitHub Actions, Helm, image present in local registry) where `src/payments/processor.ts` changed since last gather:

1. **Phase 0 CLI + tool-readiness.** Extended for `semgrep`, `syft`, `grype`, `gitleaks`, `scip-typescript`, `tree-sitter`, `docker`, `strace`. Missing tool → typed `MissingToolError`; optional tool → probe ships `confidence: low` slice.
2. **Phase 0/1 prelude.** `RepoSnapshot` via `run_allowlisted("git", "rev-parse", "HEAD")`. PathIndex built. Layer A probes run; most cache-hit. ~150 ms.
3. **Phase 0 coordinator dispatches Phase 2 probes** sorted by registry `heaviness` annotation (heavy first):
   - `SCIPIndexProbe` (heavy) starts; `RuntimeTraceProbe` (heavy) starts; `SemgrepProbe`, `GitleaksProbe`, `SyftProbe`, `TreeSitterImportGraphProbe`, `DockerfileProbe` (medium) all dispatch under the single `Semaphore(min(cpu_count(), 8))`. Light probes (`ConventionProbe`, `SkillsIndexProbe`, etc.) wait for slot availability but finish during long-tail of heavy probes. **No per-tier semaphores; one budget.**
4. **`SCIPIndexProbe` MISSES** (`.ts` source changed) — re-indexes; ~8 s. **`SyftProbe`/`GrypeProbe` cache-HIT** (image digest unchanged — image-digest token in `declared_inputs` matches). **`SemgrepProbe` MISSES** the affected files; ~3 s incremental. **`GitleaksProbe` MISSES** (.git changed); ~2 s. Findings flow through `redact_secrets` at the writer chokepoint — any AWS key in `.git/` history is replaced with `<REDACTED:fingerprint=…>` in the persisted slice.
5. **`IndexHealthProbe` runs last** (registry `runs_last=True`). Reads sibling slices; constructs `IndexFreshness.Fresh(indexed_at=…)` for SCIP (just re-indexed), `IndexFreshness.Fresh` for runtime trace (image digest match), etc. The `index_health.{scip,runtime_trace,sbom,semgrep}.confidence` strings in the persisted slice are derived from these typed values.
6. **Output merge + sanitizer + writer.** The two-pass sanitizer (Phase 0 + `redact_secrets`) runs once over the merged envelope. Validates against schema. Writes `.codegenie/context/repo-context.yaml` atomically.
7. **`CONTEXT_REPORT.md` Confidence section** is generated alongside; pattern-matches every `IndexFreshness` value via `assert_never`-checked `match`. Any `Stale` variant prints its reason.
8. **Audit anchor** (Phase 0 unchanged). Per-probe execution path (`Ran` / `CacheHit` / `Skipped`).
9. **Exit 0.** Total wall-clock: ~10 s, dominated by SCIP re-index. Without SCIP re-index (whitespace-only edit, SCIP cache-hits): ~1.5 s.

**Cold gather (first time on a 50k-LOC service with no built image):** SCIP re-index (~10 s) + `docker build` (~47 s) + 5 trace scenarios (~75 s sequential) + others in parallel under the single semaphore. Total: ~110-140 s. Meets the ≤ 180 s p95 cold-gather target.

## Failure modes & recovery

| Failure | Detected by | Containment | Recovery | Source |
|---|---|---|---|---|
| External CLI missing (e.g., `semgrep` not on `$PATH`) | Phase 0 tool-readiness check at startup | Typed `MissingToolError`; CLI exits with install-command-from-`localv2.md §6` if mandatory | Operator installs the tool | [B] |
| External CLI exits non-zero | `run_external_cli` returns non-zero `ProcessResult` | `ScannerOutcome.ScannerFailed(exit_code, stderr_tail)`; `ProbeOutput.confidence="low"` | Coordinator continues (Phase 0 failure isolation) | [B+S] |
| External CLI emits invalid JSON | Pydantic smart constructor returns `Result.Err(ParseError(...))` | Typed error; stdout/stderr tail in audit | Operator inspects audit log | [B] |
| `scip-typescript` timeout on huge monorepo | `asyncio.wait_for` at `timeout_seconds=300` | `IndexFreshness.Stale(reason=IndexerError(message="timeout"))`; Phase 3 adapter falls back to tree-sitter (per ADR-0032 declared fallback) | Operator re-runs with `--force-refresh` after fixing the underlying issue | [P+B] |
| `docker build` fails | Subprocess exit code | C-tier probes emit `confidence="unavailable"`; gather completes with degraded tier-C | Operator fixes Dockerfile; re-runs | [P] |
| `strace` exec fails (macOS) | `run_external_cli` raises `StraceUnavailable` typed exception | `TraceScenarioFailed(reason=StraceUnavailable())` per scenario; `IndexHealthProbe` reads aggregate `TraceCoverage` and emits `IndexFreshness.Stale(reason=IndexerError(message="strace_unavailable"))` for runtime_trace; gather still succeeds | macOS path is permanent; CI is Linux-canonical | [P+B+S] |
| `gitleaks` finds a real AWS key in `.git/` history | `gitleaks` parses; SecretRedactor matches `AKIA...` | Plaintext replaced with `<REDACTED:fingerprint=…>` in `repo-context.yaml`, raw artifact, cache. **Plaintext is not persisted in Phase 2.** | Human inspects fingerprint + file:line; runs `gitleaks` manually for cleartext at PR review time | [S, scaled] |
| Hostile YAML in Skill triggers `!!python/object` | `safe_yaml.load` (Phase 1 chokepoint) refuses; `yaml.YAMLError` raised | `SkillsLoader` wraps as `Result.Err(SkillsLoadError)`; the offending file is skipped with an explicit error in the gather summary; other Skills load | Operator inspects the named file; investigates supply chain | [B+S] |
| Symlink `~/.codegenie/skills/x/SKILL.md → /etc/passwd` | `os.open(O_NOFOLLOW)` returns ELOOP at the Skills call site | Skill skipped with typed `SkillsLoadError(reason="symlink_refused")`; loud CLI warning | Operator investigates planted symlinks | [S] |
| `tree-sitter` grammar BLAKE3 mismatch against `tools/grammars.lock` | Pre-load hash check | `GrammarLoadRefused` typed failure; probe slice marked `confidence: low`; no grammar code executes | Operator deliberately updates the pin (PR-reviewable) or investigates supply chain | [S] |
| Stale-SCIP fixture in CI (deliberate seeded staleness) | `IndexHealthProbe` reads `last_indexed_commit` mismatch | Returns `IndexFreshness.Stale(reason=CommitsBehind(n>=1, last_indexed=<prior>))`; CI test asserts this exact typed outcome; build passes only if probe caught it | This is the roadmap exit criterion | [synth] |
| Hostile semgrep/grype/gitleaks JSON (truncated, oversized, deeply nested) | Pydantic smart constructor + `JSONValue` tree depth cap | Probe emits `ScannerOutcome.ScannerFailed(reason="invalid_json", stderr_tail=stdout[-2048:])`; sanitizer rejects oversized payloads upstream | Operator inspects audit | [B+S] |
| Adversarial Dockerfile (forkbomb, infinite loop in build) | Phase 0 timeout + container `--network=none --cap-drop=ALL --security-opt=no-new-privileges` | Probe times out; `TraceScenarioFailed(reason=Timeout(seconds=120))`; coordinator continues per Phase 0 isolation | Operator inspects audit; investigates adversarial repo | [B+S] |
| Concurrent gather race against same repo | Phase 0 advisory lock at `.codegenie/cache/.lock` | Second invocation waits or fails fast (configurable) | — | [P] |
| Plain Stage 7 telemetry hooks needed | — | Not in Phase 2 scope per [B]'s acknowledged blind spot; Phase 9/11 ships them | — | [B] |

**Pattern across all rows:** every failure produces a typed value, not a thrown exception (Rule 12 — fail loud, structural). Exceptions are reserved for genuinely-exceptional cases (bugs, OOM, signals).

## Resource & cost profile

- **Tokens per run:** 0. Phase 0 `fence` job continues to assert. Phase 2's `gather` extras additions: `networkx` (pure Python); `py-tree-sitter` + grammars (the **one** C-extension exception per amendment to Phase 1 ADR-0009). **NO** `msgpack`, `scip-python`, `tantivy` (opt-in only, falls back to `ripgrep`-via-`run_allowlisted`), `gitleaks-python` (we shell out to the `gitleaks` binary), `httpx`/`requests`/`socket`. **No `gitpython`** — `git` is already in `ALLOWED_BINARIES`; we shell out for HEAD + rev-list-count.
- **External CLI runtime additions to ALLOWED_BINARIES:** `semgrep`, `syft`, `grype`, `gitleaks`, `scip-typescript`, `tree-sitter` (binary, optional — fallback to Python bindings), `docker`, `strace` (Linux). Each entry adds to Phase 0 `ALLOWED_BINARIES` via ADR `0001-add-docker-and-security-cli-tools.md`.
- **Wall-clock (1k-file fixture):** Cold p50 ≤ 90 s; p95 ≤ 180 s. Warm cache p50 ≤ 1.5 s. Incremental (single .ts change) p50 ≤ 10 s.
- **Memory peak:** ≤ 600 MB during cold gather (dominated by `scip-typescript` ~400 MB subprocess and `semgrep` ~200 MB; codegenie process ~150 MB). Warm: ≤ 200 MB.
- **Disk per gather:** repo-context.yaml ~60 KB; `raw/` ~8 MB (SCIP binary ~2 MB; SBOM ~1 MB; traces ~4 MB); audit anchor ~500 bytes per gather.
- **CI walltime delta vs. Phase 1:** +5–6 minutes serial on the portfolio + adversarial lanes. No `pytest-xdist` — the Phase 0 veto holds; the Phase 2 portfolio is small enough that serial CI is acceptable. The performance design's xdist exception is **rejected** (resolves critic finding #8 by not reversing the veto).
- **Where security/best-practices traded off perf:** (a) sequential runtime trace scenarios (~75 s wall-clock floor vs. theoretical 15 s if parallel) — accepted because parallel traces against the same image race resources and confuse attribution; (b) no in-process `ThreadPoolExecutor` inside `TreeSitterImportGraphProbe` (~10 s sequential vs. theoretical ~3 s threaded) — accepted because hidden parallelism lies to the coordinator's semaphore budget; (c) plaintext-not-persisted secret-redaction (operator must manually re-derive cleartext at PR review time) — accepted because in-tier encryption is theatre.

## Test plan

The Phase 0 + Phase 1 test stack carries forward unchanged. Phase 2 adds:

**Unit tests** (`tests/unit/probes/`, `tests/unit/{indices,runtime,security,conventions,skills,tccm,adapters,depgraph}/`):

| Test module | Asserts |
|---|---|
| `test_index_health_probe.py` | Per-source freshness assertions; every `IndexFreshness` variant constructible; `cache_strategy = "none"` enforced; `runs_last` annotation respected by coordinator |
| `test_indices_freshness.py` | `IndexFreshness` round-trip (`model_dump_json` → `model_validate_json` = identity); exhaustive `match` test that uses `assert_never` (missing case is a `mypy --warn-unreachable` build error in CI) |
| `test_scip_index_probe.py` | `scip-typescript` invocation; output binary present; cache-key sensitivity to tool-version stamp + Merkle of `.ts` files; timeout → `IndexerError` |
| `test_runtime_trace_probe.py` | Per-scenario sequential execution; per-scenario timeout; macOS `StraceUnavailable` deterministic path |
| `test_dep_graph_probe.py` | `@register_dep_graph_strategy` registry works; one strategy per `PackageManager` variant; monorepo graph correct |
| `test_tree_sitter_import_graph.py` | Per-file extraction; no internal thread pool; grammar pin verified at load |
| `test_security_wrappers.py` (one per scanner) | Pydantic smart constructor; subprocess mocked via `pytest-subprocess`; `ScannerOutcome` variants |
| `test_skills_loader.py` | Frontmatter parsing; `O_NOFOLLOW` symlink refusal; three-tier merge + shadowing warning; body byte-offset not loaded |
| `test_conventions_catalog.py` | One test per pattern type; `NotApplicable` path |
| `test_tccm_loader.py` | Loads the reference TCCM (`docs/phases/02-context-gather-layers-b-g/_reference-tccm/`); unknown `compute:` variant fails fast; five `DerivedQuery` variants round-trip |
| `test_adapter_protocols.py` | Protocol structural typing (a no-op stub passes `isinstance` via `runtime_checkable`); `AdapterConfidence` variants construct |
| `test_secret_redactor.py` | Each pattern class matches; entropy threshold catches generic high-entropy strings; **mutation test**: weakened regex causes at least one test to fail |
| `test_run_external_cli.py` | Env strip; allowlisted-egress respected; stdout cap; `bubblewrap` graceful no-op on macOS |

**Integration tests** (`tests/integration/`):

- One per scanner against a real-tool invocation (tiny vulnerable JS fixture for semgrep; tiny built image for syft → grype; planted dummy AWS key for gitleaks). CI-gated on the tool being present; skip-with-warning if missing.
- `RuntimeTraceProbe` end-to-end against a hello-world Node container; `shared_libs_loaded` contains expected entries; `TraceCoverage = Complete` when all 5 scenarios succeed.
- `tests/integration/tccm/test_reference_tccm_roundtrips.py` — loads the reference TCCM, asserts each `DerivedQuery` primitive variant round-trips, dispatcher mock returns typed values.

**Golden-file tests** (`tests/golden/probes/`):

- One golden file per probe per portfolio fixture. CI diffs live output vs. committed expected; `pytest --update-golden` regenerates.
- Five-repo portfolio under `tests/fixtures/portfolio/`: `minimal-ts`, `native-modules`, `monorepo-pnpm`, `distroless-target`, `stale-scip` (the load-bearing fixture).

**Property tests** (`tests/property/`):

- `IndexFreshness` round-trip identity (Hypothesis).
- `SkillsLoader.find_applicable(...)` monotone in `evidence_keys`.
- `TraceCoverage` well-formed for any combination of scenario outcomes.

**Adversarial tests** (`tests/adv/phase02/`) — the load-bearing exit:

- **`test_stale_scip_fixture.py`** — the roadmap exit criterion. Builds expect `IndexFreshness.Stale(reason=CommitsBehind(n>=1, last_indexed=<known prior commit>))`; build FAILS otherwise.
- `test_hostile_skills_yaml.py` — `!!python/object`, billion-laughs, deep nesting, symlink-escape filenames. ≥ 8 cases.
- `test_secret_in_source.py` — gitleaks finds seeded secret; SecretRedactor replaces in `repo-context.yaml`; raw artifact; cache; **and** the audit anchor. Plaintext present in zero persisted files.
- `test_image_digest_drift.py` — mutating the built image between gathers correctly invalidates tier-C caches via the image-digest declared-input token.
- `test_concurrent_gather_race.py` — two concurrent gathers don't corrupt cache; Phase 0 advisory lock works.

**End-to-end tests** (`tests/e2e/`):

- One end-to-end gather against a pinned open-source Node.js fixture; full `repo-context.yaml`; every `IndexFreshness` value is `Fresh`.

**Bench (advisory, not gating; Phase 0 §3.2 discipline):**

- `bench_portfolio_walltime.py` — flags > 50% regressions on warm/cold p50.

## Design patterns applied

| Decision | Pattern applied | Why here | Source | Pattern NOT applied (and why) |
|---|---|---|---|---|
| `IndexFreshness = Fresh \| Stale(reason: StaleReason)` instead of `freshness: Optional[str]` | Sum type / tagged union + Make-illegal-states-unrepresentable (ADR-0033 §3–4) | "Stale without a reason" is the silent failure mode B2 exists to prevent; `mypy --warn-unreachable` makes a missed `case` a build error | [B] | Null Object Pattern — loses the *reason* a stale index is stale |
| `_run_external_cli` (Layer B/G) and direct `run_allowlisted("docker", ...)` (Layer C) | Command pattern at the value-typed-argv level | Auditing "every external CLI invocation" is `grep _run_external_cli` for B/G; `grep "docker"` for C. One chokepoint per family; one ADR per `ALLOWED_BINARIES` addition | [S, scaled] | Hexagonal Port/Adapter — one adapter today is a function; "Port" labeling is ceremony (critic [S]) |
| Adapter `Protocol` definitions in `codegenie.adapters.protocols` | Structural subtyping (PEP 544) | Plugins are external (ADR-0031); inheriting from our ABC would couple plugin authors to our class hierarchy | [B] | Abstract Factory — too heavyweight for "instantiate the class named in `plugin.yaml`" |
| `@register_probe(heaviness="heavy", runs_last=True)` registry annotations | Registry pattern + decorator-data over ABC-fields | Scheduling data belongs to the coordinator's view, not the probe's contract; matches Phase 0's existing decorator-registry primitive | [synth] | `cost_tier: Literal[0,1,2,3]` ABC field ([P]) — ABC churn for a scheduling optimization (critic finding #2) |
| `@register_dep_graph_strategy(ecosystem: PackageManager)` decorator | Open/Closed at the file boundary | Adding a new ecosystem (Maven, Poetry) is a new file + decorator, never an edit to `DepGraphProbe` | [synth — overrules [B]'s deferred string-dict] | String-keyed dict ([B]) — Phase-3-deferred sum type was the exact ADR-0033 violation the critic flagged |
| `SecretRedactor` as a chokepoint pass in the existing Phase 0 sanitizer | Chain of responsibility / pipeline composition | Single chokepoint discipline survives; one pass added by composition, not a parallel sanitizer | [synth — scales [S]] | Capability pattern across LLM boundary ([S]) — LLM never holds the token; authorization with a fancier name (critic [S] finding §"Capability pattern") |
| `ScannerOutcome`, `ScenarioResult`, `ConventionResult`, `IndexFreshness` all Pydantic discriminated unions | Make illegal states unrepresentable (ADR-0033 §4) | Every state machine in Phase 2 surfaces as a typed sum; pattern-matching exhaustiveness via `mypy --warn-unreachable` | [B] | `Optional[T]` for parse results — loses the *reason* (same argument as `IndexFreshness`) |
| One file per Layer G scanner; no shared `ScannerRunner` abstraction | SRP + Rule of Three | Four scanners with four genuinely different I/O shapes don't share an abstraction worth ~60 LOC; chokepoint is at `_run_external_cli`, not at scanner-parser | [B] | Template Method / Generic ScannerRunner — speculative abstraction |
| Reference TCCM under `docs/`, not `plugins/` | Documentation as code, kept out of the plugin namespace | Phase 3 owns the plugin namespace; Phase 2 ships the schema with one consumer (the integration test) | [synth — overrules [B]'s `tests/fixtures/plugins/synthetic--syn--syn/`] | Synthetic plugin fixture under `plugins/` ([B]) — implies pluggability Phase 3 owns |
| `mypy --strict` (Phase 0 baseline) preserved; `--warn-unreachable` adopted incrementally | Strict-typing discipline (ADR-0033 §1, §4) | The `IndexFreshness` consumer in `CONTEXT_REPORT.md` requires `--warn-unreachable` to catch missed `case`s | [synth — scales [B]] | `--warn-unreachable` + `--enable-error-code=truthy-bool` repo-wide retroactively ([B]) — Phase 0/1 retrofit blast radius (critic [B] finding #4) — Phase 2 enables them **only** on `src/codegenie/{indices,probes/index_health.py,report,adapters,tccm}/**` via per-module `mypy` config; full repo enablement is a tracked backlog item |

### Patterns considered and deliberately rejected

1. **Plugin Loader in Phase 2** ([P]). Roadmap and ADR-0031 §Consequences §1 assign the loader to Phase 3 alongside the first plugin. Pulling it forward hollows out Phase 3's exit criterion ("first plugin doubles as proof the loader works") because the loader would already exist without anything to test it. We ship `Protocol` classes (documentation) and the `TCCMLoader` skeleton (kernel scaffolding) — no `plugin.yaml` parser, no `plugins/universal--*--*/` directory.

2. **`cost_tier: Literal[0,1,2,3]` on the Probe ABC** ([P]). Coordinator scheduling data does not belong on the probe contract; it belongs on the registry annotation alongside the `@register_probe` decorator. Critic finding #2 was correct that this is contract churn for a scheduling optimization.

3. **`ProbeContext.capabilities: ProbeCapabilities` discriminated union** ([S]). Every Phase 0/1 probe would need to `match` exhaustively on the discriminator to stay typecheck-clean — a coordinated every-file edit dressed as "additive." Phase 2 instead keeps capabilities implicit (the registry already declares heavy/light; the subprocess port `_run_external_cli` already gates network egress).

4. **Cryptographic anchoring on B2 + audit-log hash chain** ([S]). Defends against an attacker who can write to `.codegenie/cache/` — which per Phase 0 ADR-0011 requires having already compromised the host. Critic [S] finding #4 and #3 (hidden assumption) both correctly named this as ceremony against a non-threat.

5. **Per-repo encryption key for secret findings + `~/.codegenie/keys/<repo>.key`** ([S]). Key + ciphertext live in the same trust tier ($HOME). Critic [S] finding #5 named this as obfuscation, not security. Phase 2's structural fix: don't persist plaintext.

6. **`pytest-xdist` for the portfolio test lane** ([P]). Phase 0 vetoed xdist 10/4 with a recorded rationale. The performance design reversed the veto unilaterally; Phase 2's portfolio is small enough that serial CI walltime fits. Critic finding #8 was correct.

7. **`AdapterConfidence` as the type of every probe's freshness output** ([P]). That conflates ADR-0033's prescription for ADR-0032 adapter outputs (Phase 3) with Phase 2's probe output. We keep `IndexFreshness` localized to probes; `AdapterConfidence` is a Phase 3 concern.

8. **Event stream (`.codegenie/events/`) with hash-chained JSONL** ([S]) / shape-compatible events writer ([P]). ADR-0034 §Consequences §1 explicitly defers the canonical event log to Phase 9 (or 13). Pre-shaping events in Phase 2 risks shape drift; Phase 9 owns the schema.

9. **`scip-python` parser + msgpack-on-disk projection** ([P]). Adapter consumption shape is a Phase 3 concern. Adding a binary on-disk format that future adapters must agree on creates the very format-coupling [P] claimed projections eliminate.

10. **Out-of-process `_grammar_runner` subprocess for tree-sitter** ([S]). The grammar pin already guards the supply-chain surface; the subprocess wrap is over-engineering for the Phase-2 threat model (a malicious grammar would be a deliberate supply-chain compromise the pin catches at load).

11. **`SkillsLoader.__init__` with auto-discovery via env vars** (any design's temptation). Explicit search paths passed at construction; loader doesn't peek at env or import paths.

12. **`gitpython` as a new Phase 2 dep** ([B]'s open Q §4). `git` is already in `ALLOWED_BINARIES`; we shell out via `run_allowlisted` for HEAD + rev-list-count. Fewer deps; one less subprocess pattern.

### Anti-patterns avoided

- **Premature pluggability.** No Plugin Loader; no universal-fallback plugin; no `NullAdapter` fixture set. The Protocol classes ship as documentation; their first real consumer (Phase 3) is the proof the contract works.
- **Untyped `dict[str, Any]` interfaces.** Every Phase 2 module exchange goes through Pydantic models. The one inherited untyped surface (`ProbeOutput.schema_slice: dict[str, JSONValue]`) is bounded by Phase 0's recursive `JSONValue` type.
- **Side effects in constructors.** `SkillsLoader.__init__(self, search_paths)` is pure data; first call to `load_all()` is the first I/O.
- **Tag-and-dispatch without a tagged union.** The Phase 0 `cache_strategy: Literal["content", "none"]` field is preserved; Phase 2 does not introduce a third behavior via `cache_key()` override ([P]'s image-digest-keying is expressed as a `declared_inputs` special token, preserving the existing discriminator).
- **"Hexagonal" sandbox that smuggles subprocess into the core.** `_run_external_cli` is honestly a Command-pattern wrapper, not a hexagonal Port. We don't claim what we didn't build.
- **Schema before consumer.** Every typed sum type in Phase 2 has at least one Phase-2 consumer: `IndexFreshness` is consumed by `CONTEXT_REPORT.md`'s confidence-section renderer; `TCCM` is consumed by the reference-TCCM integration test; `ScannerOutcome` is consumed by every Layer G probe's caller. Adapter `Protocol`s are the one exception (documented as documentation-as-code, with Phase 3's exit gating their first real consumer).
- **Bypass-by-omission for `Result[T, E]`.** Phase 0/1 don't ship `Result`; Phase 2 introduces it in new code only, with a `forbidden-patterns` pre-commit rule (`bare except: pass` banned in `src/codegenie/{indices,tccm,skills,conventions,adapters,depgraph}/**`).

## Risks (top 5)

1. **Adapter Protocol drift between Phase 2 and Phase 3.** We ship four `Protocol` classes with no implementations; Phase 3's first adapter may discover the Protocol is wrong. **Mitigation:** Phase 3's exit criterion explicitly requires "the first adapter implements the Phase 2 Protocols *unchanged*" — any drift is a Phase 2 amendment ADR, not a Phase 3 quiet edit. The Phase 2 reference TCCM exercises the `DerivedQuery` discriminator across all five primitives, giving Phase 3 a typed target for the adapter dispatch shape.

2. **`IndexFreshness` consumer-coverage gap.** The Phase-2 consumer (`CONTEXT_REPORT.md`'s confidence section) is the only thing exercising the sum type's variants until Phase 3 ships. If the variant set is wrong, we discover it late. **Mitigation:** the consumer is real code (`src/codegenie/report/confidence_section.py`), not test scaffolding; every golden file exercises it; `mypy --warn-unreachable` on that module enforces exhaustiveness from day 1.

3. **The deliberately-seeded `stale-scip` fixture goes stale.** If `scip-typescript` upstream changes its header format, the fixture may stop catching the regression we built it for. **Mitigation:** the fixture is content-hash-pinned and the assertion checks the structural property (`CommitsBehind.n >= 1`), not a specific tool-version artifact. A fixture-regeneration runbook lives in `tests/fixtures/portfolio/stale-scip/README.md`.

4. **`tree-sitter` is Phase 2's one C-extension exception; its CVE surface compounds.** Phase 1 ADR-0009's named-trigger amendment accepts this; if `tree-sitter` ships a memory-corruption CVE, Phase 2's import-graph probe is the affected surface. **Mitigation:** grammar BLAKE3 pins in `tools/grammars.lock`; CVE-feed surface watched by `pip-audit` + `osv-scanner` per Phase 0 §2.5; in-process load (not subprocess) means a crashed grammar crashes the gather, which is loud (Phase 0 isolation contains it to one probe).

5. **`docker` added to `ALLOWED_BINARIES` is a new attack surface.** Phase 2 ADR `0001-add-docker-to-allowed-binaries.md` accepts this. `docker build` runs adversarial-Dockerfile RUN instructions inside a container with `--network=none --cap-drop=ALL --security-opt=no-new-privileges`. **Mitigation:** the Layer-C probes use `docker` with explicit hardening flags constructed in the probe module (not via a Hexagonal Port — direct usage is the honest shape); ADR-0012 microVM substitution is the Phase 5+ upgrade path; the Phase 2 risk is documented as the "good enough until microVM" tier per critic-noted security trade.

## Synthesis ledger

### Vertex count

- Performance design ([P]): ~32 decision vertices.
- Security design ([S]): ~38 decision vertices.
- Best-practices design ([B]): ~30 decision vertices.
- Total: ~100 atomic decision vertices.

### Edges

- AGREE: ~24 (all three on: no LLM in gather, IndexHealthProbe is load-bearing, secret findings need redaction at the writer chokepoint, sequential runtime trace scenarios, Pydantic discriminated unions for state machines, one file per Layer G scanner, no `gitleaks-python` library dep, no Bundle Builder in Phase 2)
- CONFLICT: ~18 (resolved below)
- COMPLEMENT: ~12 (e.g., [B]'s `SkillsLoader` + [S]'s `O_NOFOLLOW` discipline compose)
- SUBSUME: ~6 (e.g., [P]'s tree-sitter parallelism inside the probe is subsumed by [B]'s no-internal-pool default)

### Conflict-resolution table

| Dimension | [P] picks | [S] picks | [B] picks | Winner | Exit | Roadmap | Commitments | Critic | Pattern | Sum |
|---|---|---|---|---|---|---|---|---|---|---|
| Plugin loader in Phase 2 | YES (loader + universal fallback) | (implicit, assumes loader) | NO (Protocols + TCCMLoader only) | **[B]** | 3 (no exit dependency) | 3 (Phase 3 owns it per ADR-0031) | 3 (extension-by-addition) | 3 (critic finding #1) | 2 (premature pluggability) | **14** |
| Probe ABC contract change | YES (`cost_tier`) | YES (`capabilities`) | NO | **[B+synth]** (kernel registry annotations instead) | 2 | 2 (preserves Phase 0/1 frozen surface) | 3 (commitment §2.5) | 3 (critic finding #2) | 3 (Open/Closed) | **13** |
| `IndexFreshness` / `AdapterConfidence` / `IndexConfidence` | `AdapterConfidence` (in probes) | `IndexConfidence` (B2-only) | `IndexFreshness` (B2; sum type at `codegenie.indices.freshness`) | **[B]** | 3 (variant set fits exit criterion) | 2 (Phase 3 picks `AdapterConfidence` for adapters) | 3 (commitment §2.3) | 3 (critic finding #3) | 3 (illegal-states) | **14** |
| Secret findings handling | not addressed | redact + encrypted-on-disk under `~/.codegenie/keys` | inline JSON in `gitleaks-findings.json` | **[synth]** (redact at writer chokepoint; do NOT persist plaintext; Phase 5 microVM is escalation door) | 2 | 3 | 3 (commitment §2 host hygiene) | 3 (critic finding #7) | 2 (no theatre) | **13** |
| `pytest-xdist` reversal | YES (portfolio lane) | silent | silent | **Phase 0 veto holds** | 1 | 2 (preserves Phase 0 decision) | 2 (no flake budget) | 3 (critic finding #8) | 1 | **9** |
| External-CLI sandbox | none (cost-tier only) | mandatory bubblewrap + macOS gap | none (`run_allowlisted` only) | **[synth]** (`_run_external_cli` wraps `run_allowlisted`; bubblewrap on Linux when available, no hard requirement) | 1 | 1 | 2 | 3 (critic [S] findings #1, #6) | 2 (Command, not Hexagonal) | **9** |
| `ExternalDocsProbe` network capability | added via `httpx` | sidecar binary under bwrap | opt-in with skip-cleanly | **[B]** (opt-in; default disabled; if enabled, uses `_run_external_cli` against an allowlisted host catalog) | 2 | 2 | 3 (commitment §2 — no `httpx`/`requests`/`socket` import in `src/codegenie/`) | 2 | 2 | **11** |
| Tree-sitter dep amendment to ADR-0009 | YES (also msgpack, scip-python, tantivy, gitleaks-python) | YES (also seccomp/bubblewrap libs) | YES (just tree-sitter) | **[B]** (tree-sitter only; named trigger fired) | 2 (B3 needs it) | 2 | 3 (commitment §2.5 dep-creep) | 3 (critic shared blind spot #2) | 2 | **12** |
| Cache-key strategy for image-built probes | new `cache_key()` override hook bypassing `declared_inputs` | cryptographic anchor via audit-log | stays on `declared_inputs` | **[synth]** ([B]'s discipline + image-digest as a *declared-input token*, the special-token pathway already in `localv2.md §4`) | 2 | 2 | 3 (commitment §2 — `declared_inputs` is the universal cache key) | 3 (critic [P] finding #6) | 2 | **12** |
| Audit-log event stream | shipped (3 variants) | shipped (10+ variants, hash-chained) | not shipped | **[B]** (Phase 0 audit anchor unchanged; ADR-0034 says Phase 9 ships the event log) | 1 | 3 (ADR-0034 §Consequences §1) | 2 | 3 (critic [S] §"missed") | 2 (event sourcing before its consumer = anti-pattern) | **11** |
| `IndexFreshness` module location | (`AdapterConfidence` in `confidence.py`) | (`IndexConfidence` in `index_health.py`) | `codegenie.indices.freshness` | **[B+synth]** (separate module; Phase-2 consumer in `report/confidence_section.py` closes the schema-without-consumer gap) | 2 | 2 | 2 | 2 | 3 | **11** |
| `DepGraphProbe` ecosystem dispatch | (n/a) | (n/a) | string-keyed dict with TODO | **[synth]** (`@register_dep_graph_strategy(ecosystem: PackageManager)` decorator) | 1 | 2 | 3 (ADR-0033) | 3 (critic [B] finding #5) | 3 (Open/Closed) | **12** |
| `gitleaks` shipping shape | binary CLI (gitleaks-python lib) | binary CLI under bwrap | binary CLI via `run_allowlisted` | **[B]** (binary CLI via `_run_external_cli`) | 1 | 2 | 3 (no new C-extension lib) | 2 | 2 | **10** |
| `gitpython` dep | added | (silent) | open Q | **shell out via `run_allowlisted("git", ...)`** | 1 | 2 | 3 (one less dep; `git` already allowlisted) | 2 (critic [B] §"hidden assumption" #2) | 2 | **10** |
| `mypy --warn-unreachable` rollout | (n/a) | (implied via `assert_never`) | repo-wide retroactive | **[synth]** (per-module config: only Phase 2 modules) | 2 | 2 | 2 (commitment §3 — surgical changes) | 3 (critic [B] finding #4) | 2 | **11** |
| `RuntimeTraceProbe` cache-key shape | image-digest override hook | (silent) | `declared_inputs = ["Dockerfile", ".codegenie/scenarios.yaml"]` | **[synth]** (image digest as declared-input special token via Phase-2 ADR-gated optional `ProbeContext.image_digest_resolver`) | 2 | 2 | 3 (`declared_inputs` discipline) | 3 | 2 | **12** |
| `SkillsLoader` YAML safety | (silent) | parallel `_safe_yaml_load_skill` chokepoint | reuses Phase 1 `safe_yaml.load` | **[B+synth]** (Phase 1 chokepoint + `O_NOFOLLOW` at Skills call site) | 2 | 2 | 3 (Rule 7 — don't fork conventions) | 3 (critic [S] finding #3) | 2 | **12** |
| `TreeSitterImportGraphProbe` parallelism | internal `ThreadPoolExecutor` | (silent) | (silent) | **[synth]** (no internal pool; sequential under single semaphore) | 1 | 1 | 2 (honesty to coordinator's budget) | 3 (critic [P] §"hidden assumption" #3) | 2 | **9** |

### Shared blind spots considered

All three designs quietly agreed on patterns the synthesis re-examined and resolved:

1. **Sum type pre-shipped without a real consumer** — fixed by Phase-2-internal consumer (`CONTEXT_REPORT.md`'s confidence section) for `IndexFreshness`; reference TCCM under `docs/` for `TCCM`; Phase 3 contract for adapter `Protocol`s.
2. **`tree-sitter` added without engaging Phase 1 ADR-0009** — fixed by explicit Phase 2 ADR amendment `0002-tree-sitter-grammars-phase-2-amendment.md`; `msgpack`/`scip-python`/`tantivy`/`gitleaks-python` remain rejected.
3. **`RuntimeTraceProbe` 5-scenario configuration shape** — three designs proposed three shapes (config flag, typed enum, scenarios.yaml). Phase 2 picks **`scenarios.yaml` Pydantic-validated** ([B]); falls back to 5 default scenarios if absent.

### Pattern reconciliation

| Pattern | Where it appeared | Synthesis disposition | Rationale |
|---|---|---|---|
| Plugin architecture / Plugin loader | [P] §2 (loader + universal fallback); [B] (Protocols only) | **Adopt [B]: Protocols + TCCMLoader only.** No loader in Phase 2. | Roadmap + ADR-0031 §Consequences §1 explicitly assign loader to Phase 3 |
| Hexagonal / Ports & Adapters | [P] §2 (loader-as-Port); [S] (`_run_external_cli`-as-Port) | **Reject both as Hexagonal; accept the Command pattern shape for `_run_external_cli`.** | Critic correctly flagged "one Adapter = no Port"; we don't claim what we don't build |
| Capability pattern | [S] (`ProbeCapabilities` + `SecretFindingCapability`) | **Reject.** Authorization across an LLM boundary is not capability; LLM never holds the token | Critic [S] §"Capability pattern applied to SecretFindingCapability" |
| Event sourcing | [P] §8 (3 events); [S] §"EventStream" (10+ events with hash chain) | **Defer.** ADR-0034 §Consequences §1 says Phase 9 anchors the event log. Phase 2's audit anchor (Phase 0) is unchanged | Pre-shaping events before their consumer = schema-before-consumer anti-pattern |
| Decorator-registry | [P] (deprecated for `cost_tier` ABC field); [B] (preserved); [synth] extends with kwargs | **Adopt and extend** (`heaviness`, `runs_last`, `@register_dep_graph_strategy`) | Open/Closed at the file boundary; mirrors Phase 0 primitive |
| Smart constructor + `Result[T, E]` | [B] | **Adopt selectively** for new Phase 2 module boundaries; not retrofit to Phase 0/1 | Surgical-changes discipline (Rule 3); Phase 2 surfaces are isolated |
| Make-illegal-states-unrepresentable | [B] (every sum type); [P] (`AdapterConfidence`); [S] (`IndexConfidence`) | **Adopt with one name (`IndexFreshness`), one module, one Phase-2 consumer** | Resolves three competing names; closes critic finding #3 |
| Functional core / imperative shell | [P] (SCIP projector); [B] (CatalogLoader.apply) | **Adopt where it earns its name; reject ceremony** | Critic [P] §"FCIS on SCIP projector" — labeling pure functions as "core" doesn't earn the pattern |
| Strategy via Protocol | [B] (adapter Protocols, zero implementations) | **Accept the ceremony cost** | Protocols *are* the Phase 3 contract; risk is bounded by Phase 3 exit gating drift |
| Open/Closed | [synth] (`DepGraphProbe` decorator) | **Apply where the input designs flagged a TODO** | Critic finding #5 against [B] |

### Departures from all three inputs

1. **No event stream in Phase 2.** [P] ships 3 events; [S] ships 10+ hash-chained. **Final design ships zero.** Justification: ADR-0034 §Consequences §1 is unambiguous that Phase 9 anchors the event log; pre-shaping risks schema drift; the Phase 0 audit anchor already records `Ran/CacheHit/Skipped` per probe, which is the only signal Phase 2 actually needs to satisfy the exit criterion.

2. **Image digest as a declared-input special token, not as a cache-key override.** [P] proposed letting probes override `cache_key()`; [S] is silent; [B] stays on `declared_inputs`. **Final design extends `declared_inputs` with a special-token form** (the special-token pathway already permitted by `localv2.md §4`), via a Phase-2-ADR-gated optional `ProbeContext.image_digest_resolver` callable. The discipline survives without bypass.

3. **`heaviness` registry annotation instead of `cost_tier` ABC field.** [P] proposed ABC field; [B] proposed nothing. **Final design picks registry-annotation-as-decorator-kwarg**, preserving the Phase 0 ABC and giving the coordinator a soft sort key under the single semaphore.

4. **No plaintext secret persistence.** [S] proposed encrypted-on-disk; [P+B] silent. **Final design persists no plaintext at all.** The Phase 5 microVM is named explicitly as the escalation door for any future cleartext-required judgment.

5. **`heaviness` + `runs_last` together replace [P]'s 4-tier semaphore + `IndexHealthProbe.requires=[every-other-probe]` topological hack.** The coordinator stays single-semaphore; ordering is a registry-side concern.

6. **Reference TCCM ships under `docs/`, not `tests/fixtures/plugins/`.** [B] proposed a synthetic plugin fixture; **final design ships the reference TCCM as documentation** so it doesn't imply pluggability Phase 3 owns.

7. **`@register_dep_graph_strategy` decorator** instead of [B]'s deferred string-keyed dict. The fix is ~30 LOC and applies ADR-0033 immediately rather than deferring to Phase 3.

8. **`SkillsLoader` reuses the Phase 1 `safe_yaml.load` chokepoint** (with one extra `O_NOFOLLOW` discipline at the call site), instead of [S]'s parallel `_safe_yaml_load_skill` helper. Rule 7 — don't fork conventions.

## Exit-criteria checklist

- [x] **"Every probe layer runs against real repos"** → the 5-repo `tests/fixtures/portfolio/` (`minimal-ts`, `native-modules`, `monorepo-pnpm`, `distroless-target`, `stale-scip`) exercises every probe layer. The integration tests under `tests/integration/portfolio/` are CI-gated; the bench canary `tests/bench/bench_portfolio_walltime.py` is advisory.
- [x] **"IndexHealthProbe surfaces at least one real staleness case in CI (deliberately seeded fixture) — proving the probe actually catches what it's there to catch"** → `tests/adv/phase02/test_stale_scip_fixture.py` asserts `IndexHealthProbe` returns `IndexFreshness.Stale(reason=CommitsBehind(n>=1, last_indexed=<known prior commit>))` on the `tests/fixtures/portfolio/stale-scip/` fixture. **Build FAILS if the probe doesn't catch it.** This is the load-bearing test.

## Load-bearing commitments check

- **§2.1 No LLM in gather pipeline.** Phase 0 `fence` job continues to assert; Phase 2 `gather` extras add only `networkx` (pure Python), `py-tree-sitter` (one C-extension exception, ADR-amended), and `pydantic` extensions (already in Phase 0). No `anthropic`/`openai`/`langgraph` SDKs. ✅
- **§2.2 Facts, not judgments.** Every probe reports evidence; `IndexHealthProbe` reports `IndexFreshness.Stale(reason=CommitsBehind(n=17, …))`, not "unsafe to use." ✅
- **§2.3 Honest confidence.** `IndexHealthProbe` is the canonical example, with `IndexFreshness` as the typed return; the Phase-2 consumer (`CONTEXT_REPORT.md`'s confidence section) exercises every variant. ✅
- **§2.4 Determinism over probabilism for structural changes.** Phase 2 ships no transforms; the gather pipeline is deterministic end-to-end. ✅
- **§2.5 Extension by addition.** Adding a probe is a new file + `@register_probe`; adding an ecosystem to `DepGraphProbe` is a new file + `@register_dep_graph_strategy`; no edits to existing probes or coordinator chokepoints (`Probe` ABC, `OutputSanitizer.scrub`, `run_allowlisted`, cache API). The one ABC-adjacent edit (`ProbeContext.image_digest_resolver`) follows Phase 1 ADR-0002's `parsed_manifest` precedent — additive, optional, ADR-gated. ✅
- **§2.6 Organizational uniqueness as data, not prompts.** Skills (YAML frontmatter), conventions (YAML), TCCMs (YAML), all Pydantic-validated. ✅
- **§2.7 Progressive disclosure.** Skill bodies are byte-offset-recorded, not loaded into memory; conventions, ADRs, repo notes referenced by path only. ✅
- **§2.8 Humans always merge.** Phase 2 is gather-only; no autonomy gates touched. ✅
- **§2.9 Cost is observable end-to-end.** Phase 2 emits no LLM cost; the Phase 0 audit anchor records per-probe `Ran/CacheHit/Skipped`, which Phase 9 will project into the cost ledger when the event log lands. ✅

## Roadmap coherence check

**What prior phases established that this design depends on:**

- **Phase 0:** `Probe` ABC + `@register_probe` decorator + `Coordinator(Semaphore(min(cpu_count(), 8)))` + `Cache(declared_inputs)` + `OutputSanitizer.scrub` + `run_allowlisted` + `ALLOWED_BINARIES` + `fence` CI test + audit anchor `runs/<utc-iso>-<short>.json`. All preserved; Phase 2 extends `ALLOWED_BINARIES` and composes a new `redact_secrets` pass into the sanitizer.
- **Phase 1:** Layer A probes (`LanguageDetection`, `NodeBuildSystem`, `NodeManifest`, `CI`, `Deployment`, `TestInventory`); `parsed_manifest` memo on `ProbeContext` (precedent for the Phase 2 `image_digest_resolver` addition); `safe_yaml.load` chokepoint; ADR-0009 (no new C-extension parser deps) — amended in Phase 2 with one named-trigger exception (`py-tree-sitter`); `PackageManager` schema enum (`["bun", "pnpm", "yarn-classic", "yarn-berry", "npm"]`) — imported and reused as the `DepGraphProbe` discriminator.

**What this design establishes that later phases will need:**

- **Phase 3 (first plugin):** consumes `codegenie.adapters.protocols` Protocols, the `IndexFreshness` sum type, the `TCCMLoader`, the `_run_external_cli` chokepoint, and the per-probe slice shapes Phase 2 wrote. Phase 3 ships the **Plugin Loader + first plugin + four ADR-0032 adapter implementations + universal fallback plugin together** (as ADR-0031 §Consequences §1 prescribes — these are *all* Phase 3, not Phase 2).
- **Phase 4 (LLM fallback):** consumes the `redact_secrets` chokepoint to ensure no secret reaches an LLM prompt.
- **Phase 5 (microVM sandbox):** the escalation door for any future cleartext-required judgment on secret findings; replaces direct `docker` invocations in `RuntimeTraceProbe` per ADR-0012.
- **Phase 8 (Supervisor + Bundle Builder):** consumes `TCCMLoader`, every adapter from Phase 3+, and the `IndexFreshness` confidence signal.
- **Phase 9 (canonical event log):** projects the Phase 0 audit anchor into the typed Postgres event log; the Phase 2 slice metadata (`gathered_at`, `last_indexed_commit`, etc.) becomes input to that projection.

**Any new ADRs implied by this design that should be drafted:**

1. `docs/phases/02-context-gather-layers-b-g/ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md` — `docker`, `strace`, `semgrep`, `syft`, `grype`, `gitleaks`, `scip-typescript`, `tree-sitter` added to `ALLOWED_BINARIES` (mirroring Phase 1 ADR-0001 `node` addition).
2. `docs/phases/02-context-gather-layers-b-g/ADRs/0002-tree-sitter-grammars-phase-2-amendment.md` — amendment to Phase 1 ADR-0009 (no new C-extension parser deps): named-trigger fired for `py-tree-sitter` because `localv2.md §5.2 B3` requires it.
3. `docs/phases/02-context-gather-layers-b-g/ADRs/0003-coordinator-heaviness-sort-annotation.md` — `@register_probe(heaviness=…, runs_last=…)` registry annotations; coordinator sort-order edit; preserves the single Semaphore + ABC contract.
4. `docs/phases/02-context-gather-layers-b-g/ADRs/0004-image-digest-as-declared-input-token.md` — extends `localv2.md §4` `declared_inputs` special-token mechanism with the `image-digest:<resolver>` token; introduces optional `ProbeContext.image_digest_resolver` callable mirroring Phase 1 ADR-0002.
5. `docs/phases/02-context-gather-layers-b-g/ADRs/0005-secret-findings-no-plaintext-persistence.md` — Phase 2 does NOT persist plaintext secrets; `SecretRedactor` at writer chokepoint; Phase 5 microVM is the named escalation door for any future cleartext-required judgment.
6. `docs/phases/02-context-gather-layers-b-g/ADRs/0006-index-freshness-sum-type-location.md` — `IndexFreshness` lives at `codegenie.indices.freshness`; documents why `AdapterConfidence` and `IndexConfidence` are NOT shipped in Phase 2.
7. `docs/phases/02-context-gather-layers-b-g/ADRs/0007-no-plugin-loader-in-phase-2.md` — explicit deferral; Phase 3 ships loader + first plugin + adapters + universal fallback together per ADR-0031 §Consequences §1.
8. `docs/phases/02-context-gather-layers-b-g/ADRs/0008-no-event-stream-in-phase-2.md` — defers to ADR-0034 §Consequences §1 (Phase 9 anchors the event log).
9. `docs/phases/02-context-gather-layers-b-g/ADRs/0009-pytest-xdist-veto-preserved.md` — explicit re-affirmation of Phase 0's veto; Phase 2 portfolio fits serial CI.

## Open questions deferred to implementation

1. **Phase 5 microVM cleartext-access protocol.** The `SecretRedactor` defers cleartext persistence; if a Phase 4+ task class needs cleartext access for a remediation judgment, the Phase 5 microVM re-derives the secret from the analyzed repo at that point in time inside the sandbox. The exact handoff (does the microVM receive `(file:line, pattern_class, fingerprint)` and re-scan? does it receive the redacted slice + a one-time decryption capability tied to the workflow ID?) is a Phase 5 design concern. Phase 2's commitment is only that we do NOT persist plaintext anywhere Phase 4 can reach it.

2. **`TreeSitterImportGraphProbe` projection shape.** Phase 2 emits `raw/import-graph.json` as forward-only adjacency; Phase 3's first `ImportGraphAdapter` decides whether to pre-compute reverse, mmap a binary, or walk at query time. Phase 2 does not pre-decide this on Phase 3's behalf.

3. **`SkillsLoader` org-shared tier signing.** Per-tier signing (Sigstore-style) for `~/.codegenie/skills-org/` is a Phase 14 multi-tenant concern; Phase 2 ships three-tier merge with first-tier-wins + loud `skill_shadowed` warning.

4. **`ExternalDocsProbe` enablement & host allowlist shape.** Phase 2 ships opt-in skip-cleanly; the allowlist config schema (`external_docs:` in `.codegenie/config.yaml`) lands when the first real user opts in.

5. **`mypy --warn-unreachable` rollout beyond the Phase 2 modules.** Phase 2 enables it via per-module config on `codegenie.{indices,probes/index_health.py,report,adapters,tccm}/**`; full-repo rollout is a tracked backlog item.

6. **Per-fixture cache pre-warming for CI walltime.** Whether to commit `.codegenie/cache/` blobs to the fixture portfolio (faster CI; opaque diff) or regenerate on every CI run (slower CI; transparent diff). Phase 2 picks regenerate-on-every-run; if CI walltime regresses past 8 minutes, this flips.

7. **`stale-scip` fixture regeneration policy.** Documented in `tests/fixtures/portfolio/stale-scip/README.md`; the structural assertion (`CommitsBehind.n >= 1`) is tool-version-agnostic; if `scip-typescript` changes its header format, the fixture's pre-populated index is regenerated against the new format and the assertion still holds.
