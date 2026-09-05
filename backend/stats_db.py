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

from sqlalchemy import delete, func, inspect, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.account_paths import AccountPathRegistry
from backend.database import (
    Base,
    ButtonActionHourly,
    ButtonActionStat,
    DailyStat,
    ForwardedMessage,
    HourlyStat,
    RuleStats,
    create_sqlite_engine,
    session_factory,
    session_scope,
)
from backend.logger import get_logger

logger = get_logger()

DB_PATH = Path("data/stats.db")


class StatsDB:
    """SQLite-based persistent statistics storage"""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()

        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.engine = create_sqlite_engine(self.db_path)
        self._session_factory = session_factory(self.engine)

        # Initialize database
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Return a raw connection for legacy migration/test helpers."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _session(self):
        return session_scope(self._session_factory)

    def _init_db(self) -> None:
        """Initialize database schema"""
        with self._lock:
            Base.metadata.create_all(
                self.engine,
                tables=[
                    RuleStats.__table__,
                    ForwardedMessage.__table__,
                    DailyStat.__table__,
                    HourlyStat.__table__,
                    ButtonActionStat.__table__,
                    ButtonActionHourly.__table__,
                ],
            )
            inspector = inspect(self.engine)
            if "entities_json" not in {
                column["name"] for column in inspector.get_columns("forwarded_messages")
            }:
                with self.engine.begin() as connection:
                    connection.exec_driver_sql(
                        "ALTER TABLE forwarded_messages ADD COLUMN entities_json TEXT"
                    )
            conn = self._get_conn()
            try:
                self._backfill_hourly_from_daily(conn)
                self._backfill_button_action_hourly(conn)
                conn.commit()
            finally:
                conn.close()

    @staticmethod
    def _backfill_hourly_from_daily(conn: sqlite3.Connection) -> None:
        """Backfill legacy daily counters into a deterministic hourly bucket."""
        conn.execute("""
            INSERT INTO hourly_stats (
                rule_name, hour, forwarded_count, filtered_count, failed_count
            )
            SELECT
                daily.rule_name,
                daily.date || ' 00:00',
                CASE
                    WHEN daily.forwarded_count - COALESCE(hourly.forwarded_count, 0) > 0
                    THEN daily.forwarded_count - COALESCE(hourly.forwarded_count, 0)
                    ELSE 0
                END,
                CASE
                    WHEN daily.filtered_count - COALESCE(hourly.filtered_count, 0) > 0
                    THEN daily.filtered_count - COALESCE(hourly.filtered_count, 0)
                    ELSE 0
                END,
                0
            FROM daily_stats AS daily
            LEFT JOIN (
                SELECT
                    rule_name,
                    substr(hour, 1, 10) AS date,
                    SUM(forwarded_count) AS forwarded_count,
                    SUM(filtered_count) AS filtered_count
                FROM hourly_stats
                GROUP BY rule_name, substr(hour, 1, 10)
            ) AS hourly
              ON hourly.rule_name = daily.rule_name
             AND hourly.date = daily.date
            WHERE daily.forwarded_count - COALESCE(hourly.forwarded_count, 0) > 0
               OR daily.filtered_count - COALESCE(hourly.filtered_count, 0) > 0
            ON CONFLICT(rule_name, hour) DO UPDATE SET
                forwarded_count = hourly_stats.forwarded_count + excluded.forwarded_count,
                filtered_count = hourly_stats.filtered_count + excluded.filtered_count
        """)

    @staticmethod
    def _backfill_button_action_hourly(conn: sqlite3.Connection) -> None:
        """Backfill legacy cumulative automation counts into hourly data."""
        conn.execute("""
            INSERT INTO button_action_hourly (rule_name, hour, trigger_count)
            SELECT
                totals.rule_name,
                COALESCE(existing.first_hour, strftime('%Y-%m-%d %H:00', 'now', 'localtime')),
                totals.trigger_count - COALESCE(existing.hourly_count, 0)
            FROM button_action_stats AS totals
            LEFT JOIN (
                SELECT
                    rule_name,
                    MIN(hour) AS first_hour,
                    SUM(trigger_count) AS hourly_count
                FROM button_action_hourly
                GROUP BY rule_name
            ) AS existing ON existing.rule_name = totals.rule_name
            WHERE totals.trigger_count - COALESCE(existing.hourly_count, 0) > 0
            ON CONFLICT(rule_name, hour) DO UPDATE SET
                trigger_count = button_action_hourly.trigger_count + excluded.trigger_count
        """)

    # -- Rule stats --

    def get_stats(self, rule_name: str) -> dict:
        """Get statistics for a specific rule"""
        with self._lock:
            with self._session() as session:
                row = session.get(RuleStats, rule_name)
                return {
                    "forwarded": row.forwarded_count if row else 0,
                    "filtered": row.filtered_count if row else 0,
                }

    def get_all_stats(self) -> dict:
        """Get statistics for all rules"""
        with self._lock:
            with self._session() as session:
                return {
                    row.rule_name: {
                        "forwarded": row.forwarded_count,
                        "filtered": row.filtered_count,
                    }
                    for row in session.scalars(select(RuleStats)).all()
                }

    @staticmethod
    def _hourly_column(column: str):
        if column not in {"forwarded_count", "filtered_count", "failed_count"}:
            raise ValueError(f"Unsupported hourly stats column: {column}")

        return getattr(HourlyStat, column)

    def _increment_hourly(self, session, rule_name: str, column: str, amount: int = 1) -> None:
        hour = datetime.now().strftime("%Y-%m-%d %H:00")
        field = self._hourly_column(column)
        statement = sqlite_insert(HourlyStat).values(
            rule_name=rule_name,
            hour=hour,
            **{column: int(amount)},
        )
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[HourlyStat.rule_name, HourlyStat.hour],
                set_={column: field + statement.excluded[column]},
            )
        )

    def increment_failed(self, rule_name: str) -> None:
        """Record one forwarding task that reached its final failed state."""
        with self._lock:
            with self._session() as session:
                self._increment_hourly(session, rule_name, "failed_count")

    # -- Button action stats --

    def increment_button_action(self, rule_name: str) -> None:
        """Increment the successful trigger count for a button automation."""
        with self._lock:
            with self._session() as session:
                statement = sqlite_insert(ButtonActionStat).values(
                    rule_name=rule_name, trigger_count=1
                )
                session.execute(
                    statement.on_conflict_do_update(
                        index_elements=[ButtonActionStat.rule_name],
                        set_={
                            "trigger_count": ButtonActionStat.trigger_count
                            + statement.excluded.trigger_count
                        },
                    )
                )
                hour = datetime.now().strftime("%Y-%m-%d %H:00")
                hourly = sqlite_insert(ButtonActionHourly).values(
                    rule_name=rule_name, hour=hour, trigger_count=1
                )
                session.execute(
                    hourly.on_conflict_do_update(
                        index_elements=[ButtonActionHourly.rule_name, ButtonActionHourly.hour],
                        set_={
                            "trigger_count": ButtonActionHourly.trigger_count
                            + hourly.excluded.trigger_count
                        },
                    )
                )

    def get_button_action_stats(self) -> List[dict]:
        """Return cumulative trigger counts for all button automations."""
        with self._lock:
            with self._session() as session:
                return [
                    {"rule_name": row.rule_name, "triggered": row.trigger_count}
                    for row in session.scalars(
                        select(ButtonActionStat).order_by(ButtonActionStat.rule_name)
                    ).all()
                ]

    def reset_button_action_stats(self, rule_name: str = None) -> None:
        """Reset trigger counts for one button automation or all of them."""
        with self._lock:
            with self._session() as session:
                statement = update(ButtonActionStat).values(trigger_count=0)
                if rule_name:
                    statement = statement.where(ButtonActionStat.rule_name == rule_name)
                session.execute(statement)

    def rename_button_rule(self, old_name: str, new_name: str) -> None:
        """Keep button trigger history when a button automation is renamed."""
        with self._lock:
            with self._session() as session:
                session.execute(
                    update(ButtonActionStat)
                    .where(ButtonActionStat.rule_name == old_name)
                    .values(rule_name=new_name)
                )
                session.execute(
                    update(ButtonActionHourly)
                    .where(ButtonActionHourly.rule_name == old_name)
                    .values(rule_name=new_name)
                )

    def delete_button_rule(self, rule_name: str) -> None:
        """Remove trigger history when a button automation is deleted."""
        with self._lock:
            with self._session() as session:
                session.execute(
                    delete(ButtonActionStat).where(ButtonActionStat.rule_name == rule_name)
                )
                session.execute(
                    delete(ButtonActionHourly).where(ButtonActionHourly.rule_name == rule_name)
                )

    def increment_forwarded(self, rule_name: str) -> None:
        """Increment forwarded count for a rule"""
        with self._lock:
            with self._session() as session:
                statement = sqlite_insert(RuleStats).values(
                    rule_name=rule_name, forwarded_count=1, filtered_count=0
                )
                session.execute(
                    statement.on_conflict_do_update(
                        index_elements=[RuleStats.rule_name],
                        set_={"forwarded_count": RuleStats.forwarded_count + 1},
                    )
                )
                self._increment_hourly(session, rule_name, "forwarded_count")

    def increment_filtered(self, rule_name: str) -> None:
        """Increment filtered count for a rule"""
        with self._lock:
            with self._session() as session:
                statement = sqlite_insert(RuleStats).values(
                    rule_name=rule_name, forwarded_count=0, filtered_count=1
                )
                session.execute(
                    statement.on_conflict_do_update(
                        index_elements=[RuleStats.rule_name],
                        set_={"filtered_count": RuleStats.filtered_count + 1},
                    )
                )
                self._increment_hourly(session, rule_name, "filtered_count")

    def reset_stats(self, rule_name: str = None) -> None:
        """Reset statistics. If rule_name is None, reset all rules."""
        with self._lock:
            with self._session() as session:
                if rule_name:
                    rule_filter = RuleStats.rule_name == rule_name
                    session.execute(delete(DailyStat).where(DailyStat.rule_name == rule_name))
                    session.execute(
                        update(RuleStats).where(rule_filter).values(forwarded_count=0, filtered_count=0)
                    )
                    session.execute(
                        update(ButtonActionStat)
                        .where(ButtonActionStat.rule_name == rule_name)
                        .values(trigger_count=0)
                    )
                    session.execute(
                        update(HourlyStat)
                        .where(HourlyStat.rule_name == rule_name)
                        .values(forwarded_count=0, filtered_count=0, failed_count=0)
                    )
                    session.execute(
                        update(ButtonActionHourly)
                        .where(ButtonActionHourly.rule_name == rule_name)
                        .values(trigger_count=0)
                    )
                else:
                    session.execute(delete(DailyStat))
                    session.execute(update(RuleStats).values(forwarded_count=0, filtered_count=0))
                    session.execute(update(ButtonActionStat).values(trigger_count=0))
                    session.execute(
                        update(HourlyStat).values(forwarded_count=0, filtered_count=0, failed_count=0)
                    )
                    session.execute(update(ButtonActionHourly).values(trigger_count=0))

    def rename_rule(self, old_name: str, new_name: str) -> None:
        """Rename a rule in the stats database"""
        with self._lock:
            with self._session() as session:
                for model in (
                    RuleStats,
                    ForwardedMessage,
                    DailyStat,
                    HourlyStat,
                    ButtonActionHourly,
                ):
                    session.execute(
                        update(model)
                        .where(model.rule_name == old_name)
                        .values(rule_name=new_name)
                    )

    def delete_rule(self, rule_name: str) -> None:
        """Delete statistics for a rule"""
        with self._lock:
            with self._session() as session:
                for model in (
                    RuleStats,
                    ForwardedMessage,
                    DailyStat,
                    HourlyStat,
                    ButtonActionHourly,
                ):
                    session.execute(delete(model).where(model.rule_name == rule_name))

    # -- Message history --

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
        entities: str = None,
    ) -> None:
        """Insert a forwarded message history record"""
        now = datetime.now()
        forwarded_at = now.strftime("%Y-%m-%d %H:%M:%S.") + f"{now.microsecond // 1000:03d}"
        with self._lock:
            with self._session() as session:
                session.add(
                    ForwardedMessage(
                        rule_name=rule_name,
                        message_id=message_id,
                        source_chat_id=source_chat_id,
                        source_chat_name=source_chat_name,
                        sender_id=sender_id,
                        sender_name=sender_name,
                        sender_first_name=sender_first_name,
                        sender_last_name=sender_last_name,
                        sender_username=sender_username,
                        content=content,
                        media_type=media_type,
                        entities_json=entities,
                        forwarded_at=forwarded_at,
                    )
                )

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
            with self._session() as session:
                statement = select(ForwardedMessage)
                if rule_name:
                    statement = statement.where(ForwardedMessage.rule_name == rule_name)
                if keyword:
                    like = f"%{keyword}%"
                    statement = statement.where(
                        ForwardedMessage.content.like(like)
                        | ForwardedMessage.source_chat_name.like(like)
                        | ForwardedMessage.sender_name.like(like)
                    )
                total = session.scalar(
                    select(func.count()).select_from(statement.subquery())
                ) or 0
                records = session.scalars(
                    statement.order_by(
                        ForwardedMessage.forwarded_at.desc(), ForwardedMessage.id.desc()
                    )
                    .limit(limit)
                    .offset(offset)
                ).all()
                return [
                    {
                        "id": row.id,
                        "rule_name": row.rule_name,
                        "message_id": row.message_id,
                        "source_chat_id": row.source_chat_id,
                        "source_chat_name": row.source_chat_name,
                        "sender_id": row.sender_id,
                        "sender_name": row.sender_name,
                        "sender_first_name": row.sender_first_name,
                        "sender_last_name": row.sender_last_name,
                        "sender_username": row.sender_username,
                        "content": row.content,
                        "media_type": row.media_type,
                        "entities": json.loads(row.entities_json) if row.entities_json else None,
                        "forwarded_at": row.forwarded_at,
                    }
                    for row in records
                ], int(total)

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

    # -- Daily stats --

    def increment_daily(self, rule_name: str, is_forwarded: bool) -> None:
        """Increment today's daily counter for a rule"""
        today = datetime.now().strftime("%Y-%m-%d")
        col = "forwarded_count" if is_forwarded else "filtered_count"
        with self._lock:
            with self._session() as session:
                statement = sqlite_insert(DailyStat).values(
                    rule_name=rule_name,
                    date=today,
                    forwarded_count=1 if is_forwarded else 0,
                    filtered_count=0 if is_forwarded else 1,
                )
                session.execute(
                    statement.on_conflict_do_update(
                        index_elements=[DailyStat.rule_name, DailyStat.date],
                        set_={col: getattr(DailyStat, col) + 1},
                    )
                )

    def get_daily_stats(
        self, days: Optional[int] = 30, rule_name: str | None = None
    ) -> List[dict]:
        """
        Get daily aggregated stats for the last N days, or all recorded days.

        Returns:
            List of {date, forwarded, filtered} dicts, ordered by date ASC
        """
        with self._lock:
            with self._session() as session:
                daily_statement = select(DailyStat)
                failed_statement = select(HourlyStat)
                if days is not None:
                    cutoff_dt = datetime.now() - timedelta(days=days)
                    daily_statement = daily_statement.where(
                        DailyStat.date >= cutoff_dt.strftime("%Y-%m-%d")
                    )
                    failed_statement = failed_statement.where(
                        HourlyStat.hour >= cutoff_dt.strftime("%Y-%m-%d 00:00")
                    )
                if rule_name:
                    daily_statement = daily_statement.where(DailyStat.rule_name == rule_name)
                    failed_statement = failed_statement.where(HourlyStat.rule_name == rule_name)
                daily_rows = session.scalars(daily_statement).all()
                failed_rows = session.scalars(
                    failed_statement.where(HourlyStat.failed_count != 0)
                ).all()
                result = {
                    row.date: {"date": row.date, "forwarded": 0, "filtered": 0, "failed": 0}
                    for row in daily_rows
                }
                for row in daily_rows:
                    result[row.date]["forwarded"] += row.forwarded_count or 0
                    result[row.date]["filtered"] += row.filtered_count or 0
                for row in failed_rows:
                    date = row.hour[:10]
                    result.setdefault(
                        date, {"date": date, "forwarded": 0, "filtered": 0, "failed": 0}
                    )["failed"] += row.failed_count or 0
                return [result[key] for key in sorted(result)]

    def get_hourly_stats(
        self, hours: Optional[int] = 720, rule_name: str | None = None
    ) -> List[dict]:
        """Return hourly forwarding statistics, optionally scoped to one rule."""
        with self._lock:
            with self._session() as session:
                statement = select(HourlyStat)
                if hours is not None:
                    cutoff = datetime.now() - timedelta(hours=max(1, int(hours)))
                    statement = statement.where(HourlyStat.hour >= cutoff.strftime("%Y-%m-%d %H:00"))
                if rule_name:
                    statement = statement.where(HourlyStat.rule_name == rule_name)
                rows = session.scalars(statement.order_by(HourlyStat.hour)).all()
                grouped = {}
                for row in rows:
                    item = grouped.setdefault(row.hour, {"hour": row.hour, "forwarded": 0, "filtered": 0, "failed": 0})
                    item["forwarded"] += row.forwarded_count or 0
                    item["filtered"] += row.filtered_count or 0
                    item["failed"] += row.failed_count or 0
                return list(grouped.values())

    def get_media_type_stats(
        self, days: Optional[int] = 30, rule_name: str | None = None
    ) -> List[dict]:
        """Return forwarded message counts grouped by media type."""
        with self._lock:
            with self._session() as session:
                statement = select(ForwardedMessage)
                if days is not None:
                    cutoff = datetime.now() - timedelta(days=max(1, int(days)))
                    statement = statement.where(
                        ForwardedMessage.forwarded_at >= cutoff.strftime("%Y-%m-%d %H:%M:%S")
                    )
                if rule_name:
                    statement = statement.where(ForwardedMessage.rule_name == rule_name)
                counts: dict[str, int] = {}
                for row in session.scalars(statement).all():
                    media_type = row.media_type or "text"
                    counts[media_type] = counts.get(media_type, 0) + 1
                return [
                    {"media_type": media_type, "count": count}
                    for media_type, count in sorted(
                        counts.items(), key=lambda item: (-item[1], item[0])
                    )
                ]

    def get_button_action_hourly(
        self, hours: Optional[int] = 720, rule_name: str | None = None
    ) -> List[dict]:
        """Return hourly automation trigger counts."""
        with self._lock:
            with self._session() as session:
                statement = select(ButtonActionHourly)
                if hours is not None:
                    cutoff = datetime.now() - timedelta(hours=max(1, int(hours)))
                    statement = statement.where(
                        ButtonActionHourly.hour >= cutoff.strftime("%Y-%m-%d %H:00")
                    )
                if rule_name:
                    statement = statement.where(ButtonActionHourly.rule_name == rule_name)
                grouped: dict[str, int] = {}
                for row in session.scalars(statement).all():
                    grouped[row.hour] = grouped.get(row.hour, 0) + row.trigger_count
                return [
                    {"hour": hour, "triggered": grouped[hour]}
                    for hour in sorted(grouped)
                ]

    def get_button_action_daily(
        self, days: Optional[int] = 30, rule_name: str | None = None
    ) -> List[dict]:
        """Return daily automation trigger counts."""
        with self._lock:
            with self._session() as session:
                statement = select(ButtonActionHourly)
                if days is not None:
                    cutoff = datetime.now() - timedelta(days=max(1, int(days)))
                    statement = statement.where(
                        ButtonActionHourly.hour >= cutoff.strftime("%Y-%m-%d 00:00")
                    )
                if rule_name:
                    statement = statement.where(ButtonActionHourly.rule_name == rule_name)
                grouped: dict[str, int] = {}
                for row in session.scalars(statement).all():
                    date = row.hour[:10]
                    grouped[date] = grouped.get(date, 0) + row.trigger_count
                return [
                    {"date": date, "triggered": grouped[date]}
                    for date in sorted(grouped)
                ]

    def get_rule_stats_detail(self) -> List[dict]:
        """
        Get per-rule statistics detail (for stats dashboard).

        Returns:
            List of {rule_name, forwarded, filtered, total} dicts
        """
        with self._lock:
            with self._session() as session:
                return [
                    {
                        "rule_name": row.rule_name,
                        "forwarded": row.forwarded_count,
                        "filtered": row.filtered_count,
                        "total": row.forwarded_count + row.filtered_count,
                    }
                    for row in session.scalars(
                        select(RuleStats).order_by(RuleStats.rule_name)
                    ).all()
                ]

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


class AccountStatsRegistry:
    """Resolve one isolated statistics database per authenticated account."""

    def __init__(
        self,
        data_dir: str | Path = "data",
        paths: AccountPathRegistry | None = None,
    ):
        self.paths = paths or AccountPathRegistry(data_dir=data_dir)
        self._databases: dict[str, StatsDB] = {}
        self._lock = threading.RLock()

    def for_account(self, account_id: str) -> StatsDB:
        path = self.paths.for_account(account_id).stats_db
        with self._lock:
            database = self._databases.get(account_id)
            if database is None:
                database = StatsDB(path)
                self._databases[account_id] = database
            return database

    def discard(self, account_id: str) -> None:
        with self._lock:
            self._databases.pop(account_id, None)
