"""Command line: scan, watch, check, guide, import-discogs, deals."""
from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from .config import Config, load_config
from .db import Store
from .guide import build_guide
from .matching import is_match
from .models import Deal, Listing, WantItem
from .notify import Notifier
from .scoring import buy_under, evaluate
from .spotify import SpotifyAuth, SpotifyClient, analyze, to_wants
from .sources import build_sources
from .sources.discogs import DiscogsClient, PriceGuide
from .wantlist import load_wantlist, write_wantlist


def scan(cfg: Config, store: Store, dry_run: bool = False, only: str | None = None) -> list[Deal]:
    wants = load_wantlist(cfg.path(cfg.wantlist))
    if only:
        wants = [w for w in wants if only.lower() in w.label.lower()]
    guide = PriceGuide(cfg, store)
    sources = build_sources(cfg, guide)
    print(f"[{datetime.now():%H:%M}] scanning {len(wants)} records across {', '.join(s.name for s in sources) or 'no sources'}")

    found: dict[str, Deal] = {}
    for want in wants:
        ref = guide.reference(want)
        for src in sources:
            try:
                listings: list[Listing] = src.search(want, ref)
            except Exception as e:  # one broken source shouldn't stop the scan
                print(f"  ! {src.name} failed for {want.label}: {e}")
                continue
            for l in listings:
                if not l.exact and not is_match(want, l.title, cfg.match_threshold, extra_text=l.condition):
                    continue
                deal = evaluate(want, l, ref, cfg)
                if deal and (l.key not in found or deal.score > found[l.key].score):
                    found[l.key] = deal

    deals = sorted(found.values(), key=lambda d: (d.listing.local, d.score), reverse=True)
    fresh = [d for d in deals if dry_run or store.should_alert(d.listing.key, d.total, cfg.realert_drop_pct)]
    fresh = fresh[: cfg.max_alerts_per_scan]
    Notifier(cfg, dry_run=dry_run).send(fresh)
    if not dry_run:
        for d in fresh:
            store.record_alert(d)
    print(f"  {len(deals)} deal(s) found, {len(fresh)} new alert(s)")
    return fresh


def cmd_check(cfg: Config, store: Store, args) -> int:
    want = WantItem(artist=args.artist, title=args.title, max_price=args.max)
    for w in _safe_wantlist(cfg):
        if w.key == want.key:
            want = w
            break
    ref = PriceGuide(cfg, store).reference(want)
    listing = Listing(source="manual", source_id="check", title=want.label, url="", price=args.price,
                      shipping=args.shipping, local=args.shipping is None, currency=cfg.currency)
    deal = evaluate(want, listing, ref, cfg)
    print(want.label)
    print(f"  fair value: {'$%.2f (%s)' % (ref.value, ref.basis) if ref else 'unknown (add a Discogs token or fair_value)'}")
    if ref and ref.lowest_listed:
        print(f"  cheapest on Discogs right now: ${ref.lowest_listed:.2f} ({ref.num_for_sale} for sale)")
    cap = buy_under(want, ref, cfg)
    if cap:
        print(f"  buy under: ${cap:.2f}")
    if deal:
        print(f"  => BUY ({deal.tier})")
        for r in deal.reasons:
            print(f"     • {r}")
    else:
        print("  => PASS — not a deal at that price")
    return 0


def cmd_guide(cfg: Config, store: Store, args) -> int:
    guide = PriceGuide(cfg, store)
    rows = [(w, guide.reference(w)) for w in load_wantlist(cfg.path(cfg.wantlist))]
    out = Path(args.output)
    out.write_text(build_guide(rows, cfg), encoding="utf-8")
    print(f"wrote {out.resolve()} ({len(rows)} records)")
    return 0


def cmd_import(cfg: Config, store: Store, args) -> int:
    client = DiscogsClient(cfg.discogs_token)
    items = []
    for w in client.user_wants(args.username):
        info = w.get("basic_information", {})
        # Discogs disambiguates duplicate names as "Name (2)" — strip that.
        artist = ", ".join(re.sub(r"\s\(\d+\)$", "", a.get("name", "")) for a in info.get("artists", []))
        items.append(WantItem(artist=artist, title=info.get("title", ""), discogs_id=w.get("id"),
                              notes=w.get("notes", "") or ""))
    out = Path(args.output)
    existing = {w.key: w for w in load_wantlist(out)} if out.exists() else {}
    for it in items:
        if it.key in existing:  # keep your max prices etc.
            existing[it.key].discogs_id = existing[it.key].discogs_id or it.discogs_id
        else:
            existing[it.key] = it
    write_wantlist(out, list(existing.values()))
    print(f"imported {len(items)} wants into {out} — fill in max_price for the ones you care about")
    return 0


