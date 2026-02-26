"""
Statistics Database Module
Uses SQLite to persist forwarding statistics, message history, and daily trends.
"""
import csv
import io
import json
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple, List
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
                # Original rule_stats table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS rule_stats (
                        rule_name TEXT PRIMARY KEY,
                        forwarded_count INTEGER NOT NULL DEFAULT 0,
                        filtered_count INTEGER NOT NULL DEFAULT 0
                    )
                """)

                # Message history table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS forwarded_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        rule_name TEXT NOT NULL,
                        message_id INTEGER,
                        source_chat_id INTEGER,
                        source_chat_name TEXT,
                        sender_id INTEGER,
                        sender_name TEXT,
                        sender_first_name TEXT,
                        sender_last_name TEXT,
                        sender_username TEXT,
                        content TEXT,
                        media_type TEXT,
                        forwarded_at TEXT DEFAULT (datetime('now', 'localtime'))
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_fm_forwarded_at ON forwarded_messages(forwarded_at)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_fm_rule ON forwarded_messages(rule_name)")

                # Daily stats table for trend charts
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS daily_stats (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        rule_name TEXT NOT NULL,
                        date TEXT NOT NULL,
                        forwarded_count INTEGER DEFAULT 0,
                        filtered_count INTEGER DEFAULT 0,
                        UNIQUE(rule_name, date)
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_ds_date ON daily_stats(date)")

                conn.commit()
            finally:
                conn.close()

    # ===== Original rule_stats methods =====

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
                conn.execute(
                    "UPDATE forwarded_messages SET rule_name = ? WHERE rule_name = ?",
                    (new_name, old_name)
                )
                conn.execute(
                    "UPDATE daily_stats SET rule_name = ? WHERE rule_name = ?",
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
                conn.execute(
                    "DELETE FROM forwarded_messages WHERE rule_name = ?",
                    (rule_name,)
                )
                conn.execute(
                    "DELETE FROM daily_stats WHERE rule_name = ?",
                    (rule_name,)
                )
                conn.commit()
            finally:
                conn.close()

    # ===== Message history methods =====

    def insert_history(
        self,
        rule_name: str,
        message_id: int = None,
        source_chat_id: int = None,
        source_chat_name: str = None,
        sender_id: int = None,
        sender_name: str = None,
        sender_first_name: str = None,
        sender_last_name: str = None,
        sender_username: str = None,
        content: str = None,
        media_type: str = None,
    ) -> None:
        """Insert a forwarded message history record"""
        now = datetime.now()
        forwarded_at = now.strftime("%Y-%m-%d %H:%M:%S.") + f"{now.microsecond // 1000:03d}"
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("""
                    INSERT INTO forwarded_messages
                    (rule_name, message_id, source_chat_id, source_chat_name,
                     sender_id, sender_name, sender_first_name, sender_last_name, sender_username,
                     content, media_type, forwarded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (rule_name, message_id, source_chat_id, source_chat_name,
                      sender_id, sender_name, sender_first_name, sender_last_name, sender_username,
                      content, media_type, forwarded_at))
                conn.commit()
            finally:
                conn.close()

    def query_history(
        self,
        rule_name: str = None,
        keyword: str = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[dict], int]:
        """
        Query forwarded message history with optional filters.

        Returns:
            (list of row dicts, total count matching the filter)
        """
        with self._lock:
            conn = self._get_conn()
            try:
                where_clauses = []
                params = []

                if rule_name:
                    where_clauses.append("rule_name = ?")
                    params.append(rule_name)
                if keyword:
                    where_clauses.append("(content LIKE ? OR source_chat_name LIKE ? OR sender_name LIKE ?)")
                    like = f"%{keyword}%"
                    params.extend([like, like, like])

                where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

                # Total count
                count_cursor = conn.execute(
                    f"SELECT COUNT(*) FROM forwarded_messages{where_sql}", params
                )
                total = count_cursor.fetchone()[0]

                # Query rows
                cursor = conn.execute(
                    f"SELECT id, rule_name, message_id, source_chat_id, source_chat_name, "
                    f"sender_id, sender_name, sender_first_name, sender_last_name, sender_username, "
                    f"content, media_type, forwarded_at "
                    f"FROM forwarded_messages{where_sql} "
                    f"ORDER BY forwarded_at DESC LIMIT ? OFFSET ?",
                    params + [limit, offset]
                )

                rows = []
                for row in cursor.fetchall():
                    rows.append({
                        "id": row[0],
                        "rule_name": row[1],
                        "message_id": row[2],
                        "source_chat_id": row[3],
                        "source_chat_name": row[4],
                        "sender_id": row[5],
                        "sender_name": row[6],
                        "sender_first_name": row[7],
                        "sender_last_name": row[8],
                        "sender_username": row[9],
                        "content": row[10],
                        "media_type": row[11],
                        "forwarded_at": row[12],
                    })

                return rows, total
            finally:
                conn.close()

    def export_history(
        self,
        rule_name: str = None,
        keyword: str = None,
        fmt: str = "csv",
    ) -> str:
        """
        Export message history as CSV, JSON, or HTML string.

        Args:
            rule_name: Optional rule name filter
            keyword: Optional keyword filter
            fmt: 'csv', 'json', or 'html'

        Returns:
            Formatted string content
        """
        # Fetch all matching records (no pagination)
        rows, _ = self.query_history(rule_name=rule_name, keyword=keyword, limit=100000, offset=0)

        if fmt == "json":
            return json.dumps(rows, ensure_ascii=False, indent=2)

        elif fmt == "html":
            if not rows:
                return "<html><body><p>No data</p></body></html>"
            headers = ["Time", "Rule", "Source", "SenderID", "Sender", "FirstName", "LastName", "Username", "Content", "Media"]
            html = "<html><head><meta charset='utf-8'><style>"
            html += "table{border-collapse:collapse;width:100%;font-family:sans-serif;}"
            html += "th,td{border:1px solid #ddd;padding:8px;text-align:left;}"
            html += "th{background:#4CAF50;color:white;}"
            html += "tr:nth-child(even){background:#f2f2f2;}"
            html += "</style></head><body><h2>TeleRelay Forwarding History</h2><table>"
            html += "<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>"
            for r in rows:
                html += "<tr>"
                html += f"<td>{r.get('forwarded_at', '')}</td>"
                html += f"<td>{r.get('rule_name', '')}</td>"
                html += f"<td>{r.get('source_chat_name', '')}</td>"
                html += f"<td>{r.get('sender_id', '')}</td>"
                html += f"<td>{r.get('sender_name', '')}</td>"
                html += f"<td>{r.get('sender_first_name', '')}</td>"
                html += f"<td>{r.get('sender_last_name', '')}</td>"
                html += f"<td>{r.get('sender_username', '')}</td>"
                html += f"<td>{r.get('content', '')}</td>"
                html += f"<td>{r.get('media_type', '')}</td>"
                html += "</tr>"
            html += "</table></body></html>"
            return html

        else:  # csv
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Time", "Rule", "MsgID", "SourceChatID", "Source",
                             "SenderID", "Sender", "FirstName", "LastName", "Username", "Content", "MediaType"])
            for r in rows:
                writer.writerow([
                    r.get("forwarded_at", ""),
                    r.get("rule_name", ""),
                    r.get("message_id", ""),
                    r.get("source_chat_id", ""),
                    r.get("source_chat_name", ""),
                    r.get("sender_id", ""),
                    r.get("sender_name", ""),
                    r.get("sender_first_name", ""),
                    r.get("sender_last_name", ""),
                    r.get("sender_username", ""),
                    r.get("content", ""),
                    r.get("media_type", ""),
                ])
            return output.getvalue()

    # ===== Daily stats methods =====

    def increment_daily(self, rule_name: str, is_forwarded: bool) -> None:
        """Increment today's daily counter for a rule"""
        today = datetime.now().strftime("%Y-%m-%d")
        col = "forwarded_count" if is_forwarded else "filtered_count"
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(f"""
                    INSERT INTO daily_stats (rule_name, date, forwarded_count, filtered_count)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(rule_name, date) DO UPDATE SET
                        {col} = {col} + 1
                """, (rule_name, today,
                      1 if is_forwarded else 0,
                      0 if is_forwarded else 1))
                conn.commit()
            finally:
                conn.close()

    def get_daily_stats(self, days: int = 30) -> List[dict]:
        """
        Get daily aggregated stats for the last N days.

        Returns:
            List of {date, forwarded, filtered} dicts, ordered by date ASC
        """
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute("""
                    SELECT date,
                           SUM(forwarded_count) as forwarded,
                           SUM(filtered_count) as filtered
                    FROM daily_stats
                    WHERE date >= ?
                    GROUP BY date
                    ORDER BY date ASC
                """, (since,))
                return [
                    {"date": row[0], "forwarded": row[1], "filtered": row[2]}
                    for row in cursor.fetchall()
                ]
            finally:
                conn.close()

    def get_rule_stats_detail(self) -> List[dict]:
        """
        Get per-rule statistics detail (for stats dashboard).

        Returns:
            List of {rule_name, forwarded, filtered, total} dicts
        """
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    "SELECT rule_name, forwarded_count, filtered_count FROM rule_stats ORDER BY rule_name"
                )
                return [
                    {
                        "rule_name": row[0],
                        "forwarded": row[1],
                        "filtered": row[2],
                        "total": row[1] + row[2],
                    }
                    for row in cursor.fetchall()
                ]
            finally:
                conn.close()

    def export_stats(self, fmt: str = "csv") -> str:
        """Export rule statistics as CSV, JSON, or HTML"""
        details = self.get_rule_stats_detail()

        if fmt == "json":
            return json.dumps(details, ensure_ascii=False, indent=2)

        elif fmt == "html":
            if not details:
                return "<html><body><p>No data</p></body></html>"
            html = "<html><head><meta charset='utf-8'><style>"
            html += "table{border-collapse:collapse;width:100%;font-family:sans-serif;}"
            html += "th,td{border:1px solid #ddd;padding:8px;text-align:left;}"
            html += "th{background:#2196F3;color:white;}"
            html += "tr:nth-child(even){background:#f2f2f2;}"
            html += "</style></head><body><h2>TeleRelay Statistics</h2><table>"
            html += "<tr><th>Rule</th><th>Forwarded</th><th>Filtered</th><th>Total</th></tr>"
            for r in details:
                html += f"<tr><td>{r['rule_name']}</td><td>{r['forwarded']}</td>"
                html += f"<td>{r['filtered']}</td><td>{r['total']}</td></tr>"
            html += "</table></body></html>"
            return html

        else:  # csv
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Rule", "Forwarded", "Filtered", "Total"])
            for r in details:
                writer.writerow([r["rule_name"], r["forwarded"], r["filtered"], r["total"]])
            return output.getvalue()


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
