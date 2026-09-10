import hashlib
import json
import os
import tempfile
import unittest
from unittest import mock

from core.updater import UpdateInfo, check_for_update, download_and_verify


class _Response:
    def __init__(self, payload):
        self.payload = payload
        self.read_once = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, *args):
        if isinstance(self.payload, bytes):
            if self.read_once:
                return b""
            self.read_once = True
        if isinstance(self.payload, bytes):
            return self.payload
        return json.dumps(self.payload).encode("utf-8")


class UpdaterTests(unittest.TestCase):
    def test_manifest_rejects_non_https_download(self):
        with self.assertRaises(ValueError):
            UpdateInfo.from_payload({
                "version": "1.2.7",
                "download_url": "http://example.test/setup.exe",
                "sha256": "a" * 64,
            })

    def test_check_returns_only_newer_version(self):
        payload = {
            "version": "1.2.7",
            "download_url": "https://example.test/setup.exe",
            "sha256": "a" * 64,
        }
        with mock.patch("core.updater.urllib.request.urlopen", return_value=_Response(payload)):
            update = check_for_update("https://example.test/latest.json", "1.2.6")
        self.assertEqual(update.version, "1.2.7")

    def test_download_verifies_sha256_before_replacing(self):
        content = b"signed installer bytes"
        update = UpdateInfo(
            "1.2.7",
            "https://example.test/setup.exe",
            hashlib.sha256(content).hexdigest(),
        )
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch("core.updater.urllib.request.urlopen", return_value=_Response(content)):
                path = download_and_verify(update, directory)
            self.assertTrue(os.path.isfile(path))
            with open(path, "rb") as installer:
                self.assertEqual(installer.read(), content)


if __name__ == "__main__":
    unittest.main()
