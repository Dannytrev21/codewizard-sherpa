// Phase-4 S7-05 vuln-provenance fixture — minimal Express app.
// The interesting thing about this fixture is its Dockerfile (FROM node:20-bullseye),
// not its source. The ProvenanceGate (ADR-04-0012) must classify glibc CVEs as
// BaseImage and refuse to dispatch the LLM fallback tier.

const express = require("express");
const app = express();

app.get("/", (req, res) => {
  res.send("Phase-4 S7-05 fixture: glibc-on-node");
});

app.listen(process.env.PORT || 3000);
