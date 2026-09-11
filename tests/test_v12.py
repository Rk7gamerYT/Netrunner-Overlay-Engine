import os
import base64
import tempfile
import time
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
        self.assertIsInstance(state["platforms"]["twitch"]["lastActivity"], int)
        with engine.CHAT_LOCK:
            self.assertEqual(engine.CHAT_MESSAGES[-1]["message"], "Oi")

    def test_message_delete_removes_dashboard_and_overlay_history(self):
        self.app._receive_message("Alice", "Indesejada", "twitch")
        self.app._receive_message("Bob", "Mantém", "youtube")
        message_id = self.app.snapshot()["messages"][0]["id"]

        result = self.app.moderate({"action": "delete_message", "messageId": message_id})

        self.assertTrue(result["ok"])
        self.assertEqual(
            [message["message"] for message in self.app.snapshot()["messages"]],
            ["Mantém"],
        )
        with engine.CHAT_LOCK:
            self.assertNotIn(message_id, [message.get("id") for message in engine.CHAT_MESSAGES])
            tombstones = [message for message in engine.CHAT_MESSAGES if message.get("type") == "message_delete"]
        self.assertEqual(len(tombstones), 1)
        self.assertEqual(tombstones[0]["messageId"], message_id)
        self.assertIn("message_delete", engine.DEFAULT_LIVE_JS)

        missing = self.app.moderate({"action": "delete_message", "messageId": message_id})
        self.assertFalse(missing["ok"])

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
        dashboard_response = client.get(engine.dashboard_url())
        self.assertEqual(dashboard_response.status_code, 200)
        dashboard_html = dashboard_response.get_data(as_text=True)
        self.assertIn('id="languageSelect"', dashboard_html)
        self.assertIn("'netrunner.language'", dashboard_html)
        for language in ("pt", "en", "es", "fr"):
            self.assertIn(f'<option value="{language}">', dashboard_html)
        dashboard_response.close()
        response = client.get(engine.overlay_url("chat"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"<div>v1.2</div>", response.data)
        response.close()
        self.assertEqual(client.get("/api/state", headers={"X-Netrunner-Admin-Token": engine.admin_token()}).status_code, 200)
        for platform in ("twitch", "youtube", "tiktok", "kick"):
            icon_response = client.get(f"/assets/platforms/{platform}.png")
            self.assertEqual(icon_response.status_code, 200)
            self.assertEqual(icon_response.mimetype, "image/png")
            icon_response.close()

    def test_overlay_validation_rejects_broken_css_and_accepts_valid_source(self):
        invalid = self.app.validate_overlay({"html": "<div></div>", "css": "body{", "js": ""})
        self.assertFalse(invalid["valid"])
        self.assertIn("CSS", invalid["errors"][0])
        valid = self.app.validate_overlay({"html": "<div></div>", "css": "body{}", "js": "const value = 1;"})
        self.assertTrue(valid["valid"])

    def test_overlay_history_can_restore_applied_version(self):
        result = self.app.apply_overlay({"html": "<div>history</div>", "css": "body{}", "js": ""})
        self.assertTrue(result["ok"])
        history = self.app.list_overlay_history("chat")
        self.assertTrue(history)
        restored = self.app.load_overlay_history("chat", history[0])
        self.assertTrue(restored["ok"])
        self.assertEqual(restored["html"], "<div>history</div>")

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

    def test_platform_registry_exposes_event_capabilities(self):
        registry = self.app.platform_registry()
        self.assertIn("bits", registry["twitch"]["events"])
        self.assertIn("superchat", registry["youtube"]["events"])
        self.assertIn("gift", registry["tiktok"]["events"])
        self.assertIn("follow", registry["kick"]["events"])
        self.assertIn("heartbeat", registry["twitch"])

    def test_overlay_templates_include_optional_editable_themes(self):
        templates = self.app.overlay_templates()
        self.assertEqual(templates["chat-minimal"]["target"], "chat")
        self.assertEqual(templates["events-minimal"]["target"], "events")
        self.assertIn("#log", templates["chat-minimal"]["css"])

    def test_asset_library_accepts_allowed_files_and_exposes_local_url(self):
        encoded = base64.b64encode(b"asset-test").decode("ascii")
        result = self.app.save_asset("my alert.PNG", encoded)
        self.assertTrue(result["ok"])
        self.assertEqual(result["name"], "my-alert.png")
        self.assertEqual(self.app.list_assets()[0]["url"], "/overlay-assets/my-alert.png")
        client = engine.app.test_client()
        assets_response = client.get("/api/assets", headers={"X-Netrunner-Admin-Token": engine.admin_token()})
        self.assertEqual(assets_response.status_code, 200)
        self.assertEqual(assets_response.json["items"][0]["mimeType"], "image/png")
        assets_response.close()
        asset_response = client.get("/overlay-assets/my-alert.png")
        self.assertEqual(asset_response.status_code, 200)
        self.assertEqual(asset_response.data, b"asset-test")
        self.assertEqual(asset_response.mimetype, "image/png")
        asset_response.close()
        rejected = self.app.save_asset("script.exe", encoded)
        self.assertFalse(rejected["ok"])

    def test_event_overlay_exposes_free_audio_and_tts_contract(self):
        self.assertIn("AudioManager", engine.DEFAULT_EVENT_JS)
        self.assertIn("window.NetrunnerTTS", engine.DEFAULT_EVENT_JS)
        self.assertIn("cooldownMs", engine.DEFAULT_EVENT_JS)
        self.assertIn("data.priority", engine.DEFAULT_EVENT_JS)

    def test_diagnostics_exposes_health_and_resilience_run(self):
        health = self.app.diagnostics_snapshot()
        self.assertTrue(health["server"]["http"])
        self.assertEqual(health["queue"]["capacity"], 2000)
        started = self.app.start_diagnostic(5)
        self.assertTrue(started["ok"])
        self.assertEqual(started["diagnostic"]["status"], "running")
        deadline = time.time() + 7
        while time.time() < deadline:
            if self.app.diagnostics_snapshot()["diagnostic"]["status"] == "completed":
                break
            time.sleep(0.1)
        self.assertEqual(self.app.diagnostics_snapshot()["diagnostic"]["status"], "completed")
        client = engine.app.test_client()
        response = client.get("/api/diagnostics", headers={"X-Netrunner-Admin-Token": engine.admin_token()})
        self.assertEqual(response.status_code, 200)
        self.assertIn("diagnostic", response.json)

    def test_admin_and_overlay_tokens_enforce_scope_and_rotation(self):
        client = engine.app.test_client()
        self.assertEqual(client.get("/api/state").status_code, 401)
        self.assertEqual(client.get("/dashboard").status_code, 401)

        admin_headers = {"X-Netrunner-Admin-Token": engine.admin_token()}
        old_url = engine.overlay_url("chat")
        self.assertEqual(client.get(old_url).status_code, 200)
        websocket_path = old_url.replace("http://127.0.0.1:5000/overlay", "/ws/chat")
        self.assertTrue(engine.authorize_overlay_path("chat", websocket_path))
        self.assertFalse(engine.authorize_overlay_path("chat", "/ws/chat?token=invalid"))
        rotated = client.post(
            "/api/security/tokens",
            json={"kind": "chat", "action": "rotate"},
            headers=admin_headers,
        )
        self.assertEqual(rotated.status_code, 200)
        self.assertEqual(client.get(old_url).status_code, 401)
        new_url = engine.overlay_url("chat")
        self.assertNotEqual(old_url, new_url)
        self.assertEqual(client.get(new_url).status_code, 200)

        revoked = client.post(
            "/api/security/tokens",
            json={"kind": "chat", "action": "revoke"},
            headers=admin_headers,
        )
        self.assertEqual(revoked.status_code, 200)
        self.assertEqual(client.get(new_url).status_code, 401)
        self.assertEqual(client.get(engine.overlay_url("events")).status_code, 200)

    def test_external_content_is_bounded_and_invalid_queue_records_are_logged(self):
        self.app._receive_message("Alice\x00", "x\x00" * 5000, "twitch")
        message = self.app.snapshot()["messages"][-1]
        self.assertNotIn("\x00", message["message"])
        self.assertLessEqual(len(message["message"]), 4000)
        self.app._receive_event({}, "invalid-platform")
        self.assertIn("plataforma inválida", self.app.snapshot()["logs"][-1]["text"])

    def test_disconnect_status_does_not_match_connected_substring(self):
        self.app._receive_status("tiktok", "TikTok conectado: @tester")
        self.assertTrue(self.app.snapshot()["platforms"]["tiktok"]["connected"])
        self.app._receive_status("tiktok", "TikTok desconectado.")
        self.assertFalse(self.app.snapshot()["platforms"]["tiktok"]["connected"])

    def test_duplicate_platform_event_is_published_once(self):
        event = {
            "type": "sub",
            "eventId": "twitch-123",
            "data": {"user": "Alice", "title": "Nova inscrição"},
        }
        self.app._receive_event(event, "twitch")
        self.app._receive_event(event, "twitch")
        self.assertEqual(len(self.app.snapshot()["events"]), 1)

        event["eventId"] = "twitch-124"
        self.app._receive_event(event, "twitch")
        self.assertEqual(len(self.app.snapshot()["events"]), 2)

    def test_test_event_uses_the_same_event_pipeline(self):
        result = self.app.test_event({"platform": "youtube", "type": "super_chat"})
        self.assertTrue(result["ok"])
        event = self.app.snapshot()["events"][-1]
        self.assertEqual(event["platform"], "youtube")
        self.assertEqual(event["type"], "superchat")
        self.assertEqual(event["data"]["user"], "Netrunner Test")
        self.assertEqual(event["data"]["amount"], "R$ 10,00")

    def test_invalid_overlay_is_not_applied(self):
        before = self.app.overlay_source()["html"]
        result = self.app.apply_overlay({"html": "<div></div>", "css": "body{", "js": ""})
        self.assertFalse(result["ok"])
        self.assertEqual(self.app.overlay_source()["html"], before)

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
