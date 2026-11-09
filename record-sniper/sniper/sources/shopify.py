"""Independent record shops on Shopify (a lot of them are) expose a public product search.

Add shops in config.toml under [[shopify]]. Mark your local shops with local = true.
"""
from __future__ import annotations

import re
import urllib.parse

from ..http import get_json
from ..models import Listing, Reference, WantItem


def _price(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"\d+(?:[.,]\d{1,2})?", str(v).replace(",", ""))
    return float(m.group()) if m else None


def parse_suggest(data: dict, store: dict) -> list[Listing]:
    base = store["url"].rstrip("/")
    out: list[Listing] = []
    products = (((data or {}).get("resources") or {}).get("results") or {}).get("products") or []
    for p in products:
        if p.get("available") is False:
            continue
        price = _price(p.get("price") or p.get("price_min"))
        if price is None:
            continue
        url = p.get("url", "")
        url = urllib.parse.urljoin(base + "/", url.split("?")[0]) if url else base
        img = p.get("image") or p.get("featured_image") or ""
        if isinstance(img, dict):
            img = img.get("url", "")
        out.append(
            Listing(
                source=store.get("name") or urllib.parse.urlparse(base).netloc,
                source_id=str(p.get("id") or p.get("handle") or url),
                title=f"{p.get('vendor', '')} {p.get('title', '')}".strip(),
                url=url,
                price=price,
                currency=store.get("currency", "USD"),
                shipping=0.0 if store.get("local") else store.get("shipping"),
                location=store.get("location", ""),
                local=bool(store.get("local")),
                image=img,
            )
        )
    return out


class ShopifySource:
    def __init__(self, store: dict):
        self.store = store
        self.name = store.get("name") or store["url"]

    def search(self, want: WantItem, ref: Reference | None) -> list[Listing]:
        data = get_json(
            f"{self.store['url'].rstrip('/')}/search/suggest.json",
            params={"q": want.query, "resources[type]": "product", "resources[limit]": 10},
        )
        return parse_suggest(data, self.store)
