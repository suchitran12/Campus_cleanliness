"""Centralised, defensive validators.

Every validator takes raw user input (str, or a number coming from the GUI),
returns the cleaned value, or raises ValidationError with a friendly message.
The CLI and the NiceGUI front-end both use these functions so behaviour is
identical everywhere.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from .models import AREA_TYPES, ISSUE_TYPES, STATUSES, Report

MAX_DESCRIPTION = 300
EARLIEST_DATE = date(2000, 1, 1)
LOCATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .,&'()#/\-]{1,59}$")
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'\-]{1,39}$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class ValidationError(ValueError):
    """Raised when input does not satisfy a domain constraint."""

    def __init__(self, message: str, errors: dict[str, str] | None = None):
        super().__init__(message)
        self.errors = errors or {}


def clean_text(value) -> str:
    """Strip control characters, collapse whitespace, trim."""
    if value is None:
        return ""
    text = _CONTROL_RE.sub("", str(value))
    return re.sub(r"\s+", " ", text).strip()


def today() -> date:
    return date.today()


def validate_date(value, today_: date | None = None) -> str:
    text = clean_text(value)
    if not text:
        raise ValidationError("Date is required (format YYYY-MM-DD).")
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError("Date must be a real calendar date in YYYY-MM-DD format, e.g. 2026-11-23.")
    if parsed > (today_ or today()):
        raise ValidationError("Date cannot be in the future.")
    if parsed < EARLIEST_DATE:
        raise ValidationError(f"Date cannot be before {EARLIEST_DATE.isoformat()}.")
    return parsed.isoformat()


def validate_optional_date(value, today_: date | None = None) -> str | None:
    """Blank means 'no filter'."""
    return validate_date(value, today_) if clean_text(value) else None


def validate_location(value) -> str:
    text = clean_text(value)
    if not text:
        raise ValidationError("Location cannot be blank.")
    if len(text) < 2 or len(text) > 60:
        raise ValidationError("Location must be 2-60 characters long.")
    if not LOCATION_RE.match(text):
        raise ValidationError("Location may only contain letters, digits, spaces and . , & ' ( ) # / -")
    return text


def validate_choice(value, options: list[str], label: str) -> str:
    """Accept an option by name (case-insensitive) or by its 1-based number."""
    text = clean_text(value)
    if not text:
        raise ValidationError(f"{label} is required.")
    if text.isdigit() and 1 <= int(text) <= len(options):
        return options[int(text) - 1]
    for option in options:
        if option.casefold() == text.casefold():
            return option
    raise ValidationError(f"{label} must be one of: {', '.join(options)}.")


def validate_area_type(value) -> str:
    return validate_choice(value, AREA_TYPES, "Area type")


def validate_issue_type(value) -> str:
    return validate_choice(value, ISSUE_TYPES, "Issue type")


def validate_status(value) -> str:
    return validate_choice(value, STATUSES, "Status")


def validate_rating(value) -> int:
    """Whole number 1-5. Rejects blanks, text, decimals, booleans."""
    if isinstance(value, bool):
        raise ValidationError("Rating must be a whole number from 1 to 5.")
    if isinstance(value, float):
        if not value.is_integer():
            raise ValidationError("Rating must be a whole number from 1 to 5.")
        number = int(value)
    elif isinstance(value, int):
        number = value
    else:
        text = clean_text(value)
        if not text:
            raise ValidationError("Rating is required (1 = filthy ... 5 = spotless).")
        if not re.fullmatch(r"[+-]?\d+", text):
            raise ValidationError("Rating must be a whole number from 1 to 5.")
        number = int(text)
    if not 1 <= number <= 5:
        raise ValidationError("Rating must be between 1 and 5.")
    return number


def validate_description(value) -> str:
    text = clean_text(value)
    if len(text) > MAX_DESCRIPTION:
        raise ValidationError(f"Description is {len(text)} characters; the limit is {MAX_DESCRIPTION}.")
    return text


def validate_reporter(value) -> str:
    text = clean_text(value)
    if not text:
        return "Anonymous"
    if not NAME_RE.match(text):
        raise ValidationError("Reporter name must be 2-40 letters (spaces . ' - allowed).")
    return text


def validate_optional_rating(value) -> int | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return validate_rating(value)
    return validate_rating(value) if clean_text(value) else None


def build_report(data: dict, report_id: int, today_: date | None = None) -> Report:
    """Validate a whole record. Collects *all* field errors before raising."""
    errors: dict[str, str] = {}

    def run(name, fn, *args):
        try:
            return fn(data.get(name), *args)
        except ValidationError as exc:
            errors[name] = str(exc)
            return None

    day = run("date", validate_date, today_)
    location = run("location", validate_location)
    area = run("area_type", validate_area_type)
    rating = run("rating", validate_rating)
    issue = run("issue_type", validate_issue_type) if clean_text(data.get("issue_type")) else "None"
    description = run("description", validate_description)
    reporter = run("reporter", validate_reporter)
    if clean_text(data.get("status")):
        status = run("status", validate_status)
    else:  # sensible default: clean + issue-free reports need no follow-up
        status = "Resolved" if (issue == "None" and rating is not None and rating >= 4) else "Open"

    if errors:
        message = "; ".join(f"{k}: {v}" for k, v in errors.items())
        raise ValidationError(message, errors)
    return Report(report_id, day, location, area, rating, issue, description, reporter, status)
