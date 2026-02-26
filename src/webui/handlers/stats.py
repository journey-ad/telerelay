"""
Stats Handler - Statistics dashboard with per-rule detail and daily trend chart
"""
import os
import tempfile
from src.stats_db import get_stats_db
from src.logger import get_logger
from src.i18n import t

logger = get_logger()


class StatsHandler:
    """Statistics dashboard handler"""

    def __init__(self):
        self._db = get_stats_db()

    def get_rule_detail_table(self):
        """
        Get per-rule statistics as table data for gr.Dataframe.

        Returns:
            List of [rule_name, forwarded, filtered, total] rows
        """
        details = self._db.get_rule_stats_detail()
        return [
            [r["rule_name"], r["forwarded"], r["filtered"], r["total"]]
            for r in details
        ]

    def get_daily_trend_plot(self, days: int = 30):
        """
        Generate a daily forwarding trend chart.

        Returns:
            matplotlib Figure object (compatible with gr.Plot)
        """
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
            import matplotlib.font_manager as fm
            from datetime import datetime
        except ImportError:
            logger.warning("matplotlib not available, skipping trend chart")
            return None

        # Load bundled CJK font
        from pathlib import Path as _Path
        _bundled = _Path(__file__).parent.parent.parent / "assets" / "font.ttf"
        fm.fontManager.addfont(str(_bundled))
        _prop = fm.FontProperties(fname=str(_bundled))
        matplotlib.rcParams["font.family"] = _prop.get_name()
        matplotlib.rcParams["axes.unicode_minus"] = False

        data = self._db.get_daily_stats(days=days)

        if not data:
            # Return empty chart with message
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.text(0.5, 0.5, t("ui.label.no_stats_data"),
                    ha='center', va='center', fontsize=14, color='gray',
                    transform=ax.transAxes)
            ax.set_axis_off()
            plt.tight_layout()
            return fig

        dates = [datetime.strptime(d["date"], "%Y-%m-%d") for d in data]
        forwarded = [d["forwarded"] for d in data]
        filtered = [d["filtered"] for d in data]

        fig, ax = plt.subplots(figsize=(10, 4))
        ax.fill_between(dates, forwarded, alpha=0.3, color='#4CAF50')
        ax.plot(dates, forwarded, color='#4CAF50', linewidth=2, marker='o', markersize=4, label=t("ui.label.forwarded"))
        ax.fill_between(dates, filtered, alpha=0.3, color='#FF9800')
        ax.plot(dates, filtered, color='#FF9800', linewidth=2, marker='o', markersize=4, label=t("ui.label.filtered"))

        ax.set_xlabel(t("ui.label.date"))
        ax.set_ylabel(t("ui.label.count"))
        ax.legend(loc='upper left')
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        fig.autofmt_xdate(rotation=30)
        plt.tight_layout()

        return fig

    def export_stats(self, fmt: str):
        """
        Export statistics data to a temporary file.

        Returns:
            File path for download
        """
        content = self._db.export_stats(fmt=fmt)

        ext = {"csv": ".csv", "json": ".json", "html": ".html"}.get(fmt, ".csv")
        tmp_dir = os.path.join(tempfile.gettempdir(), "telerelay-export")
        os.makedirs(tmp_dir, exist_ok=True)
        filepath = os.path.join(tmp_dir, f"stats{ext}")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        return filepath
