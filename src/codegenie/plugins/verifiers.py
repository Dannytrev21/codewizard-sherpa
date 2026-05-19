"""Phase 3 S2-03 — :class:`PluginVerifier` Strategy seam.

ADR-0011 §Consequences line 78 explicitly pre-commits to Phase 11
substituting ``PLUGINS.lock`` SHA-256 tree-digest verification with
Sigstore signature verification at this exact interface — the loader
parameter, not the verification *algorithm*, is the seam.

Open/Closed + Plugin/Strategy: Phase 11 adds a ``SigstoreVerifier`` as a
new file plus DI substitution at the CLI entry point. Zero edits to
``codegenie.plugins.loader``. The cost of introducing the Protocol now
(one extra file, one extra parameter) buys the entire Phase 11 migration
path.

Honest-framing per ADR-0011: this module never uses the words "signature"
or "signing". The Phase-3 default is :class:`Sha256TreeDigestVerifier` —
an *integrity check* over the on-disk plugin tree. Phase 11's
``SigstoreVerifier`` lands the cryptographic-signature step at the same
``verify(plugin_dir, expected)`` interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from codegenie.result import Err, Ok, Result
from codegenie.types.identifiers import BlobDigest

__all__ = [
    "PluginVerifier",
    "Sha256TreeDigestVerifier",
    "VerificationError",
]


@dataclass(frozen=True)
class VerificationError:
    """The verifier rejected the plugin directory.

    Carries the ``expected`` digest from ``PLUGINS.lock`` plus the
    ``actual`` digest the verifier observed. For symlink-escape rejections
    the verifier reports ``actual = BlobDigest("0" * 64)`` — a structural
    placeholder, not a real digest. The loader translates this back into
    the :class:`codegenie.plugins.errors.SymlinkEscape` rejection variant
    (which carries the offending path) at its boundary.
    """

    plugin_dir: Path
    expected: BlobDigest
    actual: BlobDigest


@runtime_checkable
class PluginVerifier(Protocol):
    """Verify that the bytes on disk match the lockfile's attested digest.

    Phase 3 ships :class:`Sha256TreeDigestVerifier` as the default
    implementation. Phase 11 substitutes ``SigstoreVerifier`` via DI at
    the loader's ``verifier=`` parameter — see ADR-0011 §Consequences.
    """

    def verify(self, plugin_dir: Path, expected: BlobDigest) -> Result[None, VerificationError]:
        """Return ``Ok(None)`` if ``plugin_dir`` matches ``expected``,
        ``Err(VerificationError(...))`` otherwise.

        Implementations MUST be deterministic given identical filesystem
        contents and the same ``expected`` digest. Side-effects forbidden —
        the loader composes ``verify`` calls in fail-fast order across the
        whole plugin set BEFORE running any plugin's ``importlib`` step.
        """
        ...


_SYMLINK_ESCAPE_SENTINEL: BlobDigest = BlobDigest("0" * 64)


@dataclass(frozen=True)
class Sha256TreeDigestVerifier:
    """Phase-3 default verifier — SHA-256 tree-digest over the plugin tree.

    Composes :func:`codegenie.plugins.loader.compute_plugin_tree_digest`
    (which routes through the ``codegenie.hashing`` chokepoint per
    ADR-0001) with an equality check against the lockfile's attestation.

    The ``compute_plugin_tree_digest`` import is deferred to method-call
    time because ``codegenie.plugins.loader`` imports :class:`PluginVerifier`
    from this module at its top level; the lazy import breaks the cycle
    without touching either module's static-typing contract.
    """

    def verify(self, plugin_dir: Path, expected: BlobDigest) -> Result[None, VerificationError]:
        from codegenie.plugins.loader import compute_plugin_tree_digest

        digest_result = compute_plugin_tree_digest(plugin_dir)
        if isinstance(digest_result, Err):
            return Err(
                error=VerificationError(
                    plugin_dir=plugin_dir,
                    expected=expected,
                    actual=_SYMLINK_ESCAPE_SENTINEL,
                )
            )
        actual = digest_result.value
        if actual == expected:
            return Ok(value=None)
        return Err(error=VerificationError(plugin_dir=plugin_dir, expected=expected, actual=actual))
