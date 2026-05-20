# ADR-0005: `ProjectDetector` is a `Protocol` returning a sum type; markers live in a shared addition-only catalog

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** Structural typing (Protocol) · Tagged union / sum type · Registry / data-driven catalog · anti-duplication
**Related:** [ADR-0004](0004-python-detection-as-base-tier-probe-not-prepass.md), [ADR-0006](0006-typescript-retrofit-by-reference-probes-self-registered.md), [production ADR-0032](../../../production/adrs/0032-language-search-adapters.md), [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md), [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md)

## Context

Each `LanguagePack` must answer "is this repo a $LANGUAGE project?" — the roadmap-named *project detector* capability. Two design questions arose:

1. **The detector's type and result.** The best-practices design proposed a `ProjectDetector` returning a `Detected | NotDetected` result. The question was whether the detector is an ABC (inheritance) or a `Protocol` (structural), and whether the result is a sum type or a `bool` with loose sibling fields.

2. **Where marker knowledge lives.** The best-practices design duplicated marker tuples (`pyproject.toml`, `setup.py`, `package.json`, …) into each per-language detector and called it "the design's accepted-duplication point" — then admitted in its own Open Question Q4 that a shared catalog "would be cleaner and is addition-only." The critic flagged this as the lens inverting its own job: [ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md)'s Consequences explicitly name *duplication* as one of the "two problems in this space [that] have no mechanical fence" and a standing review criterion — and the best-practices design knowingly shipped the anti-pattern with the better option identified in the same document ([critique.md §Attacks on the best-practices design, problem 5](../critique.md)).

A complication: the shipped Phase 0/1 `LanguageDetectionProbe` already has its own marker logic. Editing it to read a new shared catalog would be a *silent edit* to shipped code.

## Options considered

- **Detector type.** *Option A — ABC inheritance:* every detector extends a base class. **Pattern:** inheritance for code reuse — couples every detector to a base. *Option B — `typing.Protocol`:* structural, no inheritance. **Pattern:** Structural typing — ADR-0032's settled adapter idiom.
- **Detection result.** *Option C — `detected: bool` + loose sibling fields (`markers=[...]`, `confidence=...`):* **Pattern:** tag-and-dispatch-without-a-tagged-union — `detected=False` with a populated `markers` list slips through. *Option D — `Detected(confidence, marker_files) | NotDetected` sum type:* **Pattern:** Tagged union — `match` + `assert_never` makes a missing case a compile error.
- **Marker knowledge.** *Option E — duplicate marker tuples per detector:* **Pattern:** duplication-by-addition — the anti-pattern ADR-0043 singles out. *Option F — a shared addition-only `markers.py` `Final` catalog* both detectors read: **Pattern:** Registry / data-driven catalog (the `_MONOREPO_PRECEDENCE` idiom).

## Decision

