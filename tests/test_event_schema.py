import unittest

from core.event_schema import EVENT_TYPES, normalize_event


class EventSchemaTests(unittest.TestCase):
    def test_common_top_level_fields_are_available_inside_data(self):
        event = normalize_event({
            "type": "Super Chat",
            "platform": "youtube",
            "userName": "alice",
            "text": "Obrigado!",
            "amountString": "R$ 10,00",
            "durationMs": 6000,
        })

        self.assertEqual(event["type"], "superchat")
        self.assertEqual(event["data"]["user"], "alice")
        self.assertEqual(event["data"]["displayName"], "alice")
        self.assertEqual(event["data"]["message"], "Obrigado!")
        self.assertEqual(event["data"]["amount"], "R$ 10,00")
        self.assertEqual(event["data"]["duration"], 6000)

    def test_existing_event_data_wins_over_adapter_aliases(self):
        event = normalize_event({
            "type": "gift",
            "user": "adapter-name",
            "data": {"user": "canonical-name", "message": "Rose", "count": 2},
        })

        self.assertEqual(event["data"]["user"], "canonical-name")
        self.assertEqual(event["data"]["message"], "Rose")
        self.assertEqual(event["data"]["count"], 2)

    def test_event_type_aliases_use_the_catalog_name(self):
        event = normalize_event({"type": "Super Chat", "platform": "youtube"})
        self.assertEqual(event["type"], "superchat")

    def test_catalog_types_are_stable(self):
        normalized = {normalize_event({"type": value})["type"] for value in EVENT_TYPES}
        self.assertEqual(normalized, set(EVENT_TYPES))


if __name__ == "__main__":
    unittest.main()
