"""
History Handler - Message history search, pagination and export
"""
import os
import tempfile
from src.stats_db import get_stats_db
from src.logger import get_logger
from src.i18n import t

logger = get_logger()

HISTORY_PAGE_SIZE = 20


class HistoryHandler:
    """Forwarded message history handler"""

    def __init__(self):
        self._db = get_stats_db()

    def get_rule_choices(self):
        """Get rule name choices for dropdown (with 'All' option)"""
        details = self._db.get_rule_stats_detail()
        names = [r["rule_name"] for r in details]
        return [""] + names  # empty string = all rules

    def search(self, rule_name: str, keyword: str, page: int):
        """
        Search history with filters and pagination.

        Returns:
            (dataframe_data, page_info_text, total_pages)
        """
        rule = rule_name if rule_name else None
        kw = keyword.strip() if keyword else None
        offset = max(0, (page - 1)) * HISTORY_PAGE_SIZE

        rows, total = self._db.query_history(
            rule_name=rule, keyword=kw,
            limit=HISTORY_PAGE_SIZE, offset=offset
        )

        total_pages = max(1, (total + HISTORY_PAGE_SIZE - 1) // HISTORY_PAGE_SIZE)

        # Format for gr.Dataframe
        table_data = []
        for r in rows:
            table_data.append([
                r.get("forwarded_at", ""),
                r.get("rule_name", ""),
                r.get("source_chat_id", ""),
                r.get("source_chat_name", ""),
                r.get("sender_name", ""),
                r.get("sender_username", "") or "",
                ((c := r.get("content", "") or "") and (c[:100] + "..." if len(c) > 100 else c)),
                r.get("media_type", ""),
            ])

        page_info = t("ui.label.page_info", page=page, total=total_pages, count=total)

        return table_data, page_info, total_pages

    def export_data(self, rule_name: str, keyword: str, fmt: str):
        """
        Export history data to a temporary file.

        Returns:
            File path for download
        """
        rule = rule_name if rule_name else None
        kw = keyword.strip() if keyword else None

        content = self._db.export_history(rule_name=rule, keyword=kw, fmt=fmt)

        ext = {"csv": ".csv", "json": ".json", "html": ".html"}.get(fmt, ".csv")
        tmp_dir = os.path.join(tempfile.gettempdir(), "telerelay-export")
        os.makedirs(tmp_dir, exist_ok=True)
        filepath = os.path.join(tmp_dir, f"history{ext}")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        return filepath
