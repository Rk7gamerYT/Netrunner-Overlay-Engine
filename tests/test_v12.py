import unittest

import engine
from core.base_bot import BaseBot
from main import DesktopAPI
from ui.web_dashboard import WebDashboardController


class FakeBot(BaseBot):
    def run(self):
        self.running = True
        self.new_message.emit("tester", "hello", "twitch")


class ThreadBridgeTests(unittest.TestCase):
    def test_bot_signals_and_finished_event(self):
        received = []
        finished = []
        bot = FakeBot("channel")
        bot.new_message.connect(lambda *args: received.append(args))
        bot.finished.connect(lambda: finished.append(True))
        bot.start()
        self.assertTrue(bot.wait(1000))
        self.assertEqual(received, [("tester", "hello", "twitch")])
        self.assertEqual(finished, [True])

    def test_desktop_api_does_not_expose_native_objects(self):
        class FakeProcess:
            def is_alive(self):
                return False

        api = DesktopAPI(FakeProcess())
        public_data = [
            name for name in dir(api)
            if not name.startswith("_") and not callable(getattr(api, name))
        ]
        self.assertEqual(public_data, [])


class DashboardTests(unittest.TestCase):
    def setUp(self):
        with engine.CHAT_LOCK:
            engine.CHAT_MESSAGES.clear()
        self.app = WebDashboardController()
        engine.set_dashboard_controller(self.app)

    def tearDown(self):
        self.app.shutdown()
        engine.set_dashboard_controller(None)

    def test_message_updates_dashboard_and_overlay_queue(self):
        self.app._receive_message("Alice", "Oi", "twitch")
        state = self.app.snapshot()
        self.assertEqual(state["platforms"]["twitch"]["count"], 1)
        self.assertEqual(state["messages"][-1]["message"], "Oi")
        with engine.CHAT_LOCK:
            self.assertEqual(engine.CHAT_MESSAGES[-1]["message"], "Oi")

    def test_overlay_editor_and_real_preview_routes(self):
        result = self.app.apply_overlay({"html": "<div>v1.2</div>", "css": "body{}", "js": ""})
        self.assertTrue(result["ok"])
        client = engine.app.test_client()
        dashboard_response = client.get("/dashboard")
        self.assertEqual(dashboard_response.status_code, 200)
        dashboard_response.close()
        response = client.get("/overlay")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"<div>v1.2</div>", response.data)
        response.close()
        self.assertEqual(client.get("/api/state").status_code, 200)


if __name__ == "__main__":
    unittest.main()
