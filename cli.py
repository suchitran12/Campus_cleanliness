"""Menu-driven terminal interface with ANSI colours and defensive input loops."""
from __future__ import annotations

import os
import sys
from datetime import date

from . import __version__, alerts as alerts_mod, charts, export, summary, validation as v
from .logic import ReportStore, recurring_areas
from .models import AREA_TYPES, ISSUE_TYPES, RATING_LABELS, STATUSES
from .storage import EXPORT_DIR
from .tables import format_table, paginate

if os.name == "nt":
    os.system("")  # enable ANSI escape sequences on Windows terminals

_COLOR = (sys.stdout.isatty() and not os.environ.get("NO_COLOR")) or bool(os.environ.get("FORCE_COLOR"))


def c(text, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else str(text)


def green(t): return c(t, "32")
def red(t): return c(t, "31")
def yellow(t): return c(t, "33")
def cyan(t): return c(t, "36")
def bold(t): return c(t, "1")
def dim(t): return c(t, "2")


BANNER = r"""
  ╔══════════════════════════════════════════════════════════╗
  ║      C A M P U S   C L E A N L I N E S S   R E P O R T E R      ║
  ║          StudentLife Hack  ·  Environment & Sustainability       ║
  ╚══════════════════════════════════════════════════════════╝"""

MENU = [
    ("1", "Record a new cleanliness report"),
    ("2", "Browse all reports (paginated)"),
    ("3", "Search & filter reports"),
    ("4", "Update a report (edit / change status)"),
    ("5", "Delete a report"),
    ("6", "Recurring problem areas"),
    ("7", "Executive summary"),
    ("8", "Threshold warnings"),
    ("9", "Generate charts (Matplotlib)"),
    ("10", "Export reports (Markdown / TXT / CSV)"),
    ("11", "Bulk import from CSV"),
    ("0", "Exit"),
]


# ------------------------------------------------------------------ input wrappers
def ask(prompt: str, validator, default=None):
    """Loop until `validator` accepts the input. Blank input uses `default` when given."""
    suffix = f" [{default}]" if default not in (None, "") else ""
    while True:
        raw = input(f"  {prompt}{suffix}: ")
        if not raw.strip() and default is not None:
            raw = str(default)
        try:
            return validator(raw)
        except v.ValidationError as exc:
            print(red(f"    ✖ {exc}  Please try again."))


def ask_optional(prompt: str, validator):
    """Blank = skip (returns None)."""
    while True:
        raw = input(f"  {prompt} (Enter to skip): ")
        if not raw.strip():
            return None
        try:
            return validator(raw)
        except v.ValidationError as exc:
            print(red(f"    ✖ {exc}"))


def ask_choice(label: str, options: list[str], default=None) -> str:
    print("   " + "  ".join(f"{i}) {o}" for i, o in enumerate(options, 1)))
    return ask(f"{label} (name or number)", lambda x: v.validate_choice(x, options, label), default)


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        raw = input(f"  {prompt} [{hint}]: ").strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print(red("    ✖ Please answer y or n."))


def ask_id(store: ReportStore) -> int:
    def check(raw):
        if not v.clean_text(raw).isdigit():
            raise v.ValidationError("Report id must be a number.")
        try:
            store.get(int(raw))
        except KeyError:
            raise v.ValidationError(f"No report with id {int(raw)}.")
        return int(raw)

    return ask("Report id", check)


def pause():
    input(dim("\n  Press Enter to continue..."))


# ------------------------------------------------------------------ display helpers
def rating_cell(rating: int) -> str:
    return f"{rating} {RATING_LABELS[rating]}"


def reports_table(reports) -> str:
    rows = [[r.id, r.date, r.location, r.area_type, rating_cell(r.rating), r.issue_type, r.status] for r in reports]
    return format_table(["ID", "Date", "Location", "Type", "Rating", "Issue", "Status"], rows, [4, 10, 30, 10, 11, 16, 11])


def show_paginated(reports, size: int = 10) -> None:
    if not reports:
        print(yellow("\n  No matching reports."))
        return
    page = 1
    while True:
        chunk, pages = paginate(reports, page, size)
        print("\n" + reports_table(chunk))
        print(dim(f"\n  Page {page}/{pages} · {len(reports)} report(s)"))
        if pages == 1:
            return
        nav = input("  [n]ext  [p]revious  [number] jump  [q]uit: ").strip().lower()
        if nav in ("q", ""):
            return
        if nav == "n":
            page = min(page + 1, pages)
        elif nav == "p":
            page = max(page - 1, 1)
        elif nav.isdigit():
            page = int(nav)
        else:
            print(red("    ✖ Use n, p, a page number or q."))


def show_report(r) -> None:
    print(f"\n  {bold('#' + str(r.id))}  {r.date}  {bold(r.location)} ({r.area_type})")
    print(f"  Rating {r.rating}/5 ({RATING_LABELS[r.rating]}) · issue: {r.issue_type} · status: {r.status} · by {r.reporter}")
    if r.description:
        print(f"  \"{r.description}\"")


def print_alerts(alert_list, limit: int = 12) -> None:
    if not alert_list:
        print(green("  ✔ No threshold warnings."))
        return
    colour = {"critical": red, "warning": yellow, "info": cyan}
    for a in alert_list[:limit]:
        print(f"  {colour[a.level](f'[{a.level.upper():8}]')} {a.message}")
    if len(alert_list) > limit:
        print(dim(f"  ... {len(alert_list) - limit} more (menu 8 shows all)"))


# ------------------------------------------------------------------ actions
def action_add(store: ReportStore) -> None:
    print(bold("\n  ── Record a new cleanliness report ──"))
    print(dim("  Tip: invalid input is caught and re-asked; Enter accepts [defaults]."))
    data = {
        "date": ask("Date YYYY-MM-DD", v.validate_date, default=date.today().isoformat()),
        "location": ask("Location (e.g. Main Cafeteria)", v.validate_location),
        "area_type": ask_choice("Area type", AREA_TYPES),
        "rating": ask("Rating 1 (filthy) .. 5 (spotless)", v.validate_rating),
        "issue_type": ask_choice("Issue type", ISSUE_TYPES, default="None"),
        "description": ask(f"Description (max {v.MAX_DESCRIPTION} chars, optional)", v.validate_description, default=""),
        "reporter": ask("Your name (optional)", v.validate_reporter, default="Anonymous"),
    }
    report = store.add(data)
    print(green(f"\n  ✔ Saved report #{report.id} for {report.location} (status: {report.status})."))
    related = [r for r in store.reports if r.location.casefold() == report.location.casefold()]
    if len(related) > 1:
        avg = sum(r.rating for r in related) / len(related)
        print(f"  This location now has {len(related)} reports, average {avg:.1f}/5.")
    flagged = [a for a in alerts_mod.generate_alerts([report]) if a.code in ("CRITICAL_RATING", "ANOMALY")]
    print_alerts(flagged)


def action_browse(store: ReportStore) -> None:
    show_paginated(sorted(store.reports, key=lambda r: (r.date, r.id), reverse=True))


def action_search(store: ReportStore) -> None:
    print(bold("\n  ── Search & filter ──  (every filter is optional)"))
    keyword = input("  Keyword (location / description / issue / reporter): ").strip()
    area = ask_optional("Area type", lambda x: v.validate_choice(x, AREA_TYPES, "Area type"))
    status = ask_optional("Status", v.validate_status)
    issue = ask_optional("Issue type", v.validate_issue_type)
    lo = ask_optional("Minimum rating", v.validate_rating)
    hi = ask_optional("Maximum rating", v.validate_rating)
    d_from = ask_optional("From date YYYY-MM-DD", v.validate_date)
    d_to = ask_optional("To date YYYY-MM-DD", v.validate_date)
    if lo and hi and lo > hi:
        lo, hi = hi, lo
        print(yellow("  (min and max rating were swapped)"))
    show_paginated(store.search(keyword, area, status, issue, lo, hi, d_from, d_to))


def action_update(store: ReportStore) -> None:
    if not store.reports:
        print(yellow("\n  Nothing to update yet."))
        return
    rid = ask_id(store)
    show_report(store.get(rid))
    mode = ask_choice("Action", ["Change status", "Edit all fields"])
    old = store.get(rid)
    if mode == "Change status":
        status = ask_choice("New status", STATUSES, default=old.status)
        store.update(rid, {"status": status})
    else:
        changes = {
            "date": ask("Date", v.validate_date, default=old.date),
            "location": ask("Location", v.validate_location, default=old.location),
            "area_type": ask_choice("Area type", AREA_TYPES, default=old.area_type),
            "rating": ask("Rating", v.validate_rating, default=old.rating),
            "issue_type": ask_choice("Issue type", ISSUE_TYPES, default=old.issue_type),
            "description": ask("Description", v.validate_description, default=old.description or ""),
            "reporter": ask("Reporter", v.validate_reporter, default=old.reporter),
            "status": ask_choice("Status", STATUSES, default=old.status),
        }
        store.update(rid, changes)
    print(green(f"\n  ✔ Report #{rid} updated."))


def action_delete(store: ReportStore) -> None:
    if not store.reports:
        print(yellow("\n  Nothing to delete."))
        return
    rid = ask_id(store)
    show_report(store.get(rid))
    if ask_yes_no(f"Permanently delete report #{rid}?"):
        store.delete(rid)
        print(green("  ✔ Deleted."))
    else:
        print("  Cancelled.")


def action_recurring(store: ReportStore) -> None:
    print(bold("\n  ── Recurring problem areas ──"))
    days = ask("Look-back window in days (0 = all time)", lambda x: _int_in(x, 0, 3650), default=30)
    minimum = ask("Minimum problem reports (rating <= 3)", lambda x: _int_in(x, 1, 100), default=3)
    areas = recurring_areas(store.reports, days or None, minimum)
    if not areas:
        print(green("\n  ✔ No recurring problem areas for these settings."))
        return
    print("\n" + summary.recurring_table(areas))
    print(dim("\n  Why flagged:"))
    for a in areas:
        print(f"   • {bold(a.location)}: " + "; ".join(a.reasons))


def _int_in(raw, lo: int, hi: int) -> int:
    text = v.clean_text(raw)
    if not text.lstrip("-").isdigit():
        raise v.ValidationError("Please enter a whole number.")
    n = int(text)
    if not lo <= n <= hi:
        raise v.ValidationError(f"Enter a number between {lo} and {hi}.")
    return n


def action_summary(store: ReportStore) -> None:
    print("\n" + summary.format_summary_text(summary.executive_summary(store.reports)))


def action_alerts(store: ReportStore) -> None:
    print(bold("\n  ── Threshold warnings ──"))
    alert_list = alerts_mod.generate_alerts(store.reports)
    counts = alerts_mod.alert_counts(alert_list)
    print(f"  {red(str(counts['critical']) + ' critical')} · {yellow(str(counts['warning']) + ' warning')} · "
          f"{cyan(str(counts['info']) + ' info')}\n")
    print_alerts(alert_list, limit=500)


def action_charts(store: ReportStore) -> None:
    files = charts.generate_all(store.reports)
    if not files:
        print(yellow("\n  Matplotlib is not installed, so charts are unavailable (pip install matplotlib)."))
        print("  Text summary instead:\n")
        print(summary.format_summary_text(summary.executive_summary(store.reports)))
        return
    print(green("\n  ✔ Charts saved:"))
    for title, path in files.items():
        print(f"    {title:<22}{path}")
    if ask_yes_no("Open the charts folder / images now?"):
        _open_path(charts.CHART_DIR)


def _open_path(path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            os.system(f'open "{path}"')
        else:
            os.system(f'xdg-open "{path}" >/dev/null 2>&1 &')
    except Exception as exc:  # never crash the menu for a viewer problem
        print(yellow(f"  Could not open automatically ({exc})."))


def action_export(store: ReportStore) -> None:
    choice = ask_choice("Format", ["Markdown", "Text audit log", "CSV", "All three"])
    charts_made = charts.generate_all(store.reports)
    rel = {t: f"charts/{p.name}" for t, p in charts_made.items()}
    if choice == "Markdown":
        out = {"Markdown summary": export.export_markdown(store.reports, chart_files=rel)}
    elif choice == "Text audit log":
        out = {"Audit log": export.export_audit_log(store.reports)}
    elif choice == "CSV":
        out = {"CSV report": export.export_csv(store.reports)}
    else:
        out = export.export_all(store.reports)
        export.export_markdown(store.reports, chart_files=rel, name=out["Markdown summary"].name)
    print(green("\n  ✔ Exported:"))
    for label, path in out.items():
        print(f"    {label:<22}{path}")


def action_import(store: ReportStore) -> None:
    print(bold("\n  ── Bulk import from CSV ──"))
    print(dim("  Required columns: date, location, area_type, rating. Optional: issue_type, description, reporter, status"))
    path = input("  Path to CSV file (try data/bad_import_sample.csv): ").strip().strip('"')
    if not path:
        print("  Cancelled.")
        return
    try:
        result = store.import_csv(path)
    except FileNotFoundError:
        print(red(f"  ✖ File not found: {path}"))
        return
    except OSError as exc:
        print(red(f"  ✖ Could not read file: {exc}"))
        return
    if result.fatal:
        print(red(f"  ✖ Import failed: {result.fatal}"))
    print(f"\n  Rows read: {result.total_rows} · {green(str(len(result.imported)) + ' imported')} · "
          f"{red(str(len(result.errors)) + ' rejected')}")
    for err in result.errors[:15]:
        print(red(f"    row {err.row}: ") + err.message)
    if len(result.errors) > 15:
        print(dim(f"    ... {len(result.errors) - 15} more in the log"))
    print(f"  Row-by-row error log: {result.log_path}")


ACTIONS = {"1": action_add, "2": action_browse, "3": action_search, "4": action_update, "5": action_delete,
           "6": action_recurring, "7": action_summary, "8": action_alerts, "9": action_charts,
           "10": action_export, "11": action_import}


def main_menu(store: ReportStore) -> None:
    print(cyan(BANNER))
    print(f"  v{__version__} · data file: {store.path} · {len(store.reports)} report(s) loaded")
    for note in store.notes:
        print(yellow(f"  ⚠ {note}"))
    counts = alerts_mod.alert_counts(alerts_mod.generate_alerts(store.reports))
    if counts["total"]:
        print(yellow(f"  ⚠ {counts['critical']} critical / {counts['warning']} warning alert(s) — choose 8 to review."))
    while True:
        print("\n" + bold("  MAIN MENU"))
        for key, label in MENU:
            print(f"   {key:>2}) {label}")
        choice = input("\n  Select an option: ").strip()
        if choice == "0":
            print(green("\n  Data saved. Keep campus clean — goodbye!"))
            return
        action = ACTIONS.get(choice)
        if not action:
            print(red("  ✖ Invalid choice — enter a number from the menu."))
            continue
        try:
            action(store)
        except KeyboardInterrupt:
            print(yellow("\n  (cancelled — back to menu)"))
        except OSError as exc:
            print(red(f"  ✖ File problem: {exc}"))
        try:
            pause()
        except (KeyboardInterrupt, EOFError):
            print()


def run_cli(store: ReportStore | None = None) -> None:
    store = store or ReportStore()
    try:
        main_menu(store)
    except (EOFError, KeyboardInterrupt):
        print(green("\n\n  Input closed. Data is already saved — goodbye!"))
