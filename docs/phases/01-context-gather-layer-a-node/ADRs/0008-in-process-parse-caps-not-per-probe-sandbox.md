# ADR-0008: In-process parse caps in `parsers/`, no per-probe fork+exec sandbox

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** security · adversarial-input · parser-hardening · chokepoint · phase-evolution
**Related:** [Phase 0 ADR-0005](../../00-bullet-tracer-foundations/ADRs/0005-coordinator-async-from-day-one.md), [Phase 0 ADR-0007](../../00-bullet-tracer-foundations/ADRs/0007-probe-contract-frozen-snapshot.md), [Phase 0 ADR-0008](../../00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md), ADR-0004

## Context

Phase 1 is **the first phase parsing adversarial bytes from untrusted repos at scale** — `package.json`, `pnpm-lock.yaml`, `tsconfig.json`, `Chart.yaml`, GitHub Actions YAML, Kustomize manifests. The security lens's design (`design-security.md`) made this the architecture's load-bearing concern and proposed a per-probe fork+exec parser sandbox: every probe runs as `python -m codegenie.probes._sandbox <probe-module>` with `bwrap` on Linux, `sandbox-exec` on macOS, env strip, stdin DEVNULL, and rlimits set pre-exec. The threat closure: ~95% threat surface from YAML/JSON bombs + ~5% from parser-CVE-in-C-extension classes that an in-process check cannot catch.

