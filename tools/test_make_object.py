"""New objects: glTF reading, winding, triplanar UVs, Gob/Sco writing, archive append.

Game-free except the template and Bennu checks, which need the user's 2.9.2
client (and requirements.txt for the archive key) or the downloaded model.
"""
import hashlib
import json
import math
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aoacrypt
import aoapack
import gob2obj
import make_object

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "game/2.9.2"
SPEC = ROOT / "config/objects/bennu.json"
BENNU = ROOT / "builds/bennu-nasa/bennu.glb"
try:
    import capstone  # noqa: F401  (pe_util, for the archive key)
    HAVE_ANALYSIS = True
except ImportError:
    HAVE_ANALYSIS = False
HAVE_GAME = HAVE_ANALYSIS and (GAME / "AOAOBJECTS.ODB").exists()

# Octahedron of radius 2 centred at (1, 0, 0), wound inward with inward normals.
OCTA = [(3, 0, 0), (-1, 0, 0), (1, 2, 0), (1, -2, 0), (1, 0, 2), (1, 0, -2)]
OCTA_TRIS = [(0, 2, 4), (2, 1, 4), (1, 3, 4), (3, 0, 4), (2, 0, 5), (1, 2, 5), (3, 1, 5), (0, 3, 5)]


def glb(positions, triangles, normals=None):
    """A minimal binary glTF with one primitive."""
    blob = b"".join(struct.pack("<3f", *p) for p in positions)
    views = [{"buffer": 0, "byteOffset": 0, "byteLength": len(blob)}]
    accessors = [{"bufferView": 0, "componentType": 5126, "count": len(positions), "type": "VEC3"}]
    attributes = {"POSITION": 0}
    if normals:
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": 12 * len(normals)})
        blob += b"".join(struct.pack("<3f", *n) for n in normals)
        accessors.append({"bufferView": 1, "componentType": 5126, "count": len(normals), "type": "VEC3"})
        attributes["NORMAL"] = 1
    index = b"".join(struct.pack("<3H", *t) for t in triangles)
    views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(index)})
    accessors.append({"bufferView": len(views) - 1, "componentType": 5123, "count": 3 * len(triangles), "type": "SCALAR"})
    blob += index + b"\0" * (-len(index) % 4)
    doc = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(blob)}], "bufferViews": views,
           "accessors": accessors, "meshes": [{"primitives": [{"attributes": attributes, "indices": len(accessors) - 1}]}]}
    text = json.dumps(doc).encode()
    text += b" " * (-len(text) % 4)
    body = struct.pack("<I4s", len(text), b"JSON") + text + struct.pack("<I4s", len(blob), b"BIN\0") + blob
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


def outward(verts, faces):
    count = 0
    for a, b, c in faces:
        n = make_object._cross(make_object._sub(verts[b][:3], verts[a][:3]), make_object._sub(verts[c][:3], verts[a][:3]))
        count += make_object._dot(n, [verts[a][k] + verts[b][k] + verts[c][k] for k in range(3)]) > 0
    return count


class GeometryTests(unittest.TestCase):
    def test_glb_and_winding(self):
        inward = [make_object._unit((1 - x, -y, -z)) for x, y, z in OCTA]
        pos, nrm, tris = make_object.read_glb(glb(OCTA, OCTA_TRIS, inward))
        self.assertEqual((len(pos), len(tris)), (6, 8))
        self.assertAlmostEqual(nrm[0][0], -1)
        pos, nrm, tris, flipped = make_object.prepare(pos, tris, 1000.0)
        # glTF z is negated; centred and scaled to the radius.
        self.assertAlmostEqual(max(math.dist(p, (0, 0, 0)) for p in pos), 1000.0)
        self.assertEqual([round(v) for v in pos[4]], [0, 0, -1000])
        verts, faces = make_object.triplanar(pos, nrm, tris, 500.0)
        self.assertEqual(outward(verts, faces), 8)
        self.assertTrue(all(make_object._dot(v[5:8], v[:3]) > 0 for v in verts))
        # The same mesh wound the other way needs no flip.
        _, _, _, again = make_object.prepare(OCTA, [(a, c, b) for a, b, c in OCTA_TRIS], 1000.0)
        self.assertNotEqual(flipped, again)

    def test_triplanar_uvs_and_mesh_block(self):
        pos, nrm, tris, _ = make_object.prepare(OCTA, OCTA_TRIS, 1000.0)
        verts, faces = make_object.triplanar(pos, nrm, tris, 250.0)
        for x, y, z, u, v, *_ in verts:
            self.assertIn((round(u * 250, 3), round(v * 250, 3)),
                          {(round(z, 3), round(y, 3)), (round(x, 3), round(z, 3)), (round(x, 3), round(y, 3))})
        block = make_object.mesh_block(verts, faces)
        mesh = gob2obj.try_mesh(block, 0)
        self.assertEqual((len(mesh["verts"]), len(mesh["faces"]), mesh["end"]), (len(verts), len(faces), len(block)))
        at = 8 + 64 * len(verts)
        a, b, c, flags = struct.unpack_from("<4H", block, at)
        self.assertEqual(flags, make_object.FACE_FLAGS)
        lengths = struct.unpack_from("<3f", block, at + 24)
        for got, (i, j) in zip(lengths, ((a, b), (b, c), (c, a))):
            self.assertAlmostEqual(got, math.dist(verts[i][:3], verts[j][:3]), places=2)
        self.assertEqual(struct.unpack_from("<II", block, 8 + 56), (0xFFFFFFFF, 2))

    def test_spec_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            for bad in ({"object": "Has space", "model": "M"}, {"object": "O", "model": "x" * 24}):
                path = Path(tmp) / "s.json"
                path.write_text(json.dumps({**bad, "texture": "t.tga", "radius": 1, "tile": 1}))
                with self.assertRaises(ValueError):
                    make_object.load_spec(path)

    def test_refuses_main_client(self):
        with self.assertRaises(SystemExit):
            make_object.install(make_object.load_spec(SPEC), BENNU, GAME)
        with self.assertRaises(SystemExit):
            make_object.undo(GAME)


