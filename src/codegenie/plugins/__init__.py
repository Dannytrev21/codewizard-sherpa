"""Phase-3 plugin-kernel namespace — registry, scope sum type, manifest, loader.

This package is the small stable kernel the plugin system is built on. Per
Phase-3 ADR-0010 §Decision §1 the kernel ships value types here and the
registry / resolver lands in S2-01 / S2-04. No eager re-exports — consumers
import the specific submodule (``codegenie.plugins.scope``) directly so the
kernel stays cold-start friendly and the import-linter contracts in S1-05
can pin the public surface explicitly.
"""
