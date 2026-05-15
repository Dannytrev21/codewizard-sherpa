"""S3-06 AC-8 / AC-9 / AC-10 — raw-artifact-budget truncation on
``NodeManifestProbe``.

**Status: BLOCKED on S3-05 follow-up** — see ``_attempts/S3-06.md`` for
the full analysis. The blocker has two load-bearing components and one
infrastructural gap; each is a separate follow-up:

1. **Probe does not emit raw artifacts.** ``NodeManifestProbe`` returns
   ``raw_artifacts=[]`` unconditionally (line 478 of
   ``node_manifest.py``). The S1-09 truncation policy only fires inside
   ``cli.py``'s raw-artifact-collection loop over
   ``output.raw_artifacts``; an empty list = inert policy. **Naïvely
   adding** ``raw_artifacts=[repo.root / selected]`` breaks the S3-06
   AC-7 catalog-invalidation test because ``declared_inputs_for`` uses
   :meth:`pathlib.Path.rglob` and the cli-side raw-artifact writer
   names files by basename — the cold-run write of
   ``.codegenie/context/raw/pnpm-lock.yaml`` then matches *every*
   subsequent probe's ``rglob("pnpm-lock.yaml")``, changing
   ``node_build_system``'s warm-run cache key. The dependency
   ordering is real: AC-8/9/10 cannot land until raw-artifact
   filenames are namespaced (e.g., ``<probe>.<basename>``) or
   ``declared_inputs_for`` filters out the ``.codegenie/`` output
   namespace. Either is in :data:`codegenie.cli` / :data:`codegenie.
   cache.keys`, not in S3-06's surgical scope.

2. **``os.fstat`` monkey-patch pattern is not applicable.** The story
   AC-8 prescribes ``monkeypatch.setattr(os, "fstat", ...)`` to
   simulate 30 MB without writing it. But the truncation policy reads
   the payload via ``Path.read_bytes()`` (``cli.py:466``) and judges
   size from ``len(payload)`` (``raw_truncation.py:88``) — neither
   reads ``os.fstat`` on the raw artifact. So the monkey-patch never
   intercepts. The pattern of record from S3-05 T-9 / S3-01/02/03 is
   for *parser-cap* tests (where ``input_snapshot._fingerprint_from_fd``
   does call ``os.fstat``), not the *raw-artifact-budget* path.

3. **Filename mismatch with story AC-9.** Story AC-9 reads
   ``.codegenie/context/raw/node_manifest.json``. The cli writer
   names raw artifacts by basename (``raw_path.name``) — once probe
   #1 is unblocked, the path becomes
   ``.codegenie/context/raw/pnpm-lock.yaml`` (or a future namespaced
   name). The story's filename presumes a writer-side rename pass
   that does not exist; landing this AC needs either a writer
   amendment or a story-text correction.

When the three blockers above are unblocked, the test below pins the
load-bearing intent of AC-8/9/10:

- exactly one ``probe.raw_artifact.truncated`` structlog event
  (``len(events) == 1``, not ``>= 1``);
- the truncated artifact is valid JSON containing
  ``{"__truncated_at_budget__": true, "original_bytes": N >= 30 MiB,
   "budget_bytes": 25 MiB, ...}`` per ``raw_truncation.Truncated``;
- the event payload mirrors the marker (probe == "node_manifest",
  ``original_bytes`` and ``budget_bytes`` byte-equal to the marker
  values).

The test is xfail-marked until the blockers land; xfail keeps the
test in CI so a future unblocking change flips it to an unexpected
pass that fails CI, prompting xfail removal. See
``_attempts/S3-06.md`` for the full audit trail.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(
    reason=(
        "S3-06 AC-8/9/10 BLOCKED on three load-bearing follow-ups: "
        "(1) NodeManifestProbe raw_artifact emission requires namespaced "
        "filenames or .codegenie/-aware declared_inputs_for, "
        "(2) os.fstat monkey-patch does not intercept Path.read_bytes() "
        "in the cli raw-artifact loop, "
        "(3) story-prescribed filename (node_manifest.json) does not match "
        "the writer's basename-derived naming. See _attempts/S3-06.md."
    ),
    strict=True,
)
def test_30mb_lockfile_truncates_at_25mb() -> None:
    """Placeholder pin — see module docstring for the blocker analysis."""
    raise AssertionError(
        "S3-06 AC-8/9/10 are not implementable inside S3-06's surgical "
        "scope. The module docstring documents the three blockers; this "
        "xfail keeps the gap visible in CI."
    )
