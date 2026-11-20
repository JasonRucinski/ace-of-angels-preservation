"""The research tools against fake openers and temp files; game-free, no network.

Every request goes to a scripted opener through aoa/research/http.py with
sleeps recorded instead of taken; socket connects fail for the whole run as
a guard. Nothing is written outside a temporary folder.

    python -I tools/test.py test_research
"""
import contextlib
import email.message
import hashlib
import io
import json
import socket
import sys
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aoa import builds
from aoa.paths import ROOT
from aoa.research import fetch
from aoa.research import http as research_http
from aoa.research import disc_image, ia_disc_find, ia_fulltext, version, wayback
from aoa.research import restore_web_archive as rwa


class Response(io.BytesIO):
    def __init__(self, body, url):
        super().__init__(body)
        self.status = 200
        self.url = url
        self.headers = email.message.Message()
        self.headers["Content-Length"] = str(len(body))

    def geturl(self):
        return self.url


class Opener:
    """Answers each URL from a dict: bytes, or an exception to raise."""

    def __init__(self, answers):
        self.answers = answers
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request.full_url)
        answer = self.answers[request.full_url]
        if isinstance(answer, BaseException):
            raise answer
        return Response(answer, request.full_url)


def polite(answers):
    opener = Opener(answers)
    http = research_http.Polite(opener=opener, sleep=lambda s: None, min_interval=0.0,
                                base_delay=0.0, retries=1, log=lambda m: None)
    return http, opener


