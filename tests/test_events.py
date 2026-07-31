import unittest

from backend.events import EventBus


class EventBusTests(unittest.TestCase):
    def test_recent_is_bounded_newest_first_and_excludes_logs(self):
        events = EventBus(history_size=2)

        events.publish("bot", {"action": "start"})
        events.publish("log", {"message": "noise"})
        events.publish("forward", {"status": "completed"})
        events.publish("stats", {"action": "reset"})

        recent = events.recent(10)
        self.assertEqual([event["type"] for event in recent], ["stats", "forward"])
        self.assertEqual([event["id"] for event in recent], [4, 3])
        self.assertEqual(events.recent(0), [])

    def test_recent_filters_types_before_applying_limit(self):
        events = EventBus()
        events.publish("bot", {"action": "start"})
        events.publish("stats", {"action": "reset"})
        events.publish("forward", {"status": "completed"})

        recent = events.recent(1, {"bot", "stats"})

        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["type"], "stats")


if __name__ == "__main__":
    unittest.main()
