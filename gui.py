"""NiceGUI web interface - same core logic as the CLI, modern look.

Run with:  python main.py --gui      (then open http://localhost:8080)
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import date

from nicegui import app, ui

from . import alerts as alerts_mod, charts, export, summary, validation as v
from .logic import ReportStore, recurring_areas, search_reports
from .models import AREA_TYPES, ISSUE_TYPES, RATING_LABELS, STATUSES
from .storage import DATA_DIR, EXPORT_DIR

_store: ReportStore | None = None

NAV = [("Dashboard", "/", "space_dashboard"), ("New report", "/new", "add_circle"),
       ("Records", "/records", "table_rows"), ("Recurring areas", "/recurring", "repeat"),
       ("Analytics", "/analytics", "insights"), ("Import / Export", "/data", "import_export")]

HEAD = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@500;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--ink:#17301f;--paper:#f4f3ea;--card:#ffffff;--line:#dcdfcf;--leaf:#2f6b3f;--clay:#c8553d;--sun:#e2a72e;--muted:#667466}
body.body--dark{--ink:#e7efe0;--paper:#0f1a13;--card:#17251c;--line:#2b3b30;--muted:#9bb09f}
body,.q-page,.q-layout{background:var(--paper)!important;color:var(--ink);font-family:'IBM Plex Sans',system-ui,sans-serif}
.display{font-family:'Bricolage Grotesque','IBM Plex Sans',sans-serif;letter-spacing:-.02em;font-weight:700}
.panel{background:var(--card);border:1px solid var(--line);border-radius:16px;box-shadow:none;padding:18px}
.kpi-v{font-family:'Bricolage Grotesque',sans-serif;font-size:2.1rem;line-height:1;font-weight:700}
.kpi-l{color:var(--muted);font-size:.78rem;text-transform:uppercase;letter-spacing:.08em}
.app-header{background:var(--leaf)!important;color:#fff}
.app-drawer{background:var(--card)!important;border-right:1px solid var(--line)}
.nav-item{border-radius:10px;padding:8px 12px;color:var(--ink);text-decoration:none;width:100%}
.nav-item:hover,.nav-item.active{background:rgba(47,107,63,.14)}
.nav-item.active{font-weight:600;color:var(--leaf)}
body.body--dark .nav-item.active{color:#9fd8a8}
.muted{color:var(--muted)}
.alert-row{border-left:4px solid var(--sun);padding:6px 10px;border-radius:6px;background:rgba(226,167,46,.10)}
.alert-row.critical{border-color:var(--clay);background:rgba(200,85,61,.10)}
.alert-row.info{border-color:#5b8bb0;background:rgba(91,139,176,.10)}
</style>
"""


def get_store() -> ReportStore:
    global _store
    if _store is None:
        _store = ReportStore()
    return _store


def validator_for(fn):
    """Adapt a ccr validator to NiceGUI's `validation=` callable (returns message or None)."""
    def check(value):
        try:
            fn(value)
            return None
        except v.ValidationError as exc:
            return str(exc)
    return check


def optional_date(value):
    return v.validate_optional_date(value)


def rating_color(r: int) -> str:
    return {1: "negative", 2: "deep-orange", 3: "warning", 4: "light-green", 5: "positive"}[r]


def download(url: str) -> None:
    getattr(ui.download, "from_url", ui.download)(url)


# ------------------------------------------------------------------ layout
@contextmanager
def page_frame(active: str):
    ui.colors(primary="#2f6b3f", secondary="#6b8f71", accent="#e2a72e",
              positive="#2f8f4e", negative="#c8553d", warning="#e2a72e")
    ui.add_head_html(HEAD)
    dark = ui.dark_mode(app.storage.user.get("dark", False))

    def toggle_dark():
        dark.value = not dark.value
        app.storage.user["dark"] = dark.value

    with ui.header().classes("app-header items-center justify-between q-px-md"):
        with ui.row().classes("items-center gap-2"):
            ui.button(icon="menu", on_click=lambda: drawer.toggle()).props("flat round dense color=white")
            ui.label("Campus Cleanliness Reporter").classes("display text-lg")
        ui.button(icon="dark_mode", on_click=toggle_dark).props("flat round dense color=white").tooltip("Toggle dark mode")
    with ui.left_drawer(value=True, bordered=False).classes("app-drawer") as drawer:
        ui.label("StudentLife Hack · #42").classes("kpi-l q-mb-sm")
        for label, path, icon in NAV:
            with ui.link(target=path).classes("nav-item" + (" active" if path == active else "")):
                with ui.row().classes("items-center gap-3 no-wrap"):
                    ui.icon(icon)
                    ui.label(label)
        for note in get_store().notes:
            ui.label("⚠ " + note).classes("text-xs q-mt-md").style("color:var(--clay)")
    with ui.column().classes("w-full max-w-6xl mx-auto gap-4 q-pa-md"):
        yield


