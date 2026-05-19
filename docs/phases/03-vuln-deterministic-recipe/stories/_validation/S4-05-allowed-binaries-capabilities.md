# Validation report — S4-05 `ALLOWED_BINARIES` amendment + `Capability` tokens + `mint()` chokepoint + ruff custom fence + `--ignore-scripts` enforcement

**Verdict:** HARDENED
**Validated:** 2026-05-19
**Story file:** [`../S4-05-allowed-binaries-capabilities.md`](../S4-05-allowed-binaries-capabilities.md)

## Summary

Four critic lenses (Coverage / Test-Quality / Consistency / Design-Patterns) surfaced **6 BLOCK-grade** structural issues plus ~10 HARDEN-grade mutation-survival gaps. All BLOCKs are inline-patchable; no `phase-story-writer` re-run needed.

Most consequential resolutions (also summarized at the head of the hardened story):

1. **Missing `_forward.py` substitution + fence amendment (BLOCK).** The Phase-3-Step-1 shim at `src/codegenie/transforms/_forward.py:50` ships an empty `class CapabilityBundle(BaseModel): pass` placeholder whose docstring (lines 14-20) explicitly declares S4-05's contract to "Move `CapabilityBundle` to `codegenie.plugins.capabilities` and re-export from this module." Story originally omitted the flip — a literal implementation would build a real `CapabilityBundle` in `capabilities.py` while leaving the shim's empty class in place, diverging. Existing consumers (`apply_context.py:32`) already `from codegenie.transforms._forward import CapabilityBundle, SandboxedPath` — they'd silently bind to the wrong class. Added **AC-Sub-1** (substitute `_forward.CapabilityBundle` to a re-export), **AC-Sub-2** (amend `_FORWARD_ALLOWED` in `tests/fence/test_transforms_module_purity.py`), **AC-Sub-3** (three-path import identity test + `ApplyContext` round-trip). Mirrors S4-04's `SandboxedPath` substitution discipline exactly.

2. **`bubblewrap` polarity error (BLOCK).** Story's AC-9 + Notes said "REMOVE `bwrap` AND `bubblewrap`" from the closed-set negative regression. Verified at `tests/unit/test_exec.py:362-363`: both names are in the negative list per S1-06 AC-15. But 03-ADR-0012 only admits `"bwrap"` (the short symlink) to `ALLOWED_BINARIES` — not `"bubblewrap"` (the canonical long name). Removing both would silently allow `bubblewrap`-only operator environments to escape the closed-set discipline. AC-9 rewritten: REMOVE only `"bwrap"`; KEEP `"bubblewrap"` with explicit comment; add companion assertion `"bubblewrap" not in ALLOWED_BINARIES`.

3. **Walker-home conflict (BLOCK).** Story prescribed `tooling/ruff_rules/no_capability_construction.py` (greenfield — no `tooling/` directory in the repo, no ruff-plugin scaffolding precedent). Codebase precedent (Rule 11, established by S1-05 / `_phase3_fence.py`) is `src/codegenie/_<name>_fence.py` consumed from `tests/fence/`. ADR-0011 §Consequences names the `tooling/ruff_rules/` path but the codebase has moved past that aspiration. Surfaced per Rule 7 ("surface conflicts, don't average them"): AC-15 rewritten to pin the walker at `src/codegenie/_capability_fence.py` (extension-by-addition, mirrors `_phase3_fence.py` shape); AC-15 also schedules the ADR-0011 §Consequences amendment within this same story.

4. **AC-13 mutation-trivial grep test (BLOCK).** `outside_mint = src.replace(mint_src, "")` substring search misses: (a) `inspect.getsource` dedent / whitespace mismatches that make `replace()` a no-op; (b) capability constructors in helpers `mint()` *calls* but that live outside `mint()`; (c) a second constructor inside `mint()` itself via a sneaky closure that still matches `mint_src`. Rewritten to **AST-based**: parse the module, locate `FunctionDef("mint")`, capture its `lineno`/`end_lineno`, walk `Call` nodes whose `func.id` is in `_CAPABILITY_CLASS_NAMES`, assert each call's `lineno` is inside `mint()`'s range AND no sibling `FunctionDef` contains capability `Call` nodes.

