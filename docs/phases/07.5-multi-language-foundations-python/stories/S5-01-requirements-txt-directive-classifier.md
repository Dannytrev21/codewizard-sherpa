# Story S5-01 — `requirements.txt` directive classifier with fail-closed taxonomy

**Step:** Step 5 — Build the Python dep-graph strategies (pip / poetry / uv)
**Status:** Ready
**Effort:** M
**Depends on:** S1-01
**ADRs honored:** ADR-0009, ADR-0008

## Context
`requirements.txt` is not a manifest — it is a directive DSL whose lines (`-e .`, `git+...`, `--index-url`, `-r other.txt`, plus future pip syntax) are attacker-controlled. ADR-0009 mandates that every non-pinned-dependency directive be recorded as a *typed fact, never acted on*, with an unknown directive failing closed. This story lands the pure classifier and its two frozen contract dataclasses (`UnresolvedDependency`, `IndexOverride`) so the pip strategy (S5-02) can consume them without ever fetching, executing, or escaping the repo root.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Python dep-graph strategies (pip / poetry / uv)` — the directive-fact mapping table (`-e .` → editable_install, `git+...` → vcs_source, `--index-url` → `IndexOverride{url_host}`, `-r` → out_of_tree_include, unknown → unknown_directive).
- **Architecture:** `../phase-arch-design.md §Data model — Python dep-graph unresolved facts` — the exact `UnresolvedDependency`/`IndexOverride` dataclass shapes (frozen, `reason` is a closed `Literal`, `IndexOverride.url_host` is host-only).
- **Architecture:** `../phase-arch-design.md §Edge cases` rows 6, 7, 8 — `--index-url http://attacker/` (host only), `-r ../../../etc/passwd` (out-of-tree), unknown directive (fail-closed).
- **Phase ADRs:** `../ADRs/0009-requirements-txt-directive-language-parsing-contract.md` — ADR-0009 — directive-language contract, closed `reason` `Literal`, fail-closed default-deny, `url_host` data-minimization.
- **Phase ADRs:** `../ADRs/0008-python-depgraph-pure-parsing-no-resolution.md` — ADR-0008 — pure parsing, zero network, zero subprocess.
- **Production ADRs:** `../../../production/adrs/0033-domain-modeling-discipline.md` — closed sum types; `../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md` — the taxonomy as a named contract.
- **Existing code:** `src/codegenie/types/identifiers.py §PackageManager` — confirm `"pip"` is in the Literal after S1-01.
- **Existing code:** `src/codegenie/depgraph/model.py` — where dep-graph value types already live; mirror its `from __future__ import annotations` + frozen-dataclass style.

## Goal
Land a pure `classify_requirements_directive` function plus the frozen `UnresolvedDependency`/`IndexOverride` contract dataclasses that map every non-pinned `requirements.txt` line to a typed fact, failing closed on any unrecognized directive.

