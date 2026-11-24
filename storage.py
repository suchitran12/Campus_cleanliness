"""Local persistence (JSON primary, CSV supported) with corruption recovery."""
from __future__ import annotations

import csv
import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from .models import FIELDS, Report
from .validation import ValidationError, build_report

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
EXPORT_DIR = ROOT / "exports"
DEFAULT_PATH = DATA_DIR / "reports.json"
SCHEMA_VERSION = 1


def _atomic_write(path: Path, writer) -> None:
    """Write via a temp file then os.replace so a crash never half-writes data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer(handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def save_json(reports: list[Report], path=DEFAULT_PATH) -> None:
    payload = {"schema_version": SCHEMA_VERSION, "reports": [r.to_dict() for r in reports]}
    _atomic_write(Path(path), lambda h: json.dump(payload, h, indent=2, ensure_ascii=False))


def save_csv(reports: list[Report], path) -> None:
    def writer(handle):
        out = csv.DictWriter(handle, fieldnames=FIELDS)
        out.writeheader()
        for report in reports:
            out.writerow(report.to_dict())

    _atomic_write(Path(path), writer)


def save_reports(reports: list[Report], path=DEFAULT_PATH) -> None:
    (save_csv if Path(path).suffix.lower() == ".csv" else save_json)(reports, path)


def _backup_corrupt(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.stem}.corrupt-{stamp}{path.suffix}")
    shutil.copy2(path, backup)
    return backup


def load_reports(path=DEFAULT_PATH) -> tuple[list[Report], list[str]]:
    """Return (reports, notes). Never raises for missing/corrupt storage:
    a missing file is created, a corrupt one is backed up and replaced."""
    path = Path(path)
    notes: list[str] = []

    if path.suffix.lower() == ".csv":
        from .importer import parse_csv  # local import avoids a cycle

        try:
            result = parse_csv(path)
        except FileNotFoundError:
            save_csv([], path)
            return [], [f"{path.name} was missing - created a clean file."]
        if result.fatal:
            backup = _backup_corrupt(path)
            save_csv([], path)
            return [], [f"{path.name} unreadable ({result.fatal}); backed up to {backup.name}, started clean."]
        notes += [f"Skipped row {e.row}: {e.message}" for e in result.errors]
        return result.imported, notes

    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
        records = raw.get("reports") if isinstance(raw, dict) else raw
        if not isinstance(records, list):
            raise ValueError("expected a list of reports")
    except FileNotFoundError:
        save_json([], path)
        return [], [f"{path.name} was missing - created a clean file."]
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        backup = _backup_corrupt(path)
        save_json([], path)
        return [], [f"{path.name} was corrupted ({exc}); backed up to {backup.name} and started clean."]

    reports: list[Report] = []
    seen: set[int] = set()
    for index, record in enumerate(records, start=1):
        try:
            if not isinstance(record, dict):
                raise ValidationError("record is not an object")
            rid = int(record.get("id", -1))
            if rid < 1 or rid in seen:
                raise ValidationError("missing or duplicate id")
            reports.append(build_report(record, rid))
            seen.add(rid)
        except (ValidationError, ValueError, TypeError) as exc:
            notes.append(f"Skipped stored record #{index}: {exc}")
    return reports, notes
