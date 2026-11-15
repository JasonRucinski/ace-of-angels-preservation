"""The import rules of docs/restructure/PLAN.md section 2, rule 1; game-free.

Builds the import graph of aoa/ with the ast module (nested imports count)
and checks each edge against the layers:

- aoa.paths, aoa.cli and aoa.builds are the base every layer may use.
- formats imports nothing else in aoa.
- protocol and maps may import formats.
- client and host may import formats, protocol and maps, never each other.
- launchers sits on top of those.
- research, analysis, emulation, live and reel are leaves: nothing in client,
  host or launchers imports them.
- nothing in aoa imports archive/ or tests/.

Edges that break a rule today are listed in KNOWN with the audit finding
that covers them (docs/restructure/audits/); phase 2 removes them. The test
fails on a new violation and on a KNOWN entry that no longer occurs.

    python -I tools/test.py test_layering
"""
import ast
import unittest

from aoa.paths import ROOT

BASE = {"aoa", "aoa.paths", "aoa.cli", "aoa.builds"}
LEAVES = {"research", "analysis", "emulation", "live", "reel"}
MAY_IMPORT = {
    "formats": {"formats"},
    "protocol": {"formats", "protocol"},
    "maps": {"formats", "maps"},
    "client": {"formats", "protocol", "maps", "client"},
    "host": {"formats", "protocol", "maps", "host"},
    "launchers": {"formats", "protocol", "maps", "client", "host", "launchers"},
    **{leaf: {"formats", "protocol", "maps", "client", "host", "launchers"} | LEAVES for leaf in LEAVES},
}

# (importer, imported): why it is allowed for now. Remove an entry when phase 2 fixes it.
KNOWN = {
    # online_terrain holds both the client patch and the server's map registry (H12).
    ("aoa.host.dedicated", "aoa.client.patches.online_terrain"): "H12: map registry in a client patch",
    ("aoa.host.runtime", "aoa.client.patches.online_terrain"): "H12: map registry in a client patch",
    ("aoa.host.server", "aoa.client.patches.online_terrain"): "H12: map registry in a client patch",
    ("aoa.maps.make_map", "aoa.client.patches.online_terrain"): "H12: map registry in a client patch",
    ("aoa.maps.map_viewer", "aoa.client.patches.online_terrain"): "H12: map registry in a client patch",
    ("aoa.maps.navigation", "aoa.client.patches.online_terrain"): "H12: map registry in a client patch",
    # Audit scripts kept as libraries: the emulator for their CLIs, and the
    # server cycle through warp_routes (R4, H12).
    ("aoa.maps.arena1a_audit", "aoa.analysis.pe_util"): "R4: audit CLI in a library module",
    ("aoa.maps.turret_hierarchy", "aoa.analysis.pe_util"): "R4: audit CLI in a library module",
    ("aoa.maps.turret_hierarchy", "aoa.emulation.emu"): "R4: audit CLI in a library module",
    ("aoa.maps.warp_routes", "aoa.analysis.pe_util"): "R4: audit CLI in a library module",
    ("aoa.maps.warp_routes", "aoa.emulation.emu"): "R4: audit CLI in a library module",
    ("aoa.maps.warp_routes", "aoa.host.server"): "H12, R4: the server import cycle",
    ("aoa.maps.warp_routes", "aoa.protocol.motion"): "R4: audit CLI in a library module",
}


def module_name(path):
    return ".".join(path.relative_to(ROOT).with_suffix("").parts).removesuffix(".__init__")


def resolve(name):
    """The module a dotted import name refers to (a package attribute resolves to its package)."""
    while name:
        parts = name.split(".")
        if (ROOT.joinpath(*parts).with_suffix(".py")).is_file() or (ROOT.joinpath(*parts) / "__init__.py").is_file():
            return name
        name = name.rpartition(".")[0]
    return None


def imports(path):
    """Every module name of this repository that the file imports, nested imports included."""
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [f"{node.module}.{a.name}" for a in node.names]
        else:
            continue
        for name in names:
            if name.split(".")[0] in ("aoa", "archive", "tests"):
                target = resolve(name)
                if target:
                    found.add(target)
    return found


def layer(name):
    if name in BASE:
        return "base"
    parts = name.split(".")
    return parts[1] if parts[0] == "aoa" else parts[0]


def violations():
    found = {}
    for path in sorted((ROOT / "aoa").rglob("*.py")):
        importer = module_name(path)
        for target in sorted(imports(path)):
            source_layer, target_layer = layer(importer), layer(target)
            if target_layer == "base":
                continue
            if target_layer in ("archive", "tests"):
                found[(importer, target)] = f"aoa imports {target_layer}/"
            elif source_layer == "base":
                found[(importer, target)] = "the base imports a layer"
            elif target_layer not in MAY_IMPORT[source_layer]:
                found[(importer, target)] = f"{source_layer} may not import {target_layer}"
    return found


class LayeringTests(unittest.TestCase):
    def test_no_new_violations(self):
        new = {edge: rule for edge, rule in violations().items() if edge not in KNOWN}
        self.assertEqual(new, {}, "imports that break PLAN.md rule 1 (fix them, do not list them)")

    def test_known_violations_still_exist(self):
        gone = sorted(set(KNOWN) - set(violations()))
        self.assertEqual(gone, [], "fixed: remove these from KNOWN")

    def test_graph_is_not_empty(self):
        # Guards the import scan itself.
        server = imports(ROOT / "aoa/host/server.py")
        self.assertIn("aoa.host.runtime", server)
        self.assertIn("aoa.protocol.codec", server)


if __name__ == "__main__":
    unittest.main()