## Acceptance criteria
- [ ] The TDD red test exists, is committed, and fails before implementation — then green.
- [ ] `UnresolvedDependency` and `IndexOverride` are `@dataclass(frozen=True)`; `UnresolvedDependency.reason` is the exact closed `Literal["editable_install", "vcs_source", "out_of_tree_include", "unknown_directive"]`; `IndexOverride` stores `url_host` only (the full URL is never an attribute, never returned).
- [ ] `-e .`/`-e <path>` → `editable_install`; `git+https://...` (and other `git+`/`hg+`/`bzr+` VCS prefixes) → `vcs_source`; `--index-url`/`--extra-index-url` → `IndexOverride` with host-only; `-r <path>`/`-c <path>` → classified for downstream root-containment by the caller; any unrecognized leading `--`/directive token → `unknown_directive` (fail closed, never `None`, never dropped).
- [ ] A pinned dependency line (`flask==2.0.1`) is classified as a normal dependency (NOT an `UnresolvedDependency`) so the pip strategy can build a real edge from it.
- [ ] The classifier is a pure function — no I/O, no network, no subprocess, no filesystem access; it operates on the line string only (path resolution is the caller's job, S5-02).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` pass on touched files; `pytest` green on touched test files.
- [ ] Status set to `Done` on completion.

## Implementation outline
1. Create `src/codegenie/depgraph/python/__init__.py` (new sub-package) and `src/codegenie/depgraph/python/requirements.py`.
2. Define `UnresolvedDependency` and `IndexOverride` frozen dataclasses exactly per the arch-design data model; export both from the module `__all__`.
3. Define a small result sum type for the classifier output — e.g. a `PinnedDependency` dataclass (name + version spec, sanitized) plus the two unresolved fact types — so the caller `match`es exhaustively.
4. Implement `classify_requirements_directive(raw_line: str) -> ...` as pure parsing: strip comments/whitespace, detect leading `-e`/`-r`/`-c`/`--index-url`/`--extra-index-url`/`git+`-style URLs, else if the line starts with `--` or an unrecognized directive token → `unknown_directive`; else parse as a pinned/loose dependency spec.
5. For `--index-url`/`--extra-index-url`: extract `url_host` via `urllib.parse.urlsplit` for *parsing only* (string split, no fetch) — store the host, discard the rest.
6. Add a module-level `_WARNING_IDS: Final[frozenset[str]]` if the classifier emits warnings (e.g. `python.unknown_requirements_directive`), validated at import per the `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` convention.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/depgraph/python/test_requirements_classifier.py`.
Test name: `test_unknown_directive_fails_closed`.
```python
def test_unknown_directive_fails_closed() -> None:
    # arrange: a directive pip may add in the future that the classifier
    #          has never seen — the dangerous case (fetch instruction or
    #          real dependency).
    line = "--future-pip-directive=somevalue"
    # act
    result = classify_requirements_directive(line)
    # assert: it is recorded loudly as unknown_directive — never None,
    #         never silently dropped, never honored (ADR-0009 fail-closed).
    assert isinstance(result, UnresolvedDependency)
    assert result.reason == "unknown_directive"
```
Also red in the same file before impl: `test_index_url_stores_host_only` (`--index-url http://attacker.example/simple/` → `IndexOverride(url_host="attacker.example")`, asserting the path/scheme are absent from every field), `test_editable_install_classified`, `test_vcs_url_classified`, `test_pinned_dependency_is_not_unresolved`. All must fail with `ImportError`/`NameError` before `requirements.py` exists.

### Green — make it pass
Implement `requirements.py` with the two frozen dataclasses and `classify_requirements_directive`. Smallest shape: a prefix-table (`Final` tuple/dict of `(prefix, reason)` pairs — the data-driven catalog idiom) iterated in order; a default-deny final branch returning `unknown_directive`. `urlsplit().hostname` for the index-host extraction.

### Refactor — clean up
Add docstrings citing ADR-0009; type every helper; ensure the prefix catalog is a module-level `Final`; confirm no `urllib` *request* surface is imported (only `urllib.parse`); add the `match`-friendly result union and a module docstring stating "pure parsing — never honors a directive."

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/depgraph/python/__init__.py` | New Python dep-graph sub-package collection point. |
| `src/codegenie/depgraph/python/requirements.py` | The directive classifier + `UnresolvedDependency`/`IndexOverride` contract dataclasses. |
| `tests/unit/depgraph/python/__init__.py` | New test sub-package. |
| `tests/unit/depgraph/python/test_requirements_classifier.py` | The directive-classifier unit tests. |

## Out of scope
- Building the `networkx.DiGraph` from classified directives — S5-02 (pip strategy).
- Repo-root containment resolution for `-r` paths — S5-02 owns the filesystem-relative check; this story only *classifies* the directive shape.
- The adversarial corpus + zero-egress monitors — S5-05.
- The depgraph-purity AST fence — S5-06.

## Notes for the implementer
- `urllib.parse` is import-safe (no network); `urllib.request` is NOT — never import it. S5-06's fence will catch `urllib.request`/`urllib.error` but you should not need them at all.
- `IndexOverride` must never carry the full URL on any field — the arch-design and ADR-0009 are explicit: the path/query are attacker-controlled and discarded. A test asserts this.
- Fail-closed means the *default* branch returns `unknown_directive`, not `None` and not a silent skip — the unknown-directive test is the teeth (Rule 9; ADR-0009's "moving target" risk).
- A pinned dependency must remain a first-class non-unresolved result — if you collapse everything into `UnresolvedDependency` the pip strategy can build no edges.
- Keep the function pure: path resolution for `-r`/`-c` is the caller's job (S5-02). This story classifies the *directive token*, not the filesystem.
- Mirror `codegenie.depgraph.model`'s `from __future__ import annotations` + frozen-dataclass conventions; do not invent a new style.
