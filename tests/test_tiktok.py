import asyncio
import threading
import time
import unittest
from unittest.mock import patch

import bots.tiktok as tiktok_module
from websockets.datastructures import Headers
from websockets.exceptions import InvalidStatusCode


class FakeTikTokClient:
    instances = []

    def __init__(self, unique_id):
        self.unique_id = unique_id
        self.connected = threading.Event()
        self.closed = threading.Event()
        self.connect_calls = 0
        FakeTikTokClient.instances.append(self)

    def on(self, _event):
        return lambda callback: callback

    async def start(self):  # pragma: no cover - regression guard
        raise AssertionError("TikTokBot must use the blocking connect API")

    async def connect(self):
        self.connect_calls += 1
        self.connected.set()
        await _wait_async(self.closed)

    async def disconnect(self):
        self.closed.set()


class OfflineTikTokClient(FakeTikTokClient):
    async def connect(self):
        self.connect_calls += 1
        raise tiktok_module.UserOfflineError("offline")


class RejectedTikTokClient(FakeTikTokClient):
    async def connect(self):
        self.connect_calls += 1
        raise InvalidStatusCode(400, Headers())


async def _wait_async(event):
    while not event.is_set():
        await asyncio.sleep(0.01)


class TikTokConnectionTests(unittest.TestCase):
    def test_channel_accepts_handle_name_and_profile_url(self):
        normalize = tiktok_module.normalize_tiktok_channel
        self.assertEqual(normalize("@lidiacampos1508"), "lidiacampos1508")
        self.assertEqual(normalize("lidiacampos1508"), "lidiacampos1508")
        self.assertEqual(
            normalize("https://www.tiktok.com/@lidiacampos1508/live"),
            "lidiacampos1508",
        )

    def test_connection_does_not_enter_reconnect_loop_before_disconnect(self):
        FakeTikTokClient.instances.clear()
        with patch.object(tiktok_module, "TikTokLiveClient", FakeTikTokClient):
            bot = tiktok_module.TikTokBot("@lidiacampos1508")
            bot.start()
            deadline = time.monotonic() + 1
            while (
                not FakeTikTokClient.instances
                or not FakeTikTokClient.instances[0].connected.is_set()
            ) and time.monotonic() < deadline:
                time.sleep(0.01)

            self.assertEqual(len(FakeTikTokClient.instances), 1)
            self.assertTrue(FakeTikTokClient.instances[0].connected.is_set())
            self.assertEqual(FakeTikTokClient.instances[0].connect_calls, 1)

            bot.requestInterruption()
            self.assertTrue(bot.wait(2000))
            self.assertEqual(len(FakeTikTokClient.instances), 1)

    def test_offline_channel_does_not_retry_forever(self):
        OfflineTikTokClient.instances.clear()
        statuses = []
        with patch.object(tiktok_module, "TikTokLiveClient", OfflineTikTokClient):
            bot = tiktok_module.TikTokBot("@lidiacampos1508")
            bot.status_update.connect(statuses.append)
            bot.start()
            self.assertTrue(bot.wait(2000))

        self.assertEqual(len(OfflineTikTokClient.instances), 1)
        self.assertEqual(OfflineTikTokClient.instances[0].connect_calls, 1)
        self.assertIn("Live do TikTok offline", statuses[-1])

    def test_http_400_rejection_does_not_retry_forever(self):
        RejectedTikTokClient.instances.clear()
        statuses = []
        with patch.object(tiktok_module, "TikTokLiveClient", RejectedTikTokClient):
            bot = tiktok_module.TikTokBot("@lidiacampos1508")
            bot.status_update.connect(statuses.append)
            bot.start()
            self.assertTrue(bot.wait(2000))

        self.assertEqual(len(RejectedTikTokClient.instances), 1)
        self.assertEqual(RejectedTikTokClient.instances[0].connect_calls, 1)
        self.assertIn("HTTP 400", statuses[-1])


if __name__ == "__main__":
    unittest.main()
