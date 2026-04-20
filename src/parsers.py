"""Converts listing-alert emails into Listing records.

Strategy: most aggregator alert emails follow the same rough shape: a sequence
of listing "cards" with an anchor to the listing page, a price, a bed/bath
line, and an address/neighborhood. We dispatch on sender domain for slight
layout variations, but fall back to a generic extractor that works acceptably
well across all senders. We prefer under-extracting (fewer listings) over
wrong data, because a missed listing is just a lost 5-minute head start while
a wrong price wastes a phone call.
"""
from __future__ import annotations

import logging
import re
from typing import Callable, Iterator
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .gmail_source import RawEmail
from .model import Listing

log = logging.getLogger(__name__)

_PRICE_RE = re.compile(r"\$\s?([\d,]{3,})")
_BEDS_RE = re.compile(r"(\d(?:\.\d)?)\s*(?:br|bed|bedroom)s?\b", re.IGNORECASE)
_FEE_RE = re.compile(r"\b(no[- ]?fee|no broker fee|fee)\b", re.IGNORECASE)

# Domains whose <a href> we treat as a listing detail page. We anchor dedupe on
# the listing URL, so picking the canonical domain per source matters.
_LISTING_HOSTS = {
    "streeteasy.com": "streeteasy",
    "zillow.com": "zillow",
    "trulia.com": "trulia",
    "apartments.com": "apartments",
    "renthop.com": "renthop",
    "zumper.com": "zumper",
    "hotpads.com": "hotpads",
    "realtyhop.com": "realtyhop",
    "padmapper.com": "padmapper",
    "listingsproject.com": "listingsproject",
    "leasebreak.com": "leasebreak",
    "nybits.com": "nybits",
    "citysnap.com": "citysnap",
    "openigloo.com": "openigloo",
    "localize.city": "localize",
    "corcoran.com": "corcoran",
    "elliman.com": "elliman",
    "compass.com": "compass",
    "bhsusa.com": "bhs",
    "halstead.com": "halstead",
    "nestseekers.com": "nestseekers",
    "realnyproperties.com": "realny",
    "rent.com": "rent",
    "rentals.com": "rentals",
    "forrent.com": "forrent",
    "rentcafe.com": "rentcafe",
}


def parse_email(email: RawEmail) -> Iterator[Listing]:
    html = email.html or email.text
    if not html:
        return
    soup = BeautifulSoup(html, "lxml")

    # A listing "card" is typically a block anchored on an <a> pointing at a
    # detail page on one of the known listing hosts. We walk those anchors,
    # then look at the surrounding context for price/beds/neighborhood.
    seen_urls: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url, source = _canonical_listing_url(anchor["href"])
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        context = _card_context(anchor)
        price = _extract_price(context)
        beds = _extract_beds(context)
        hood, addr = _extract_location(context, anchor)
        fee_text, fee_flag = _extract_fee(context)
        image_url = _nearest_image(anchor)
        title = (anchor.get_text(" ", strip=True) or email.subject)[:200]

        yield Listing(
            source=source,
            url=url,
            title=title,
            price=price,
            bedrooms=beds,
            neighborhood=hood,
            address=addr,
            broker_fee=fee_flag,
            fee_text=fee_text,
            raw_excerpt=context[:400],
            image_url=image_url,
        )


def _canonical_listing_url(href: str) -> tuple[str, str]:
    if not href or href.startswith(("mailto:", "tel:", "#")):
        return "", ""
    try:
        u = urlparse(href)
    except ValueError:
        return "", ""
    host = (u.netloc or "").lower()
    host = host.lstrip(".")
    if host.startswith("www."):
        host = host[4:]
    for known, label in _LISTING_HOSTS.items():
        if host == known or host.endswith("." + known):
            # Strip tracking params / fragments.
            clean = f"{u.scheme}://{u.netloc}{u.path}"
            # Require a path of at least /foo/bar to avoid nav links.
            if clean.count("/") < 4:
                return "", ""
            return clean, label
    return "", ""


def _card_context(anchor) -> str:
    """Return the text of the nearest block ancestor, which usually holds the
    full listing card (price, beds, neighborhood)."""
    node = anchor
    for _ in range(5):
        parent = node.parent
        if parent is None:
            break
        text = parent.get_text(" ", strip=True)
        if len(text) > 80:
            return text
        node = parent
    return anchor.get_text(" ", strip=True)


def _extract_price(text: str) -> int | None:
    # Multiple prices can appear (e.g. "was $X, now $Y"); take the last one,
    # which in email layouts is usually the current asking rent.
    matches = list(_PRICE_RE.finditer(text))
    if not matches:
        return None
    try:
        return int(matches[-1].group(1).replace(",", ""))
    except ValueError:
        return None


def _extract_beds(text: str) -> float | None:
    m = _BEDS_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _extract_location(text: str, anchor) -> tuple[str, str]:
    # Aggregators often render the address on its own element; grab the
    # longest comma-delimited token as address and the final token as hood.
    for candidate in (anchor.get_text(" ", strip=True), text):
        m = re.search(
            r"(\d{1,5}\s+[A-Z][A-Za-z0-9 .'-]+(?:,\s*[A-Z][A-Za-z .'-]+){0,3})",
            candidate,
        )
        if m:
            addr = m.group(1).strip()
            parts = [p.strip() for p in addr.split(",") if p.strip()]
            hood = parts[-1] if len(parts) > 1 else ""
            return hood, addr
    return "", ""


def _extract_fee(text: str) -> tuple[str, bool | None]:
    m = _FEE_RE.search(text)
    if not m:
        return "", None
    raw = m.group(0)
    return raw, "no" in raw.lower()


def _nearest_image(anchor) -> str:
    img = anchor.find("img")
    if img and img.get("src"):
        return img["src"]
    # Walk up to find an image in the same card.
    node = anchor
    for _ in range(4):
        parent = node.parent
        if parent is None:
            break
        img = parent.find("img")
        if img and img.get("src"):
            return img["src"]
        node = parent
    return ""
