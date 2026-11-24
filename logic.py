"""Core business logic: the report store, search, and recurring-area analysis."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .importer import ImportResult, parse_csv, write_error_log
from .models import Report
from .storage import DEFAULT_PATH, EXPORT_DIR, load_reports, save_reports
from .validation import ValidationError, build_report, validate_status

PROBLEM_RATING = 3  # a rating <= 3 ("Fair" or worse) counts as a problem report


class ReportStore:
    """In-memory list of reports kept in sync with a JSON/CSV file."""

    def __init__(self, path=DEFAULT_PATH):
        self.path = Path(path)
        self.reports: list[Report] = []
        self.notes: list[str] = []
        self.reload()

    # persistence ------------------------------------------------------
    def reload(self) -> None:
        self.reports, self.notes = load_reports(self.path)

    def save(self) -> None:
        save_reports(self.reports, self.path)

    def _next_id(self) -> int:
        return max((r.id for r in self.reports), default=0) + 1

    # CRUD -------------------------------------------------------------
    def get(self, report_id: int) -> Report:
        for report in self.reports:
            if report.id == report_id:
                return report
        raise KeyError(f"No report with id {report_id}")

    def add(self, data: dict, today_: date | None = None) -> Report:
        report = build_report(data, self._next_id(), today_)
        self.reports.append(report)
        self.save()
        return report

    def update(self, report_id: int, changes: dict, today_: date | None = None) -> Report:
        old = self.get(report_id)
        new = build_report({**old.to_dict(), **changes}, report_id, today_)
        self.reports[self.reports.index(old)] = new
        self.save()
        return new

    def set_status(self, report_id: int, status: str) -> Report:
        return self.update(report_id, {"status": validate_status(status)})

    def delete(self, report_id: int) -> Report:
        report = self.get(report_id)
        self.reports.remove(report)
        self.save()
        return report

    # bulk import ------------------------------------------------------
    def import_csv(self, csv_path, log_path=None) -> ImportResult:
        result = parse_csv(csv_path, start_id=self._next_id(), existing=self.reports)
        if result.imported:
            self.reports.extend(result.imported)
            self.save()
        write_error_log(result, log_path or EXPORT_DIR / "import_errors.log")
        return result

    # query & search ---------------------------------------------------
    def locations(self) -> list[str]:
        return sorted({r.location for r in self.reports}, key=str.casefold)

    def search(self, keyword: str = "", area_type: str | None = None, status: str | None = None,
               issue_type: str | None = None, min_rating: int | None = None, max_rating: int | None = None,
               date_from: str | None = None, date_to: str | None = None) -> list[Report]:
        return search_reports(self.reports, keyword, area_type, status, issue_type,
                              min_rating, max_rating, date_from, date_to)


def search_reports(reports, keyword="", area_type=None, status=None, issue_type=None,
                   min_rating=None, max_rating=None, date_from=None, date_to=None) -> list[Report]:
    """Keyword + category filtering. Newest first."""
    words = [w.casefold() for w in (keyword or "").split()]
    out = []
    for r in reports:
        if area_type and r.area_type != area_type:
            continue
        if status and r.status != status:
            continue
        if issue_type and r.issue_type != issue_type:
            continue
        if min_rating is not None and r.rating < min_rating:
            continue
        if max_rating is not None and r.rating > max_rating:
            continue
        if date_from and r.date < date_from:
            continue
        if date_to and r.date > date_to:
            continue
        if words:
            haystack = " ".join([r.location, r.area_type, r.issue_type, r.description, r.reporter, r.status]).casefold()
            if not all(w in haystack for w in words):
                continue
        out.append(r)
    return sorted(out, key=lambda r: (r.date, r.id), reverse=True)


# ---------------------------------------------------------------------
# Recurring-area analysis
# ---------------------------------------------------------------------
@dataclass
class AreaStat:
    location: str
    area_type: str
    count: int
    problem_count: int
    avg_rating: float
    min_rating: int
    top_issue: str
    last_date: str
    open_count: int
    trend: str  # improving | worsening | stable | n/a
    reasons: list[str] = field(default_factory=list)

    @property
    def severity(self) -> float:
        """Higher = needs attention sooner."""
        return self.problem_count * (5.0 - self.avg_rating) + self.open_count


def _trend(chronological: list[Report]) -> str:
    n = len(chronological)
    if n < 2:
        return "n/a"
    if n >= 4:
        half = n // 2
        earlier, later = chronological[:half], chronological[half:]
    else:
        earlier, later = chronological[:1], chronological[-1:]
    diff = (sum(r.rating for r in later) / len(later)) - (sum(r.rating for r in earlier) / len(earlier))
    if diff >= 0.5:
        return "improving"
    if diff <= -0.5:
        return "worsening"
    return "stable"


def build_area_stats(reports: list[Report]) -> list[AreaStat]:
    """Group reports by location (case-insensitive) and compute statistics."""
    groups: dict[str, list[Report]] = defaultdict(list)
    for r in reports:
        groups[r.location.casefold()].append(r)
    stats = []
    for items in groups.values():
        items.sort(key=lambda r: (r.date, r.id))
        issues = Counter(r.issue_type for r in items if r.issue_type != "None")
        stats.append(AreaStat(
            location=Counter(r.location for r in items).most_common(1)[0][0],
            area_type=Counter(r.area_type for r in items).most_common(1)[0][0],
            count=len(items),
            problem_count=sum(1 for r in items if r.rating <= PROBLEM_RATING),
            avg_rating=round(sum(r.rating for r in items) / len(items), 2),
            min_rating=min(r.rating for r in items),
            top_issue=issues.most_common(1)[0][0] if issues else "None",
            last_date=items[-1].date,
            open_count=sum(1 for r in items if r.status != "Resolved"),
            trend=_trend(items),
        ))
    return sorted(stats, key=lambda s: (-s.severity, s.location.casefold()))


def recurring_areas(reports: list[Report], window_days: int | None = 30, min_reports: int = 3,
                    max_avg: float = 2.5, today_: date | None = None) -> list[AreaStat]:
    """Locations that keep coming up.

    A location is *recurring* when, inside the time window, it has either
      * at least `min_reports` problem reports (rating <= 3), or
      * two or more reports with an average rating <= `max_avg`.
    """
    if window_days:
        cutoff = ((today_ or date.today()) - timedelta(days=window_days)).isoformat()
        reports = [r for r in reports if r.date >= cutoff]
    flagged = []
    for stat in build_area_stats(reports):
        if stat.problem_count >= min_reports:
            span = f"last {window_days} days" if window_days else "all time"
            stat.reasons.append(f"{stat.problem_count} problem reports in {span}")
        if stat.count >= 2 and stat.avg_rating <= max_avg:
            stat.reasons.append(f"average rating {stat.avg_rating:.1f} <= {max_avg}")
        if stat.reasons:
            flagged.append(stat)
    return flagged
