"""Generate realistic sample data (48 reports) relative to a chosen 'today'.

Usage:  python scripts/generate_sample_data.py [--today YYYY-MM-DD]
Writes: data/sample_reports.json, data/sample_reports.csv, data/reports.json,
        data/bad_import_sample.csv
"""
import argparse
import csv
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ccr.models import FIELDS  # noqa: E402

LOC = {
    "L": ("Central Library - Ground Floor", "Library"), "C": ("Main Cafeteria", "Cafeteria"),
    "R": ("Block C Restroom (Men)", "Restroom"), "H": ("Boys Hostel A - Common Room", "Hostel"),
    "X": ("Chemistry Lab 2", "Lab"), "A": ("Lecture Hall 101", "Classroom"),
    "B": ("Lecture Hall 204", "Classroom"), "K": ("Computer Lab 1", "Lab"),
    "D": ("Admin Block Corridor", "Corridor"), "S": ("Sports Ground", "Outdoor"),
    "G": ("Main Gate Garden", "Outdoor"), "Q": ("Girls Hostel B - Lobby", "Hostel"),
    "W": ("Central Library - Reading Hall", "Library"), "V": ("Block A Restroom (Women)", "Restroom"),
    "E": ("Block D & E Corridor (2nd Floor)", "Corridor"),
}
REPORTERS = ["Aarav Sharma", "Priya Nair", "Rahul Verma", "Sneha Reddy", "Kiran Patel",
             "Meera Iyer", "Ananya Rao", "Vikram Singh", "Faculty Staff"]
TEXT = {
    "None": ["Area looks tidy and well kept.", "Floors swept, bins empty, nothing to report.", "Spotless this morning."],
    "Litter": ["Wrappers and paper cups scattered on the floor.", "Packaging left on tables and benches.", "Litter around the seating area."],
    "Overflowing bin": ["Bin is overflowing and attracting flies.", "Waste bins not emptied since yesterday.", "Garbage spilling out of the bin."],
    "Spill": ["Sticky liquid spill left uncleaned.", "Water on the floor, slipping hazard.", "Food spill near the entrance."],
    "Odor": ["Strong unpleasant smell, needs ventilation and cleaning.", "Drain smell is noticeable.", "Stale odor throughout the room."],
    "Missing supplies": ["No soap or tissue available.", "Hand wash dispenser is empty.", "Cleaning supplies not restocked."],
    "Graffiti": ["Marker graffiti on the wall.", "Scribbles on the desks and door."],
}
# (days_ago, location_key, rating, issue, status, reporter)
ROWS = [
    (27, "L", 3, "Litter", "Resolved", 1), (19, "L", 3, "Spill", "Resolved", 2), (14, "L", 2, "Odor", "In Progress", 3),
    (6, "L", 2, "Overflowing bin", "Open", 6), (2, "L", 2, "Litter", "Open", 4),
    (25, "C", 2, "Overflowing bin", "Resolved", 0), (21, "C", 3, "Spill", "Resolved", 1), (15, "C", 2, "Litter", "Resolved", 3),
    (9, "C", 1, "Overflowing bin", "Open", 5), (5, "C", 2, "Spill", "In Progress", 7), (1, "C", 2, "Litter", "Open", 6),
    (24, "R", 3, "Odor", "Resolved", 2), (18, "R", 2, "Missing supplies", "Resolved", 0), (12, "R", 2, "Odor", "Resolved", 4),
    (7, "R", 1, "Odor", "Open", 1), (3, "R", 2, "Missing supplies", "Open", 5),
    (22, "H", 2, "Litter", "Resolved", 3), (16, "H", 2, "Spill", "Resolved", 7), (8, "H", 3, "Litter", "Resolved", 2),
    (2, "H", 4, "None", "Resolved", 0),
    (20, "X", 3, "Spill", "Resolved", 8), (11, "X", 3, "Missing supplies", "Resolved", 8), (4, "X", 2, "Spill", "Open", 8),
    (30, "A", 5, "None", "Resolved", 1), (10, "A", 4, "None", "Resolved", 4), (28, "B", 4, "None", "Resolved", 5),
    (13, "B", 3, "Litter", "Resolved", 2), (33, "K", 5, "None", "Resolved", 7), (9, "K", 4, "None", "Resolved", 0),
    (38, "D", 4, "None", "Resolved", 3), (17, "D", 3, "Graffiti", "Resolved", 6), (35, "S", 4, "Litter", "Resolved", 1),
    (7, "S", 3, "Litter", "In Progress", 5), (40, "G", 5, "None", "Resolved", 2), (31, "Q", 4, "None", "Resolved", 4),
    (4, "Q", 5, "None", "Resolved", 6), (36, "W", 5, "None", "Resolved", 0), (12, "W", 4, "None", "Resolved", 7),
    (29, "V", 3, "Odor", "Resolved", 3), (6, "V", 4, "None", "Resolved", 1),
    # edge cases ----------------------------------------------------------
    (3, "B", 1, "None", "Open", 5),            # boundary rating 1, no issue (anomaly)
    (8, "A", 5, "Graffiti", "Resolved", 2),    # boundary rating 5 but an issue (anomaly)
    (15, "K", 3, "Odor", "Resolved", 4),       # 300-character description (set below)
    (1, "C", 2, "Litter", "Open", 6),          # same-day near-duplicate of a cafeteria report
    (20, "E", 4, "None", "Resolved", "Arjun O'Connor"),  # apostrophe + & ( ) in names
    (0, "G", 5, "None", "Resolved", "Anonymous"),        # reported today
    (44, "A", 5, "None", "Resolved", 3),       # oldest entry
    (5, "S", 2, "None", "Open", 7),            # rating 2 with no issue (anomaly)
]


