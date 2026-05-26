"""Phase 6 S2-01 AC-12 — checkpoint adapters must import the canonical sanitizer.

AST fence: walks both checkpoint adapter modules and asserts that

1. ``codegenie.output.sanitizer.sanitize_for_persistence`` is imported
   (the canonical regex set has a single declaration site);
2. No local ``re.compile`` / ``re.fullmatch`` / ``re.search`` /
   ``regex.`` call exists — forking the regex set is the Phase-9
   critique-report failure mode.

Plus a runtime property: an event carrying a secret-shaped string in
its ``triggering_outcome`` is persisted with the redaction marker, not
the raw secret.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from codegenie.types.identifiers import (
    BlobDigest,
    ChainHead,
    TransitionId,
    WorkflowId,
)
from codegenie.workflows import (
    _replay,
    in_memory_checkpoints,
    replay,
    sqlite_checkpoints,
)
from codegenie.workflows.sqlite_checkpoints import SqliteCheckpointStore
from codegenie.workflows.vuln_ledger import TransitionEvent

_ADAPTER_MODULES = (in_memory_checkpoints, sqlite_checkpoints)
_REPLAY_MODULES = (replay, _replay)


def _walk_imports(module: object) -> set[tuple[str, str]]:
    """Return the set of ``(module_path, imported_name)`` pairs."""
    tree = ast.parse(inspect.getsource(module))
    pairs: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                pairs.add((mod, alias.name))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                pairs.add((alias.name, alias.name))
    return pairs


def test_ac12_both_adapters_import_canonical_sanitizer() -> None:
    for module in _ADAPTER_MODULES:
        pairs = _walk_imports(module)
        assert ("codegenie.output.sanitizer", "sanitize_for_persistence") in pairs, (
            f"{module.__name__} must import sanitize_for_persistence from "
            "codegenie.output.sanitizer — the regex-set fork failure mode is "
            "the Phase-9 critique report finding."
        )


def test_ac12_no_local_regex_in_checkpoint_adapters() -> None:
    """Neither adapter imports ``re`` / ``regex`` directly."""
    for module in _ADAPTER_MODULES:
        pairs = _walk_imports(module)
        for mod, name in pairs:
            assert not mod.startswith("re"), (
                f"{module.__name__} imports {mod!r}; the canonical regex set "
                "lives in codegenie.output.sanitizer. Route through "
                "sanitize_for_persistence."
            )
            assert not mod.startswith("regex"), (
                f"{module.__name__} imports {mod!r} — third-party regex fork "
                "is forbidden; use sanitize_for_persistence."
            )
            assert name != "re", f"{module.__name__} imports the 're' module directly."


def test_s202_no_local_regex_in_replay_modules() -> None:
    """Phase-6 S2-02 AC-12 — verifier modules MUST NOT fork the regex set.

    Defends against an executor "improving" the verifier with ad-hoc
    regex parsing of persisted bytes (which would re-introduce
    primitive-obsession over the typed ``TransitionEvent`` shape).
    """
    for module in _REPLAY_MODULES:
        pairs = _walk_imports(module)
        for mod, name in pairs:
            assert not mod.startswith("re"), (
                f"{module.__name__} imports {mod!r}; canonical regex set lives in "
                "codegenie.output.sanitizer (S2-02 AC-12)."
            )
            assert not mod.startswith("regex"), (
                f"{module.__name__} imports {mod!r} — third-party regex fork is forbidden."
            )
            assert name != "re", f"{module.__name__} imports the 're' module directly."


def test_ac12_secret_shape_string_is_redacted_on_persist(tmp_path: Path) -> None:
    """A secret-shaped string in ``triggering_outcome`` is redacted on write."""
    secret = "AKIA" + "A" * 16  # canonical AWS access key shape
    event = TransitionEvent(
        transition_id=TransitionId("01HZZZZZZZZZZZZZZAC012A001"),
        prior_state_id="needs_plan",
        next_state_id="plan_ready",
        triggering_outcome={"leaked": secret},
        evidence_digest=BlobDigest("blake3:" + "b" * 64),
        chain_head=ChainHead("0" * 64),
        workflow_id=WorkflowId("01HZZZZZZZZZZZZZZAC012WF01"),
    )
    store = SqliteCheckpointStore(tmp_path)
    try:
        store.append(event)
        # Re-read what landed on disk
        events = list(store.read_all_for_workflow(WorkflowId("01HZZZZZZZZZZZZZZAC012WF01")))
        assert len(events) == 1
        persisted_payload = events[0].model_dump_json()
        assert secret not in persisted_payload, (
            "Secret-shaped string persisted as cleartext — canonical sanitizer not invoked."
        )
        assert "REDACTED" in persisted_payload
    finally:
        store.close()
