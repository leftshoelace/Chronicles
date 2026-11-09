"""Core data types shared across the sniper."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WantItem:
    """One record on your wantlist."""

    artist: str
    title: str
    max_price: float | None = None  # the most you'd pay, shipping included
    min_condition: str | None = None  # e.g. "VG+" (only enforced when a listing states a grade)
    discogs_id: int | None = None  # Discogs *release* id, if you know the exact pressing
    fair_value: float | None = None  # manual override for the reference price
    must_include: list[str] = field(default_factory=list)  # e.g. ["first press"]
    exclude: list[str] = field(default_factory=list)  # e.g. ["reissue", "2016"]
    notes: str = ""

    @property
    def query(self) -> str:
        return f"{self.artist} {self.title}".strip()

    @property
    def label(self) -> str:
        return f"{self.artist} – {self.title}"

    @property
    def key(self) -> str:
        return f"{self.artist.lower().strip()}|{self.title.lower().strip()}"


@dataclass
class Listing:
    """A copy of a record for sale somewhere."""

    source: str
    source_id: str
    title: str
    url: str
    price: float
    currency: str = "USD"
    shipping: float | None = None  # None = unknown
    location: str = ""
    local: bool = False  # can be picked up near you
    is_auction: bool = False
    ends_at: str | None = None  # ISO timestamp for auctions
    condition: str = ""
    image: str = ""
    exact: bool = False  # True when the source already matched the exact release (skip fuzzy matching)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"


@dataclass
class Reference:
    """What a record is actually worth."""

    value: float
    basis: str  # human-readable, e.g. "Discogs VG+ suggestion"
    release_id: int | None = None
    num_for_sale: int | None = None
    lowest_listed: float | None = None


@dataclass
class Deal:
    want: WantItem
    listing: Listing
    total: float
    shipping_assumed: bool
    reference: Reference | None
    tier: str  # "STEAL" or "DEAL"
    score: float  # 0..1, higher = better
    reasons: list[str]
    flip_profit: float | None
    hours_left: float | None = None
