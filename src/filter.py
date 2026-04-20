"""Drop listings that don't match our hard criteria."""
from __future__ import annotations

from .config import (
    ACCEPTED_NEIGHBORHOODS,
    BLOCKED_NEIGHBORHOODS,
    MAX_TOTAL_RENT,
    MIN_BEDROOMS,
)
from .model import Listing


def passes(listing: Listing) -> bool:
    if listing.price is not None and listing.price > MAX_TOTAL_RENT:
        return False
    if listing.bedrooms is not None and listing.bedrooms < MIN_BEDROOMS:
        return False
    if _is_blocked(listing):
        return False
    # Don't filter on accepted-neighborhood here. Email parsers frequently fail
    # to extract a neighborhood, and we'd rather show a possible match with
    # unknown neighborhood than silently drop it. Scoring handles ranking.
    return True


def _is_blocked(listing: Listing) -> bool:
    haystack = " ".join(
        (listing.neighborhood, listing.address, listing.title, listing.raw_excerpt)
    ).lower()
    return any(b in haystack for b in BLOCKED_NEIGHBORHOODS)


def is_accepted_neighborhood(listing: Listing) -> bool:
    haystack = " ".join(
        (listing.neighborhood, listing.address, listing.title, listing.raw_excerpt)
    ).lower()
    return any(n in haystack for n in ACCEPTED_NEIGHBORHOODS)
