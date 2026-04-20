"""Craigslist RSS ingestion. Public feeds, ToS-compliant."""
from __future__ import annotations

import logging
import re
from typing import Iterator

import feedparser

from .config import CRAIGSLIST_FEEDS
from .model import Listing

log = logging.getLogger(__name__)

_PRICE_RE = re.compile(r"\$\s?([\d,]+)")
_BEDS_RE = re.compile(r"(\d(?:\.\d)?)\s*br\b", re.IGNORECASE)
_HOOD_RE = re.compile(r"\(([^)]+)\)\s*$")


def fetch_craigslist() -> Iterator[Listing]:
    for url in CRAIGSLIST_FEEDS:
        feed = feedparser.parse(url)
        if feed.bozo:
            log.warning("craigslist feed parse warning: %s", feed.bozo_exception)
        for entry in feed.entries:
            listing = _entry_to_listing(entry)
            if listing:
                yield listing


def _entry_to_listing(entry) -> Listing | None:
    title = getattr(entry, "title", "") or ""
    link = getattr(entry, "link", "") or ""
    if not link:
        return None

    price = None
    m = _PRICE_RE.search(title)
    if m:
        try:
            price = int(m.group(1).replace(",", ""))
        except ValueError:
            price = None

    beds = None
    m = _BEDS_RE.search(title)
    if m:
        try:
            beds = float(m.group(1))
        except ValueError:
            beds = None

    hood = ""
    m = _HOOD_RE.search(title)
    if m:
        hood = m.group(1).strip()

    summary = getattr(entry, "summary", "") or ""

    return Listing(
        source="craigslist",
        url=link,
        title=title,
        price=price,
        bedrooms=beds,
        neighborhood=hood,
        raw_excerpt=_strip(summary)[:400],
    )


def _strip(s: str) -> str:
    return re.sub(r"<[^>]+>", " ", s).strip()
