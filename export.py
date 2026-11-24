"""Multi-format export: Markdown summary, plain-text audit log, standardised CSV."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from .alerts import generate_alerts
from .models import FIELDS
from .storage import EXPORT_DIR
from .summary import executive_summary, format_summary_text

_FORMULA_CHARS = ("=", "+", "-", "@")


def _safe(value):
    """Neutralise spreadsheet formula injection in free-text cells."""
    return "'" + value if isinstance(value, str) and value.startswith(_FORMULA_CHARS) else value


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def export_csv(reports, outdir=EXPORT_DIR, name: str | None = None) -> Path:
    path = Path(outdir) / (name or f"cleanliness_report_{_stamp()}.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for r in sorted(reports, key=lambda r: r.id):
            row = r.to_dict()
            row["description"], row["reporter"] = _safe(row["description"]), _safe(row["reporter"])
            writer.writerow(row)
    return path


def export_markdown(reports, outdir=EXPORT_DIR, name: str | None = None, chart_files: dict | None = None) -> Path:
    s = executive_summary(reports)
    alerts = generate_alerts(reports)
    md = [f"# Campus Cleanliness Report", f"_Generated {s['generated']}_", "",
          "## Overview", "", "| Metric | Value |", "|---|---|",
          f"| Total reports | {s['total']} |",
          f"| Average rating | {s['avg_rating'] if s['avg_rating'] is not None else 'n/a'} / 5 |",
          f"| Campus status | **{s['status']}** |",
          f"| Resolution rate | {s['resolution_rate']}% |",
          f"| Warnings | {s['alerts']['critical']} critical / {s['alerts']['warning']} warning / {s['alerts']['info']} info |",
          "", "## Key trends", ""] + [f"- {t}" for t in s["trends"]]
    md += ["", "## Status breakdown", "", "| Status | Reports |", "|---|---|"]
    md += [f"| {k} | {v} |" for k, v in s["status_counts"].items()]
    md += ["", "## Recurring problem areas", ""]
    if s["recurring"]:
        md += ["| Location | Type | Problem/All | Avg | Top issue | Last | Open | Trend |", "|---|---|---|---|---|---|---|---|"]
        md += [f"| {a.location} | {a.area_type} | {a.problem_count}/{a.count} | {a.avg_rating:.2f} | {a.top_issue} "
               f"| {a.last_date} | {a.open_count} | {a.trend} |" for a in s["recurring"]]
    else:
        md.append("None detected.")
    md += ["", "## Threshold warnings", ""]
    md += [f"- **{a.level.upper()}** `{a.code}` {a.message}" for a in alerts[:25]] or ["None."]
    if len(alerts) > 25:
        md.append(f"- ... and {len(alerts) - 25} more (see the audit log).")
    for title, rel in (chart_files or {}).items():
        md += ["", f"### {title}", f"![{title}]({rel})"]
    md += ["", "## Most recent reports", "", "| ID | Date | Location | Rating | Issue | Status |", "|---|---|---|---|---|---|"]
    md += [f"| {r.id} | {r.date} | {r.location} | {r.rating} | {r.issue_type} | {r.status} |"
           for r in sorted(reports, key=lambda r: (r.date, r.id), reverse=True)[:20]]
    path = Path(outdir) / (name or f"cleanliness_summary_{_stamp()}.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return path


def export_audit_log(reports, outdir=EXPORT_DIR, name: str | None = None) -> Path:
    s = executive_summary(reports)
    lines = ["CAMPUS CLEANLINESS REPORTER - AUDIT LOG", f"Generated: {s['generated']}", "=" * 72,
             format_summary_text(s), "", "THRESHOLD WARNINGS", "=" * 72]
    lines += [f"[{a.level.upper():8}] {a.code:<15} {a.message}" for a in generate_alerts(reports)] or ["none"]
    lines += ["", "FULL RECORD LISTING", "=" * 72]
    for r in sorted(reports, key=lambda r: r.id):
        lines.append(f"#{r.id:<4} {r.date} | {r.location} | {r.area_type} | rating {r.rating} | {r.issue_type} | "
                     f"{r.status} | by {r.reporter} | {r.description}")
    lines.append(f"-- end of log: {len(reports)} record(s) --")
    path = Path(outdir) / (name or f"audit_log_{_stamp()}.txt")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def export_all(reports, outdir=EXPORT_DIR) -> dict[str, Path]:
    outdir = Path(outdir)
    return {"Markdown summary": export_markdown(reports, outdir),
            "Plain-text audit log": export_audit_log(reports, outdir),
            "CSV report": export_csv(reports, outdir)}
