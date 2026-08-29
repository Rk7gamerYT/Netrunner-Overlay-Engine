import unittest

import dearpygui.dearpygui as dpg

import engine
from core.base_bot import BaseBot
from ui.dashboard import DashboardApp


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


class DashboardTests(unittest.TestCase):
    def setUp(self):
        dpg.create_context()
        with engine.CHAT_LOCK:
            engine.CHAT_MESSAGES.clear()
        self.app = DashboardApp()
        self.app._start_server = lambda: None
        self.app.build()

    def tearDown(self):
        self.app.shutdown()
        dpg.destroy_context()

    def test_message_updates_dashboard_and_overlay_queue(self):
        self.app.events.put(("message", "Alice", "Oi", "twitch"))
        self.app.tick()
        self.assertEqual(dpg.get_value("count_twitch"), "1 mensagens")
        self.assertEqual(len(self.app.messages), 1)
        with engine.CHAT_LOCK:
            self.assertEqual(engine.CHAT_MESSAGES[-1]["message"], "Oi")

    def test_navigation_and_overlay_editor(self):
        self.app._switch_page(user_data="platforms")
        self.assertTrue(dpg.is_item_shown("page_platforms"))
        dpg.set_value("editor_html", "<div>v1.2</div>")
        self.app.apply_overlay()
        self.assertEqual(engine.LIVE_HTML, "<div>v1.2</div>")


if __name__ == "__main__":
    unittest.main()
