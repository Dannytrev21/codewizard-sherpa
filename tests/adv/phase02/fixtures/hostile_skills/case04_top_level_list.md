---
- not
- a
- mapping
---
Case 4 — top-level YAML is a list, not a mapping. `safe_yaml.load` raises
MalformedYAMLError; loader surfaces `unsafe_yaml`.
