import os
import tempfile
import unittest

import engine
from core.base_bot import BaseBot
from bots.youtube import YouTubeBot
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
        self.temp_dir = tempfile.TemporaryDirectory()
        self.overlay_config_path = os.path.join(self.temp_dir.name, "overlay.json")
        self.channels_config_path = os.path.join(self.temp_dir.name, "channels.json")
        self.app = WebDashboardController(self.overlay_config_path, self.channels_config_path)
        engine.set_dashboard_controller(self.app)

    def tearDown(self):
        self.app.shutdown()
        engine.set_dashboard_controller(None)
        self.temp_dir.cleanup()

    def test_message_updates_dashboard_and_overlay_queue(self):
        self.app._receive_message("Alice", "Oi", "twitch")
        state = self.app.snapshot()
        self.assertEqual(state["platforms"]["twitch"]["count"], 1)
        self.assertEqual(state["messages"][-1]["message"], "Oi")
        with engine.CHAT_LOCK:
            self.assertEqual(engine.CHAT_MESSAGES[-1]["message"], "Oi")

    def test_overlay_editor_and_real_preview_routes(self):
        for platform in ("twitch", "youtube", "tiktok", "kick"):
            self.assertIn(f"/assets/platforms/{platform}.png", engine.DEFAULT_LIVE_JS)
        result = self.app.apply_overlay({"html": "<div>v1.2</div>", "css": "body{}", "js": ""})
        self.assertTrue(result["ok"])
        self.assertTrue(os.path.isfile(self.overlay_config_path))
        self.assertTrue(self.app.overlay_source()["saved"])
        self.app.shutdown()
        self.app = WebDashboardController(self.overlay_config_path, self.channels_config_path)
        engine.set_dashboard_controller(self.app)
        self.assertEqual(self.app.overlay_source()["html"], "<div>v1.2</div>")
        client = engine.app.test_client()
        dashboard_response = client.get("/dashboard")
        self.assertEqual(dashboard_response.status_code, 200)
        dashboard_html = dashboard_response.get_data(as_text=True)
        self.assertIn('id="languageSelect"', dashboard_html)
        self.assertIn("'netrunner.language'", dashboard_html)
        for language in ("pt", "en", "es", "fr"):
            self.assertIn(f'<option value="{language}">', dashboard_html)
        dashboard_response.close()
        response = client.get("/overlay")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"<div>v1.2</div>", response.data)
        response.close()
        self.assertEqual(client.get("/api/state").status_code, 200)
        for platform in ("twitch", "youtube", "tiktok", "kick"):
            icon_response = client.get(f"/assets/platforms/{platform}.png")
            self.assertEqual(icon_response.status_code, 200)
            self.assertEqual(icon_response.mimetype, "image/png")
            icon_response.close()

    def test_platform_channels_are_saved_and_loaded(self):
        result = self.app.save_channels({
            "youtube": " @ rk7 gamer yt ",
            "tiktok": " @ zykagames ",
        })
        self.assertTrue(result["ok"])
        self.app.shutdown()
        self.app = WebDashboardController(self.overlay_config_path, self.channels_config_path)
        state = self.app.snapshot()
        self.assertEqual(state["platforms"]["youtube"]["channel"], "@rk7gameryt")
        self.assertEqual(state["platforms"]["tiktok"]["channel"], "@zykagames")

    def test_disconnect_status_does_not_match_connected_substring(self):
        self.app._receive_status("tiktok", "TikTok conectado: @tester")
        self.assertTrue(self.app.snapshot()["platforms"]["tiktok"]["connected"])
        self.app._receive_status("tiktok", "TikTok desconectado.")
        self.assertFalse(self.app.snapshot()["platforms"]["tiktok"]["connected"])

    def test_youtube_accepts_handle_without_spaces(self):
        calls = []

        class FakeResponse:
            text = '<link rel="canonical" href="https://www.youtube.com/watch?v=abc12345678">'

            def raise_for_status(self):
                return None

        import bots.youtube as youtube_module
        saved_get = youtube_module.requests.get
        youtube_module.requests.get = lambda url, **kwargs: (calls.append(url) or FakeResponse())
        try:
            self.assertEqual(YouTubeBot.resolve_video_id(" @ rk7 gamer yt "), "abc12345678")
        finally:
            youtube_module.requests.get = saved_get
        self.assertEqual(calls, ["https://www.youtube.com/@rk7gameryt/live"])


if __name__ == "__main__":
    unittest.main()
