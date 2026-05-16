#!/usr/bin/env bash
# Regenerate ``tools/grammars.lock`` from the BLAKE3 hashes of the vendored
# grammar binaries under ``tools/grammars/``.
#
# Idempotent: a second invocation with unchanged binaries produces a
# byte-identical lock file. Refuses (exit 1) if any binary referenced by an
# existing lock entry is missing.
#
# Does NOT download grammars — vendoring is a PR-reviewable step.
# See ``tools/grammars/README.md`` for the vendoring protocol.
#
# Sources:
# - docs/phases/02-context-gather-layers-b-g/stories/S4-03-scip-index-probe.md AC-11.
# - docs/phases/02-context-gather-layers-b-g/ADRs/0002-tree-sitter-grammars-phase-2-amendment.md
#   §Consequences ("Grammar regeneration is a PR with a binary diff").

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCK_FILE="${REPO_ROOT}/tools/grammars.lock"
GRAMMARS_DIR="${REPO_ROOT}/tools/grammars"

if [[ ! -d "${GRAMMARS_DIR}" ]]; then
  echo "ERROR: ${GRAMMARS_DIR} does not exist" >&2
  exit 1
fi

# Python is the BLAKE3 chokepoint per ADR-0001 (no separate ``b3sum``
# binary in the repo's runtime closure). The venv interpreter is the
# canonical one; fall back to the system ``python3`` for developer use.
if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  PYTHON="${REPO_ROOT}/.venv/bin/python"
else
  PYTHON="$(command -v python3)"
fi

if [[ -z "${PYTHON}" ]]; then
  echo "ERROR: python3 not found on PATH" >&2
  exit 1
fi

# Refuse to run if a lock entry references a missing binary — failing loud
# is preferable to silently dropping a pin.
if [[ -f "${LOCK_FILE}" ]]; then
  missing="$("${PYTHON}" - "${LOCK_FILE}" "${REPO_ROOT}" <<'PY'
import sys
from pathlib import Path
import yaml

lock_path = Path(sys.argv[1])
repo_root = Path(sys.argv[2])
payload = yaml.safe_load(lock_path.read_text(encoding="utf-8")) or {}
missing = []
for pin in payload.get("grammars", []) or []:
    fp = repo_root / str(pin.get("file", ""))
    if not fp.is_file():
        missing.append(str(fp))
print("\n".join(missing))
PY
)"
  if [[ -n "${missing}" ]]; then
    echo "ERROR: missing vendored binaries referenced by ${LOCK_FILE}:" >&2
    echo "${missing}" >&2
    exit 1
  fi
fi

"${PYTHON}" - "${REPO_ROOT}" "${LOCK_FILE}" "${GRAMMARS_DIR}" <<'PY'
import sys
from pathlib import Path

import yaml
from blake3 import blake3

repo_root = Path(sys.argv[1])
lock_path = Path(sys.argv[2])
grammars_dir = Path(sys.argv[3])

# Preserve language→version mapping from the existing lock file (if any) so
# regenerating only updates the blake3 — the upstream version pin is a
# manual reviewer concern.
prior_versions: dict[str, str] = {}
if lock_path.is_file():
    payload = yaml.safe_load(lock_path.read_text(encoding="utf-8")) or {}
    for pin in payload.get("grammars", []) or []:
        lang = str(pin.get("language", "")).strip()
        ver = str(pin.get("version", "")).strip()
        if lang and ver:
            prior_versions[lang] = ver

entries: list[dict[str, object]] = []
for so_path in sorted(grammars_dir.glob("*.so")):
    language = so_path.stem
    version = prior_versions.get(language, "0.0.0")
    digest = blake3(so_path.read_bytes()).hexdigest()
    entries.append(
        {
            "language": language,
            "version": version,
            "file": str(so_path.relative_to(repo_root)),
            "blake3": digest,
        }
    )

# Manual YAML rendering for byte-stable idempotency — yaml.safe_dump's
# default flow style / key ordering is not guaranteed across versions.
lines = ["schema_version: 1", "grammars:"]
for entry in entries:
    lines.append(f"  - language: {entry['language']}")
    lines.append(f'    version: "{entry["version"]}"')
    lines.append(f"    file: {entry['file']}")
    lines.append(f"    blake3: {entry['blake3']}")
lock_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"wrote {lock_path} ({len(entries)} grammar(s))")
PY
