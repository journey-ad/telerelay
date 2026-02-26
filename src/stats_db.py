"""
Statistics Database Module
Uses SQLite to persist forwarding statistics (forwarded count, filtered count, etc.)
"""
import sqlite3
import threading
from pathlib import Path
from src.logger import get_logger

logger = get_logger()

DB_PATH = Path("data/stats.db")


class StatsDB:
    """SQLite-based persistent statistics storage"""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()

        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Create a new connection (sqlite3 connections are not thread-safe)"""
        return sqlite3.connect(str(self.db_path))

    def _init_db(self) -> None:
        """Initialize database schema"""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS rule_stats (
                        rule_name TEXT PRIMARY KEY,
                        forwarded_count INTEGER NOT NULL DEFAULT 0,
                        filtered_count INTEGER NOT NULL DEFAULT 0
                    )
                """)
                conn.commit()
            finally:
                conn.close()

    def get_stats(self, rule_name: str) -> dict:
        """Get statistics for a specific rule"""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    "SELECT forwarded_count, filtered_count FROM rule_stats WHERE rule_name = ?",
                    (rule_name,)
                )
                row = cursor.fetchone()
                if row:
                    return {"forwarded": row[0], "filtered": row[1]}
                return {"forwarded": 0, "filtered": 0}
            finally:
                conn.close()

    def get_all_stats(self) -> dict:
        """Get statistics for all rules"""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    "SELECT rule_name, forwarded_count, filtered_count FROM rule_stats"
                )
                result = {}
                for row in cursor.fetchall():
                    result[row[0]] = {"forwarded": row[1], "filtered": row[2]}
                return result
            finally:
                conn.close()

    def increment_forwarded(self, rule_name: str) -> None:
        """Increment forwarded count for a rule"""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("""
                    INSERT INTO rule_stats (rule_name, forwarded_count, filtered_count)
                    VALUES (?, 1, 0)
                    ON CONFLICT(rule_name) DO UPDATE SET
                        forwarded_count = forwarded_count + 1
                """, (rule_name,))
                conn.commit()
            finally:
                conn.close()

    def increment_filtered(self, rule_name: str) -> None:
        """Increment filtered count for a rule"""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("""
                    INSERT INTO rule_stats (rule_name, forwarded_count, filtered_count)
                    VALUES (?, 0, 1)
                    ON CONFLICT(rule_name) DO UPDATE SET
                        filtered_count = filtered_count + 1
                """, (rule_name,))
                conn.commit()
            finally:
                conn.close()

    def reset_stats(self, rule_name: str = None) -> None:
        """Reset statistics. If rule_name is None, reset all rules."""
        with self._lock:
            conn = self._get_conn()
            try:
                if rule_name:
                    conn.execute(
                        "UPDATE rule_stats SET forwarded_count = 0, filtered_count = 0 WHERE rule_name = ?",
                        (rule_name,)
                    )
                else:
                    conn.execute(
                        "UPDATE rule_stats SET forwarded_count = 0, filtered_count = 0"
                    )
                conn.commit()
            finally:
                conn.close()

    def rename_rule(self, old_name: str, new_name: str) -> None:
        """Rename a rule in the stats database"""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "UPDATE rule_stats SET rule_name = ? WHERE rule_name = ?",
                    (new_name, old_name)
                )
                conn.commit()
            finally:
                conn.close()

    def delete_rule(self, rule_name: str) -> None:
        """Delete statistics for a rule"""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "DELETE FROM rule_stats WHERE rule_name = ?",
                    (rule_name,)
                )
                conn.commit()
            finally:
                conn.close()


# Singleton instance
_stats_db: StatsDB = None
_stats_db_lock = threading.Lock()


def get_stats_db() -> StatsDB:
    """Get the global StatsDB singleton"""
    global _stats_db
    if _stats_db is None:
        with _stats_db_lock:
            if _stats_db is None:
                _stats_db = StatsDB()
    return _stats_db
