from __future__ import annotations

import ast
import json
from pathlib import Path

from codegenie.probes.registry import default_registry

ROOT = Path(__file__).resolve().parents[2]
PROBES_DIR = ROOT / "src" / "codegenie" / "probes"
PROBES_INIT = PROBES_DIR / "__init__.py"
SCHEMAS_DIR = ROOT / "src" / "codegenie" / "schema" / "probes"
ENVELOPE = ROOT / "src" / "codegenie" / "schema" / "repo_context.schema.json"
_ENVELOPE_ALIASES = {
    "external_docs.schema.json": "external_docs",
    "skills_index.schema.json": "skills_index",
}


def test_every_registered_probe_module_is_explicitly_imported() -> None:
    imported_modules = _imported_probe_modules()
    discovered_modules = {
        _module_name(path) for path in PROBES_DIR.rglob("*.py") if _defines_register_probe(path)
    }

    assert discovered_modules <= imported_modules


def test_every_subschema_on_disk_is_wired_into_envelope() -> None:
    envelope = json.loads(ENVELOPE.read_text())
    properties = envelope["properties"]["probes"]["properties"]
    wired_refs = {name: payload["$ref"] for name, payload in properties.items()}

    covered_probe_names = set(wired_refs)
    for path in SCHEMAS_DIR.rglob("*.schema.json"):
        schema = json.loads(path.read_text())
        probe_name = path.stem.replace(".schema", "")
        if schema["$id"] in wired_refs.values():
            covered_probe_names.discard(probe_name)
            continue
        assert _ENVELOPE_ALIASES.get(path.name) == probe_name, (
            f"{path} is neither envelope-wired nor an explicit alias"
        )

    assert not covered_probe_names, f"envelope refs without on-disk schema: {covered_probe_names}"


def test_sbom_and_cve_are_live_default_probes() -> None:
    live = {probe.name for probe in default_registry.all_probes()}

    assert {"sbom", "cve"} <= live


def _defines_register_probe(path: Path) -> bool:
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id == "register_probe":
                return True
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Name)
                and decorator.func.id == "register_probe"
            ):
                return True
    return False


def _module_name(path: Path) -> str:
    rel = path.relative_to(PROBES_DIR).with_suffix("")
    return ".".join(("codegenie", "probes", *rel.parts))


def _imported_probe_modules() -> set[str]:
    tree = ast.parse(PROBES_INIT.read_text())
    imported: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        if node.module == "codegenie.probes":
            imported.update(f"codegenie.probes.{alias.name}" for alias in node.names)
        elif node.module.startswith("codegenie.probes."):
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    return imported
