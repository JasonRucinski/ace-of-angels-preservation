"""aoa/builds.py agrees with the manifests and require_build refuses other bytes; game-free.

    python -I tools/test.py test_builds
"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aoa import builds
from aoa.paths import ROOT


class KnownBuilds(unittest.TestCase):
    def test_hashes_match_the_download_manifest(self):
        manifest = json.loads((ROOT / "manifest/downloads.json").read_text(encoding="utf-8"))
        clients, installers = {}, {}
        for entry in manifest["downloads"]:
            clients[entry["runtime_version"]] = entry["client_sha256"]
            if "installer" in entry["kind"]:
                installers[entry["runtime_version"]] = entry["sha256"]
        self.assertEqual(builds.CLIENT_SHA256, clients)
        self.assertEqual(builds.INSTALLER_SHA256, installers)

    def test_installer_matches_the_client_config(self):
        config = json.loads((ROOT / "config/client-2.9.2.json").read_text(encoding="utf-8"))
        self.assertEqual(config["installer_sha256"], builds.INSTALLER_SHA256[config["client"]])

    def test_require_build(self):
        data = b"not a client"
        with self.assertRaises(ValueError) as caught:
            builds.require_build(data, "2.9.2")
        self.assertEqual(len(str(caught.exception).splitlines()), 1)
        self.assertIn("2.9.2", str(caught.exception))
        with self.assertRaises(ValueError):
            builds.require_build(data, "9.9.9")
        with mock_hash("2.9.2", data):
            self.assertEqual(builds.require_build(bytearray(data), "2.9.2"), data)
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "AOACLIENT.EXE"
                path.write_bytes(data)
                self.assertEqual(builds.require_build(path, "2.9.2"), data)
                self.assertEqual(builds.require_build(str(path), "2.9.2"), data)


def mock_hash(version, data):
    return mock.patch.dict(builds.CLIENT_SHA256, {version: hashlib.sha256(data).hexdigest()})


if __name__ == "__main__":
    unittest.main()
