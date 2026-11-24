"""Executive summary: totals, averages, status indicators and key trends."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from .alerts import alert_counts, generate_alerts
from .logic import build_area_stats, recurring_areas
from .models import AREA_TYPES, ISSUE_TYPES, STATUSES, Report
from .tables import format_table


def status_label(avg: float | None) -> str:
    if avg is None:
        return "No data"
    if avg >= 4.0:
        return "Excellent"
    if avg >= 3.5:
        return "Good"
    if avg >= 2.5:
        return "Needs attention"
    return "Critical"


def weekly_trend(reports: list[Report]) -> list[dict]:
    weeks = defaultdict(list)
    for r in reports:
        monday = r.day - timedelta(days=r.day.weekday())
        weeks[monday].append(r.rating)
    return [{"week": w.isoformat(), "avg": round(sum(v) / len(v), 2), "count": len(v)}
            for w, v in sorted(weeks.items())]


def _window_avg(reports, start: date, end: date):
    vals = [r.rating for r in reports if start <= r.day <= end]
    return (sum(vals) / len(vals)) if vals else None


def executive_summary(reports: list[Report], today_: date | None = None, window_days: int = 30) -> dict:
    today_ = today_ or date.today()
    total = len(reports)
    avg = round(sum(r.rating for r in reports) / total, 2) if total else None
    status_counts = {s: sum(1 for r in reports if r.status == s) for s in STATUSES}
    unresolved = total - status_counts["Resolved"]
    issue_counts = Counter(r.issue_type for r in reports if r.issue_type != "None")
    stats = build_area_stats(reports)
    ranked = [s for s in stats if s.count >= 2] or stats
    recurring = recurring_areas(reports, window_days, today_=today_)
    alerts = generate_alerts(reports, today_)
    counts = alert_counts(alerts)
    overdue = sum(1 for a in alerts if a.code == "OVERDUE")

    trends: list[str] = []
    recent = _window_avg(reports, today_ - timedelta(days=6), today_)
    previous = _window_avg(reports, today_ - timedelta(days=13), today_ - timedelta(days=7))
    if recent is not None and previous is not None:
        word = "improving" if recent - previous >= 0.3 else "declining" if previous - recent >= 0.3 else "steady"
        trends.append(f"Average rating over the last 7 days is {recent:.2f} vs {previous:.2f} the week before ({word}).")
    elif recent is not None:
        trends.append(f"Average rating over the last 7 days is {recent:.2f} (no prior week to compare).")
    if issue_counts:
        issue, n = issue_counts.most_common(1)[0]
        trends.append(f"'{issue}' is the most reported issue ({n} of {total} reports).")
    if recurring:
        trends.append(f"{len(recurring)} recurring problem area(s); worst is {recurring[0].location} "
                      f"(avg {recurring[0].avg_rating:.1f}, {recurring[0].trend}).")
    worsening = [s.location for s in stats if s.trend == "worsening" and s.count >= 3]
    if worsening:
        trends.append("Getting worse: " + ", ".join(worsening[:4]) + ".")
    improving = [s.location for s in stats if s.trend == "improving" and s.count >= 3]
    if improving:
        trends.append("Improving: " + ", ".join(improving[:4]) + ".")
    trends.append(f"{unresolved} report(s) unresolved, {overdue} overdue.")

    return {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total": total,
        "avg_rating": avg,
        "status": status_label(avg),
        "status_counts": status_counts,
        "unresolved": unresolved,
        "resolution_rate": round(100 * status_counts["Resolved"] / total, 1) if total else 0.0,
        "rating_dist": {i: sum(1 for r in reports if r.rating == i) for i in range(1, 6)},
        "area_counts": {a: sum(1 for r in reports if r.area_type == a) for a in AREA_TYPES},
        "issue_counts": {i: issue_counts.get(i, 0) for i in ISSUE_TYPES if i != "None"},
        "worst_locations": sorted(ranked, key=lambda s: (s.avg_rating, -s.count))[:3],
        "best_locations": sorted(ranked, key=lambda s: (-s.avg_rating, -s.count))[:3],
        "recurring": recurring,
        "weekly_trend": weekly_trend(reports),
        "alerts": counts,
        "trends": trends,
        "date_range": (min(r.date for r in reports), max(r.date for r in reports)) if reports else None,
    }


def recurring_table(areas) -> str:
    rows = [[a.location, a.area_type, f"{a.problem_count}/{a.count}", f"{a.avg_rating:.2f}",
             a.top_issue, a.last_date, a.open_count, a.trend] for a in areas]
    return format_table(["Location", "Type", "Prob/All", "Avg", "Top issue", "Last", "Open", "Trend"], rows,
                        [32, 10, 8, 5, 16, 10, 4, 9])


def format_summary_text(s: dict) -> str:
    lines = ["EXECUTIVE SUMMARY", "=" * 60,
             f"Generated        : {s['generated']}",
             f"Reports          : {s['total']}"
             + (f"  ({s['date_range'][0]} to {s['date_range'][1]})" if s["date_range"] else ""),
             f"Average rating   : {s['avg_rating'] if s['avg_rating'] is not None else 'n/a'} / 5",
             f"Campus status    : {s['status']}",
             f"Resolution rate  : {s['resolution_rate']}%   "
             + "  ".join(f"{k}: {v}" for k, v in s["status_counts"].items()),
             f"Warnings         : {s['alerts']['critical']} critical, {s['alerts']['warning']} warning, "
             f"{s['alerts']['info']} info", "", "Rating distribution:"]
    peak = max(s["rating_dist"].values(), default=0) or 1
    for rating, n in s["rating_dist"].items():
        lines.append(f"  {rating} | {'#' * round(24 * n / peak):<24} {n}")
    lines += ["", "Key trends:"] + [f"  - {t}" for t in s["trends"]]
    lines += ["", "Top issues:"] + [f"  {k:<18}{v}" for k, v in sorted(s["issue_counts"].items(), key=lambda kv: -kv[1]) if v]
    lines += ["", "Lowest-rated locations:"]
    lines += [f"  {a.location:<34}{a.avg_rating:.2f}  ({a.count} reports)" for a in s["worst_locations"]]
    lines += ["", "Best-rated locations:"]
    lines += [f"  {a.location:<34}{a.avg_rating:.2f}  ({a.count} reports)" for a in s["best_locations"]]
    lines += ["", "Recurring problem areas:"]
    lines += [recurring_table(s["recurring"])] if s["recurring"] else ["  none"]
    return "\n".join(lines)
