"""Threshold warning indicators: critical ratings, overdue items, anomalies."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from .models import Report

LEVELS = {"critical": 0, "warning": 1, "info": 2}


@dataclass
class Alert:
    level: str  # critical | warning | info
    code: str
    message: str
    report_id: int | None = None
    location: str | None = None


def generate_alerts(reports: list[Report], today_: date | None = None, overdue_days: int = 3,
                    repeat_critical: int = 3) -> list[Alert]:
    today_ = today_ or date.today()
    alerts: list[Alert] = []

    for r in reports:
        unresolved = r.status != "Resolved"
        age = (today_ - r.day).days
        if unresolved and r.rating <= 2:
            alerts.append(Alert("critical" if r.rating == 1 else "warning", "CRITICAL_RATING",
                                f"#{r.id} {r.location}: rated {r.rating}/5 ({r.issue_type}) and still {r.status}",
                                r.id, r.location))
        if unresolved and age > overdue_days:
            level = "critical" if age > 14 else "warning"
            alerts.append(Alert(level, "OVERDUE",
                                f"#{r.id} {r.location}: {r.status} for {age} days (limit {overdue_days})",
                                r.id, r.location))
        if r.rating >= 4 and r.issue_type != "None":
            alerts.append(Alert("info", "ANOMALY",
                                f"#{r.id} {r.location}: rating {r.rating} but issue '{r.issue_type}' reported",
                                r.id, r.location))
        if r.rating <= 2 and r.issue_type == "None":
            alerts.append(Alert("info", "ANOMALY",
                                f"#{r.id} {r.location}: rating {r.rating} but no issue type given",
                                r.id, r.location))

    groups = defaultdict(list)
    for r in reports:
        groups[(r.date, r.location.casefold(), r.issue_type, r.reporter.casefold())].append(r)
    for items in groups.values():
        if len(items) > 1:
            ids = ", ".join(f"#{i.id}" for i in items)
            alerts.append(Alert("info", "ANOMALY",
                                f"Possible duplicate reports {ids}: {items[0].location} on {items[0].date}",
                                items[0].id, items[0].location))

    critical_by_loc = defaultdict(list)
    for r in reports:
        if r.status != "Resolved" and r.rating <= 2:
            critical_by_loc[r.location.casefold()].append(r)
    for items in critical_by_loc.values():
        if len(items) >= repeat_critical:
            alerts.append(Alert("critical", "LIMIT_BREACH",
                                f"{items[0].location}: {len(items)} unresolved critical reports "
                                f"(limit {repeat_critical - 1})", None, items[0].location))

    alerts.sort(key=lambda a: (LEVELS[a.level], a.code, a.report_id or 0))
    return alerts


def alert_counts(alerts: list[Alert]) -> dict[str, int]:
    counts = {"critical": 0, "warning": 0, "info": 0}
    for a in alerts:
        counts[a.level] += 1
    counts["total"] = len(alerts)
    return counts