5. **AC-11 / AC-12 / AC-14 mutation-trivial (BLOCK).** AC-11 collapsed `frozen=True` and `extra="forbid"` into one chained test — a mutant dropping `frozen=True` survives the `extra="forbid"` check. AC-12's `GitLocalOpsCapability(push=True)` fails on missing-required-fields FIRST (before `extra="forbid"` rejects `push`) — test passes for the wrong reason. AC-14's `monkeypatch.setattr` on `_emit_capability_minted` won't intercept if `mint()` does `from codegenie.plugins.events import emit_capability_minted` (binds at def-time inside the function body's local namespace). All three rewritten with concrete decoupled assertions + AST-level checks for the `_emit_capability_minted` chokepoint binding.

6. **`CapabilityScope` shape unpinned (HARDEN→pinned).** Story exported `CapabilityScope` but left its shape free-form. Risk: executor invents an arbitrary shape S5-02 / S6-01 can't fit. **AC-Sub-5** pins it as a closed sum type matching `PluginScope`'s discipline (ADR-0010 §1): `CapabilityScope: TypeAlias = NpmScope | FsScope | GitLocalOpsScope`, each a frozen Pydantic model, `mint()` dispatches via `isinstance` with `assert_never(scope)` exhaustiveness.

7. **`CapabilityBundle` semantics ambiguous (HARDEN→pinned).** Three Optional fields invited "can more than one be non-None?" Per ADR-0011's audit framing, one `mint()` call serves one scope ⇒ one capability. **AC-Sub-4** adds a `model_validator(mode="after")` asserting **exactly one** non-None field; unit tests parametric over (zero-non-None, two-non-None) rejection. Surfaces a load-bearing invariant the story had silently glossed.

The hardened story keeps the Goal and Out-of-scope shape intact; it tightens ACs so the executor's validator pass can fail on a wrong implementation, and pulls in the seam-wiring (`_forward.py` substitution + fence allowlist + `ApplyContext` round-trip) that ADR-0001 + the existing shim's docstring already anticipated.

## Context Brief

- **What the story promises:** Three changes in one coherent story: (a) `ALLOWED_BINARIES` amendment (12→16 entries) per 03-ADR-0012; (b) `src/codegenie/plugins/capabilities.py` with three frozen Pydantic capability types + `CapabilityBundle` + `mint()` chokepoint per 03-ADR-0011; (c) AST-based custom-ruff-rule fence + `--ignore-scripts` CLI-half static fence per 03-ADR-0006.
- **Phase exit criterion this serves:** G1 (subprocess + filesystem isolation primitives) + G6 (zero edits to Phase 0/1/2 — the only permitted edit is `ALLOWED_BINARIES` extension via ADR amendment).
- **Sibling-family lineage:** S4-05 is the **Phase 3 sibling** of Phase 2 S1-06 (the structural template for allowlist amendments) and the structural counterpart to S4-04 (`SandboxedPath` substitution via `_forward.py`). S4-04's validation report Pass 2 added `AC-Sub-1`/`AC-Sub-2`/`AC-Sub-3` for the exact same pattern — substitute the `_forward.py` shim + amend the purity fence + round-trip existing consumers. S4-05 needed identical seam-wiring discipline for `CapabilityBundle`.
- **Arch + ADR constraints:**
  - 03-ADR-0012 (omnibus amendment ADR): the four-binary expansion; single-chokepoint preservation ("`SubprocessJail` adapters wrap `bwrap`/`sandbox-exec` via `run_external_cli` — they do NOT bypass the chokepoint"); `java` NOT added (Phase 7).
  - 03-ADR-0011 (honest framing): three primitives ship with honest claims — `Capability` = audit + lint, not unforgeable; `SandboxedPath` = in-jail at construction + `O_NOFOLLOW` second-line; `PLUGINS.lock` = integrity check, not signature. `GitLocalOpsCapability` has NO `push` field (ADR-0009 humans-always-merge).
  - 03-ADR-0010 (domain modeling discipline): Pydantic frozen + `extra="forbid"` for value types; closed `Literal` sums; sum-type discriminants over magic strings.
  - 03-ADR-0006: `--ignore-scripts` enforced at BOTH CLI and env (S4-01 lands env; this story lands CLI-half static fence).
  - 02-ADR-0001 (the amendment target): closed-set discipline + amendment-only allowlist.
