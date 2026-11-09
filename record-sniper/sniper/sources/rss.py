"""Generic RSS/Atom search feeds. Point it at any site that offers a search feed, using {query}
in the URL (and optionally {max_price})."""
from __future__ import annotations

import hashlib
import re
import urllib.parse
import xml.etree.ElementTree as ET

from ..http import request
from ..models import Listing, Reference, WantItem
from ..scoring import buy_under

_PRICE_RE = re.compile(r"(?:US\s?)?[$£€]\s?(\d{1,5}(?:[.,]\d{2})?)")
_TAG_RE = re.compile(r"<[^>]+>")


def find_price(*texts: str) -> float | None:
    for t in texts:
        m = _PRICE_RE.search(t or "")
        if m:
            return float(m.group(1).replace(",", "."))
    return None


def _text(el, *names) -> str:
    for n in names:
        found = el.find(n)
        if found is not None:
            return (found.text or found.get("href") or "").strip()
    return ""


def parse_feed(xml_bytes: bytes, feed: dict) -> list[Listing]:
    root = ET.fromstring(xml_bytes)
    atom = "{http://www.w3.org/2005/Atom}"
    items = root.findall(".//item") or root.findall(f".//{atom}entry")
    out: list[Listing] = []
    for it in items:
        title = _text(it, "title", f"{atom}title")
        link = _text(it, "link", f"{atom}link")
        desc = _TAG_RE.sub(" ", _text(it, "description", f"{atom}summary", f"{atom}content"))
        price = find_price(title, desc)
        if price is None:
            continue
        guid = _text(it, "guid", f"{atom}id") or link or title
        out.append(
            Listing(
                source=feed.get("name", "RSS"),
                source_id=hashlib.sha1(guid.encode()).hexdigest()[:16],
                title=title,
                url=link,
                price=price,
                currency=feed.get("currency", "USD"),
                shipping=0.0 if feed.get("local") else feed.get("shipping"),
                location=feed.get("location", ""),
                local=bool(feed.get("local")),
                condition=desc[:200],
            )
        )
    return out


class RssSource:
    def __init__(self, feed: dict, cfg):
        self.feed = feed
        self.cfg = cfg
        self.name = feed.get("name", "RSS")

    def search(self, want: WantItem, ref: Reference | None) -> list[Listing]:
        cap = buy_under(want, ref, self.cfg)
        url = self.feed["url"].format(
            query=urllib.parse.quote_plus(want.query),
            max_price=int(cap) + 1 if cap else "",
        )
        return parse_feed(request(url, headers={"Accept": "application/rss+xml, application/xml, */*"}), self.feed)