def kpi(label: str, value, hint: str = "") -> None:
    with ui.column().classes("panel gap-1 grow").style("min-width:150px"):
        ui.label(str(value)).classes("kpi-v")
        ui.label(label).classes("kpi-l")
        if hint:
            ui.label(hint).classes("text-xs muted")


def alert_list(items, limit: int = 6) -> None:
    if not items:
        ui.label("✔ No threshold warnings.").classes("muted")
        return
    icons = {"critical": "error", "warning": "warning", "info": "info"}
    for a in items[:limit]:
        with ui.row().classes(f"alert-row {a.level} items-center gap-2 w-full no-wrap"):
            ui.icon(icons[a.level])
            ui.label(a.message).classes("text-sm")
    if len(items) > limit:
        with ui.expansion(f"Show {len(items) - limit} more").classes("w-full"):
            for a in items[limit:]:
                with ui.row().classes(f"alert-row {a.level} items-center gap-2 w-full no-wrap"):
                    ui.icon(icons[a.level])
                    ui.label(a.message).classes("text-sm")


def image_or_notice(path, caption: str = "") -> None:
    if path:
        ui.image(f"/exports/charts/{path.name}?v={int(time.time())}").classes("w-full rounded-lg")
    else:
        ui.label("Charts need Matplotlib: pip install matplotlib").classes("muted")


def date_field(label: str, value: str = "", required: bool = True):
    rule = v.validate_date if required else optional_date
    with ui.input(label, value=value, placeholder="YYYY-MM-DD", validation=validator_for(rule)).classes("w-full") as inp:
        with ui.menu().props("no-parent-event") as menu:
            with ui.date().bind_value(inp):
                with ui.row().classes("justify-end"):
                    ui.button("Close", on_click=menu.close).props("flat")
        with inp.add_slot("append"):
            ui.icon("edit_calendar").on("click", menu.open).classes("cursor-pointer")
    return inp


# ------------------------------------------------------------------ report form (new + edit)
class ReportForm:
    def __init__(self, report=None):
        store = get_store()
        r = report
        self.location = ui.input("Location", value=r.location if r else "", placeholder="e.g. Main Cafeteria",
                                 autocomplete=store.locations(), validation=validator_for(v.validate_location)).classes("w-full")
        with ui.row().classes("w-full no-wrap gap-3"):
            self.area = ui.select(AREA_TYPES, label="Area type", value=r.area_type if r else AREA_TYPES[0]).classes("grow")
            self.date = date_field("Date", r.date if r else date.today().isoformat())
        with ui.row().classes("w-full no-wrap gap-3 items-start"):
            self.rating = ui.number("Rating (1 filthy – 5 spotless)", value=r.rating if r else None,
                                    min=1, max=5, step=1, format="%.0f",
                                    validation=validator_for(v.validate_rating)).classes("grow")
            self.issue = ui.select(ISSUE_TYPES, label="Issue type", value=r.issue_type if r else "None").classes("grow")
        self.description = ui.textarea("Description (optional, max 300 characters)", value=r.description if r else "",
                                       validation=validator_for(v.validate_description)).classes("w-full").props("counter autogrow")
        with ui.row().classes("w-full no-wrap gap-3"):
            self.reporter = ui.input("Your name (optional)", value=r.reporter if r and r.reporter != "Anonymous" else "",
                                     validation=validator_for(v.validate_reporter)).classes("grow")
            self.status = ui.select(["Auto"] + STATUSES, label="Status", value=r.status if r else "Auto").classes("grow")

    def fields(self):
        return [self.location, self.date, self.rating, self.description, self.reporter]

    def validate(self) -> bool:
        return all([f.validate() for f in self.fields()])  # list => run all, show every error

    def values(self) -> dict:
        return {"location": self.location.value, "area_type": self.area.value, "date": self.date.value,
                "rating": self.rating.value, "issue_type": self.issue.value, "description": self.description.value,
                "reporter": self.reporter.value, "status": "" if self.status.value == "Auto" else self.status.value}


