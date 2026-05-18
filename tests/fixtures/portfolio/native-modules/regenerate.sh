#!/usr/bin/env bash
# Regenerate the native-modules/ fixture tree.
#
# Review-as-code (S7-01 AC-22 / Phase-1 Step-6 discipline). Idempotent;
# two consecutive bash regenerate.sh invocations produce a byte-identical
# tracked-files tree (verified locally before merge per S7-01 AC-30).
#
# This script DOES NOT invoke pnpm, npm, or node-gyp. None are in
# ALLOWED_BINARIES (02-ADR-0001); AC-31's tokenizer-based static check
# fails loud if any of them appear. The C-extension dependency
# (bcrypt@5.1.0) is pinned via the hand-authored pnpm-lock.yaml bytes
# committed to this fixture (Phase-1 node_typescript_helm/ precedent).
#
# AC-16b — stale-output check: assert no build/Release/ directory
# exists in the tree before exiting. If a contributor accidentally
# compiled the native module locally despite ignore-scripts=true in
# .npmrc, fail loud so the artifact is removed before commit.
set -euo pipefail

cd "$(dirname "$0")"

# Idempotent skeleton-verify.
mkdir -p src

if [ -e build/Release ]; then
  printf 'native-modules/regenerate.sh: build/Release/ exists in fixture tree.\n' 1>&2
  printf 'A local node-gyp rebuild appears to have run despite ignore-scripts=true.\n' 1>&2
  printf 'Remove build/ before committing to keep the closed-set test passing.\n' 1>&2
  exit 1
fi

echo "native-modules/ fixture: tree skeleton verified; no stale build/Release/."
