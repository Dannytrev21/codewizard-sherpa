"""Output sanitizer + writer (ADR-0008, ADR-0010, ADR-0011).

Two-pass sanitizer (defense-in-depth secret-key rejection + path scrubbing)
and atomic writer (raw-then-yaml publish, symlink refusal, recursive chmod
discipline). The sanitizer's pass-1 imports
:data:`codegenie.coordinator.validator.SECRET_FIELD_PATTERN` **by identity** —
there is exactly one compiled regex for secret-shaped field names in the
entire ``src/codegenie/`` tree (ADR-0008 single-source rule).
"""
