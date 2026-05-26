"""Phase 6 S1-02 AC-8 — AST no-side-effects fence over ``_chain.py``.

Walks the AST of ``src/codegenie/workflows/_chain.py`` and refuses any
reference to names that would let the chain-head computation depend on
the clock, env, randomness, or filesystem state.

ADR-0003 §"Consequences" requires that "failed verification transitions
to ``FailedUnrecoverable(reason='checkpoint_integrity')``." If the
chain-head computation EVER depends on impure state, the same event
sequence would produce DIFFERENT chain heads across the
``LocalVulnRemediationSut`` (in-process LangGraph) and
``TemporalVulnRemediationSut`` (Temporal Activity worker) substrates —
every Phase-9 replay would spuriously trip
``FailedUnrecoverable(reason='checkpoint_integrity')``. This fence starts
trivially passing today and starts BITING the moment any later story
widens ``_chain.py`` with impurity.

``uuid`` is forbidden specifically because a chain-head computation that
ever calls ``uuid4()`` would diverge across substrates — Phase-9 S4-05
G5 invariance failure mode.
"""

from __future__ import annotations

import ast
from pathlib import Path

import codegenie.workflows._chain as chain_module
import codegenie.workflows._replay as replay_module

_PURE_CORE_MODULES = (chain_module, replay_module)

_FORBIDDEN_NAMES = {
    "open",
    "socket",
    "urllib",
    "httpx",
    "requests",
    "random",
    "uuid",
}

_FORBIDDEN_ATTRS = {
    "time": {"time", "monotonic", "perf_counter", "process_time", "time_ns"},
    "datetime": {"now", "utcnow", "today"},
    "os": {"environ", "getenv", "urandom"},
}


def _scan_module_for_impurity(module: object) -> list[str]:
    src = Path(module.__file__).read_text()
    tree = ast.parse(src)
    bad: list[str] = []
    for node in ast.walk(tree):
        # Direct name references (e.g. open(), uuid.uuid4()).
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            bad.append(f"{node.id} @ line {node.lineno}")
        # ``import x`` of a forbidden module.
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in _FORBIDDEN_NAMES:
                    bad.append(f"import {alias.name} @ line {node.lineno}")
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in _FORBIDDEN_NAMES:
                bad.append(f"from {node.module} import ... @ line {node.lineno}")
        # ``time.time()`` / ``datetime.now()`` / ``os.environ`` etc.
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            base = node.value.id
            if base in _FORBIDDEN_ATTRS and node.attr in _FORBIDDEN_ATTRS[base]:
                bad.append(f"{base}.{node.attr} @ line {node.lineno}")
    return bad


def test_chain_module_has_no_impure_names() -> None:
    bad = _scan_module_for_impurity(chain_module)
    assert not bad, (
        "AC-8: _chain.py contains impure-name references that would break "
        "the Phase-9 byte-equality replay invariance:\n  - "
        + "\n  - ".join(sorted(set(bad)))
        + "\n\nThe chain-head computation MUST stay purely functional — see "
        "ADR-0003 §Consequences. If a new dependency is genuinely needed, "
        "amend ADR-0003 first."
    )


def test_replay_module_has_no_impure_names() -> None:
    """Phase-6 S2-02 AC-3 — the pure-core replay fold inherits the same fence.

    A ``time.time()`` call inside the fold would make the verifier flaky
    on slow CI; a ``sqlite3`` import would re-couple the pure core to
    SQLite, breaking the Phase-9 Postgres parity. Either regression is
    surfaced by this fence.
    """
    bad = _scan_module_for_impurity(replay_module)
    assert not bad, (
        "S2-02 AC-3: _replay.py contains impure-name references that "
        "would break the verifier's substrate-agnostic property:\n  - "
        + "\n  - ".join(sorted(set(bad)))
        + "\n\nThe replay fold MUST stay purely functional — same "
        "rationale as _chain.py."
    )
