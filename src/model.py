"""Normalized listing record shared across sources."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Listing:
    source: str                 # "streeteasy" | "craigslist" | "zillow" | ...
    url: str
    title: str = ""
    price: Optional[int] = None
    bedrooms: Optional[float] = None
    neighborhood: str = ""
    address: str = ""
    broker_fee: Optional[bool] = None   # True=fee, False=no-fee, None=unknown
    fee_text: str = ""                  # raw fee string if present
    posted_at: Optional[datetime] = None
    raw_excerpt: str = ""               # short snippet for debugging / Telegram
    image_url: str = ""

    def fingerprint(self) -> str:
        """Stable hash used for dedupe. Prefer URL; fall back to content."""
        key = (self.url or f"{self.source}|{self.address}|{self.price}").lower()
        key = re.sub(r"[?#].*$", "", key).rstrip("/")
        return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]

    def neighborhood_key(self) -> str:
        return _normalize(self.neighborhood)


def _normalize(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9' -]", "", s)
    return re.sub(r"\s+", " ", s)