def notify_errors(exc: v.ValidationError) -> None:
    ui.notify("; ".join(exc.errors.values()) or str(exc), type="negative", multi_line=True)


# ------------------------------------------------------------------ pages
@ui.page("/")
def dashboard():
    store = get_store()
    with page_frame("/"):
        s = summary.executive_summary(store.reports)
        alerts = alerts_mod.generate_alerts(store.reports)
        ui.label(f"Campus status: {s['status']}").classes("display text-3xl")
        ui.label(f"{s['total']} reports · average {s['avg_rating'] if s['avg_rating'] is not None else 'n/a'}/5 · "
                 f"{len(s['recurring'])} recurring problem area(s)").classes("muted")
        with ui.row().classes("w-full gap-3"):
            kpi("Total reports", s["total"])
            kpi("Average rating", s["avg_rating"] if s["avg_rating"] is not None else "–", "out of 5")
            kpi("Unresolved", s["unresolved"], f"{s['resolution_rate']}% resolved")
            kpi("Critical warnings", s["alerts"]["critical"], f"{s['alerts']['warning']} more warnings")
        with ui.row().classes("w-full gap-4 items-start"):
            with ui.column().classes("panel grow gap-2").style("flex-basis:380px"):
                ui.label("Threshold warnings").classes("display text-lg")
                alert_list(alerts)
            with ui.column().classes("panel grow gap-2").style("flex-basis:380px"):
                ui.label("Hotspots right now").classes("display text-lg")
                if not s["recurring"]:
                    ui.label("✔ No recurring problem areas.").classes("muted")
                for a in s["recurring"][:4]:
                    with ui.row().classes("items-center justify-between w-full no-wrap"):
                        with ui.column().classes("gap-0"):
                            ui.label(a.location).classes("font-medium")
                            ui.label(f"{a.top_issue} · {a.problem_count} problem reports · {a.trend}").classes("text-xs muted")
                        ui.badge(f"{a.avg_rating:.1f}", color=rating_color(max(1, min(5, round(a.avg_rating)))))
        with ui.column().classes("panel w-full gap-2"):
            ui.label("Key trends").classes("display text-lg")
            for t in s["trends"]:
                ui.label("• " + t).classes("text-sm")
            try:
                image_or_notice(charts.rating_trend_chart(store.reports))
            except charts.ChartUnavailable:
                image_or_notice(None)


@ui.page("/new")
def new_report():
    store = get_store()
    with page_frame("/new"):
        ui.label("Record a cleanliness report").classes("display text-3xl")
        ui.label("Every field is validated live — the same rules as the terminal app.").classes("muted")
        with ui.column().classes("panel w-full max-w-2xl gap-3"):
            form = ReportForm()

            def submit():
                if not form.validate():
                    ui.notify("Please fix the highlighted fields.", type="warning")
                    return
                try:
                    report = store.add(form.values())
                except v.ValidationError as exc:
                    notify_errors(exc)
                    return
                ui.notify(f"Saved report #{report.id} for {report.location}", type="positive")
                for a in alerts_mod.generate_alerts([report]):
                    if a.code in ("CRITICAL_RATING", "ANOMALY"):
                        ui.notify(a.message, type="warning" if a.level != "info" else "info")
                ui.navigate.to("/records")

            ui.button("Save report", icon="check", on_click=submit).props("unelevated color=primary")