- **CLAUDE.md commitments:** Extension by addition (new capabilities = new modules + new ADRs, not edits to the kernel). Match existing convention (Rule 11). Surface conflicts, don't average them (Rule 7). Newtype identifiers (`PluginId`, `RegistryUrl`). Functional core / imperative shell (mint's emit is the imperative shell — deferred as DI-vs-module-attribute trade in Notes).
- **Codebase precedents read:**
  - `src/codegenie/exec/__init__.py:96-111` — current 12-entry `ALLOWED_BINARIES`; `_SENSITIVE_EXACT`, `_SENSITIVE_PREFIX`, `_RUNNING_PROCS` weakref discipline.
  - `tests/unit/exec/test_allowed_binaries.py` — Phase 2 S1-06 precedent for amendment tests; `monkeypatch.setattr` mocking style; exact-equality discipline; ADR cross-document gate.
  - `tests/unit/test_exec.py:348-381` — the closed-set negative-list parametrize at canonical line 362-363 (`"bwrap"`, `"bubblewrap"`).
  - `src/codegenie/transforms/_forward.py:50` — empty `CapabilityBundle` shim; docstring lines 14-20 prescribe S4-05's substitution.
  - `tests/fence/test_transforms_module_purity.py:29` — `_FORWARD_ALLOWED` allowlist (the fence to amend).
  - `src/codegenie/_phase3_fence.py` — established AST-walker pattern (S1-05): `PHASE3_ROOTS`, `walk_any_annotations`, `scan_phase3_surface`, `Violation` dataclass, planted-positive matrix, floor-guard pattern.
  - `tests/fence/test_no_any_in_plugin_surface.py` — the consumer test pattern (live + planted-positive call the same walker).
  - `_validation/S4-04-sandboxed-path-onofollow.md` — the exact-same-shape S4-04 validation that pinned the seam-wiring discipline this story needed but was missing.
  - `_validation/S1-06-...` (referenced by story) — the Phase 2 template.

## Stage 2 — Critic findings

Severity legend: `block` = must rewrite before executor; `harden` = real gap a mutant would survive; `nit` = small polish.

### Critic A — Coverage

| # | Severity | Title |
|---|---|---|
| COV-01 | block | Missing AC: substitute `_forward.CapabilityBundle` to re-export from `codegenie.plugins.capabilities` |
| COV-02 | block | Missing AC: amend `_FORWARD_ALLOWED` in `tests/fence/test_transforms_module_purity.py` |
| COV-03 | block | Missing AC: existing Pydantic consumer (`ApplyContext.capabilities`) round-trip post-substitution |
| COV-04 | block | AC-13 grep test is substring-based; misses helper-function leak path |
| COV-05 | harden | `CapabilityScope` exported but no AC pins its shape |
| COV-06 | harden | No AC for per-scope-discriminant `mint()` output (parametric over scope variants) |
| COV-07 | harden | `bundle_digest` shape unpinned; could be `uuid.uuid4()` non-determinism |
| COV-08 | harden | `CapabilityBundle(npm=A, fs=B)` ambiguous — no AC pins the "exactly one" invariant |
| COV-09 | harden | AC-2 docstring substring `"03-ADR-0012"` doesn't enforce binary enumeration in the docstring |
| COV-10 | nit | AC-15 mentions scanning `plugins/` (future dir) — graceful absence handling unspecified |

### Critic B — Test Quality (mutation-resistance)

