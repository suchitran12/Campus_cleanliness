"""Fixed-width plain-text tables and pagination helpers."""
from __future__ import annotations


def truncate(value, width: int) -> str:
    text = str(value)
    return text if len(text) <= width else text[: max(width - 1, 1)] + "…"


def format_table(headers: list[str], rows: list[list], widths: list[int]) -> str:
    """Render rows using fixed column widths and ' | ' separators."""
    def line(cells):
        return " | ".join(truncate(c, w).ljust(w) for c, w in zip(cells, widths))

    rule = "-+-".join("-" * w for w in widths)
    out = [line(headers), rule] + [line(r) for r in rows]
    return "\n".join(out)


def paginate(items: list, page: int, size: int = 10) -> tuple[list, int]:
    """Return (items_on_page, total_pages). `page` is 1-based and clamped."""
    pages = max((len(items) + size - 1) // size, 1)
    page = min(max(page, 1), pages)
    return items[(page - 1) * size: page * size], pages