@ui.page("/records")
def records():
    store = get_store()
    with page_frame("/records"):
        ui.label("Records").classes("display text-3xl")
        with ui.column().classes("panel w-full gap-2"):
            with ui.row().classes("w-full items-end gap-3"):
                kw = ui.input("Search keyword", placeholder="location, description, issue…").props("clearable dense outlined").classes("grow")
                area = ui.select(["Any"] + AREA_TYPES, value="Any", label="Area").props("dense outlined").classes("w-36")
                status = ui.select(["Any"] + STATUSES, value="Any", label="Status").props("dense outlined").classes("w-36")
                issue = ui.select(["Any"] + ISSUE_TYPES, value="Any", label="Issue").props("dense outlined").classes("w-44")
                lo = ui.select([1, 2, 3, 4, 5], value=1, label="Min rating").props("dense outlined").classes("w-28")
                hi = ui.select([1, 2, 3, 4, 5], value=5, label="Max rating").props("dense outlined").classes("w-28")
            with ui.row().classes("w-full items-start gap-3"):
                d_from = date_field("From date", "", required=False).props("dense outlined").classes("w-44")
                d_to = date_field("To date", "", required=False).props("dense outlined").classes("w-44")
            count = ui.label().classes("muted text-sm")

        columns = [
            {"name": "id", "label": "ID", "field": "id", "sortable": True, "align": "left"},
            {"name": "date", "label": "Date", "field": "date", "sortable": True, "align": "left"},
            {"name": "location", "label": "Location", "field": "location", "sortable": True, "align": "left"},
            {"name": "area_type", "label": "Type", "field": "area_type", "sortable": True, "align": "left"},
            {"name": "rating", "label": "Rating", "field": "rating", "sortable": True, "align": "center"},
            {"name": "issue_type", "label": "Issue", "field": "issue_type", "sortable": True, "align": "left"},
            {"name": "status", "label": "Status", "field": "status", "sortable": True, "align": "left"},
            {"name": "actions", "label": "", "field": "id", "align": "right"},
        ]
        table = ui.table(columns=columns, rows=[], row_key="id", pagination=10).classes("w-full panel")
        table.add_slot("body-cell-rating", r"""
            <q-td :props="props">
              <q-badge :color="['','negative','deep-orange','warning','light-green','positive'][props.row.rating]"
                       :label="props.row.rating + ' · ' + props.row.rating_label" />
            </q-td>""")
        table.add_slot("body-cell-status", r"""
            <q-td :props="props">
              <q-badge outline :color="props.row.status==='Resolved'?'positive':props.row.status==='Open'?'negative':'warning'"
                       :label="props.row.status" />
            </q-td>""")
        table.add_slot("body-cell-actions", r"""
            <q-td :props="props">
              <q-btn flat dense round icon="visibility" @click="() => $parent.$emit('view', props.row)" />
              <q-btn flat dense round icon="check_circle" color="positive" @click="() => $parent.$emit('resolve', props.row)" />
              <q-btn flat dense round icon="edit" @click="() => $parent.$emit('edit', props.row)" />
              <q-btn flat dense round icon="delete" color="negative" @click="() => $parent.$emit('remove', props.row)" />
            </q-td>""")

        current: list = []

        def refresh(_=None):
            try:
                d1, d2 = v.validate_optional_date(d_from.value), v.validate_optional_date(d_to.value)
            except v.ValidationError:
                return  # inline validation message is already visible
            a, b = sorted((lo.value, hi.value))
            found = search_reports(store.reports, kw.value or "", None if area.value == "Any" else area.value,
                                   None if status.value == "Any" else status.value,
                                   None if issue.value == "Any" else issue.value, a, b, d1, d2)
            current[:] = found
            table.rows = [{**r.to_dict(), "rating_label": RATING_LABELS[r.rating]} for r in found]
            table.update()
            count.set_text(f"{len(found)} of {len(store.reports)} reports match")

        for control in (kw, area, status, issue, lo, hi, d_from, d_to):
            control.on_value_change(refresh)

        def reset():
            kw.value, area.value, status.value, issue.value, lo.value, hi.value = "", "Any", "Any", "Any", 1, 5
            d_from.value = d_to.value = ""
            refresh()

        def export_filtered():
            path = export.export_csv(current, name="filtered_records.csv")
            download(f"/exports/{path.name}")

        with ui.row().classes("gap-2"):
            ui.button("Reset filters", icon="restart_alt", on_click=reset).props("flat")
            ui.button("Export these results (CSV)", icon="download", on_click=export_filtered).props("flat")

        def view(e):
            row = e.args
            with ui.dialog() as dlg, ui.card().classes("w-96"):
                ui.label(f"#{row['id']} · {row['location']}").classes("display text-lg")
                ui.label(f"{row['date']} · {row['area_type']} · reported by {row['reporter']}").classes("muted text-sm")
                ui.label(f"Rating {row['rating']}/5 ({row['rating_label']}) · {row['issue_type']} · {row['status']}")
                ui.label(row["description"] or "No description.")
                ui.button("Close", on_click=dlg.close).props("flat")
            dlg.open()

        def resolve(e):
            store.set_status(e.args["id"], "Resolved")
            ui.notify(f"Report #{e.args['id']} marked Resolved", type="positive")
            refresh()

        def edit(e):
            report = store.get(e.args["id"])
            with ui.dialog() as dlg, ui.card().classes("w-full max-w-xl gap-3"):
                ui.label(f"Edit report #{report.id}").classes("display text-lg")
                form = ReportForm(report)

                def save():
                    if not form.validate():
                        return
                    try:
                        store.update(report.id, form.values())
                    except v.ValidationError as exc:
                        notify_errors(exc)
                        return
                    ui.notify("Report updated", type="positive")
                    dlg.close()
                    refresh()

                with ui.row().classes("justify-end w-full"):
                    ui.button("Cancel", on_click=dlg.close).props("flat")
                    ui.button("Save", on_click=save).props("unelevated color=primary")
            dlg.open()

        def remove(e):
            rid = e.args["id"]
            with ui.dialog() as dlg, ui.card():
                ui.label(f"Permanently delete report #{rid}?")
                with ui.row().classes("justify-end w-full"):
                    ui.button("Cancel", on_click=dlg.close).props("flat")

                    def confirm():
                        store.delete(rid)
                        dlg.close()
                        ui.notify(f"Deleted report #{rid}", type="info")
                        refresh()

                    ui.button("Delete", on_click=confirm).props("unelevated color=negative")
            dlg.open()

        table.on("view", view)
        table.on("resolve", resolve)
        table.on("edit", edit)
        table.on("remove", remove)
        refresh()