| # | Severity | Title |
|---|---|---|
| TQ-01 | block | AC-13 `src.replace(mint_src, "")` survives helper-function leak mutations |
| TQ-02 | block | AC-11 chains `frozen=True` + `extra="forbid"` — a mutant dropping `frozen=True` survives |
| TQ-03 | block | AC-12 `GitLocalOpsCapability(push=True)` fails on missing-required-fields first, not `push` |
| TQ-04 | block | AC-14 `monkeypatch.setattr` on `_emit_capability_minted` defeated by `from ... import` rebinding |
| TQ-05 | block | `bubblewrap` removal would silently green allowlist for the canonical long name |
| TQ-06 | harden | AC-12 docstring assertion uses `or` disjunction — mutant matching one phrase survives |
| TQ-07 | harden | AC-18 dormant-skip silent; no AC asserts the skip fires loudly |
| TQ-08 | harden | `--ignore-scripts` subcommand catalog missing `rebuild`/`pack`/`publish`/`update`/`run-script` |
| TQ-09 | harden | AC-14 `bundle_digest` not pinned as deterministic across calls |
| TQ-10 | harden | No per-class planted-positive test in the capability fence (mutant detecting only one class survives) |

### Critic C — Consistency

| # | Severity | Title |
|---|---|---|
| CON-01 | block | Walker home: ADR-0011 says `tooling/ruff_rules/`; codebase precedent says `src/codegenie/_<name>_fence.py` — surface conflict per Rule 7 |
| CON-02 | block | `CapabilityBundle` is already a shim in `_forward.py:50` — story silently rebuilds without flipping the shim |
| CON-03 | harden | `SandboxedPath` import path ambiguous: `from codegenie.plugins.sandbox_path import` vs `from codegenie.transforms._forward import` |
| CON-04 | harden | `JailedSubprocessSpec` symbol name not pinned against S4-01's prescribed name (drift risk) |
| CON-05 | harden | `tests/static/test_capability_fence.py` placement diverges from `tests/fence/` precedent (kernel-wide vs per-module locality) |
| CON-06 | nit | `_capability_fence.py` `_FORWARD_ALLOWED` allowlist amendment in fence test cross-references not pinned |

### Critic D — Design Patterns

| # | Severity | Title |
|---|---|---|
| DP-01 | harden | `_emit_capability_minted` as module-level mutable sink — DI alternative surfaced |
| DP-02 | harden | `CapabilityBundle` shape (three Optional fields) invites "any-subset" ambiguity; sum-type discipline cleaner |
| DP-03 | harden | AST walker hardcoded class-name set — data-driven discovery deferred (rule-of-three threshold) |
| DP-04 | harden | `mint()` Strategy via registry deferred — three concrete variants is the rule-of-three threshold but no current reuse benefit |
| DP-05 | nit | `BinaryName` newtype premature (mirrors S1-06 Pass-2 observation) |

Stage 3 (research) skipped — no `NEEDS RESEARCH` findings; every gap was answerable from the existing arch + ADRs + S4-04 / S1-06 precedents + verified repo state.

## Stage 4 — Synthesizer edits applied

