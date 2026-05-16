"""``codegenie.grammars`` — typed boundary for vendored tree-sitter grammars.

Phase 2 vendors tree-sitter grammar binaries (``.so`` / ``.dylib``) under
``tools/grammars/`` and pins their content hashes in ``tools/grammars.lock``.
This package exposes the typed loader/verifier (:mod:`codegenie.grammars.lock`)
both this story's tests and S4-04's ``TreeSitterImportGraphProbe`` import to
refuse a tampered binary at load time (supply-chain defense per phase-arch
row 10; 02-ADR-0002).
"""

__all__: list[str] = []