@ui.page("/recurring")
def recurring():
    store = get_store()
    with page_frame("/recurring"):
        ui.label("Recurring problem areas").classes("display text-3xl")
        ui.label("A location recurs when it has enough problem reports (rating ≤ 3) in the window, "
                 "or an average rating at or below the limit.").classes("muted")
        with ui.row().classes("panel w-full items-end gap-4"):
            days = ui.number("Window (days, 0 = all time)", value=30, min=0, max=3650, format="%.0f").classes("w-52")
            minimum = ui.number("Min problem reports", value=3, min=1, max=100, format="%.0f").classes("w-44")
            max_avg = ui.number("Max average rating", value=2.5, min=1, max=5, step=0.1).classes("w-44")

        @ui.refreshable
        def results():
            areas = recurring_areas(store.reports, int(days.value or 0) or None, int(minimum.value or 3),
                                    float(max_avg.value or 2.5))
            ui.label(f"{len(areas)} recurring area(s)").classes("muted")
            rows = [{"location": a.location, "area": a.area_type, "problems": f"{a.problem_count}/{a.count}",
                     "avg": a.avg_rating, "issue": a.top_issue, "last": a.last_date, "open": a.open_count,
                     "trend": {"worsening": "↘ worsening", "improving": "↗ improving", "stable": "→ stable"}.get(a.trend, "–"),
                     "why": "; ".join(a.reasons)} for a in areas]
            cols = [{"name": k, "label": lab, "field": k, "align": "left", "sortable": True} for k, lab in
                    [("location", "Location"), ("area", "Type"), ("problems", "Problem/All"), ("avg", "Avg"),
                     ("issue", "Top issue"), ("last", "Last reported"), ("open", "Open"), ("trend", "Trend"), ("why", "Why flagged")]]
            ui.table(columns=cols, rows=rows, row_key="location", pagination=10).classes("w-full panel")

        results()
        for control in (days, minimum, max_avg):
            control.on_value_change(lambda _: results.refresh())


@ui.page("/analytics")
def analytics():
    store = get_store()
    with page_frame("/analytics"):
        ui.label("Analytics").classes("display text-3xl")

        @ui.refreshable
        def body():
            s = summary.executive_summary(store.reports)
            with ui.row().classes("w-full gap-3"):
                kpi("Campus status", s["status"])
                kpi("Average rating", s["avg_rating"] if s["avg_rating"] is not None else "–")
                kpi("Resolution rate", f"{s['resolution_rate']}%")
                kpi("Warnings", s["alerts"]["total"], f"{s['alerts']['critical']} critical")
            with ui.column().classes("panel w-full gap-1"):
                ui.label("Key trends").classes("display text-lg")
                for t in s["trends"]:
                    ui.label("• " + t).classes("text-sm")
            files = charts.generate_all(store.reports)
            if not files:
                image_or_notice(None)
            with ui.grid(columns=2).classes("w-full gap-4"):
                for title, path in files.items():
                    with ui.column().classes("panel gap-2"):
                        ui.label(title).classes("display")
                        image_or_notice(path)
            with ui.row().classes("w-full gap-4 items-start"):
                with ui.column().classes("panel grow gap-1"):
                    ui.label("Top issues").classes("display text-lg")
                    for k, n in sorted(s["issue_counts"].items(), key=lambda kv: -kv[1]):
                        ui.label(f"{k}: {n}").classes("text-sm")
                with ui.column().classes("panel grow gap-1"):
                    ui.label("Lowest-rated locations").classes("display text-lg")
                    for a in s["worst_locations"]:
                        ui.label(f"{a.location}: {a.avg_rating:.2f} ({a.count} reports)").classes("text-sm")

        ui.button("Refresh charts", icon="refresh", on_click=body.refresh).props("flat")
        body()


