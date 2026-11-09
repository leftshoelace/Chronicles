from __future__ import annotations

from ..config import Config
from .discogs import DiscogsSource, PriceGuide
from .ebay import EbaySource
from .rss import RssSource
from .shopify import ShopifySource


def build_sources(cfg: Config, guide: PriceGuide) -> list:
    sources: list = []
    if cfg.discogs_as_source:
        sources.append(DiscogsSource(guide))
    if cfg.ebay_client_id and cfg.ebay_client_secret:
        sources.append(EbaySource(cfg))
    sources += [ShopifySource(s) for s in cfg.shopify_stores if s.get("url")]
    sources += [RssSource(f, cfg) for f in cfg.rss_feeds if f.get("url")]
    return sources
