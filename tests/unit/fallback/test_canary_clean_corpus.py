"""Phase-4 S2-03 AC-9 — clean payloads pass canary scan.

20+ benign payloads (CVE descriptions, package metadata blurbs, source
snippets, README excerpts) must return ``CanaryClean()``. At least one row
is a deliberate near-miss — a CVE description that benignly mentions
``instructions`` or quotes a security advisory *about* prompt injection —
so the test actively pressures pattern over-breadth instead of passing
trivially.

If a clean-corpus row fails, the offending pattern in
``INJECTION_PATTERNS`` is too broad — narrow the bytes or drop the row.
"""

from __future__ import annotations

from typing import Final

import pytest

from codegenie.fallback.fence.canary import CanaryGuard
from codegenie.fallback.fence.wrapper import CanaryClean
from codegenie.types.identifiers import HexNonce

_BENIGN_NONCE: Final[HexNonce] = HexNonce("0" * 32)


_CLEAN_PAYLOADS: Final[tuple[str, ...]] = (
    # --- CVE / advisory prose (benign mentions of security-sensitive terms) ---
    "CVE-2023-12345: Buffer overflow in libfoo when parsing crafted PDF files.",
    "CVE-2024-00001: lodash prototype pollution via _.merge in versions < 4.17.21.",
    "Advisory: an attacker could read arbitrary files via path traversal.",
    # Deliberate near-misses — these benignly mention "instructions" or
    # advisory text about prompt injection itself; they must not fire.
    "CVE description: the vulnerability allows attackers to bypass safety checks.",
    "Security advisory documents how to mitigate cross-site scripting flaws.",
    "Research paper: techniques for detecting injection patterns in user input.",
    "Background reading on prompt-injection defenses for LLM applications.",
    # --- package metadata blurbs ----
    "lodash is a modern JavaScript utility library delivering modularity and performance.",
    "express is a fast, unopinionated, minimalist web framework for Node.js.",
    "react: A JavaScript library for building user interfaces.",
    "Author: Jane Smith <jane@example.com>; License: MIT; Maintained: yes",
    # --- README excerpts -----
    "# my-project\n\nA Python tool for analysing JSON logs.\n\n## Usage\n\nRun the CLI to start.",
    "## Installation\n\n```\nnpm install my-package\n```\n\nThen import from your code.",
    "Contributing: please open an issue before submitting a pull request.",
    "## Testing\n\nWe use pytest. Run `make test` to execute the unit suite.",
    # --- source snippet excerpts (real code containing imports / functions) ---
    "import os\nimport sys\nfrom pathlib import Path\n\ndef main() -> int:\n    return 0",
    "function add(a, b) { return a + b; }",
    "class Foo:\n    def __init__(self, name: str) -> None:\n        self.name = name",
    "<?php\nfunction sanitize($input) { return htmlspecialchars($input); }\n?>",
    'package main\n\nimport "fmt"\n\nfunc main() { fmt.Println("hello") }',
    # --- transitive-dep / lockfile-like blurbs ----
    "Resolved dependency tree: 142 packages, 14 direct, 128 transitive.",
    "lodash@4.17.21 — direct dependency of express@4.18.2.",
    # --- sandbox stderr-style benign ----
    "test_foo.py::test_basic PASSED                              [ 50%]",
    "Build succeeded; 0 warnings; 0 errors; 12 files compiled.",
    # --- prior-attempt summary blurbs ----
    "Previous attempt: applied patch v1; sandbox run failed with exit code 1.",
)


def test_clean_corpus_has_at_least_twenty_rows() -> None:
    assert len(_CLEAN_PAYLOADS) >= 20


@pytest.mark.parametrize("payload", _CLEAN_PAYLOADS)
def test_clean_payload_scans_clean(payload: str) -> None:
    """No false positives on benign payloads — including deliberate near-misses."""
    result = CanaryGuard().scan(payload, _BENIGN_NONCE)
    assert result == CanaryClean(), f"benign payload {payload!r:80} unexpectedly fired: {result!r}"