def build(today: date):
    rng = random.Random(42)
    rows = []
    for ago, key, rating, issue, status, rep in ROWS:
        name, area = LOC[key]
        desc = rng.choice(TEXT[issue])
        if (ago, key, rating) == (15, "K", 3):
            desc = ("Persistent odor near the workstations after the weekend; ventilation seems weak and the bins "
                    "were not cleared. Please arrange a deep clean and check the air handling units before the "
                    "next practical session begins.")
            desc = (desc + " " + "x" * 300)[:300]
        if (ago, key) == (1, "C") and rows and any(r["date"] == (today - timedelta(days=1)).isoformat()
                                                    and r["location"] == name and r["issue_type"] == "Litter" for r in rows):
            desc = "Second note about the same tables - still littered."
        reporter = rep if isinstance(rep, str) else REPORTERS[rep]
        rows.append({"date": (today - timedelta(days=ago)).isoformat(), "location": name, "area_type": area,
                     "rating": rating, "issue_type": issue, "description": desc, "reporter": reporter,
                     "status": status})
    rows.sort(key=lambda r: r["date"])
    for i, row in enumerate(rows, 1):
        row["id"] = i
    return [{k: r[k] for k in FIELDS} for r in rows]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--today", default=date.today().isoformat())
    today = date.fromisoformat(parser.parse_args().today)
    data = build(today)
    d = ROOT / "data"
    d.mkdir(exist_ok=True)
    payload = json.dumps({"schema_version": 1, "reports": data}, indent=2, ensure_ascii=False)
    (d / "sample_reports.json").write_text(payload, encoding="utf-8")
    (d / "reports.json").write_text(payload, encoding="utf-8")
    with open(d / "sample_reports.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(data)

    iso = lambda n: (today - timedelta(days=n)).isoformat()
    bad = [
        [iso(2), "Lecture Hall 305", "Classroom", 4, "None", "Valid row - imports fine", "Priya Nair", ""],
        [iso(1), "Auditorium Foyer", "Corridor", 3, "Litter", "Valid row - imports fine", "Rahul Verma", "Open"],
        ["23/11/2026", "Main Cafeteria", "Cafeteria", 3, "Spill", "Wrong date format", "Kiran Patel", "Open"],
        [(today + timedelta(days=5)).isoformat(), "Main Cafeteria", "Cafeteria", 3, "Spill", "Future date", "Kiran Patel", ""],
        [iso(3), "Sports Ground", "Outdoor", 7, "Litter", "Rating out of range", "Meera Iyer", "Open"],
        [iso(3), "Sports Ground", "Outdoor", "abc", "Litter", "Rating not a number", "Meera Iyer", "Open"],
        [iso(3), "", "Library", 3, "None", "Blank location", "Ananya Rao", "Open"],
        [iso(3), "Rooftop Terrace", "Rooftop", 3, "None", "Unknown area type", "Ananya Rao", "Open"],
        [iso(3), "<script>alert(1)</script>", "Lab", 3, "None", "Illegal characters", "Vikram Singh", "Open"],
        [iso(3), "Chemistry Lab 2", "Lab", 3, "Spill", "y" * 320, "Vikram Singh", "Open"],
        [iso(3), "Chemistry Lab 2", "Lab", "", "Spill", "Missing rating", "Vikram Singh", "Open"],
        [data[0]["date"], data[0]["location"], data[0]["area_type"], data[0]["rating"], data[0]["issue_type"],
         data[0]["description"], data[0]["reporter"], data[0]["status"]],
    ]
    with open(d / "bad_import_sample.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "location", "area_type", "rating", "issue_type", "description", "reporter", "status"])
        w.writerows(bad)
    print(f"Wrote {len(data)} sample reports ending {data[-1]['date']} (today={today}) to {d}")


if __name__ == "__main__":
    main()
