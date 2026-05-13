"""Coordinator package — internal harness boundary (ADR-0010).

Intentionally empty. Submodules (e.g. :mod:`codegenie.coordinator.validator`)
are lazy-imported from the CLI entry point so ``codegenie --help`` does not
pay Pydantic's import cost. ``_ProbeOutputValidator`` is module-private and
must NOT be re-exported here.
"""
