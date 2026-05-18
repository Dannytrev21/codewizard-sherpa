#!/usr/bin/env bash
# Regenerate the distroless-target/ fixture artifacts.
#
# Review-as-code (S7-01 AC-22 / Phase-1 Step-6 discipline). On success
# writes the resolved built-image content digest to built-image.digest
# (gitignored per AC-23) and tears the image down. Two consecutive runs
# produce the same tracked-files tree; the gitignored built-image.digest
# is out of scope for AC-30 byte-identity by design (docker may rebuild
# with subtly-different layer digests across runs).
#
# Exits non-zero with a clear message if docker is unavailable on the
# host. docker is the only binary this script invokes beyond shell
# coreutils, and it is in ALLOWED_BINARIES per 02-ADR-0001.
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  printf 'distroless-target/regenerate.sh: docker is not available on PATH.\n' 1>&2
  printf 'Install Docker Desktop or rootless docker and retry.\n' 1>&2
  exit 2
fi

IMAGE_TAG="distroless-target-fixture:latest"

docker build -t "${IMAGE_TAG}" .

# Capture the built image's sha256 content digest in the canonical
# shape ProbeContext.image_digest_resolver consumes (S7-01 AC-38):
# exactly one line matching ^sha256:[0-9a-f]{64}\n$.
docker inspect --format='{{.Id}}' "${IMAGE_TAG}" > built-image.digest

# Tear down the local image — fixtures are stateless across runs.
docker image rm "${IMAGE_TAG}"

echo "distroless-target/ fixture: image built, digest captured, image torn down."
