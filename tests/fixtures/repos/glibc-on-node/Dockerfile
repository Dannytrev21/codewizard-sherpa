# Phase-4 S7-05 — `glibc-on-node` fixture (vuln-provenance / ProvenanceGate refuse).
#
# This fixture exists to anchor the ProvenanceGate's "refuse non-app-layer CVE"
# path (ADR-04-0012). The CVE listed in tests/fixtures/phase4_portfolio.py
# (CVE-2023-4911, "Looney Tunables") is a glibc vulnerability — it lives in
# the BASE IMAGE (debian glibc), not in any npm dependency this app pulls in.
#
# The classification assertion is S7-03's job (vuln_provenance adapter); this
# fixture only provides the structural artifacts the adapter reads:
#
#   * a Dockerfile pinning a Node base image
#   * a minimal package.json so the project is npm-loadable
#
# Adapter responsibility: Read the FROM line, resolve the base image's
# provenance, classify CVE-2023-4911 as BaseImage → refuse-set → tier-0
# refuse → ProvenanceGate.classify(...) returns BaseImage.

FROM node:20-bullseye

WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY . .
CMD ["node", "index.js"]
