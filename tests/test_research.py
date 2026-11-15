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
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aoa import builds
from aoa.paths import ROOT
from aoa.research import fetch
from aoa.research import http as research_http


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
        for version in ("2.0.0", "2.3.1", "2.7.1", "2.8.2", "2.9.2"):
            entry = fetch.entry_for(version)
            self.assertEqual(fetch.expected(entry)["sha256"], entry["sha256"])
            self.assertTrue(fetch.urls(entry))
        with self.assertRaises(fetch.FetchError):
            fetch.urls(fetch.entry_for("2.8.0"))


def _no_network(*args, **kwargs):
    raise AssertionError("test_research must not use the network")


if __name__ == "__main__":
    socket.socket.connect = _no_network
    socket.create_connection = _no_network
    unittest.main()
