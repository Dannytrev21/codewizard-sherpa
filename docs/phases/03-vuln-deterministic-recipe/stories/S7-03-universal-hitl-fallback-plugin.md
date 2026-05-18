# Story S7-03 — `plugins/universal--*--*/` — universal HITL fallback plugin (NFKC-sanitized handoff)

**Step:** Step 7 — First production plugin, universal HITL fallback plugin, synthetic third plugin
**Status:** Ready
**Effort:** M
**Depends on:** S6-04 (the orchestrator must already understand `RemediationOutcome.RequiresHumanReview(reason, handoff_path)` as a valid terminal outcome and exit with code 7), S2-04 (the resolver must already return `UniversalFallbackResolution` when no concrete plugin matches), S6-01 (`emit_internal(RequiresHumanReview)` is a typed `WorkflowInternalEvent` variant)
**ADRs honored:** [ADR-0003](../ADRs/0003-plugin-resolution-and-universal-fallback-semantics.md) (**the load-bearing ADR for this story** — the universal fallback IS a registered plugin under `plugins/universal--*--*/`, NOT a code branch in the resolver; specificity-0 `(*, *, *)` scope guarantees lowest sort priority; loader exits 4 on a *concrete* plugin's import failure BEFORE the resolver runs, so the universal is NEVER silently substituted), [ADR-0002](../ADRs/0002-plugin-registry-kernel-instance-with-default-singleton.md) (`@register_plugin(...)` against `default_registry` at import time — same machinery as the npm plugin), [ADR-0011](../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md) (the handoff markdown is written via `SandboxedPath` with `O_NOFOLLOW`; `PLUGINS.lock` row regen for this plugin)

## Context

Production ADR-0031 (§"No-match fallback") commits: *"no specific plugin matches is never a silent failure."* Phase 3's ADR-0003 implements that commitment by making the universal fallback **a normal registered plugin loaded by the same machinery as every other plugin**, with scope `(*, *, *)` (three `Wildcard` dims, specificity 0). The resolver sorts by `(specificity desc, precedence desc, name asc)` so the universal naturally lands LAST; when the head of the sorted list is the universal, the resolver returns the **typed variant** `UniversalFallbackResolution(reason=NoConcreteMatch)` — distinguishable at compile time from `ConcreteResolution`. There is no `if plugin.is_fallback:` branch anywhere in the resolver; the discriminator lives in the return type.

This story lands the plugin directory + manifest + subgraph that:
1. Resolves to `UniversalFallbackResolution` when no concrete plugin matches the workflow's scope (per ADR-0003).
2. Writes a **sanitized markdown handoff** to `.codegenie/handoff/<workflow_id>.md` — sanitization is **NFKC normalization + ANSI escape strip + bidi-control strip + zero-width strip** (the baseline established in `phase-arch-design.md §"Open questions deferred to implementation"`).
3. Emits a `RequiresHumanReview` workflow-internal event.
4. Returns `RemediationOutcome.RequiresHumanReview(reason=NoConcreteMatch, handoff_path=...)`.
5. Causes the CLI to exit 7 (per architecture §Decision points — "No plugin matches → universal fallback fires → `RequiresHumanReview` → exit 7. Never 'no match' exit").

**The most subtle invariant this story must protect (ADR-0003 + Edge case E10):** if a *concrete* plugin matches the scope but fails to load (e.g., its `import_module` raises), the loader exits 4 with `PluginRejected(import_error)` **before resolution even runs** — the universal fallback is NOT silently substituted. Edge case E10 is the contract; the negative test `tests/integration/test_universal_fallback_never_silent.py` (called out in `High-level-impl.md §Step 7 Done criteria` bullet 4) is the gate.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Scenarios B` — the universal-fallback sequence diagram (CLI → orchestrator → resolver returns `UniversalFallbackResolution` → universal plugin's subgraph writes sanitized markdown → emits `RequiresHumanReview` → returns `RemediationOutcome.RequiresHumanReview` → exit 7).
  - `../phase-arch-design.md §Edge cases E2` (Yarn Berry → universal) and **`E10` (concrete plugin import-error short-circuits BEFORE resolver runs)**.
  - `../phase-arch-design.md §Component design C2` (`resolve()` algorithm: "head plugin's id is `universal--*--*`, return `UniversalFallbackResolution`").
  - `../phase-arch-design.md §Decision points` (exit 7 mapping).
  - `../phase-arch-design.md §"Open questions deferred to implementation"` — "Sanitization of HITL `.codegenie/handoff/*.md`. Synthesis adopts security's NFKC + ANSI/bidi/zero-width strip; implementation may need to add more once we see real HITL content."
- **Phase ADRs:**
  - `../ADRs/0003-plugin-resolution-and-universal-fallback-semantics.md` — the load-bearing ADR for this story. **Read all 67 lines.** Especially §Decision (the algorithm), §Tradeoffs (loader startup check that `default_registry.get(PluginId("universal--*--*"))` must succeed), §Consequences (every consumer must `match` over `PluginResolution`).
  - `../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — handoff markdown is written via `SandboxedPath` with `O_NOFOLLOW`; consumers handle `OSError(errno=ELOOP)` and emit `FilesystemRaceDetected`.
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` — `§No-match fallback`; "loaded by the same mechanism."
  - `../../../production/adrs/0009-humans-always-merge.md` — the universal plugin's existence is the explicit type-level enforcement of "no autonomous merge ever."
- **Source for the resolver invariant the negative test rests on:**
  - `src/codegenie/plugins/loader.py` (from S2-03) — `importlib.import_module(...)` per plugin tree; an `ImportError` here raises `PluginRejected(import_error)` and exits 4 before `default_registry.resolve(...)` is ever called.
- **Sanitization precedent (if any):** search the repo for existing NFKC normalization helpers — `unicodedata.normalize("NFKC", s)` is stdlib. ANSI/bidi/zero-width strip is regex-based. If no helper exists, this story creates `src/codegenie/plugins/handoff_sanitize.py`.

## Goal

Land `plugins/universal--*--*/{plugin.yaml,api.py,subgraph/__init__.py}` plus a sanitizer helper at `src/codegenie/plugins/handoff_sanitize.py`, such that:
1. The plugin loads, registers via `@register_plugin(...)`, and is resolvable as `UniversalFallbackResolution` when no concrete plugin matches.
2. Its subgraph writes a sanitized markdown handoff to `.codegenie/handoff/<workflow_id>.md` via `SandboxedPath`.
3. Its terminal `RemediationOutcome.RequiresHumanReview(reason=NoConcreteMatch, handoff_path=...)` flows back to the orchestrator, which exits 7.
4. **Crucially:** the negative test proves that when a *concrete* plugin's import fails, the loader exits 4 **before** resolution and the universal is NOT silently substituted.

## Acceptance criteria

- [ ] `plugins/universal--*--*/plugin.yaml` is a valid `PluginManifest` with: `name: universal--*--*`, `version: 0.1.0`, `scope: *--*--*`, `precedence: 0` (lowest — even ties between two wildcard plugins broken by precedence), `extends: []`, `tccm: tccm.yaml` (a minimal TCCM with empty `must_read` is acceptable — the universal does not consume context, it escalates).
- [ ] `plugins/universal--*--*/api.py` declares the plugin via `@register_plugin(plugin)` at module-import time; its `build_subgraph(registry)` returns a one-node `PluginSubgraph` whose single `SubgraphNode.run(state) -> NodeTransition` writes the handoff, emits the event, and returns `ShortCircuit(RemediationOutcome.RequiresHumanReview(...))`.
- [ ] **Loader startup check** (ADR-0003 §Consequences): if `default_registry.get(PluginId("universal--*--*"))` fails after loader completes, the loader emits a `PluginRegistryCorrupted` spanning event and hard-exits. A unit test deletes the plugin directory in a fixture, runs the loader, and asserts the corrupted-registry path fires.
- [ ] `default_registry.resolve(PluginScope.parse("vulnerability-remediation--rust--cargo").unwrap())` returns `UniversalFallbackResolution(reason=NoConcreteMatch, candidates_considered=[...])` — the Rust/Cargo scope matches no concrete plugin, so the universal head wins.
- [ ] The universal subgraph writes `.codegenie/handoff/<workflow_id>.md` via `SandboxedPath.create(jail, f"handoff/{workflow_id}.md")` + `O_NOFOLLOW` (per ADR-0011); the handoff file's content is markdown.
- [ ] Sanitization helper `src/codegenie/plugins/handoff_sanitize.py` exposes `sanitize_for_handoff(s: str) -> str` that:
  1. Applies `unicodedata.normalize("NFKC", s)`.
  2. Strips ANSI escape sequences (regex `r"\x1b\[[0-9;]*[A-Za-z]"` covers CSI; also strip OSC and the bare `\x1b` introducer).
  3. Strips Unicode bidi-control characters (the four overrides: `U+202A`–`U+202E` and the two isolates `U+2066`–`U+2069`).
  4. Strips zero-width characters (`U+200B`, `U+200C`, `U+200D`, `U+FEFF`).
- [ ] `sanitize_for_handoff(...)` unit tests cover each strip category with adversarial fixtures (an ANSI-injecting CVE description; a bidi-override-injecting package name; a zero-width-padded version string).
- [ ] The universal subgraph emits a `RequiresHumanReview` `WorkflowInternalEvent` (typed; from S6-01's event taxonomy).
- [ ] **Negative test `tests/integration/test_universal_fallback_never_silent.py`**: a fixture concrete plugin under `tests/fixtures/plugins/broken-import--node--npm/` has an `api.py` that raises `ImportError("synthetic")` at module-import time. Running the loader (or `codegenie remediate ./tests/fixtures/repos/express-cve-2024-21501 --cve CVE-2024-21501`) exits 4 with `PluginRejected(import_error)` — NOT exit 7. The universal fallback is NOT registered as a substitute for the broken plugin.
- [ ] `plugins/PLUGINS.lock` contains a row for `universal--*--*`.
- [ ] No LLM SDK import added under `plugins/universal--*--*/` or in the sanitizer (verified via `make fence` + `make lint-imports`).
- [ ] CLI exit code from running `codegenie remediate ./tests/fixtures/repos/rust-cargo-fixture --cve CVE-2024-Y` is **7**, and `.codegenie/handoff/<workflow_id>.md` exists with non-empty sanitized content.
- [ ] The red test from §TDD plan exists, was committed at red, and is now green.
- [ ] `ruff format --check`, `ruff check`, `mypy --strict` clean on touched files; existing tests still pass.

## Implementation outline

1. **Create the directory tree.** The directory name uses literal hyphens and stars — `plugins/universal--*--*/`. Shell globbing in scripts must quote it. The Python module-name mapping under whatever convention S2-03 set (likely `universal____` or similar) is handled by the loader; **don't** invent a new convention for this directory.
2. **`plugin.yaml`** — minimal valid manifest. Scope `*--*--*` (three wildcard dims; `PluginScope.parse` must produce three `Wildcard`s and `specificity() == 0`). Precedence `0`. Extends `[]`. TCCM `tccm.yaml`.
3. **`tccm.yaml`** — minimal: empty `must_read`, empty `should_read`, empty `may_read`, empty `provides`, empty `requires`. The universal does no context gathering; it escalates.
4. **`api.py`** — declares the plugin, calls `register_plugin(plugin)` at module top level. The `build_subgraph(registry)` returns a one-node `PluginSubgraph` wrapping `UniversalFallbackNode`. The plugin's `adapters()` returns `{}`. `transforms()` returns `{}`.
5. **`subgraph/handoff_node.py`** — the one `SubgraphNode` implementation:
   ```python
   class UniversalFallbackNode:
       async def run(self, state: SubgraphState) -> NodeTransition:
           md = self._render_markdown(state)
           sanitized = sanitize_for_handoff(md)
           handoff_path = SandboxedPath.create(
               state.jail, f"handoff/{state.workflow_id}.md"
           ).unwrap()
           with handoff_path.open("w") as f:
               f.write(sanitized)
           state.event_log.emit_internal(
               RequiresHumanReview(
                   workflow_id=state.workflow_id,
                   reason=NoConcreteMatch,
                   handoff_path=handoff_path,
                   candidates_considered=state.resolution.candidates_considered,
               )
           )
           return ShortCircuit(
               RemediationOutcome.RequiresHumanReview(
                   reason=NoConcreteMatch,
                   handoff_path=handoff_path,
               )
           )
   ```
6. **`src/codegenie/plugins/handoff_sanitize.py`** — `sanitize_for_handoff(s: str) -> str`. Pure function, stdlib-only. Test it independently from the plugin.
7. **Loader startup check.** Verify (or add — depending on what S2-03 shipped) the invariant: after loader completes, `default_registry.get(PluginId("universal--*--*"))` must succeed; on miss, emit `PluginRegistryCorrupted` (spanning) and exit. If S2-03's loader does NOT enforce this, that's a gap — surface it and add the check at loader-exit time.
8. **Negative test.** Create `tests/fixtures/plugins/broken-import--node--npm/{plugin.yaml,api.py}` where `api.py` body is `raise ImportError("synthetic broken plugin")`. The loader's `importlib.import_module(...)` raises; loader translates to `PluginRejected(import_error)` and the process exits 4. The test asserts exit code 4 AND that NO `.codegenie/handoff/*.md` was written (the universal subgraph never ran).
9. **`PLUGINS.lock` regen** — add the `universal--*--*` row.

## TDD plan — red / green / refactor

### Red

Test file path: `tests/unit/plugins/test_universal_fallback_plugin.py`

```python
# tests/unit/plugins/test_universal_fallback_plugin.py
import pytest

from codegenie.plugins.registry import default_registry
from codegenie.plugins.resolution import UniversalFallbackResolution
from codegenie.plugins.scope import PluginScope
from codegenie.types.identifiers import PluginId
from codegenie.plugins.handoff_sanitize import sanitize_for_handoff


def test_universal_plugin_registered_with_wildcard_scope():
    plugin = default_registry.get(PluginId("universal--*--*"))
    assert plugin is not None
    assert plugin.manifest.scope.specificity() == 0    # three Wildcards


def test_resolver_returns_universal_fallback_for_unmatched_scope():
    scope = PluginScope.parse("vulnerability-remediation--rust--cargo").unwrap()
    resolution = default_registry.resolve(scope)
    assert isinstance(resolution, UniversalFallbackResolution)
    assert resolution.reason.kind == "no_concrete_match"


def test_sanitize_strips_ansi_escape_sequences():
    raw = "package \x1b[31mmalicious\x1b[0m\n"
    assert "\x1b" not in sanitize_for_handoff(raw)
    assert "malicious" in sanitize_for_handoff(raw)


def test_sanitize_strips_bidi_override_characters():
    raw = "package ‮good‬"    # right-to-left override + pop
    out = sanitize_for_handoff(raw)
    assert "‮" not in out
    assert "‬" not in out


def test_sanitize_strips_zero_width():
    raw = "ver​sion-1.0"
    assert "​" not in sanitize_for_handoff(raw)


def test_sanitize_applies_nfkc_normalization():
    import unicodedata
    raw = "fiﬁnale"    # FB01 = ligature fi
    out = sanitize_for_handoff(raw)
    assert out == unicodedata.normalize("NFKC", "fiﬁnale").replace("​", "")
```

A second integration test for the universal-never-silent invariant:

```python
# tests/integration/test_universal_fallback_never_silent.py
import subprocess
from pathlib import Path

def test_concrete_plugin_import_error_exits_4_not_7(tmp_path, monkeypatch):
    """ADR-0003 + Edge case E10:
    When a concrete plugin matching the scope fails to import,
    the loader exits 4 BEFORE resolution. The universal fallback is NEVER
    silently substituted. This is the load-bearing invariant.
    """
    # Arrange: a fixture plugin tree with broken-import--node--npm/ whose
    # api.py raises ImportError at module-import time. Plus PLUGINS.lock
    # populated with the right tree sha.
    fixture_plugins = Path("tests/fixtures/plugins/broken_import_setup")
    # Act: invoke the CLI (or call the loader directly) with the fixture
    # plugins directory taking precedence over the production one.
    result = subprocess.run(
        ["codegenie", "remediate",
         "./tests/fixtures/repos/express-cve-2024-21501",
         "--cve", "CVE-2024-21501",
         "--plugins-root", str(fixture_plugins)],
        capture_output=True, env={"CODEGENIE_PLUGINS_ROOT": str(fixture_plugins)},
    )
    # Assert: exit 4 (PluginRejected), NOT 7 (RequiresHumanReview).
    assert result.returncode == 4
    assert b"PluginRejected" in result.stderr
    # And no handoff was written — the universal subgraph never ran.
    assert not list(Path(".codegenie/handoff").glob("*.md"))
```

A third integration test for the happy path:

```python
# tests/integration/test_universal_fallback.py
def test_rust_cargo_repo_routes_to_universal_fallback_and_exits_7(tmp_path):
    result = subprocess.run(
        ["codegenie", "remediate",
         "./tests/fixtures/repos/cargo-fixture", "--cve", "CVE-2024-Y"],
        capture_output=True,
    )
    assert result.returncode == 7
    handoffs = list(Path(".codegenie/handoff").glob("*.md"))
    assert len(handoffs) == 1
    content = handoffs[0].read_text()
    assert "CVE-2024-Y" in content
    # No ANSI escapes leaked through:
    assert "\x1b" not in content
```

Run; confirm `KeyError` on `default_registry.get(PluginId("universal--*--*"))` and `ImportError` on `sanitize_for_handoff`; commit the red.

### Green

Land the plugin tree + sanitizer + the one-node subgraph + `PLUGINS.lock` row + the fixture `cargo-fixture/` and `broken_import_setup/` fixtures.

Smallest shape:
- `sanitize_for_handoff` is ~15 lines: NFKC normalize, regex strip ANSI, strip a fixed `frozenset` of bidi + zero-width codepoints via `str.translate`.
- `UniversalFallbackNode.run(...)` is ~20 lines: render markdown from `state` (CVE id, candidates considered, why-no-match summary), sanitize, write via `SandboxedPath`, emit event, `ShortCircuit(...)`.
- `api.py` is ~10 lines.

### Refactor

- Move the markdown template into a Jinja-free f-string helper at module scope so the `UniversalFallbackNode` body stays a sequence of three lines.
- Confirm `mypy --strict` clean. `NodeTransition = Advance(state) | ShortCircuit(outcome) | Escalate(reason)` from S6-03; the universal returns `ShortCircuit` exclusively.
- Document in the module docstring that this plugin's existence is the type-level enforcement of ADR-0009 (humans always merge) at the "no concrete plugin" boundary.
- Add a `WARNING` log line in the universal subgraph reporting which scope fell through and which concrete plugins were considered — operator visibility into "why did I land in HITL."

## Files to touch

| Path | Why |
|---|---|
| `plugins/universal--*--*/plugin.yaml` | New — `PluginManifest` with `*--*--*` scope, precedence 0 |
| `plugins/universal--*--*/tccm.yaml` | New — minimal TCCM (empty must_read; universal does not gather context) |
| `plugins/universal--*--*/api.py` | New — `@register_plugin(plugin)` + `build_subgraph` returning one-node subgraph |
| `plugins/universal--*--*/subgraph/__init__.py` | New — re-exports `UniversalFallbackNode` |
| `plugins/universal--*--*/subgraph/handoff_node.py` | New — `UniversalFallbackNode` writing sanitized markdown + emitting event + returning `ShortCircuit` |
| `src/codegenie/plugins/handoff_sanitize.py` | New — pure `sanitize_for_handoff(s) -> str` (NFKC + ANSI/bidi/zero-width strip) |
| `plugins/PLUGINS.lock` | Modified — add row for `universal--*--*` |
| `tests/fixtures/repos/cargo-fixture/` | New (or extend) — minimal Cargo repo fixture for the universal-fallback happy-path integration test |
| `tests/fixtures/plugins/broken_import_setup/` | New — fixture plugin tree with `broken-import--node--npm/` raising ImportError at import time + a PLUGINS.lock matching that tree |
| `tests/unit/plugins/test_universal_fallback_plugin.py` | New — registration + resolution + sanitization unit tests |
| `tests/unit/plugins/test_handoff_sanitize.py` | New — per-category sanitization tests with adversarial fixtures |
| `tests/integration/test_universal_fallback.py` | New — exit-7 + handoff-written happy path |
| `tests/integration/test_universal_fallback_never_silent.py` | New — **the negative test** — concrete plugin import failure exits 4, NOT 7 |
| `tests/unit/plugins/test_loader_universal_corruption_check.py` | New — loader emits `PluginRegistryCorrupted` + exits if universal not found |

## Out of scope

- **Markdown HTML-embed neutralization** — `phase-arch-design.md §Open questions` explicitly defers: "Synthesis adopts security's NFKC + ANSI/bidi/zero-width strip; implementation may need to add more (e.g., markdown HTML-embed neutralization) once we see real HITL content." This story ships the baseline; future hardening is its own story.
- **Yarn Berry routing test (`tests/integration/test_yarn_berry_routed_to_universal.py`)** — that's S8-04's adversarial coverage. This story ships the universal plugin; the routing-against-Yarn-Berry case is part of the adversarial portfolio.
- **`extends`-chain composition with the universal as a base** — the universal does not appear in any concrete plugin's `extends` chain in Phase 3; concrete plugins compose only with each other (if at all — Phase 3 uses depth-0 chains exclusively per S7-01 + S7-02).
- **Bench / performance** — universal-fallback path is rare; no bench needed in Phase 3. Phase 9 may add `bench_universal_resolution_latency` if relevant.
- **Bench-replayable emission** — S9-04's surface.
- **Sigstore signing** of the universal plugin — Phase 11.

## Notes for the implementer

- **READ ADR-0003 IN FULL.** This story stands or falls on whether the universal-fallback semantics match the ADR. Especially: §Decision (the four-step algorithm), §Tradeoffs (the loader startup check), §Consequences (the `PluginRegistryCorrupted` event). Do not paraphrase the ADR; implement it.
- **The negative test is the gate.** Edge case E10 (`phase-arch-design.md §Edge cases`) is the documented invariant: a concrete plugin's import failure exits 4 BEFORE resolution — universal is NOT substituted. If you cannot make the negative test fail with an honest implementation (i.e., if your green code makes it return exit 7 instead), the architecture is wrong, not the test. Fix the implementation.
- **Subgraph node is `ShortCircuit`, NOT `Advance`.** `NodeTransition = Advance(state) | ShortCircuit(outcome) | Escalate(reason)`. The universal terminates the workflow with the human-review outcome; it does not advance to a next node. If S6-03's `SubgraphNode` Protocol forces an `Advance` shape, that's a Gap-1 regression — surface it.
- **The handoff path uses `SandboxedPath`, not `pathlib.Path` directly.** Per ADR-0011, `SandboxedPath.open(...)` is always `O_NOFOLLOW`; a symlink swap between `create()` and `open()` raises `OSError(ELOOP)`. The universal subgraph must catch `ELOOP` and emit `FilesystemRaceDetected` (per `phase-arch-design.md §Edge cases`). Don't skip the try/except — symlink TOCTOU on the handoff directory is a real attack vector.
- **`sanitize_for_handoff` is stdlib-only and pure.** No regex compilation at call time — compile module-level. No state. No I/O. Test it independently from the plugin. Property-test it with Hypothesis if cheap: `assume property: sanitize_for_handoff(sanitize_for_handoff(s)) == sanitize_for_handoff(s)` (idempotence).
- **The scope `*--*--*` is the discriminator.** `PluginScope.parse("*--*--*").unwrap().specificity() == 0` is a strict assertion. If `specificity()` somehow returns >0 for an all-wildcard scope, that's an S1-02 / S2-04 regression — surface it.
- **Precedence `0` is fine** — the universal is the only specificity-0 plugin in Phase 3, so precedence ties are not possible. Phase 7+ may register other wildcard plugins (e.g., a cross-cutting `TreeSitterImportGraphAdapter` carrier per ADR-0032 §Consequences), at which point precedence ties become possible and the name-sort tiebreaker per ADR-0003 kicks in.
- **No `extends`** for the universal — it is the base of nothing; nothing inherits from it. ADR-0003 §Tradeoffs: cross-cutting "base" adapters can ship in `(*,*,*)` plugins per ADR-0032 §Consequences, but Phase 3 does not exercise that. Keep `extends: []`.
- **`RequiresHumanReview` is a `WorkflowInternalEvent`, NOT `WorkflowSpanningEvent`.** Per `phase-arch-design.md §Component design C9` event taxonomy. Don't emit it on the spanning stream by accident; the BLAKE3 chain there is for cross-workflow integrity.
- **Resist gold-plating.** No retry. No "maybe a concrete plugin matches if I squint." If the resolver returned `UniversalFallbackResolution`, the workflow ends in HITL. The handoff markdown should explain *what was tried and why nothing matched*, sized small (≤ 8 KB target; align with `AttemptSummary.prior_failure_summary` cap from S1-04).
