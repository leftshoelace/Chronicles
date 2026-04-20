"""Rank listings so the Telegram push surfaces the best first."""
from __future__ import annotations

from .config import MAX_TOTAL_RENT, NEIGHBORHOOD_PRIORITY
from .filter import is_accepted_neighborhood
from .model import Listing


def score(listing: Listing) -> int:
    """Higher is better. Combines neighborhood priority with price headroom."""
    hood_score = _neighborhood_score(listing)
    price_score = _price_headroom(listing)
    fee_penalty = -5 if listing.broker_fee is True else 0
    return hood_score + price_score + fee_penalty


def _neighborhood_score(listing: Listing) -> int:
    haystack = " ".join(
        (listing.neighborhood, listing.address, listing.title, listing.raw_excerpt)
    ).lower()
    best = 0
    for name, rank in NEIGHBORHOOD_PRIORITY.items():
        if name in haystack:
            # rank 1 -> 60, rank 6 -> 10; ties broken by price below
            value = 70 - rank * 10
            best = max(best, value)
    if best:
        return best
    if is_accepted_neighborhood(listing):
        return 5
    return 0


def _price_headroom(listing: Listing) -> int:
    if listing.price is None:
        return 0
    slack = MAX_TOTAL_RENT - listing.price
    if slack < 0:
        return -50
    # Each $500 under budget = +1 point, capped at +10.
    return min(10, slack // 500)
