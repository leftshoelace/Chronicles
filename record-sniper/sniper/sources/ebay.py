"""eBay via the official Browse API (free developer keys: https://developer.ebay.com).

Runs two searches per record: a nationwide one, and a "local pickup near my zip" one so you
also catch sellers within driving distance.
"""
from __future__ import annotations

import base64
import json
import time

from ..config import Config
from ..http import get_json, request
from ..models import Listing, Reference, WantItem
from ..scoring import buy_under

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
VINYL_CATEGORY = "176985"  # Music > Vinyl Records


def parse_items(data: dict, local: bool = False) -> list[Listing]:
    out: list[Listing] = []
    for it in (data or {}).get("itemSummaries", []) or []:
        buying = it.get("buyingOptions") or []
        is_auction = "AUCTION" in buying and "FIXED_PRICE" not in buying
        price_obj = (it.get("currentBidPrice") if is_auction else None) or it.get("price")
        if not price_obj or price_obj.get("value") is None:
            continue
        ship = None
        for so in it.get("shippingOptions") or []:
            c = so.get("shippingCost")
            if c and c.get("value") is not None:
                v = float(c["value"])
                ship = v if ship is None else min(ship, v)
        loc = it.get("itemLocation") or {}
        location = ", ".join(x for x in (loc.get("city"), loc.get("stateOrProvince"), loc.get("postalCode"),
                                         loc.get("country")) if x)
        out.append(
            Listing(
                source="eBay",
                source_id=str(it.get("itemId")),
                title=it.get("title", ""),
                url=it.get("itemWebUrl", ""),
                price=float(price_obj["value"]),
                currency=price_obj.get("currency", "USD"),
                shipping=0.0 if local and ship is None else ship,
                location=location,
                local=local,
                is_auction=is_auction,
                ends_at=it.get("itemEndDate"),
                condition=it.get("condition", ""),
                image=(it.get("image") or {}).get("imageUrl", ""),
            )
        )
    return out


class EbaySource:
    name = "eBay"

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._token: str | None = None
        self._token_exp = 0.0

    def _auth(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        basic = base64.b64encode(f"{self.cfg.ebay_client_id}:{self.cfg.ebay_client_secret}".encode()).decode()
        raw = request(
            TOKEN_URL, method="POST",
            headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
            data="grant_type=client_credentials&scope=https%3A%2F%2Fapi.ebay.com%2Foauth%2Fapi_scope",
        )
        tok = json.loads(raw)
        self._token = tok["access_token"]
        self._token_exp = time.time() + int(tok.get("expires_in", 7200))
        return self._token

    def _filters(self, cap: float | None, local: bool) -> str:
        opts = "FIXED_PRICE|BEST_OFFER" + ("|AUCTION" if self.cfg.ebay_include_auctions else "")
        f = [f"buyingOptions:{{{opts}}}", f"priceCurrency:{self.cfg.currency}"]
        if cap:
            f.append(f"price:[..{cap:.2f}]")
        if local:
            f += [
                "deliveryOptions:{SELLER_ARRANGED_LOCAL_PICKUP}",
                f"pickupCountry:{self.cfg.country}",
                f"pickupPostalCode:{self.cfg.home_zip}",
                f"pickupRadius:{self.cfg.local_radius_miles}",
                "pickupRadiusUnit:mi",
            ]
        return ",".join(f)

    def _search(self, want: WantItem, cap: float | None, local: bool) -> list[Listing]:
        headers = {
            "Authorization": f"Bearer {self._auth()}",
            "X-EBAY-C-MARKETPLACE-ID": self.cfg.ebay_marketplace,
        }
        if self.cfg.home_zip:
            # Makes eBay return shipping costs to *your* address.
            headers["X-EBAY-C-ENDUSERCTX"] = f"contextualLocation=country={self.cfg.country},zip={self.cfg.home_zip}"
        data = get_json(SEARCH_URL, headers=headers, params={
            "q": want.query, "category_ids": VINYL_CATEGORY, "filter": self._filters(cap, local),
            "sort": "price", "limit": 50,
        })
        return parse_items(data, local=local)

    def search(self, want: WantItem, ref: Reference | None) -> list[Listing]:
        cap = buy_under(want, ref, self.cfg)
        results = {l.key: l for l in self._search(want, cap, local=False)}
        if self.cfg.ebay_local_search and self.cfg.home_zip:
            for l in self._search(want, cap, local=True):
                results[l.key] = l  # local version wins
        return list(results.values())
