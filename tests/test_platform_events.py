import json
import unittest

from bots.kick import KickBot
from bots.twitch import TwitchBot


class PlatformEventTests(unittest.TestCase):
    def test_kick_follow_payload_emits_normalized_event(self):
        bot = KickBot("channel")
        bot.running = True
        received = []
        bot.new_event.connect(received.append)

        bot.handle_event(json.dumps({
            "event": "App\\Events\\FollowerEvent",
            "sender": {"username": "alice"},
        }))

        self.assertEqual(received[0]["type"], "follow")
        self.assertEqual(received[0]["data"]["user"], "alice")

    def test_kick_events_are_ignored_after_stop(self):
        bot = KickBot("channel")
        received = []
        bot.new_event.connect(received.append)
        bot.handle_event({"event": "FollowerEvent"})
        self.assertEqual(received, [])

    def test_kick_event_name_from_pusher_is_used_for_mapping(self):
        bot = KickBot("channel")
        bot.running = True
        received = []
        bot.new_event.connect(received.append)
        bot.handle_event({"sender": {"username": "alice"}, "id": "tip-1"}, "App\\Events\\TipEvent")
        self.assertEqual(received[0]["type"], "donation")
        self.assertEqual(received[0]["data"]["eventId"], "tip-1")

    def test_twitch_bits_in_privmsg_emit_event(self):
        bot = TwitchBot("channel")
        received = []
        bot.new_event.connect(received.append)
        bot._handle_bits("@badges=;bits=100;display-name=alice;id=bits-1 :alice!u@h PRIVMSG #channel :hello")
        self.assertEqual(received[0]["type"], "bits")
        self.assertEqual(received[0]["data"]["amount"], "100")

if __name__ == "__main__":
    unittest.main()
