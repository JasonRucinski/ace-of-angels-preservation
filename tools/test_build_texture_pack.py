"""Skin pack builder on synthetic TGAs with a stand-in 4x upscaler; no game files."""
import io
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_texture_pack as build
from PIL import Image

FOOTER = bytes(8) + b"TRUEVISION-XFILE.\0"


def tga(w, h, bpp, top_left, pixel, image_id=b""):
    """Uncompressed TGA; pixel(x, y) gives RGB(A) for visual row y (0 = top)."""
    rows = []
    for y in (range(h) if top_left else reversed(range(h))):
        for x in range(w):
            r, g, b, *a = pixel(x, y)
            rows.append(bytes([b, g, r] + (a or [255])[:bpp // 8 - 3]))
    descriptor = (0x20 if top_left else 0) | (8 if bpp == 32 else 0)
    header = struct.pack("<BBBHHBHHHHBB", len(image_id), 0, 2, 0, 0, 0, 0, 0, w, h, bpp, descriptor)
    return header + image_id + b"".join(rows) + FOOTER


def nearest_x4(image):
    return image.resize((image.width * 4, image.height * 4), Image.Resampling.NEAREST)


class BuildTexturePackTests(unittest.TestCase):
    def decode(self, data):
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            return image.copy()

    def test_header_footer_and_row_order_for_both_origins(self):
        def pixel(x, y):
            return (255, 0, 0) if y < 8 else (0, 0, 255)
        for top_left in (False, True):
            with self.subTest(top_left=top_left):
                source = tga(32, 16, 24, top_left, pixel, image_id=b"id")
                out = build.upscale_tga(source, nearest_x4)
                self.assertEqual(struct.unpack_from("<HH", out, 12), (64, 32))
                self.assertEqual(out[:12] + out[16:20], source[:12] + source[16:20])  # fields and ID
                self.assertTrue(out.endswith(FOOTER))
                self.assertEqual(len(out), 18 + 2 + 64 * 32 * 3 + len(FOOTER))
                image = self.decode(out).convert("RGB")
                self.assertEqual(image.getpixel((10, 2)), (255, 0, 0))   # top stays top
                self.assertEqual(image.getpixel((10, 29)), (0, 0, 255))  # bottom stays bottom

    def test_alpha_is_upscaled_separately_and_kept(self):
        source = tga(16, 16, 32, False, lambda x, y: (200, 100, 50, 0 if x < 8 else 255))
        image = self.decode(build.upscale_tga(source, nearest_x4))
        self.assertEqual(image.mode, "RGBA")
        self.assertEqual(image.size, (32, 32))
        self.assertEqual(image.getpixel((3, 16))[3], 0)
        self.assertEqual(image.getpixel((28, 16))[3], 255)
        self.assertEqual(image.getpixel((28, 16))[:3], (200, 100, 50))
        # Colour under transparent pixels is kept (no premultiplied black fringe).
        self.assertEqual(image.getpixel((3, 16))[:3], (200, 100, 50))

    def test_wrap_padding_matches_opposite_edges(self):
        image = Image.new("RGB", (40, 20))
        image.putdata([(x * 5, y * 10, 0) for y in range(20) for x in range(40)])
        padded = build.wrap_pad(image, 4)
        self.assertEqual(padded.size, (48, 28))
        self.assertEqual(padded.getpixel((0, 0)), image.getpixel((36, 16)))
        self.assertEqual(padded.getpixel((47, 27)), image.getpixel((3, 3)))
        self.assertEqual(padded.crop((4, 4, 44, 24)).tobytes(), image.tobytes())
        seen = []
        build.upscale_tga(tga(40, 20, 24, False, lambda x, y: (x, y, 0)),
                          lambda im: seen.append(im.size) or nearest_x4(im))
        self.assertEqual(seen, [(60, 40)])  # pad capped at half the height (10), one RGB pass

    def test_rejects_compressed_and_truncated_sources(self):
        good = tga(8, 8, 24, False, lambda x, y: (1, 2, 3))
        for bad in (good[:2] + bytes([10]) + good[3:], good[:40]):
            with self.assertRaises(ValueError):
                build.upscale_tga(bad, nearest_x4)

    def test_file_names_and_zip_hash_check(self):
        self.assertEqual(build.file_name("TEXTURES.AOA:n'goc.tga"), "n_goc.tga")
        self.assertEqual(build.file_name("DATA.AOA:natak-t1.tga"), "natak-t1.tga")
        with tempfile.TemporaryDirectory() as folder:
            fake = Path(folder) / "realesrgan.zip"
            fake.write_bytes(b"not the release")
            with mock.patch.object(build, "ESRGAN_ZIP", fake), \
                    mock.patch.object(build, "ESRGAN_DIR", Path(folder) / "x"), \
                    mock.patch.object(build, "ROOT", Path(folder)):
                with self.assertRaises(SystemExit):
                    build.prepare_esrgan()
                self.assertFalse((Path(folder) / "x").exists())


if __name__ == "__main__":
    unittest.main()
