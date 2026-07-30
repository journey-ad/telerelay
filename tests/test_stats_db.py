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


if __name__ == "__main__":
    unittest.main()
