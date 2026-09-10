import asyncio
import logging
import unittest
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock
from urllib.parse import parse_qs, urlsplit

from TikTokLive.client.ws.ws_connect import WebcastConnect
from TikTokLive.proto import ProtoMessageFetchResult
from bots.tiktok_transport import build_webcast_uri, CompatibleWebcastConnect, TikTokLiveClient


class TransportTests(unittest.TestCase):
    def test_signed_values_round_trip_and_override_local_defaults(self):
        route = {"token": "opaque+token/with%2F=&value", "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "room_id": "123", "client_enter": "true"}
        response = SimpleNamespace(push_server="wss://ws-fallback.eulerstream.com/?existing=ok", route_params=route)
        uri = build_webcast_uri(response, {"room_id": "wrong", "client_enter": "1", "browser_version": "5.0%20%28Windows%29"}, "&version_code=270000")
        parsed = urlsplit(uri)
        self.assertEqual(parsed.netloc, "ws-fallback.eulerstream.com")
        self.assertFalse(any(c.isspace() for c in uri))
        values = parse_qs(parsed.query)
        for key, value in route.items():
            self.assertEqual(values[key], [value])
        self.assertEqual(values["browser_version"], ["5.0 (Windows)"])
        self.assertEqual(values["existing"], ["ok"])

    def test_direct_endpoint_keeps_additional_version(self):
        response = SimpleNamespace(push_server="wss://webcast.tiktok.com/webcast/im/push/", route_params={"cursor": "a&b"})
        uri = build_webcast_uri(response, {"version_code": "180800"}, "&version_code=270000")
        self.assertEqual(parse_qs(urlsplit(uri).query)["version_code"], ["180800", "270000"])

    def test_initial_response_triggers_room_entry_only_after_upgrade(self):
        async def check():
            bootstrap = ProtoMessageFetchResult(is_first=False)
            later = ProtoMessageFetchResult(is_first=False)
            async def upstream(_):
                yield None, bootstrap
                yield object(), later
            with patch.object(WebcastConnect, "__aiter__", upstream):
                connector = object.__new__(CompatibleWebcastConnect)
                responses = [item async for item in connector]
            self.assertTrue(responses[0][1].is_first)
            self.assertFalse(responses[1][1].is_first)
        asyncio.run(check())

    def test_failed_handshake_never_generates_connected_response(self):
        async def check():
            async def upstream(_):
                raise ConnectionError("rejected")
                yield
            with patch.object(WebcastConnect, "__aiter__", upstream):
                connector = object.__new__(CompatibleWebcastConnect)
                with self.assertRaises(ConnectionError):
                    await anext(connector.__aiter__())
        asyncio.run(check())

    def test_cancel_connection_cleans_up_without_nested_event_loop(self):
        async def check():
            client = TikTokLiveClient("tester")
            ready = asyncio.Event()
            async def receive():
                ready.set()
                await asyncio.Event().wait()
            async def start(**kwargs):
                client._event_loop_task = asyncio.create_task(receive())
                return client._event_loop_task
            with patch.object(client, "start", start), patch.object(client._ws, "disconnect", AsyncMock()):
                connected = asyncio.create_task(client.connect())
                await ready.wait()
                receiver = client._event_loop_task
                connected.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await connected
                self.assertTrue(receiver.done())
                self.assertIsNone(client._event_loop_task)
            await client.close()
        asyncio.run(check())
