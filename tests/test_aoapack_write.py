"""Archive rebuild round trip against the user's original 2.9.2 archives."""
import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aoacrypt
import aoapack

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / 'game/2.9.2'
KEY_CLIENT = ROOT / 'work/2.7.1/members/15_AOACLIENT.EXE'
MANIFEST = json.loads((ROOT / 'config/client-2.9.2.json').read_text(encoding='utf-8'))['required']
ARCHIVES = ('AOAOBJECTS.ODB', 'DATA.AOA', 'FX.AOA', 'HUD.AOA', 'IMAGES.AOA',
            'SCENARIOS.AOA', 'SCRIPTS.AOA', 'TEXTURES.AOA')


def original(name):
    """The pinned original archive, or its recorded backup if a pack is installed."""
    for path in (GAME / (name + '.before-texture-pack'), GAME / name):
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == MANIFEST[name]['sha256']:
            return path
    raise unittest.SkipTest(f'original {name} unavailable')


class ArchiveWriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key0 = aoapack.builtin_key(KEY_CLIENT)

    def test_identity_rebuild_is_byte_exact(self):
        for name in ARCHIVES:
            with self.subTest(archive=name):
                path = original(name)
                self.assertEqual(aoapack.rebuild(path, self.key0, {}), path.read_bytes())

    def test_codec_reproduces_shipped_entries(self):
        # Every DATA entry plus the first TEXTURES entries: recompression of
        # the decoded payload equals the stored (decrypted) bytes exactly.
        for name, limit in (('DATA.AOA', None), ('TEXTURES.AOA', 12)):
            d, key, _, entries = aoapack.read_archive(original(name), self.key0)
            for e in entries[:limit]:
                with self.subTest(archive=name, entry=e['name']):
                    stored = aoacrypt.decrypt(d[e['offset']:e['offset'] + e['size']], key)
                    data, _ = aoapack.decompress(stored)
                    self.assertEqual(aoapack.compress(data, with_crc=True), stored)

    def test_replacement_round_trip_and_neighbours_untouched(self):
        path = original('DATA.AOA')
        d, key, version, entries = aoapack.read_archive(path, self.key0)
        target = entries[3]
        old, _ = aoapack.entry_bytes(d, key, self.key0, target)
        new = old[:18] + bytes(range(256)) * 7 + old[18:] + b'grown'
        out = aoapack.rebuild(path, self.key0, {target['name'].upper(): new})
        self.assertEqual(out[:260], d[:260])  # key and header unchanged
        d2, key2, version2, entries2 = aoapack.read_archive_bytes(out, self.key0)
        self.assertEqual((key2, version2, len(entries2)), (key, version, len(entries)))
        for a, b in zip(entries, entries2):
            self.assertEqual((a['name'], a['compress_sel'], a['cipher_mode']),
                             (b['name'], b['compress_sel'], b['cipher_mode']))
            data, info = aoapack.entry_bytes(d2, key2, self.key0, b)
            self.assertTrue(info['crc_ok'])
            if a is target:
                self.assertEqual(data, new)
            else:
                self.assertEqual(d2[b['offset']:b['offset'] + b['size']], d[a['offset']:a['offset'] + a['size']])
        end = max(e['offset'] + e['size'] for e in entries2)
        self.assertEqual(end, len(out))
        self.assertEqual(sorted(e['offset'] for e in entries2), [e['offset'] for e in entries2])

    def test_texture_pack_install_verify_and_exact_undo(self):
        import shutil
        import struct
        import tempfile
        import texture_pack

        def enlarged(archive):
            d, key, _, entries = aoapack.read_archive(original(archive), self.key0)
            e = next(x for x in entries if x['name'].lower().endswith('.tga') and x['size'] < 50000)
            old, _ = aoapack.entry_bytes(d, key, self.key0, e)
            width, height = struct.unpack_from('<HH', old, 12)
            header = bytearray(old[:18])
            struct.pack_into('<HH', header, 12, width * 2, height * 2)
            pixels = bytes(range(256)) * (width * height * 12 // 256 + 1)
            return e, bytes(header) + pixels[:width * height * 4 * old[16] // 8]

        (tex, tex_tga), (dat, dat_tga) = enlarged('TEXTURES.AOA'), enlarged('DATA.AOA')
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            for name in texture_pack.ARCHIVES:
                shutil.copyfile(original(name), folder / name)
            shutil.copyfile(GAME / 'AOACLIENT.EXE.orig', folder / 'AOACLIENT.EXE')  # archive key
            (folder / 'a.tga').write_bytes(tex_tga)
            (folder / 'b.tga').write_bytes(dat_tga)
            pack = {tex['name'].upper(): folder / 'a.tga', 'data.aoa:' + dat['name']: folder / 'b.tga'}
            record = texture_pack.install(folder, pack)
            self.assertEqual(texture_pack.verified(folder), record)
            for name, entry, data in (('TEXTURES.AOA', tex, tex_tga), ('DATA.AOA', dat, dat_tga)):
                d2, key2, _, entries2 = aoapack.read_archive(folder / name, self.key0)
                self.assertEqual(aoapack.entry_bytes(d2, key2, self.key0, entries2[entry['index']])[0], data)
            # Reinstalling rebuilds from pinned backups; a narrower pack restores DATA.
            self.assertEqual(texture_pack.install(folder, pack), record)
            texture_pack.install(folder, {tex['name']: folder / 'a.tga'})
            self.assertEqual((folder / 'DATA.AOA').read_bytes(), original('DATA.AOA').read_bytes())
            self.assertEqual(set(texture_pack.verified(folder)['archives']), {'TEXTURES.AOA'})
            with self.assertRaises(KeyError):
                texture_pack.install(folder, {'TEXTURES.AOA:' + dat['name']: folder / 'b.tga'})
            packed = (folder / 'TEXTURES.AOA').read_bytes()
            (folder / 'TEXTURES.AOA').write_bytes(packed[:-1] + bytes([packed[-1] ^ 1]))
            with self.assertRaises(ValueError):
                texture_pack.verified(folder)
            with self.assertRaises(ValueError):
                texture_pack.install(folder, pack)
            texture_pack.undo(folder)
            for name in texture_pack.ARCHIVES:
                self.assertEqual((folder / name).read_bytes(), original(name).read_bytes())
            self.assertIsNone(texture_pack.verified(folder))
            (folder / 'a.tga').write_bytes(bytes([0, 0, 10]) + tex_tga[3:])  # RLE TGA is refused
            with self.assertRaises(ValueError):
                texture_pack.install(folder, {tex['name']: folder / 'a.tga'})

    def test_unknown_entry_rejected(self):
        with self.assertRaises(KeyError):
            aoapack.rebuild(original('FX.AOA'), self.key0, {'no-such-entry.tga': b'x' * 10})


if __name__ == '__main__':
    unittest.main()
