"""``codegenie.probes`` — frozen probe contract surface (ADR-0007).

This package's public shape — :mod:`codegenie.probes.base` — is locked
byte-for-byte to ``docs/localv2.md §4`` and pinned by
``tests/unit/test_probe_contract.py``. Adding new probes is *extension by
addition*; editing the contract requires the ADR-amendment workflow in
``templates/adr-amendment.md``.

Intentionally empty otherwise — no ``importlib.metadata`` scan, no
side-effecting registration. The registry lands in S2-05.
"""