The critic dismantled the proposal in three blows (`critique.md "Attacks on the security-first design"` #1, #2, #4):

1. The sandbox is **a brand-new architectural layer** Phase 0 never sanctioned; it inverts the coordinator-runs-probe-in-event-loop model (Phase 0 ADR-0005) without ADR amendment.
2. Per-probe ~150–300 ms fork+exec overhead × 6 probes = **~1.5 s of pure overhead** per cold-cache gather; CI walltime budget (Phase 0 §3.2) blows.
3. `bwrap` is **Linux-only**; macOS gets deprecated `sandbox-exec`; Windows is "not supported." The Goal #2 statement ("Every probe runs in a per-execution parser sandbox with rlimits enforced") is **platform-conditional** and cannot deliver on its own claim.

The synthesizer's resolution (`final-design.md "Conflict-resolution table"` row 1): **refuse the sandbox**. Move all caps in-process to a shared `parsers/` module that every probe routes through. Accept the ~5% residual (parser-CVE class) as the explicit Phase 1 risk; close it at the deployment layer in Phase 14 (OS-level rlimits + bwrap on the production worker, where one process serves many repos).

## Options considered

- **Per-probe fork+exec sandbox with bwrap/sandbox-exec ([S]).** Strongest in-Phase-1 threat closure. New architectural layer; ABC inversion; platform-conditional; ~1.5 s overhead per cold gather.
- **Each probe re-implements size/depth caps inline.** No new module. Caps drift across probes; "security goal degrades to mostly enforced" (final-design Components #8 framing).
- **Shared `parsers/` module — `safe_json.py`, `safe_yaml.py`, `jsonc.py` — each enforcing identical in-process caps + `O_NOFOLLOW`; every probe routes through it.** ~95% threat closure at ~0 ms overhead. No ABC change. No new process model. Parser-CVE-class residual is the explicit acceptance.

## Decision

**Phase 1 ships `src/codegenie/parsers/` with three modules — `safe_json.py`, `safe_yaml.py`, `jsonc.py` — and every probe parsing untrusted bytes routes through them.** Each module:

- Opens the path with `os.open(path, os.O_RDONLY | os.O_NOFOLLOW)` — refuses symlinks at open time, not after read.
- Size-checks the file descriptor before parse.
- Calls the underlying parser:
  - `safe_json.load`: stdlib `json.loads` (the Phase 0 ratified parser).
  - `safe_yaml.load`: `yaml.CSafeLoader` (Phase 0 ratified; Phase 0 `forbidden-patterns` continues to ban `yaml.load(...)` without `Loader=`).
  - `jsonc.load`: stdlib-only line + block comment stripper, then `safe_json.load`.
- Post-parse depth-walks the result to enforce `max_depth` (the C parsers have no native depth cap).
- Raises typed exceptions on cap or shape violations: `SizeCapExceeded`, `DepthCapExceeded`, `MalformedJSONError`, `MalformedYAMLError`, `SymlinkRefusedError`.

The hard caps live with each parser invocation:
- `package.json`: 5 MB / depth 64.
- Lockfile: 50 MB / depth 64.
- YAML workflow / Helm values / Kustomize: 10 MB / depth 64.

**No per-probe fork+exec sandbox is shipped.** No `codegenie.probes._sandbox` module. No bwrap/sandbox-exec dependency. The Phase 0 `Coordinator` runs probes as `asyncio.Task`s in the gather process exactly as ADR-0005 specified.

The ~5% residual (parser-CVE-class exploits that bypass the in-process depth-walker by exploiting `_json.c` or `CSafeLoader` internals) is accepted. Mitigations: `pip-audit` + `osv-scanner` + Dependabot on `pyyaml` and cpython continue to surface CVEs at the supply-chain layer; the `_ProbeOutputValidator`'s field-name regex + recursive `JSONValue` typing + `OutputSanitizer`'s path-scrubber are belt-and-suspenders defenses if parsed bytes do reach output. **Phase 14's production worker adds OS-level rlimits + bwrap** at the deployment layer where the multi-actor threat model arrives.

## Tradeoffs

| Gain | Cost |
|---|---|
| ~95% of the YAML-bomb / JSON-bomb / depth-DoS / oversized-input threat surface closes at ~0 ms overhead per parse | ~5% of the threat surface (parser-CVE in `_json.c` / `pyyaml.CSafeLoader`) remains; Phase 14 closes it at the deployment layer |
| Phase 0 ADR-0005's coordinator-runs-probe-in-asyncio model is preserved — no new process model, no IPC contract, no ABC inversion | The security lens's stronger Goal #2 ("every probe in a per-execution sandbox") is explicitly not satisfied in Phase 1 |
| Cross-platform — `O_NOFOLLOW` is POSIX (macOS + Linux); no bwrap dependency; no sandbox-exec deprecation concern | Windows isn't supported (consistent with Phase 0); the in-process model works there if the project ever ships Windows-side |
| Caps are uniform across every probe — one helper enforces the rules; new probes inherit the defense without re-implementing | All probes share the cap defaults; a future Layer C probe needing a 200 MB allowance for SBOM JSON requires a parser-module amendment |
| `O_NOFOLLOW` mitigates symlink-escape at file open — the right layer for the defense (no race between stat + open) | Adversarial fixtures must include symlink cases; the `tests/adv/test_symlink_escape_in_declared_inputs.py` test is load-bearing |
| Two passes (size → parse → depth-walk) is ~5% slower than a hypothetical depth-aware parser; immaterial at Phase 1 budgets | Not a depth-aware streaming parser — the parse-then-walk shape doesn't catch CPU-DoS during the parse itself (the cap is bytes, not CPU) |
| ~1.5 s cold-gather overhead avoided (`final-design.md` Resource & cost profile); CI walltime stays inside Phase 0 §3.2's budget | The fork+exec architectural diagram in `design-security.md` is rejected outright; reviewers reading that doc need to find this ADR |
| Phase 0 ADR-0008's `OutputSanitizer` chokepoint is preserved — no third pass added; the strictness lives at sub-schema validation per ADR-0004 | A third pass at the chokepoint would have been simpler structurally but violates Phase 0 ADR-0008's freeze (critic §"Attacks on the security-first design" #5) |

## Consequences

- `src/codegenie/parsers/` ships in Phase 1 with `safe_json.py`, `safe_yaml.py`, `jsonc.py`, plus typed exceptions in `parsers/exceptions.py` (or `codegenie.errors` extensions).
- Every Phase 1 probe that parses untrusted bytes routes through these. The lockfile parsers (`probes/_lockfiles/`) wrap `safe_json` / `safe_yaml` and add format-specific shaping.
- `tests/adv/` ships ten adversarial fixtures (`yaml_billion_laughs`, `json_bomb_deep_nesting`, `json_bomb_huge_string`, `yaml_unsafe_tag`, `symlink_escape_in_declared_inputs`, `zip_slip_kustomize`, `planted_node_on_path_ignored`, `tsconfig_pathological`, `regex_dos_yarn_lock`, `oversized_lockfile`); each pins one structural defense and is CI-gating.
- Phase 14's `phase-arch-design.md` (when written) inherits the parser-CVE residual as a known precondition. The Phase 14 production worker adds rlimits + bwrap at the OS level — the security lens's design isn't discarded, it's relocated to the right layer.
- Phase 2's `IndexHealthProbe` and other Layer B/C/D/G probes reuse `safe_json` / `safe_yaml` for `semgrep` JSON output and SCIP manifest parsing — no per-probe duplication.
- The `forbidden-patterns` Phase 0 hook continues to ban `yaml.load(...)` without `Loader=` and any `Loader != CSafeLoader`.

**Amended (Phase 1, S1-09 — Soft truncation companion).** `ResourceBudget` gains a sibling field `raw_artifact_truncate_mb: int = 5` (the **soft** on-disk truncation threshold; semantically distinct from the **hard** `raw_artifact_mb` ceiling that raises via `BudgetingContext.report_bytes`). The invariant `raw_artifact_truncate_mb <= raw_artifact_mb` is enforced at construction by `ResourceBudget.__post_init__` (fail loud per Rule 12) — otherwise the soft policy would be unreachable because the hard ceiling fires first. Enforcement is a pure helper `codegenie.output.raw_truncation.apply_raw_artifact_truncation(payload, truncate_mb)` (functional core: bytes-in, bytes-out + a tagged-union `TruncationOutcome` of `Untruncated | Truncated`), invoked from `codegenie.cli`'s raw-artifact collection loop (imperative shell); `Writer.write` is unchanged (ADR-0011 chokepoint preserved). On truncation, payload bytes are replaced with a JSON wrapper `{"__truncated_at_budget__": true, "original_bytes": ..., "budget_bytes": ..., "data": ...}` (the `data` field is the parsed JSON value if the prefix is valid JSON; else the prefix decoded as `utf-8` with `errors="replace"`) and the event `probe.raw_artifact.truncated` is emitted with structured fields `probe`, `original_bytes`, `budget_bytes`, `path`, `run_id`. Boundary semantics mirror `report_bytes` — inclusive at the limit, exclusive above (`>` not `>=`). The original `phase-arch-design.md §Gap analysis Gap 2` prescription (add `Probe.declared_raw_artifact_budget_mb` to the ABC) was superseded by this route to preserve Phase 0 ADR-0007's contract freeze and avoid duplicating the existing `ResourceBudget` mechanism (Rule 7 — surface conflicts, don't average them; see `_validation/S1-09-raw-artifact-budget.md`). `NodeManifestProbe` (S3-05) will override via `declared_resource_budget = ResourceBudget(raw_artifact_mb=50, raw_artifact_truncate_mb=25)`. Budgets > 50 MB hard ceiling continue to require a further ADR amendment.

## Reversibility

**Medium.** Adding a per-probe sandbox later (e.g., Phase 14) is mechanically additive — the parser modules continue to work; the sandbox wraps the probe `run()` call from outside. Removing the in-process caps is irreversible-feeling: probes have come to rely on the typed exceptions for degrading to `confidence: low`; ripping out `parsers/` requires every probe to re-implement caps inline, which is the failure mode the synthesis explicitly avoided. The parser-CVE residual closure is Phase 14's job; bringing it forward to Phase 1 would require resurrecting the sandbox design, which this ADR rejects.

## Evidence / sources

- `../final-design.md "Components" #8 Safe-parse helpers` — design statement
- `../final-design.md "Conflict-resolution table" row 1` — the resolution
- `../final-design.md "Risks" #2` — the parser-CVE residual register
- `../phase-arch-design.md "Component design" #8 Safe-parse helpers` — interface
- `../phase-arch-design.md "Non-goals" #2` — explicit sandbox rejection
- `../phase-arch-design.md "Path to production end state"` — Phase 14 closes the residual
- `../phase-arch-design.md "Testing strategy" "Adversarial tests"` — the ten fixtures
- `../critique.md "Attacks on the security-first design"` #1, #2, #4 — the dismantling
- [Phase 0 ADR-0005](../../00-bullet-tracer-foundations/ADRs/0005-coordinator-async-from-day-one.md) — the process model this preserves
- [Phase 0 ADR-0008](../../00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md) — the chokepoint this avoids editing