| AC | Change | Why |
|----|--------|-----|
| AC-9 | Rewrote: REMOVE only `"bwrap"`; KEEP `"bubblewrap"` with explicit comment + companion `"bubblewrap" not in ALLOWED_BINARIES` assertion | CON / TQ-05: ADR-0012 only admits `bwrap`; removing `bubblewrap` would silently green the long-name policy |
| AC-11 | Rewrote: separate `frozen=True` + `extra="forbid"` + `model_config` structural assertions; killed chained check | TQ-02: chained assertion masks single-flag mutations |
| AC-12 | Rewrote: pass valid `repo`/`branch_namespace`/`_minted_by`; assert `ValidationError` with `match="push"`; canonical docstring substring (no OR-disjunction) | TQ-03, TQ-06: localize rejection on `push`; close the disjunction escape |
| AC-13 | Rewrote: AST-based — `FunctionDef("mint")` lineno-range containment check + sibling FunctionDef scan; permits `CapabilityBundle(` everywhere (it's the aggregator) | TQ-01: substring `replace()` survives helper-function leak |
| AC-14 | Rewrote: `_emit_capability_minted` is a module-level chokepoint name (not a `from ... import` alias); AST asserts the bare `Name` form in `mint()`; pin `bundle_digest` as deterministic | TQ-04, TQ-09: defeat the local-rebind monkeypatch escape; close the non-deterministic-digest mutation |
| AC-15 | Rewrote: walker home is `src/codegenie/_capability_fence.py` mirroring `_phase3_fence.py`; pin `_CAPABILITY_FENCE_ROOTS`, `_CAPABILITY_CLASS_NAMES`, marker discipline, `Violation` dataclass | CON-01: codebase precedent + ADR amendment in this story |
| AC-16 | Rewrote: test moved to `tests/fence/`; added live + planted-positive matrix + floor guard + per-class detection + `capabilities.py` exclusion AC | TQ-10, CON-05: kernel-wide locality + mutation-resistance via shared-walker pattern |
| AC-18 | Rewrote: `_NPM_LIFECYCLE_SUBCOMMANDS` covers full lifecycle-running subset (including `rebuild`); docstring records literal-only limitation; companion AC-19 keeps walker alive | TQ-08, TQ-07 |
| **NEW** AC-Sub-1 | Added: substitute `_forward.CapabilityBundle` to re-export from `codegenie.plugins.capabilities` | CON-02, COV-01: existing shim docstring prescribes the flip |
| **NEW** AC-Sub-2 | Added: amend `_FORWARD_ALLOWED` to include `codegenie.plugins.capabilities` | COV-02: without it AC-Sub-1's substitution trips the existing purity fence |
| **NEW** AC-Sub-3 | Added: three-path import identity test (`is` identity, not equality) + `ApplyContext` round-trip + existing-consumer regression | COV-03: existing `apply_context.py:32` consumer must round-trip |
| **NEW** AC-Sub-4 | Added: `model_validator(mode="after")` for `CapabilityBundle` exactly-one invariant; rejection tests for zero and >1 non-None | COV-08, DP-02 |
| **NEW** AC-Sub-5 | Added: `CapabilityScope = NpmScope \| FsScope \| GitLocalOpsScope` closed sum type per ADR-0010; `mint()` dispatches via `isinstance` with `assert_never` exhaustiveness | COV-05, COV-06 |
| AC-20 | Extended mypy scope: `transforms/_forward.py`, `_capability_fence.py`, `tests/unit/transforms/test_capability_bundle_substitution.py`, `tests/fence/test_capability_fence.py` | New files / amended files must pass mypy --strict |
| Files-to-touch | Added: `transforms/_forward.py`, `tests/fence/test_transforms_module_purity.py`, `_capability_fence.py`, ADR-0011 amendment, `tests/unit/transforms/test_capability_bundle_substitution.py`, `tests/fence/test_capability_fence.py`. Removed: `tooling/ruff_rules/*`, `tests/static/test_capability_fence.py`. | Reflect resolutions across the seam-wiring + walker-home decisions |
| Notes-for-implementer | Added five paragraphs: `mint()` Strategy-via-registry deferral, walker hardcoded-names deferral, `bundle_digest` algorithm pin, `CapabilityBundle` exactly-one invariant rationale, ADR-0011 §Consequences amendment hook. Tightened existing `bwrap` polarity note. | DP-03, DP-04, DP-01, COV-08 — surfaced design observations without elevating to ACs |
| TDD plan | Patched the AC-12 test to import `SandboxedPath` from `transforms._forward` (forward-stable), pass valid required fields, use `match="push"`, single-canonical-phrase docstring assertion. | TQ-03, TQ-06, CON-03 |

## Verdict

**HARDENED.** Story is now ready for `phase-story-executor`. The hardened ACs collectively guarantee a wrong implementation will fail at least one check; the new AC-Sub-1..AC-Sub-5 close the seam-wiring + sum-type-discipline gaps the original story silently glossed; the walker-home conflict is resolved with an in-codebase precedent and an ADR amendment in scope. Notes-for-implementer surfaces three design opportunities (registry-dispatched `mint()`, data-driven walker, DI-injected emit) as future work without overscoping the current story.
