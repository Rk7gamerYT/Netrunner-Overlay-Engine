import asyncio
import json
import unittest

from websockets.asyncio.client import connect

from core.realtime_gateway import LocalRealtimeGateway


class RealtimeGatewayTests(unittest.TestCase):
    def test_events_are_published_to_connected_clients(self):
        gateway = LocalRealtimeGateway(port=0)
        self.assertTrue(gateway.start())

        async def exercise_client():
            uri = f"ws://127.0.0.1:{gateway.port}/ws/events"
            async with connect(uri) as websocket:
                hello = json.loads(await asyncio.wait_for(websocket.recv(), timeout=2))
                self.assertEqual(hello, {"type": "hello", "topic": "events"})

                payload = {"id": 1, "type": "gift", "data": {"message": "test"}}
                self.assertTrue(gateway.publish("events", payload))
                self.assertEqual(json.loads(await asyncio.wait_for(websocket.recv(), timeout=2)), payload)

        try:
            asyncio.run(exercise_client())
        finally:
            gateway.stop()

    def test_events_are_replayed_after_last_id(self):
        gateway = LocalRealtimeGateway(port=0, history_size=5)
        self.assertTrue(gateway.start())
        payloads = [
            {"id": 1, "type": "follow", "data": {}},
            {"id": 2, "type": "gift", "data": {}},
            {"id": 3, "type": "share", "data": {}},
        ]

        async def exercise_client():
            for payload in payloads:
                self.assertTrue(gateway.publish("events", payload))
            await asyncio.sleep(0.05)
            uri = f"ws://127.0.0.1:{gateway.port}/ws/events?after=1"
            async with connect(uri) as websocket:
                self.assertEqual(json.loads(await websocket.recv())["type"], "hello")
                replayed = [json.loads(await websocket.recv()), json.loads(await websocket.recv())]
                self.assertEqual(replayed, payloads[1:])

        try:
            asyncio.run(exercise_client())
        finally:
            gateway.stop()

    def test_source_of_truth_fills_history_after_gateway_buffer_is_gone(self):
        source = [
            {"id": 1, "type": "follow", "data": {}},
            {"id": 2, "type": "gift", "data": {}},
        ]
        gateway = LocalRealtimeGateway(
            port=0,
            history_size=1,
            history_provider=lambda topic, after: [item for item in source if item["id"] > after],
        )
        self.assertTrue(gateway.start())

        async def exercise_client():
            self.assertTrue(gateway.publish("events", source[-1]))
            await asyncio.sleep(0.05)
            uri = f"ws://127.0.0.1:{gateway.port}/ws/events?after=0"
            async with connect(uri) as websocket:
                await websocket.recv()
                replayed = [json.loads(await websocket.recv()), json.loads(await websocket.recv())]
                self.assertEqual(replayed, source)

        try:
            asyncio.run(exercise_client())
        finally:
            gateway.stop()


if __name__ == "__main__":
    unittest.main()
