# repo-root sitecustomize.py — installed at interpreter start per PEP 370 / site.py.
#
# Phase-4 S3-03: install the process-wide :class:`EgressGuard` socket wrapper
# before any user code runs. This is the *belt* layer that catches transitive
# deps silently dialing unexpected hosts (the *suspenders* are the explicit
# ``egress_guard.pinned_to(...)`` envelope around every Anthropic SDK call
# inside :class:`AnthropicLeafAdapter`).
#
# The ``try/except ImportError`` is the ONLY acceptable swallow — it covers
# the "codegenie not on path" case (a contributor's tox env without
# ``pip install -e .``). Any other exception during install (including an
# :class:`EgressViolation` raised by a buggy implementation) propagates so
# the operator sees the failure.

try:
    from codegenie.fallback.leaf.egress_guard import EgressGuard

    EgressGuard.install()
except ImportError:
    pass