`ProjectDetector` is a **`typing.Protocol`** (structural, no inheritance — ADR-0032's adapter idiom). It returns a **sum type** `DetectionResult = Detected | NotDetected`, where `Detected` carries `confidence: Confidence` and `marker_files: tuple[Path, ...]`. Marker knowledge lives in a **new, addition-only `src/codegenie/languages/markers.py` `Final` catalog** — a `LANGUAGE_MARKERS: Final[Mapping[Language, tuple[str, ...]]]` that every per-language `ProjectDetector` consults. The shipped `LanguageDetectionProbe` is **not edited** to read the catalog (that would be a silent edit); it keeps its Phase-0/1 marker logic, and a conformance assertion proves probe and detectors agree on the golden fixtures. Detection is **monotone / additive**: a polyglot repo is detected as *both* languages; a detector never demotes another language's verdict. The Python detector returns `Detected(confidence="high")` only on a real manifest and `Detected(confidence="low")` for a bare `*.py` tree.

## Tradeoffs

| Gain | Cost |
|---|---|
| Marker duplication — the anti-pattern ADR-0043 names — is killed addition-only; one `Final` catalog is the source of truth for the new detectors | `LanguageDetectionProbe` keeps its *own* marker logic; the catalog is the source of truth only for the *new* detectors, not for the shipped probe |
| The catalog is a new file — zero edit to the shipped `LanguageDetectionProbe`, no silent edit | Probe and detectors agree by *conformance assertion*, not by a shared call — a tested invariant rather than a structural one |
| `Protocol` gives the detector contract with no inheritance coupling — a new language implements it with zero base-class ceremony | `Protocol` conformance is structural; a detector that drifts from the contract is caught by `mypy`/conformance, not by an inheritance compile error |
| `Detected \| NotDetected` makes "detected with no markers" unrepresentable — a `match` missing a case is a compile error | A sum type is slightly more verbose at call sites than a `bool` — paid once, worth it |
| `confidence="high"` only on a real manifest narrows the attacker's "force Python parsers to run on a Node repo" surface | A bare `*.py` tree still triggers Python probes at `confidence="low"` — over-detection is accepted as the lesser evil vs. a silent skip |

## Pattern fit

Three toolkit patterns, each load-bearing. **Structural typing (Protocol)** — the toolkit and ADR-0032 both prefer Protocols over ABC inheritance at technology/contract boundaries; a detector is a contract, not an `is-a` relationship. **Tagged union / sum type** — "Detected vs not" is a state with per-variant fields; the toolkit flags "booleans for state" as an anti-pattern because `detected=False` with `markers=[...]` is an illegal combination a bool allows and a sum type forbids. **Registry / data-driven catalog** — marker knowledge is *iterated data, not branched code*; the codebase already uses the `_MONOREPO_PRECEDENCE` / `_LOCKFILE_PRECEDENCE` `Final`-tuple idiom, and a shared `markers.py` is that idiom applied to detection. The anti-pattern avoided is duplication-by-addition: copying marker tuples into each detector is the exact "extension-by-addition taken literally produces near-duplicate components" failure ADR-0043 names as a standing review criterion.

## Consequences

- A new language's detection markers are added as one row in `LANGUAGE_MARKERS` — addition-only, no edit to any existing detector or to the shipped probe.
- Detection is monotone: a planted `pyproject.toml` in a real Node repo adds a (correct, if real) Python verdict; it cannot demote or mis-route the Node verdict (edge case #3, [phase-arch-design.md §Edge cases](../phase-arch-design.md#edge-cases)).
- The `confidence="high"` / `confidence="low"` split means a bare `*.py` tree is detected but every resulting slice carries low confidence — honest under-confidence over a silent skip.
- A conformance assertion verifies `LanguageDetectionProbe` and the per-language detectors agree on the golden fixtures — drift between the shipped probe's logic and the catalog becomes a red test, not a silent divergence.
- `register_language` does not couple detectors and probes — the detector is a pack capability; the probe is a registry entry; the catalog is shared data both read.

## Reversibility

**High.** `ProjectDetector` is a `Protocol` and `markers.py` is a `Final` mapping — both are in-memory, addition-only structures. Swapping the detector type or restructuring the catalog is a localized edit. The one durable commitment is *not* editing `LanguageDetectionProbe` to read the catalog: doing so later would be a sanctioned migration (a loud, reviewed sweep) rather than a casual edit, precisely because it touches shipped behavior. Until then the conformance assertion is the agreed-upon bridge.

## Evidence / sources

- [final-design.md §Components — `ProjectDetector` + the shared marker catalog](../final-design.md#components), §Synthesis ledger CR-3, §Pattern reconciliation
- [phase-arch-design.md §Component design — `ProjectDetector` + `DetectionResult` + the `markers.py` catalog](../phase-arch-design.md#component-design), §Data model, §Edge cases #3
- [critique.md §Attacks on the best-practices design](../critique.md) — problem 5 (knowingly-shipped duplication anti-pattern)
- [production ADR-0032](../../../production/adrs/0032-language-search-adapters.md) — the `Protocol` adapter idiom; [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md) — sum types
- [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md) — duplication as a standing review criterion; silent edits forbidden