class Fetch(unittest.TestCase):
    PAYLOAD = b"MZ fake installer" * 100

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="aoa-fetch-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.log = self.tmp / "download_log.jsonl"
        self.manifest = self.tmp / "downloads.json"
        self.entry = {"runtime_version": "9.9.9", "kind": "full_installer",
                      "suggested_local_filename": "aoa_9.9.9_full.exe",
                      "bytes": len(self.PAYLOAD), "sha256": hashlib.sha256(self.PAYLOAD).hexdigest(),
                      "direct_url": "https://archive.org/download/x/aoa.exe",
                      "client_bytes": 1, "client_sha256": "0" * 64}
        self.write_manifest()
        patch = mock.patch.dict(builds.INSTALLER_SHA256, {"9.9.9": self.entry["sha256"]})
        patch.start()
        self.addCleanup(patch.stop)

    def write_manifest(self):
        self.manifest.write_text(json.dumps({"downloads": [self.entry]}), encoding="utf-8")

    def run_fetch(self, answers, **kwargs):
        http, opener = polite(answers)
        lines = []
        final = fetch.fetch("9.9.9", self.tmp / "out", manifest=self.manifest, log=self.log,
                            open_url=http.open, say=lines.append, **kwargs)
        return final, opener, lines

    def records(self):
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def test_verified_download_is_kept_and_logged(self):
        final, opener, _ = self.run_fetch({self.entry["direct_url"]: self.PAYLOAD})
        self.assertEqual(final, self.tmp / "out" / "aoa_9.9.9_full.exe")
        self.assertEqual(final.read_bytes(), self.PAYLOAD)
        self.assertFalse((self.tmp / "out" / "aoa_9.9.9_full.exe.part").exists())
        [record] = self.records()
        self.assertTrue(record["verified"])
        self.assertEqual(record["sha256"], self.entry["sha256"])

    def test_wrong_bytes_leave_the_part_file(self):
        final, _, _ = self.run_fetch({self.entry["direct_url"]: b"error page"})
        self.assertIsNone(final)
        self.assertTrue((self.tmp / "out" / "aoa_9.9.9_full.exe.part").exists())
        self.assertFalse((self.tmp / "out" / "aoa_9.9.9_full.exe").exists())
        self.assertFalse(self.records()[0]["verified"])

    def test_manifest_md5_is_checked(self):
        self.entry["md5"] = "0" * 32
        self.write_manifest()
        final, _, _ = self.run_fetch({self.entry["direct_url"]: self.PAYLOAD})
        self.assertIsNone(final)
        self.assertEqual(self.records()[0]["expected_md5"], "0" * 32)

    def test_manifest_must_agree_with_aoa_builds(self):
        with mock.patch.dict(builds.INSTALLER_SHA256, {"9.9.9": "1" * 64}):
            with self.assertRaises(fetch.FetchError):
                self.run_fetch({})

    def test_mirror_after_a_failed_direct_url(self):
        mirror = "https://archive.org/download/y/aoa.exe"
        with mock.patch.dict(fetch.MIRRORS, {"9.9.9": [mirror]}):
            final, opener, _ = self.run_fetch({self.entry["direct_url"]: research_http.urllib.error.HTTPError(
                self.entry["direct_url"], 404, "gone", email.message.Message(), None), mirror: self.PAYLOAD})
        self.assertIsNotNone(final)
        self.assertEqual(opener.requests, [self.entry["direct_url"], mirror])

    def test_existing_file_is_checked_not_overwritten(self):
        (self.tmp / "out").mkdir()
        target = self.tmp / "out" / "aoa_9.9.9_full.exe"
        target.write_bytes(b"something else")
        final, opener, _ = self.run_fetch({})
        self.assertIsNone(final)
        self.assertEqual(opener.requests, [])
        self.assertEqual(target.read_bytes(), b"something else")

    def test_no_direct_url(self):
        del self.entry["direct_url"]
        self.write_manifest()
        with self.assertRaises(fetch.FetchError):
            self.run_fetch({})

    def test_default_log_is_in_work_not_evidence(self):
        committed = ROOT / "evidence" / "download_log.jsonl"
        before = committed.stat()
        self.assertEqual(fetch.LOG, ROOT / "work" / "download_log.jsonl")
        work_log = self.tmp / "work" / "download_log.jsonl"
        http, _ = polite({self.entry["direct_url"]: self.PAYLOAD})
        with mock.patch.object(fetch, "LOG", work_log), mock.patch.object(fetch, "polite_open", http.open), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(fetch.main(["9.9.9", "--out", str(self.tmp / "a"), "--manifest", str(self.manifest)]), 0)
            # The launcher's call: the old MANIFEST VERSION OUT_DIR form.
            self.assertEqual(fetch.main([str(self.manifest), "9.9.9", str(self.tmp / "b")]), 0)
            chosen = self.tmp / "kept.jsonl"
            fetch.main(["9.9.9", "--out", str(self.tmp / "c"), "--manifest", str(self.manifest),
                        "--evidence", str(chosen)])
        self.assertEqual(len(work_log.read_text(encoding="utf-8").splitlines()), 2)
        self.assertEqual(len(chosen.read_text(encoding="utf-8").splitlines()), 1)
        after = committed.stat()
        self.assertEqual((before.st_size, before.st_mtime_ns), (after.st_size, after.st_mtime_ns))

    def test_both_command_forms_parse(self):
        seen = []

        def fake(version, out, **kwargs):
            seen.append((version, Path(out), kwargs["client"], kwargs["manifest"]))
            return Path(out)

        with mock.patch.object(fetch, "fetch", fake):
            fetch.main(["2.7.1", "--out", "originals/2.7.1", "--client"])
            fetch.main(["manifest/downloads.json", "2.7.1", "originals/2.7.1", "--client"])
            fetch.main(["2.9.2"])
        self.assertEqual(seen[0], seen[1][:3] + (str(fetch.MANIFEST),))
        self.assertEqual(seen[1][3], "manifest/downloads.json")
        self.assertEqual(seen[2][1], ROOT / "builds" / "2.9.2")

    def test_known_builds_keep_their_folders(self):
        seen = []

        def fake(version, out, **kwargs):
            seen.append((version, Path(out).relative_to(self.tmp).as_posix(), kwargs["name"]))
            return Path(out) / kwargs["name"]

        with mock.patch.object(fetch, "fetch", fake), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(fetch.known_builds([str(self.tmp)]), 0)
        self.assertEqual(seen, [("2.8.2", "v2.8.2_2002-03_CD-Action-06-2002", "aoa-current.exe"),
                                ("2.9.2", "v2.9.2_2004_FamilyGamePack3", "aoa-current.exe")])

    def test_real_manifest_entries_agree(self):
        for runtime in ("2.0.0", "2.3.1", "2.7.1", "2.8.2", "2.9.2"):
            entry = fetch.entry_for(runtime)
            self.assertEqual(fetch.expected(entry)["sha256"], entry["sha256"])
            self.assertTrue(fetch.urls(entry))
        with self.assertRaises(fetch.FetchError):
            fetch.urls(fetch.entry_for("2.8.0"))