@ui.page("/data")
def data_page():
    store = get_store()
    with page_frame("/data"):
        ui.label("Import / Export").classes("display text-3xl")
        with ui.column().classes("panel w-full gap-3"):
            ui.label("Export reports").classes("display text-lg")
            ui.label("Files are written to the exports/ folder and downloaded.").classes("muted text-sm")

            def do_export(kind: str):
                made_charts = charts.generate_all(store.reports)
                rel = {t: f"charts/{p.name}" for t, p in made_charts.items()}
                paths = {"md": lambda: export.export_markdown(store.reports, chart_files=rel),
                         "txt": lambda: export.export_audit_log(store.reports),
                         "csv": lambda: export.export_csv(store.reports)}
                for key in (["md", "txt", "csv"] if kind == "all" else [kind]):
                    path = paths[key]()
                    ui.notify(f"Exported {path.name}", type="positive")
                    download(f"/exports/{path.name}")

            with ui.row().classes("gap-2"):
                ui.button("Markdown summary", icon="description", on_click=lambda: do_export("md")).props("outline")
                ui.button("Text audit log", icon="receipt_long", on_click=lambda: do_export("txt")).props("outline")
                ui.button("CSV report", icon="table_chart", on_click=lambda: do_export("csv")).props("outline")
                ui.button("All three", icon="download", on_click=lambda: do_export("all")).props("unelevated color=primary")

        with ui.column().classes("panel w-full gap-3"):
            ui.label("Bulk import from CSV").classes("display text-lg")
            ui.label("Required columns: date, location, area_type, rating · optional: issue_type, description, reporter, status. "
                     "Every row is validated; bad rows are skipped and logged.").classes("muted text-sm")
            ui.link("Download the bad-row demo file (bad_import_sample.csv)", "/data-files/bad_import_sample.csv")
            result_box = ui.column().classes("w-full gap-2")

            async def handle_upload(e):
                if hasattr(e, "file"):  # NiceGUI >= 3
                    content, name = await e.file.read(), e.file.name
                else:  # NiceGUI 1.x / 2.x
                    content, name = e.content.read(), e.name
                tmp = EXPORT_DIR / "_upload.csv"
                EXPORT_DIR.mkdir(parents=True, exist_ok=True)
                tmp.write_bytes(content)
                result = store.import_csv(tmp, EXPORT_DIR / "import_errors.log")
                result.source = name
                from .importer import write_error_log
                write_error_log(result, EXPORT_DIR / "import_errors.log")
                result_box.clear()
                with result_box:
                    if result.fatal:
                        ui.label(f"✖ Import failed: {result.fatal}").style("color:var(--clay)")
                    ui.label(f"{name}: {result.total_rows} rows read · {len(result.imported)} imported · "
                             f"{len(result.errors)} rejected").classes("font-medium")
                    if result.errors:
                        cols = [{"name": "row", "label": "Row", "field": "row", "align": "left"},
                                {"name": "message", "label": "Reason", "field": "message", "align": "left"}]
                        ui.table(columns=cols, rows=[{"row": x.row, "message": x.message} for x in result.errors],
                                 row_key="row", pagination=8).classes("w-full")
                        ui.button("Download error log", icon="download",
                                  on_click=lambda: download("/exports/import_errors.log")).props("flat")
                ui.notify(f"Imported {len(result.imported)} report(s)", type="positive" if result.imported else "warning")

            ui.upload(label="Drop a CSV here or click to choose", on_upload=handle_upload, auto_upload=True,
                      max_file_size=2_000_000).props("accept=.csv flat bordered").classes("w-full")


def run_gui(store: ReportStore | None = None, host: str = "127.0.0.1", port: int = 8080) -> None:
    global _store
    if store is not None:
        _store = store
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    (EXPORT_DIR / "charts").mkdir(parents=True, exist_ok=True)
    app.add_static_files("/exports", str(EXPORT_DIR))
    app.add_static_files("/data-files", str(DATA_DIR))
    ui.run(title="Campus Cleanliness Reporter", host=host, port=port, reload=False, show=True,
           favicon="🧹", storage_secret="campus-cleanliness-reporter")
