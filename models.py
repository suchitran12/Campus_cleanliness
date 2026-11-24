"""Data model and domain constants."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date as _date

AREA_TYPES = ["Classroom", "Library", "Cafeteria", "Restroom", "Hostel", "Lab", "Corridor", "Outdoor"]
ISSUE_TYPES = ["None", "Litter", "Overflowing bin", "Spill", "Odor", "Missing supplies", "Graffiti"]
STATUSES = ["Open", "In Progress", "Resolved"]
RATING_LABELS = {1: "Filthy", 2: "Poor", 3: "Fair", 4: "Clean", 5: "Spotless"}
FIELDS = ["id", "date", "location", "area_type", "rating", "issue_type", "description", "reporter", "status"]


@dataclass
class Report:
    """One cleanliness report for one location on one day."""

    id: int
    date: str  # ISO format YYYY-MM-DD
    location: str
    area_type: str
    rating: int  # 1 (filthy) .. 5 (spotless)
    issue_type: str = "None"
    description: str = ""
    reporter: str = "Anonymous"
    status: str = "Open"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Report":
        return cls(**{k: data[k] for k in FIELDS if k in data})

    @property
    def day(self) -> _date:
        return _date.fromisoformat(self.date)
