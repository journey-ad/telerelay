import tempfile
import sqlite3
import unittest
from pathlib import Path

from backend.stats_db import StatsDB


class StatsDBTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = StatsDB(Path(self.temp_dir.name) / "stats.db")

    def test_history_round_trips_entities_json(self):
        self.database.insert_history(
            rule_name="规则A",
            content="看 https://example.com 和 alice@example.com",
            media_type="text",
            entities=(
                '[{"type": "url", "offset": 2, "length": 18, "url": null}, '
                '{"type": "email", "offset": 22, "length": 17, "url": null}]'
            ),
        )
        self.database.insert_history(
            rule_name="规则A",
            content="无实体消息",
            media_type="text",
            entities=None,
        )

        rows, total = self.database.query_history(rule_name="规则A")

        self.assertEqual(total, 2)
        # Match rows by content instead of relying on row order: forwarded_at
        # has millisecond precision, so two records inserted in the same
        # millisecond would make a position-based assertion flaky.
        by_content = {row["content"]: row["entities"] for row in rows}
        self.assertEqual(
            by_content["看 https://example.com 和 alice@example.com"],
            [
                {"type": "url", "offset": 2, "length": 18, "url": None},
                {"type": "email", "offset": 22, "length": 17, "url": None},
            ],
        )
        self.assertIsNone(by_content["无实体消息"])

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

    def test_hourly_stats_and_media_distribution_can_be_filtered(self):
        self.database.increment_forwarded("news")
        self.database.increment_filtered("news")
        self.database.increment_failed("news")
        self.database.increment_button_action("automation")
        self.database.insert_history(rule_name="news", content="text", media_type="text")
        self.database.insert_history(rule_name="news", content="photo", media_type="photo")

        hourly = self.database.get_hourly_stats(24, "news")
        self.assertEqual(len(hourly), 1)
        self.assertEqual(hourly[0]["forwarded"], 1)
        self.assertEqual(hourly[0]["filtered"], 1)
        self.assertEqual(hourly[0]["failed"], 1)
        self.assertEqual(
            self.database.get_media_type_stats(1, "news"),
            [{"media_type": "photo", "count": 1}, {"media_type": "text", "count": 1}],
        )
        self.assertEqual(self.database.get_button_action_hourly(24, "automation")[0]["triggered"], 1)

    def test_legacy_daily_stats_are_backfilled_into_hourly_stats(self):
        legacy_path = Path(self.temp_dir.name) / "legacy.db"
        with sqlite3.connect(legacy_path) as connection:
            connection.execute(
                """
                CREATE TABLE daily_stats (
                    rule_name TEXT NOT NULL,
                    date TEXT NOT NULL,
                    forwarded_count INTEGER DEFAULT 0,
                    filtered_count INTEGER DEFAULT 0
                )
                """
            )
            connection.executemany(
                "INSERT INTO daily_stats VALUES (?, ?, ?, ?)",
                [("legacy", "2026-08-01", 10, 4), ("legacy", "2026-08-02", 3, 2)],
            )

        database = StatsDB(legacy_path)

        self.assertEqual(
            database.get_hourly_stats(None, "legacy"),
            [
                {
                    "hour": "2026-08-01 00:00",
                    "forwarded": 10,
                    "filtered": 4,
                    "failed": 0,
                },
                {
                    "hour": "2026-08-02 00:00",
                    "forwarded": 3,
                    "filtered": 2,
                    "failed": 0,
                },
            ],
        )

        with database._get_conn() as connection:
            connection.execute(
                "DELETE FROM hourly_stats WHERE rule_name = ? AND hour = ?",
                ("legacy", "2026-08-03 00:00"),
            )
            connection.execute(
                """
                INSERT INTO hourly_stats
                    (rule_name, hour, forwarded_count, filtered_count, failed_count)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(rule_name, hour) DO UPDATE SET
                    forwarded_count = forwarded_count + excluded.forwarded_count,
                    filtered_count = filtered_count + excluded.filtered_count
                """,
                ("legacy", "2026-08-03 12:00", 2, 1, 0),
            )
            connection.execute(
                "INSERT INTO daily_stats VALUES (?, ?, ?, ?)",
                ("legacy", "2026-08-03", 5, 4),
            )

        with database._get_conn() as connection:
            database._backfill_hourly_from_daily(connection)
            database._backfill_hourly_from_daily(connection)
        self.assertEqual(
            next(
                item
                for item in database.get_hourly_stats(None, "legacy")
                if item["hour"] == "2026-08-03 00:00"
            ),
            {
                "hour": "2026-08-03 00:00",
                "forwarded": 3,
                "filtered": 3,
                "failed": 0,
            },
        )

    def test_legacy_button_action_totals_are_backfilled_into_hourly_stats(self):
        legacy_path = Path(self.temp_dir.name) / "legacy-buttons.db"
        with sqlite3.connect(legacy_path) as connection:
            connection.execute(
                "CREATE TABLE button_action_stats (rule_name TEXT PRIMARY KEY, trigger_count INTEGER NOT NULL)"
            )
            connection.execute(
                "INSERT INTO button_action_stats VALUES (?, ?)",
                ("legacy-button", 5),
            )

        database = StatsDB(legacy_path)
        self.assertEqual(
            database.get_button_action_hourly(None, "legacy-button")[0]["triggered"],
            5,
        )

        with database._get_conn() as connection:
            connection.execute(
                "UPDATE button_action_stats SET trigger_count = 8 WHERE rule_name = ?",
                ("legacy-button",),
            )
            database._backfill_button_action_hourly(connection)
            database._backfill_button_action_hourly(connection)

        self.assertEqual(
            sum(
                item["triggered"]
                for item in database.get_button_action_hourly(None, "legacy-button")
            ),
            8,
        )


if __name__ == "__main__":
    unittest.main()
