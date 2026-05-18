#!/usr/bin/env bash
# Regenerate the minimal-ts/ fixture tree.
#
# Review-as-code (S7-01 AC-22 / Phase-1 Step-6 discipline). Idempotent;
# two consecutive bash regenerate.sh invocations produce a byte-identical
# tracked-files tree (verified locally before merge per S7-01 AC-30).
#
# This script intentionally does NOT invoke pnpm, npm, node-gyp, docker,
# or any package manager — none are in ALLOWED_BINARIES per 02-ADR-0001,
# and AC-31's tokenizer-based static check would (correctly) fail. The
# fixture's bytes are hand-authored and committed verbatim. This script
# is the placeholder for the eventual S7-03 golden-regeneration step
# that consumes this tree.
set -euo pipefail

cd "$(dirname "$0")"

# Ensure the closed-set tree skeleton exists. Idempotent.
mkdir -p src deploy/chart .github/workflows

echo "minimal-ts/ fixture: tree skeleton verified."