def tiny_client(numbers=(2, 9, 2)):
    """A two-section PE whose code loads three .data globals and pushes a version format."""
    base, e = 0x400000, 0x80
    header = bytearray(0x400)
    header[:2] = b"MZ"
    struct.pack_into("<I", header, 0x3C, e)
    header[e:e + 4] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", header, e + 4, 0x14C, 2, 0, 0, 0, 0xE0, 0x10F)
    struct.pack_into("<H", header, e + 24, 0x10B)
    struct.pack_into("<I", header, e + 24 + 28, base)
    struct.pack_into("<I", header, e + 24 + 56, 0x3000)
    for k, (name, rva, raw_off, chars) in enumerate(((b".text", 0x1000, 0x400, 0x60000020),
                                                     (b".data", 0x2000, 0x600, 0xC0000040))):
        o = e + 24 + 0xE0 + 40 * k
        header[o:o + 8] = name.ljust(8, b"\0")
        struct.pack_into("<IIII", header, o + 8, 0x200, rva, 0x200, raw_off)
        struct.pack_into("<I", header, o + 36, chars)
    fmt_va, globals_va = base + 0x2010, base + 0x2100
    code = (b"\xa1" + struct.pack("<I", globals_va) + b"\x8b\x0d" + struct.pack("<I", globals_va + 4)
            + b"\x8b\x15" + struct.pack("<I", globals_va + 8) + b"\x68" + struct.pack("<I", fmt_va))
    data = bytearray(0x200)
    text = version.FORMATS[0]
    data[0x10:0x10 + len(text)] = text
    struct.pack_into("<3I", data, 0x100, *numbers)
    return bytes(header) + code.ljust(0x200, b"\x90") + bytes(data)


