"""Bulk CSV import with automatic format validation and a row-by-row error log."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from .models import Report
from .validation import ValidationError, build_report, clean_text

REQUIRED_COLUMNS = ["date", "location", "area_type", "rating"]
OPTIONAL_COLUMNS = ["id", "issue_type", "description", "reporter", "status"]
MAX_ROWS = 5000


@dataclass
class RowError:
    row: int  # spreadsheet row number (header = 1)
    message: str
    raw: dict = field(default_factory=dict)


@dataclass
class ImportResult:
    source: str
    total_rows: int = 0
    imported: list[Report] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    fatal: str | None = None
    log_path: Path | None = None


def exact_key(r: Report) -> tuple:
    return (r.date, r.location.casefold(), r.area_type, r.rating, r.issue_type, r.description, r.reporter.casefold())


def _norm_header(name: str) -> str:
    return clean_text(name).lower().replace(" ", "_")


def _unformula(value):
    """Undo the apostrophe prefix added to neutralise spreadsheet formulas on export."""
    if isinstance(value, str) and len(value) > 1 and value[0] == "'" and value[1] in "=+-@":
        return value[1:]
    return value


def parse_csv(path, start_id: int = 1, existing: list[Report] | None = None,
              today_: date | None = None) -> ImportResult:
    """Validate every row. Good rows are returned; bad rows are collected with a reason."""
    path = Path(path)
    result = ImportResult(source=path.name)
    seen = {exact_key(r) for r in (existing or [])}
    next_id = start_id
    try:
        with open(path, newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                result.fatal = "file is empty or has no header row"
                return result
            reader.fieldnames = [_norm_header(h) for h in reader.fieldnames]
            missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
            if missing:
                result.fatal = f"missing required column(s): {', '.join(missing)}"
                return result
            for line_no, row in enumerate(reader, start=2):
                if result.total_rows >= MAX_ROWS:
                    result.errors.append(RowError(line_no, f"row limit of {MAX_ROWS} reached; remaining rows ignored"))
                    break
                if None in row:  # more cells than headers
                    result.total_rows += 1
                    result.errors.append(RowError(line_no, "row has more columns than the header", dict(row)))
                    continue
                if not any(clean_text(v) for v in row.values()):
                    continue  # silently skip fully blank lines
                result.total_rows += 1
                data = {k: _unformula(v) for k, v in row.items() if k}
                try:
                    report = build_report(data, next_id, today_)
                except ValidationError as exc:
                    result.errors.append(RowError(line_no, str(exc), data))
                    continue
                key = exact_key(report)
                if key in seen:
                    result.errors.append(RowError(line_no, "duplicate: an identical report already exists", data))
                    continue
                seen.add(key)
                result.imported.append(report)
                next_id += 1
    except UnicodeDecodeError:
        result.fatal = "file is not valid UTF-8 text"
    except csv.Error as exc:
        result.fatal = f"CSV parsing failed: {exc}"
    return result


def write_error_log(result: ImportResult, log_path) -> Path:
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"Import log - {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Source        : {result.source}",
        f"Rows read     : {result.total_rows}",
        f"Imported      : {len(result.imported)}",
        f"Rejected      : {len(result.errors)}",
    ]
    if result.fatal:
        lines.append(f"FATAL         : {result.fatal}")
    lines.append("-" * 70)
    for err in result.errors:
        lines.append(f"Row {err.row}: {err.message}")
        if err.raw:
            lines.append(f"    data: {dict(err.raw)}")
    if not result.errors and not result.fatal:
        lines.append("No errors.")
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result.log_path = log_path
    return log_path
