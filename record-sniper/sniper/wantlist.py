"""Read / write the wantlist CSV."""
from __future__ import annotations

import csv
from pathlib import Path

from .models import WantItem

FIELDS = ["artist", "title", "max_price", "min_condition", "discogs_id", "fair_value", "must_include", "exclude", "notes"]


def _num(v: str | None) -> float | None:
    v = (v or "").strip().replace("$", "")
    return float(v) if v else None


def _list(v: str | None) -> list[str]:
    return [x.strip() for x in (v or "").split(";") if x.strip()]


def load_wantlist(path: str | Path) -> list[WantItem]:
    items: list[WantItem] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            if not row.get("artist") and not row.get("title"):
                continue
            if row.get("artist", "").startswith("#"):
                continue
            try:
                did = row.get("discogs_id", "")
                items.append(
                    WantItem(
                        artist=row.get("artist", ""),
                        title=row.get("title", ""),
                        max_price=_num(row.get("max_price")),
                        min_condition=row.get("min_condition") or None,
                        discogs_id=int(did) if did else None,
                        fair_value=_num(row.get("fair_value")),
                        must_include=_list(row.get("must_include")),
                        exclude=_list(row.get("exclude")),
                        notes=row.get("notes", ""),
                    )
                )
            except ValueError as e:
                raise ValueError(f"{path}: bad value on line {i}: {e}") from e
    return items


def write_wantlist(path: str | Path, items: list[WantItem]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for it in items:
            w.writerow(
                {
                    "artist": it.artist,
                    "title": it.title,
                    "max_price": "" if it.max_price is None else f"{it.max_price:g}",
                    "min_condition": it.min_condition or "",
                    "discogs_id": it.discogs_id or "",
                    "fair_value": "" if it.fair_value is None else f"{it.fair_value:g}",
                    "must_include": ";".join(it.must_include),
                    "exclude": ";".join(it.exclude),
                    "notes": it.notes,
                }
            )
