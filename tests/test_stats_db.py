import tempfile
import unittest
from pathlib import Path

from backend.stats_db import StatsDB


class StatsDBTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = StatsDB(Path(self.temp_dir.name) / "stats.db")

    def test_all_time_daily_stats_are_not_limited_by_date(self):
        with self.database._get_conn() as connection:
            connection.executemany(
                """
                INSERT INTO daily_stats (rule_name, date, forwarded_count, filtered_count)
                VALUES (?, ?, ?, ?)
                """,
                [
                    ("rule", "2020-01-01", 2, 1),
                    ("rule", "2026-07-30", 4, 3),
                ],
            )

        all_time = self.database.get_daily_stats(None)
        recent = self.database.get_daily_stats(365)

        self.assertEqual([item["date"] for item in all_time], ["2020-01-01", "2026-07-30"])
        self.assertEqual([item["date"] for item in recent], ["2026-07-30"])

    def test_button_action_stats_increment_rename_reset_and_delete(self):
        self.database.increment_button_action("签到")
        self.database.increment_button_action("签到")
        self.database.increment_button_action("其他")

        self.assertEqual(
            {
                item["rule_name"]: item["triggered"]
                for item in self.database.get_button_action_stats()
            },
            {"签到": 2, "其他": 1},
        )

        self.database.rename_button_rule("签到", "每日签到")
        self.database.reset_button_action_stats("其他")
        self.database.delete_button_rule("每日签到")

        self.assertEqual(
            self.database.get_button_action_stats(),
            [{"rule_name": "其他", "triggered": 0}],
        )


if __name__ == "__main__":
    unittest.main()
