"""Positive control mypy --strict fixture for S3-03 AC-2b.

Proves the fixture-mypy harness is wired correctly: a ``RedactedSlice``
built via the only public path (:func:`redact_secrets`) clean-passes
``python -m mypy --strict``. Without this control AC-2 could pass
spuriously on a broken mypy invocation.
"""

from __future__ import annotations

from pathlib import Path

from codegenie.output.sanitizer import redact_secrets
from codegenie.output.writer import Writer
from codegenie.types.identifiers import ProbeId

redacted, _findings = redact_secrets({}, ProbeId("__envelope__"))
Writer().write(redacted, [], Path("/tmp"))
