"""Discogs: the price guide (what a record is worth) and a source (cheapest copy listed right now).

Uses the official API: https://www.discogs.com/developers
Get a personal token at https://www.discogs.com/settings/developers
"""
from __future__ import annotations

import time

from ..config import Config
from ..db import Store
from ..http import HttpError, get_json
from ..models import Listing, Reference, WantItem

API = "https://api.discogs.com"


class DiscogsClient:
    def __init__(self, token: str, min_interval: float | None = None):
        self.token = token
        # 60 req/min authenticated, 25 unauthenticated.
        self.min_interval = min_interval if min_interval is not None else (1.05 if token else 2.5)
        self._last = 0.0

    def get(self, path: str, **params):
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        headers = {"Authorization": f"Discogs token={self.token}"} if self.token else {}
        try:
            return get_json(f"{API}{path}", params=params or None, headers=headers)
        finally:
            self._last = time.monotonic()

    # --- lookups ------------------------------------------------------------
    def search_release_id(self, artist: str, title: str) -> int | None:
        """Find the canonical (main) release for an artist/title, preferring vinyl."""
        if not self.token:
            return None  # database search requires auth
        res = self.get("/database/search", artist=artist, release_title=title, type="master", format="Vinyl", per_page=5)
        for r in res.get("results", []):
            if r.get("type") == "master" and r.get("id"):
                master = self.get(f"/masters/{r['id']}")
                if master.get("main_release"):
                    return int(master["main_release"])
        res = self.get("/database/search", artist=artist, release_title=title, type="release", format="Vinyl", per_page=5)
        for r in res.get("results", []):
            if r.get("id"):
                return int(r["id"])
        return None

    def stats(self, release_id: int, currency: str = "USD") -> dict:
        return self.get(f"/marketplace/stats/{release_id}", curr_abbr=currency) or {}

    def price_suggestions(self, release_id: int) -> dict:
        """Requires the token's account to have seller settings filled in; returns {} otherwise."""
        if not self.token:
            return {}
        try:
            return self.get(f"/marketplace/price_suggestions/{release_id}") or {}
        except HttpError as e:
            if e.status in (401, 403, 404):
                return {}
            raise

    def user_wants(self, username: str):
        page = 1
        while True:
            res = self.get(f"/users/{username}/wants", page=page, per_page=100)
            yield from res.get("wants", [])
            if page >= res.get("pagination", {}).get("pages", 1):
                break
            page += 1


class PriceGuide:
    """Works out a fair value for each wanted record, cached in SQLite."""

    def __init__(self, cfg: Config, store: Store, client: DiscogsClient | None = None):
        self.cfg = cfg
        self.store = store
        self.client = client or DiscogsClient(cfg.discogs_token)

    def release_id(self, want: WantItem) -> int | None:
        if want.discogs_id:
            return want.discogs_id
        ck = f"discogs:rid:{want.key}"
        cached = self.store.cache_get(ck, ttl_hours=None)
        if cached is not None:
            return cached or None
        rid = self.client.search_release_id(want.artist, want.title)
        self.store.cache_set(ck, rid or 0)
        return rid

    def _market(self, rid: int) -> dict:
        ck = f"discogs:market:{rid}:{self.cfg.currency}"
        cached = self.store.cache_get(ck, ttl_hours=self.cfg.discogs_cache_hours)
        if cached is not None:
            return cached
        data = {"stats": self.client.stats(rid, self.cfg.currency), "suggestions": self.client.price_suggestions(rid)}
        self.store.cache_set(ck, data)
        return data

    def reference(self, want: WantItem) -> Reference | None:
        rid = None
        try:
            rid = self.release_id(want)
        except HttpError as e:
            print(f"  ! Discogs search failed for {want.label}: {e}")
        if want.fair_value:
            return Reference(value=want.fair_value, basis="your fair value", release_id=rid)
        if not rid:
            return None
        try:
            m = self._market(rid)
        except HttpError as e:
            print(f"  ! Discogs price lookup failed for {want.label}: {e}")
            return None
        stats, sugg = m.get("stats") or {}, m.get("suggestions") or {}
        lowest = (stats.get("lowest_price") or {}).get("value")
        n = stats.get("num_for_sale")
        s = sugg.get(self.cfg.discogs_reference_condition) or {}
        if s.get("value"):
            short = self.cfg.discogs_reference_condition.split("(")[-1].rstrip(")")
            return Reference(value=round(float(s["value"]), 2), basis=f"Discogs {short} suggestion",
                             release_id=rid, num_for_sale=n, lowest_listed=lowest)
        if lowest:
            return Reference(value=round(float(lowest), 2), basis="Discogs lowest listing",
                             release_id=rid, num_for_sale=n, lowest_listed=lowest)
        return None


class DiscogsSource:
    """Flags when the cheapest copy on the Discogs marketplace is itself a deal.

    The public API doesn't expose individual listings, only the lowest price — so the alert links
    you to the sorted-by-price marketplace page for that release.
    """

    name = "Discogs"

    def __init__(self, guide: PriceGuide):
        self.guide = guide

    def search(self, want: WantItem, ref: Reference | None) -> list[Listing]:
        if ref is None or not ref.release_id or not ref.lowest_listed:
            return []
        rid = ref.release_id
        price = float(ref.lowest_listed)
        return [
            Listing(
                source=self.name,
                source_id=f"{rid}:{price:.2f}",
                title=f"{want.label} (cheapest of {ref.num_for_sale or '?'} on Discogs — check the grade)",
                url=f"https://www.discogs.com/sell/release/{rid}?sort=price%2Casc",
                price=price,
                currency=self.guide.cfg.currency,
                exact=True,
            )
        ]