class ArchiveAppendTests(unittest.TestCase):
    """A synthetic archive: any 256-byte keys work for the cipher round trip."""

    def archive(self, key0, key, entries):
        directory, body, offset = bytearray(), [], 260 + 280 * len(entries)
        for name, data in entries:
            raw = aoacrypt.encrypt(aoapack.compress(data, with_crc=True), key)
            directory += name.encode().ljust(256, b"\0") + struct.pack("<QIIII", offset, len(raw), 0, 1, 0)
            body.append(raw)
            offset += len(raw)
        head = aoacrypt.encrypt(struct.pack("<HH", len(entries), 0x0402), key)
        return aoacrypt.encrypt(key, key0) + head + aoacrypt.encrypt(bytes(directory), key) + b"".join(body)

    def test_append(self):
        key0, key = bytes(range(256)), bytes((7 * i + 3) % 256 for i in range(256))
        original = [("DataBaseHeader", b"Odb\0"), ("A.Sco", b"sco" * 50), ("A.Gob", bytes(range(200)) * 3)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.odb"
            path.write_bytes(self.archive(key0, key, original))
            self.assertEqual(aoapack.rebuild(path, key0, {}), path.read_bytes())
            out = aoapack.rebuild(path, key0, {}, {"New.Sco": b"n" * 99, "New1.Gob": b"g" * 5000})
            d, k, version, entries = aoapack.read_archive_bytes(out, key0)
            self.assertEqual(version, 0x0402)
            self.assertEqual([e["name"] for e in entries], ["DataBaseHeader", "A.Sco", "A.Gob", "New.Sco", "New1.Gob"])
            got = [aoapack.entry_bytes(d, k, key0, e)[0] for e in entries]
            self.assertEqual(got, [b for _, b in original] + [b"n" * 99, b"g" * 5000])
            for bad in ({"a.sco": b"x"}, {"N.Sco": b"x", "n.sco": b"y"}):
                with self.assertRaises(KeyError):
                    aoapack.rebuild(path, key0, {}, bad)


@unittest.skipUnless(HAVE_GAME, "requires the user's 2.9.2 client and requirements.txt")
class TemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        key0 = aoapack.builtin_key(GAME / "AOACLIENT.EXE")
        cls.templates = make_object.templates_from(GAME / "AOAOBJECTS.ODB", aoapack, key0)

    def test_gob_and_sco(self):
        pos, nrm, tris, _ = make_object.prepare(OCTA, OCTA_TRIS, 5000.0)
        verts, faces = make_object.triplanar(pos, nrm, tris, 1000.0)
        template = self.templates[make_object.TEMPLATE_GOB]
        gob = make_object.write_gob(template, "Octa1", "astr4_a.tga", verts, faces)
        strings = [t for _, _, t in gob2obj.strings(gob)]
        self.assertEqual(strings[0], "Octa1")
        self.assertEqual(strings.count("astr4_a.tga"), 2)
        self.assertNotIn("astr3.tga", strings)
        self.assertEqual(struct.unpack_from("<I", gob, 0x0C)[0], 162 + 5)
        after = gob2obj.strings(gob)[0][1]
        lo, hi = [min(v[k] for v in verts) for k in range(3)], [max(v[k] for v in verts) for k in range(3)]
        for got, want in zip(struct.unpack_from("<6f", gob, after), lo + hi):
            self.assertAlmostEqual(got, want, places=2)
        (node, node_after), = make_object._strings(gob, make_object.TEMPLATE_NODE)
        self.assertEqual(gob[node_after:node_after + 24], gob[after:after + 24])
        self.assertEqual(gob[node_after + 0x74:node_after + 0x80], bytes(12))
        mesh = gob2obj.parse(gob)[0]
        self.assertEqual(len(gob) - mesh["end"], len(template) - gob2obj.parse(template)[0]["end"] + 2)
        sco = make_object.write_sco(self.templates[make_object.TEMPLATE_SCO], "Octa", "Octa1")
        template_sco = self.templates[make_object.TEMPLATE_SCO]
        self.assertEqual(len(sco), len(template_sco) - len("Astr-C") + 4 - len("Astr-C_mip") + 5)
        self.assertEqual(sco[-200:], template_sco[-200:])

    @unittest.skipUnless(BENNU.exists(), "requires builds/bennu-nasa/bennu.glb")
    def test_bennu(self):
        spec = make_object.load_spec(SPEC)
        self.assertEqual(hashlib.sha256(BENNU.read_bytes()).hexdigest(), spec["source"]["sha256"])
        entries, stats = make_object.build(spec, BENNU, self.templates)
        self.assertEqual(sorted(entries), ["Bennu.Sco", "Bennu1.Gob"])
        self.assertEqual((stats["faces"], stats["radius"], stats["flipped"]), (18240, 60000, True))
        mesh = gob2obj.parse(entries["Bennu1.Gob"])[0]
        verts = mesh["verts"]
        self.assertEqual(outward(verts, [f[:3] for f in mesh["faces"]]), len(mesh["faces"]))
        self.assertEqual(sum(v[0] * v[5] + v[1] * v[6] + v[2] * v[7] > 0 for v in verts), len(verts))


if __name__ == "__main__":
    unittest.main()
