"""Matplotlib charts. Degrades gracefully (ChartUnavailable) if Matplotlib is missing."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from .logic import build_area_stats
from .models import STATUSES
from .storage import EXPORT_DIR
from .summary import weekly_trend

CHART_DIR = EXPORT_DIR / "charts"
GREEN, CLAY, SUN, INK = "#2F6B3F", "#C8553D", "#E2A72E", "#17301F"


class ChartUnavailable(RuntimeError):
    """Raised when Matplotlib cannot be imported."""


def _plt():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:  # fallback path required by the brief
        raise ChartUnavailable("Matplotlib is not installed (pip install matplotlib).") from exc
    return plt


def matplotlib_available() -> bool:
    try:
        _plt()
        return True
    except ChartUnavailable:
        return False


def _finish(fig, plt, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def _empty(ax, text="No data yet"):
    ax.text(0.5, 0.5, text, ha="center", va="center", transform=ax.transAxes, color="#777")
    ax.set_xticks([])
    ax.set_yticks([])


def rating_trend_chart(reports, path=CHART_DIR / "rating_trend.png") -> Path:
    plt = _plt()
    fig, ax = plt.subplots(figsize=(7, 3.6))
    weeks = weekly_trend(reports)
    if weeks:
        labels = [w["week"][5:] for w in weeks]
        ax.bar(labels, [w["count"] for w in weeks], color="#DCE6CC", label="Reports per week")
        ax.set_ylabel("Reports")
        ax2 = ax.twinx()
        ax2.plot(labels, [w["avg"] for w in weeks], color=GREEN, marker="o", linewidth=2.2, label="Avg rating")
        ax2.set_ylim(1, 5)
        ax2.set_ylabel("Average rating")
        ax2.axhline(2.5, color=CLAY, linestyle="--", linewidth=1)
        ax.set_xlabel("Week starting (MM-DD)")
        ax.tick_params(axis="x", rotation=45)
    else:
        _empty(ax)
    ax.set_title("Weekly average rating trend", color=INK, fontweight="bold")
    return _finish(fig, plt, Path(path))


def location_bar_chart(reports, path=CHART_DIR / "reports_by_location.png", top: int = 10) -> Path:
    plt = _plt()
    fig, ax = plt.subplots(figsize=(8, 4.2))
    stats = sorted(build_area_stats(reports), key=lambda s: s.count, reverse=True)[:top][::-1]
    if stats:
        colors = [CLAY if s.avg_rating <= 2.5 else SUN if s.avg_rating < 3.5 else GREEN for s in stats]
        bars = ax.barh([s.location[:36] for s in stats], [s.count for s in stats], color=colors)
        for bar, s in zip(bars, stats):
            ax.text(bar.get_width() + 0.05, bar.get_y() + bar.get_height() / 2, f"avg {s.avg_rating:.1f}",
                    va="center", fontsize=8, color=INK)
        ax.set_xlabel("Number of reports  (red: avg <= 2.5, amber: < 3.5, green: better)")
    else:
        _empty(ax)
    ax.set_title("Reports per location", color=INK, fontweight="bold")
    return _finish(fig, plt, Path(path))


def rating_distribution_chart(reports, path=CHART_DIR / "rating_distribution.png") -> Path:
    plt = _plt()
    fig, ax = plt.subplots(figsize=(6, 3.6))
    counts = Counter(r.rating for r in reports)
    values = [counts.get(i, 0) for i in range(1, 6)]
    ax.bar([1, 2, 3, 4, 5], values, color=[CLAY, "#DE8A4A", SUN, "#8FB35A", GREEN])
    for x, v in zip(range(1, 6), values):
        ax.text(x, v + 0.1, str(v), ha="center", fontsize=9)
    ax.set_xlabel("Rating (1 = filthy, 5 = spotless)")
    ax.set_ylabel("Reports")
    ax.set_title("Rating distribution", color=INK, fontweight="bold")
    return _finish(fig, plt, Path(path))


def status_pie_chart(reports, path=CHART_DIR / "status_breakdown.png") -> Path:
    plt = _plt()
    fig, ax = plt.subplots(figsize=(5, 3.8))
    counts = [sum(1 for r in reports if r.status == s) for s in STATUSES]
    if sum(counts):
        ax.pie(counts, labels=[f"{s} ({c})" for s, c in zip(STATUSES, counts)],
               colors=[CLAY, SUN, GREEN], startangle=90, wedgeprops={"width": 0.42, "edgecolor": "white"})
    else:
        _empty(ax)
    ax.set_title("Report status", color=INK, fontweight="bold")
    return _finish(fig, plt, Path(path))


def generate_all(reports, outdir=CHART_DIR) -> dict[str, Path]:
    """Create every chart. Returns {} if Matplotlib is unavailable."""
    outdir = Path(outdir)
    try:
        return {
            "Rating trend": rating_trend_chart(reports, outdir / "rating_trend.png"),
            "Reports per location": location_bar_chart(reports, outdir / "reports_by_location.png"),
            "Rating distribution": rating_distribution_chart(reports, outdir / "rating_distribution.png"),
            "Status breakdown": status_pie_chart(reports, outdir / "status_breakdown.png"),
        }
    except ChartUnavailable:
        return {}
