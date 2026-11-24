"""The GitHub Pages site in site/: its images exist, its URLs agree, its structured data parses; game-free."""
import json
import re
import unittest
from html.parser import HTMLParser

from aoa.paths import ROOT

SITE = ROOT / "site"
BASE = "https://jasonrucinski.github.io/ace-of-angels-preservation/"


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta, self.links, self.images, self.title, self.ld = {}, {}, [], "", []
        self._in = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            self.meta[a.get("name") or a.get("property")] = a.get("content")
        elif tag == "link":
            self.links[a.get("rel")] = a.get("href")
        elif tag == "img":
            self.images.append(a)
        elif tag == "title" or (tag == "script" and a.get("type") == "application/ld+json"):
            self._in = tag

    def handle_endtag(self, tag):
        self._in = None

    def handle_data(self, data):
        if self._in == "title":
            self.title += data
        elif self._in == "script":
            self.ld.append(data)


def page():
    p = Page()
    p.feed((SITE / "index.html").read_text(encoding="utf-8"))
    return p


class SiteTests(unittest.TestCase):
    def test_local_images_exist(self):
        # The workflow copies docs/images/*.jpg to images/; other files are in site/.
        for img in page().images:
            src = img["src"]
            if src.startswith("images/"):
                self.assertTrue((ROOT / "docs" / src).is_file(), src)
            else:
                self.assertTrue((SITE / src).is_file(), src)
            if not img.get("aria-hidden"):
                self.assertTrue(img.get("alt"), f"{src} needs alt text")

    def test_head_tags(self):
        p = page()
        self.assertIn("Ace of Angels", p.title)
        self.assertLessEqual(len(p.title), 70, "titles longer than about 70 characters get cut off in results")
        self.assertTrue(70 <= len(p.meta["description"]) <= 300)
        self.assertEqual(p.links["canonical"], BASE)
        self.assertEqual(p.meta["og:url"], BASE)
        self.assertTrue(p.meta["og:image"].startswith(BASE))
        self.assertTrue((SITE / p.meta["og:image"][len(BASE):]).is_file())

    def test_structured_data_parses(self):
        data = json.loads("".join(page().ld))
        types = {item["@type"] for item in data["@graph"]}
        self.assertEqual(types, {"VideoGame", "SoftwareSourceCode"})

    def test_sitemap_and_robots_name_the_page(self):
        sitemap = (SITE / "sitemap.xml").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"<loc>(.*?)</loc>", sitemap), [BASE])
        self.assertIn(f"Sitemap: {BASE}sitemap.xml", (SITE / "robots.txt").read_text(encoding="utf-8"))

    def test_og_image_size(self):
        data = (SITE / "og-image.jpg").read_bytes()
        # Width and height from the JPEG's SOF marker.
        i = 2
        while i < len(data):
            marker, length = data[i + 1], int.from_bytes(data[i + 2:i + 4], "big")
            if marker in (0xC0, 0xC1, 0xC2):
                h, w = int.from_bytes(data[i + 5:i + 7], "big"), int.from_bytes(data[i + 7:i + 9], "big")
                self.assertEqual((w, h), (1280, 640))
                return
            i += 2 + length
        self.fail("no frame header in og-image.jpg")


if __name__ == "__main__":
    unittest.main()