class Version(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="aoa-version-")
        self.addCleanup(tmp.cleanup)
        self.client = Path(tmp.name) / "AOACLIENT.EXE"
        self.client.write_bytes(tiny_client())

    def test_compiled_in_version(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            version.main([str(self.client)])
        self.assertIn("-> v2.9.2", out.getvalue())

    def test_old_probe_form_means_detail(self):
        seen = []
        with mock.patch.object(version, "detail", lambda path: seen.append(path) or {
                "call_sites": [], "global_ref_stats": {}, "distinct_versions": []}), \
                contextlib.redirect_stdout(io.StringIO()):
            out = self.client.with_name("probe.json")
            with contextlib.redirect_stderr(io.StringIO()) as note:
                version.main([str(self.client), "cache.pkl", str(out)])
            self.assertIn("ignoring cache.pkl", note.getvalue())
            version.main([str(self.client), "--detail"])
        self.assertEqual(seen, [str(self.client)] * 2)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["distinct_versions"], [])

    def test_out_needs_detail(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            version.main([str(self.client), "--out", "x.json"])

FIELDS_ROW = ["timestamp", "original", "mimetype", "statuscode", "digest", "length"]
CAPTURE_ROW = ["20010127072200", "http://www.aceofangels.com/", "text/html", "200", "ABC", "1234"]


class DisassemblyCache(unittest.TestCase):
    def test_old_cache_arguments_are_dropped(self):
        from aoa.analysis.cache_args import drop_cache_args
        with contextlib.redirect_stderr(io.StringIO()) as note:
            self.assertEqual(drop_cache_args(["a.exe", "work/2.9.2/disasm.pkl", "out.json"]), ["a.exe", "out.json"])
            self.assertEqual(drop_cache_args(["ref.exe", "r.pkl", "o.exe", "o.pkl", "out.json", "f=0x1"], (1, 3)),
                             ["ref.exe", "o.exe", "out.json", "f=0x1"])
        self.assertEqual(note.getvalue().count("ignoring"), 3)
        # The new forms pass through untouched, options included.
        self.assertEqual(drop_cache_args(["a.exe", "-", "out.json", "--x"]), ["a.exe", "-", "out.json", "--x"])
        self.assertEqual(drop_cache_args(["a.exe", "sz.json", "x.pkl"]), ["a.exe", "sz.json", "x.pkl"])

    def test_cache_is_keyed_by_the_executable(self):
        try:
            from aoa.analysis import pe_util
        except ImportError as error:
            self.skipTest(f"needs {error.name}")
        a, b = pe_util.cache_file(b"one"), pe_util.cache_file(b"two", "elsewhere")
        self.assertEqual(a.parent, ROOT / "work" / "cache")
        self.assertEqual(a.name, hashlib.sha256(b"one").hexdigest() + ".pkl")
        self.assertEqual(b, Path("elsewhere") / (hashlib.sha256(b"two").hexdigest() + ".pkl"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.exe"
            path.write_bytes(tiny_client())
            pe = pe_util.PE(path)
            first = pe_util.Disasm(pe, cache_dir=tmp)
            self.assertTrue(pe_util.cache_file(pe.data, tmp).is_file())
            self.assertEqual(pe_util.Disasm(pe, cache_dir=tmp).insns, first.insns)
            self.assertEqual(first.at(first.addrs[0])[2], "mov")


class Cdx(unittest.TestCase):
    def test_query_url_and_header(self):
        answers = {}
        http, opener = polite(answers)
        builds_url = ("https://web.archive.org/cdx/search/cdx?url=aceofangels.com&matchType=domain"
                      "&output=json&fl=timestamp%2Coriginal%2Cmimetype%2Cstatuscode%2Cdigest%2Clength")
        answers[builds_url] = json.dumps([FIELDS_ROW, CAPTURE_ROW]).encode()
        # wayback_builds' query is unchanged by the move to the shared helper.
        self.assertEqual(wayback.cdx_rows("aceofangels.com", http=http), [CAPTURE_ROW])
        self.assertEqual(wayback.without_header([CAPTURE_ROW]), [CAPTURE_ROW])

    def test_restore_web_archive_cdx_writes_the_indexes_it_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            answers = {}
            for name, (domain, collapse) in rwa.CDX_INDEXES.items():
                url = ("https://web.archive.org/cdx/search/cdx?url=" + domain + "&matchType=domain"
                       "&output=json&fl=timestamp%2Coriginal%2Cmimetype%2Cstatuscode%2Cdigest%2Clength"
                       "&filter=statuscode%3A200&collapse=" + collapse)
                answers[url] = json.dumps([FIELDS_ROW, CAPTURE_ROW]).encode()
            http, opener = polite(answers)
            (out / "wayback-forum-index.json").write_text("kept", encoding="utf-8")
            rwa.write_cdx_indexes(out, list(rwa.CDX_INDEXES), http, say=lambda m: None)
            self.assertEqual(len(opener.requests), 2)
            self.assertEqual((out / "wayback-forum-index.json").read_text(encoding="utf-8"), "kept")
            # The same [1:] slice import_indexes applies.
            site = json.loads((out / "wayback-site-index.json").read_text(encoding="utf-8"))
            self.assertEqual(site[1:], [CAPTURE_ROW])

    def test_handoff_seeds_the_crawl(self):
        # The 20 October handoff moved from docs/history/ to data/: the crawl's seed list reads it.
        self.assertEqual(rwa.HANDOFF.relative_to(ROOT).as_posix(), "data/research-handoff-2026-10-20.txt")
        captures = rwa.CAPTURE.findall(rwa.HANDOFF.read_text(encoding="utf-8"))
        self.assertTrue(captures, "no Wayback capture URLs in the handoff")

    def test_cdx_subcommand_parses_and_old_flags_still_do(self):
        seen = []
        with mock.patch.object(rwa, "write_cdx_indexes", lambda out, names, http: seen.append((out, names))):
            rwa.main(["cdx", "--only", "wayback-site-index.json", "--out", "x"])
        self.assertEqual(seen, [(Path("x"), ["wayback-site-index.json"])])
        with mock.patch.object(rwa, "Mirror") as mirror:
            rwa.main(["--import-indexes", "--recover", "--limit", "5"])
        mirror.return_value.recover.assert_called_once_with(5)


class DiscSearch(unittest.TestCase):
    def listing(self, *names):
        return "".join(f'<a href="//archive.org/download/x/{n}">{n}</a>' for n in names).encode()

    def search(self, item, pages):
        answers = {"https://archive.org/metadata/" + item: json.dumps(
            {"metadata": {"title": "Cover CD"}, "files": [{"name": n} for n in pages]}).encode()}
        for name, body in pages.items():
            answers[f"https://archive.org/download/{item}/{name}/"] = body
        http, _ = polite(answers)
        with contextlib.redirect_stdout(io.StringIO()):
            return ia_disc_find.search(item, ia_disc_find.re.compile(ia_disc_find.DEFAULT), get=http.get)

    def test_rows(self):
        files = [f"DEMOS/GAME{i}/SETUP.EXE" for i in range(8)]
        none = self.search("cd1", {"cd1.iso": self.listing(*files)})
        self.assertEqual(ia_disc_find.log_row(none, "2026-11-15"),
                         "cd1\tCover CD\tsearched\tnone (cd1.iso: 8 entries listed) [ia_disc_find, 2026-11-15]")
        hit = self.search("cd2", {"cd2.iso": self.listing(*files, "Ace of Angels/aoa-current.exe")})
        self.assertEqual(ia_disc_find.log_row(hit, "d").split("\t")[2], "listing hit")
        wrapped = self.search("cd3", {"cd3.rar": self.listing("CD3.img")})
        self.assertEqual(ia_disc_find.log_row(wrapped, "d").split("\t")[2], "NOT searched")
        self.assertIn("1 entries listed", ia_disc_find.log_row(wrapped, "d"))

    def test_append_keeps_existing_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            table = Path(tmp) / "disc_search.tsv"
            table.write_bytes(b"archive.org item\ttitle\tstatus\tresult\nold\tt\tsearched\tnone")
            ia_disc_find.append_log(table, "new\tt\tsearched\tnone (x)")
            self.assertEqual(table.read_bytes(), b"archive.org item\ttitle\tstatus\tresult\nold\tt\tsearched\tnone"
                                                 b"\nnew\tt\tsearched\tnone (x)\n")

    def test_log_must_exist(self):
        with self.assertRaises(SystemExit) as caught:
            ia_disc_find.main(["x", "--log", "no-such-table.tsv"])
        self.assertIn("not found", str(caught.exception.code))

    def test_committed_table_has_four_columns(self):
        for line in (ROOT / "data/disc_search.tsv").read_text(encoding="utf-8").splitlines():
            self.assertEqual(len(line.split("\t")), 4, line)


class FullText(unittest.TestCase):
    def test_search_writes_hits(self):
        page = {"response": {"body": {"hits": {"total": 1, "hits": [
            {"fields": {"identifier": "pcgamer", "filename": "p_hocr_searchtext.txt.gz", "title": "PC Gamer"}}]}}}}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(ia_fulltext, "polite_get", lambda url, timeout: json.dumps(page).encode()), \
                contextlib.redirect_stdout(io.StringIO()):
            ia_fulltext.main(["search", tmp])
            [hit] = json.loads((Path(tmp) / ia_fulltext.HITS).read_text())
        self.assertEqual(hit["identifier"], "pcgamer")
        self.assertEqual(len(hit["queries"]), len(ia_fulltext.QUERIES))

    def test_context_reads_cached_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / ia_fulltext.HITS).write_text(json.dumps([{"identifier": "mag", "filename": "a.txt", "title": "Mag"}]))
            (d / "txt").mkdir()
            (d / "txt" / "mag__a.txt").write_text("Intro. Ace of Angels is a space sim from Flying Rock. The end.")
            with mock.patch.object(ia_fulltext, "get", lambda u: self.fail("fetched a cached file")), \
                    contextlib.redirect_stdout(io.StringIO()):
                ia_fulltext.main(["context", tmp])
            passages = (d / ia_fulltext.PASSAGES).read_text(encoding="utf-8")
        self.assertIn(">> Ace of Angels is a space sim from Flying Rock.", passages)

    def test_old_names_insert_the_subcommand(self):
        from aoa.research import ia_fulltext_context, ia_fulltext_search
        seen = []
        with mock.patch.object(ia_fulltext, "main", seen.append):
            ia_fulltext_search.main(["data/"])
            ia_fulltext_context.main(["--trim", "x.txt"])
        self.assertEqual(seen, [["search", "data/"], ["context", "--trim", "x.txt"]])


def tiny_iso(name=b"AOA.TXT;1", body=b"hello"):
    """Sectors 0-15 empty, a primary descriptor, a terminator, the root directory, one file."""
    def record(extent, size, flags, ident):
        length = 33 + len(ident) + (len(ident) + 1) % 2
        r = bytearray(length)
        r[0] = length
        struct.pack_into("<I", r, 2, extent)
        struct.pack_into("<I", r, 10, size)
        r[25], r[32] = flags, len(ident)
        r[33:33 + len(ident)] = ident
        return bytes(r)
    pvd = bytearray(2048)
    pvd[0:6] = b"\x01CD001"
    pvd[156:190] = record(18, 2048, 2, b"\0")
    end = bytearray(2048)
    end[0:6] = b"\xffCD001"
    root = (record(18, 2048, 2, b"\0") + record(18, 2048, 2, b"\1") + record(19, len(body), 0, name)).ljust(2048, b"\0")
    return bytes(16 * 2048) + bytes(pvd) + bytes(end) + root + body.ljust(2048, b"\0")


class DiscImage(unittest.TestCase):
    def test_iso_stream_extract(self):
        with tempfile.TemporaryDirectory() as tmp:
            stdin = io.TextIOWrapper(io.BytesIO(tiny_iso()))
            with mock.patch.object(sys, "stdin", stdin), contextlib.redirect_stdout(io.StringIO()):
                disc_image.main(["iso", "(?i)aoa", tmp])
            self.assertEqual((Path(tmp) / "AOA.TXT").read_bytes(), b"hello")

    def test_old_names_insert_the_subcommand(self):
        from aoa.research import iso_stream_extract, rar_img2iso
        seen = []
        with mock.patch.object(disc_image, "main", seen.append):
            iso_stream_extract.main(["re", "out"])
            rar_img2iso.main(["a.rar", "a.img", "a.iso"])
        self.assertEqual(seen, [["iso", "re", "out"], ["rar", "a.rar", "a.img", "a.iso"]])


class Requirements(unittest.TestCase):
    """The split of audit F-10: players need no packages; research and the texture builder do."""

    def packages(self, name):
        lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
        return [line.split("==")[0].lower() for line in lines if line.strip() and not line.startswith("#")]

    def test_split(self):
        self.assertEqual(self.packages("requirements.txt"), [])
        self.assertEqual(sorted(self.packages("requirements-research.txt")), ["capstone", "pefile", "unicorn"])
        self.assertEqual(self.packages("requirements-texture.txt"), ["pillow"])

    def test_ci_installs_them(self):
        workflow = (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")
        for name in ("requirements-research.txt", "requirements-texture.txt"):
            self.assertIn("-r " + name, workflow)


def _no_network(*args, **kwargs):
    raise AssertionError("test_research must not use the network")


if __name__ == "__main__":
    socket.socket.connect = _no_network
    socket.create_connection = _no_network
    unittest.main()
