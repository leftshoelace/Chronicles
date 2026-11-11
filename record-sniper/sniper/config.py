"""Load config.toml, with secrets overridable by environment variables."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    # general
    home_zip: str = ""
    country: str = "US"
    currency: str = "USD"
    local_radius_miles: int = 30
    default_shipping: float = 5.0
    deal_ratio: float = 0.6
    steal_ratio: float = 0.4
    resale_fee_pct: float = 0.15
    min_flip_profit: float = 10.0
    match_threshold: float = 0.8
    auction_alert_hours: float = 12.0
    realert_drop_pct: float = 10.0
    max_alerts_per_scan: int = 20
    wantlist: str = "wantlist.csv"
    db_path: str = "sniper.db"

    # discogs
    discogs_token: str = ""
    discogs_reference_condition: str = "Very Good Plus (VG+)"
    discogs_cache_hours: float = 24.0
    discogs_as_source: bool = True

    # ebay
    ebay_client_id: str = ""
    ebay_client_secret: str = ""
    ebay_marketplace: str = "EBAY_US"
    ebay_include_auctions: bool = True
    ebay_local_search: bool = True

    shopify_stores: list[dict] = field(default_factory=list)
    rss_feeds: list[dict] = field(default_factory=list)

    # notify
    notify_console: bool = True
    ntfy_topic: str = ""
    ntfy_server: str = "https://ntfy.sh"
    discord_webhook: str = ""
    email: dict = field(default_factory=dict)

    # spotify
    spotify_client_id: str = ""
    spotify_redirect_uri: str = "http://127.0.0.1:8888/callback"

    # links / field guide
    facebook_city: str = ""
    craigslist_site: str = ""

    base_dir: Path = Path(".")

    def path(self, p: str) -> Path:
        pp = Path(p).expanduser()
        return pp if pp.is_absolute() else self.base_dir / pp


def load_config(path: str | Path | None) -> Config:
    cfg = Config()
    raw: dict = {}
    if path:
        p = Path(path)
        if p.exists():
            raw = tomllib.loads(p.read_text())
            cfg.base_dir = p.resolve().parent
        else:
            raise FileNotFoundError(f"Config file not found: {p} (copy config.example.toml to start)")

    g = raw.get("general", {})
    for k in (
        "home_zip", "country", "currency", "local_radius_miles", "default_shipping", "deal_ratio",
        "steal_ratio", "resale_fee_pct", "min_flip_profit", "match_threshold", "auction_alert_hours",
        "realert_drop_pct", "max_alerts_per_scan", "wantlist", "db_path",
    ):
        if k in g:
            setattr(cfg, k, g[k])
    cfg.home_zip = str(cfg.home_zip)

    d = raw.get("discogs", {})
    cfg.discogs_token = d.get("token", cfg.discogs_token)
    cfg.discogs_reference_condition = d.get("reference_condition", cfg.discogs_reference_condition)
    cfg.discogs_cache_hours = d.get("cache_hours", cfg.discogs_cache_hours)
    cfg.discogs_as_source = d.get("as_source", cfg.discogs_as_source)

    e = raw.get("ebay", {})
    cfg.ebay_client_id = e.get("client_id", cfg.ebay_client_id)
    cfg.ebay_client_secret = e.get("client_secret", cfg.ebay_client_secret)
    cfg.ebay_marketplace = e.get("marketplace", cfg.ebay_marketplace)
    cfg.ebay_include_auctions = e.get("include_auctions", cfg.ebay_include_auctions)
    cfg.ebay_local_search = e.get("local_search", cfg.ebay_local_search)

    cfg.shopify_stores = raw.get("shopify", [])
    cfg.rss_feeds = raw.get("rss", [])

    n = raw.get("notify", {})
    cfg.notify_console = n.get("console", cfg.notify_console)
    cfg.ntfy_topic = n.get("ntfy_topic", cfg.ntfy_topic)
    cfg.ntfy_server = n.get("ntfy_server", cfg.ntfy_server).rstrip("/")
    cfg.discord_webhook = n.get("discord_webhook", cfg.discord_webhook)
    cfg.email = n.get("email", {})

    sp = raw.get("spotify", {})
    cfg.spotify_client_id = sp.get("client_id", cfg.spotify_client_id)
    cfg.spotify_redirect_uri = sp.get("redirect_uri", cfg.spotify_redirect_uri)

    lk = raw.get("links", {})
    cfg.facebook_city = lk.get("facebook_city", cfg.facebook_city)
    cfg.craigslist_site = lk.get("craigslist_site", cfg.craigslist_site)

    # Secrets from the environment win, so you never have to commit them.
    env = os.environ
    cfg.discogs_token = env.get("DISCOGS_TOKEN", cfg.discogs_token)
    cfg.ebay_client_id = env.get("EBAY_CLIENT_ID", cfg.ebay_client_id)
    cfg.ebay_client_secret = env.get("EBAY_CLIENT_SECRET", cfg.ebay_client_secret)
    cfg.spotify_client_id = env.get("SPOTIFY_CLIENT_ID", cfg.spotify_client_id)
    cfg.ntfy_topic = env.get("NTFY_TOPIC", cfg.ntfy_topic)
    cfg.discord_webhook = env.get("DISCORD_WEBHOOK", cfg.discord_webhook)
    if env.get("SMTP_PASSWORD"):
        cfg.email = {**cfg.email, "password": env["SMTP_PASSWORD"]}
    return cfg