def cmd_spotify(cfg: Config, store: Store, args) -> int:
    if not cfg.spotify_client_id:
        print("Set spotify client_id in config.toml (or SPOTIFY_CLIENT_ID). Setup steps are in the README.")
        return 2
    auth = SpotifyAuth(cfg.spotify_client_id, cfg.path("spotify_token.json"), cfg.spotify_redirect_uri)
    client = SpotifyClient(auth.access_token(open_browser=not args.no_browser))
    tracks = client.saved_tracks()
    try:
        top = client.top_artists()
    except Exception as e:  # top artists are a bonus signal; don't fail without them
        print(f"  (couldn't read top artists: {e})")
        top = []
    albums = analyze(tracks, top, min_liked=args.min_liked, min_fraction=args.min_fraction)
    wl_path = cfg.path(cfg.wantlist)
    have = {w.key for w in _safe_wantlist(cfg)}
    albums = [a for a in albums if WantItem(a.artist, a.title).key not in have][: args.limit]

    print(f"{len(tracks)} liked songs -> {len(albums)} album suggestions not already on your wantlist\n")
    for n, a in enumerate(albums, 1):
        print(f"{n:>3}. {a.artist} - {a.title}" + (f" ({a.year})" if a.year else "") + f"   [{a.reason()}]")
    if top:
        print("\nYour top artists: " + ", ".join(top[:10]))
    wants = to_wants(albums)
    out = Path(args.output)
    write_wantlist(out, wants)
    print(f"\nsaved to {out} - review it, or re-run with --add to put them on your wantlist")
    if args.add and wants:
        existing = _safe_wantlist(cfg)
        write_wantlist(wl_path, existing + wants)
        print(f"added {len(wants)} to {wl_path} - fill in max_price for the ones you care about")
    return 0


def cmd_deals(cfg: Config, store: Store, args) -> int:
    rows = store.recent_alerts(args.limit)
    if not rows:
        print("no alerts yet")
    for r in rows:
        loc = " 📍" if r["local"] else ""
        print(f"{r['last_alerted'][:16]}  {r['tier']:5}  ${r['total']:>7.2f}  {r['source']:<10} {r['want']}{loc}\n"
              f"{'':>20}{r['url']}")
    return 0


def _safe_wantlist(cfg: Config) -> list[WantItem]:
    try:
        return load_wantlist(cfg.path(cfg.wantlist))
    except FileNotFoundError:
        return []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sniper", description="Find records on your wantlist selling below value.")
    ap.add_argument("-c", "--config", default="config.toml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="search every source once and alert on deals")
    s.add_argument("--dry-run", action="store_true", help="print deals, don't notify or remember them")
    s.add_argument("--only", help="only scan wants whose name contains this text")

    w = sub.add_parser("watch", help="scan forever on an interval")
    w.add_argument("--every", type=float, default=30, help="minutes between scans (default 30)")

    c = sub.add_parser("check", help="is this price a deal? (for flea markets, shops, FB listings)")
    c.add_argument("artist")
    c.add_argument("title")
    c.add_argument("price", type=float)
    c.add_argument("--shipping", type=float, help="omit for in-person/local")
    c.add_argument("--max", type=float, help="your max price, if not on the wantlist")

    g = sub.add_parser("guide", help="build a phone-friendly field guide with buy-under prices and search links")
    g.add_argument("-o", "--output", default="guide.html")

    i = sub.add_parser("import-discogs", help="pull your Discogs wantlist into the CSV")
    i.add_argument("username")
    i.add_argument("-o", "--output", default="wantlist.csv")

    sp = sub.add_parser("import-spotify", help="rank albums from your Spotify liked songs and suggest them as wants")
    sp.add_argument("--min-liked", type=int, default=2, help="liked songs needed from an album (default 2)")
    sp.add_argument("--min-fraction", type=float, default=0.3, help="...or this share of the album liked (default 0.3)")
    sp.add_argument("--limit", type=int, default=50)
    sp.add_argument("--add", action="store_true", help="add the suggestions to your wantlist.csv")
    sp.add_argument("--no-browser", action="store_true", help="print the login URL instead of opening a browser")
    sp.add_argument("-o", "--output", default="suggestions.csv")

    d = sub.add_parser("deals", help="show recent alerts")
    d.add_argument("--limit", type=int, default=30)

    args = ap.parse_args(argv)
    cfg = load_config(args.config) if Path(args.config).exists() or args.config != "config.toml" else Config()
    store = Store(cfg.path(cfg.db_path))
    try:
        if args.cmd == "scan":
            scan(cfg, store, dry_run=args.dry_run, only=args.only)
        elif args.cmd == "watch":
            while True:
                try:
                    scan(cfg, store)
                except Exception as e:
                    print(f"  ! scan failed: {e}", file=sys.stderr)
                time.sleep(args.every * 60)
        elif args.cmd == "check":
            return cmd_check(cfg, store, args)
        elif args.cmd == "guide":
            return cmd_guide(cfg, store, args)
        elif args.cmd == "import-discogs":
            return cmd_import(cfg, store, args)
        elif args.cmd == "import-spotify":
            return cmd_spotify(cfg, store, args)
        elif args.cmd == "deals":
            return cmd_deals(cfg, store, args)
    except KeyboardInterrupt:
        return 130
    finally:
        store.close()
    return 0
