#!/usr/bin/env bash
# Regenerates the stale-scip fixture. See README.md.
# MUST keep HEAD ahead of the parent commit by >= 1.
set -euo pipefail
cd "$(dirname "$0")"
rm -rf .git .codegenie

git init -q -b main
git config user.email "fixture@codewizard.local"
git config user.name  "Fixture Bot"

# v0 — content of package.json is the seed commit; LAST_INDEXED will point here.
git add package.json && git commit -q -m "v0 — seeded last_indexed_commit"
PARENT_COMMIT=$(git rev-parse HEAD)

# v1 — HEAD moves forward.
git add main.ts && git commit -q -m "v1 — HEAD moves forward"

# Materialize the runtime sibling-slice from the tracked template.
mkdir -p .codegenie/context/raw
sed "s|PARENT_COMMIT|${PARENT_COMMIT}|g" \
  _seed/scip-slice.template.json > .codegenie/context/raw/scip.json
cp _seed/scip-index.scip.placeholder .codegenie/context/raw/scip-index.scip

# Guard — env-overrideable so `test_regenerate_sh_guard` can force the failing branch.
# Default: the parent of HEAD (which by construction is NOT HEAD itself).
LAST_INDEXED="${LAST_INDEXED:-$(git rev-parse HEAD~1)}"
if [[ "$LAST_INDEXED" == "$(git rev-parse HEAD)" ]]; then
  echo "ERROR: regenerate.sh refuses to set last_indexed_commit == HEAD" >&2
  echo "       This fixture must have HEAD ahead by >= 1. See README.md." >&2
  exit 1
fi
echo "stale-scip fixture regenerated. last_indexed=$PARENT_COMMIT head=$(git rev-parse HEAD)"
