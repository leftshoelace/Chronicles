"""Field guide: a phone-friendly page with your buy-under prices and one-tap searches for sites
that can't (or shouldn't) be scraped — Facebook Marketplace, Craigslist, OfferUp, etc.

Open it on your phone at flea markets / record fairs / thrift stores.
"""
from __future__ import annotations

import html
import urllib.parse
from datetime import date

from .config import Config
from .models import Reference, WantItem
from .scoring import buy_under


def search_links(want: WantItem, cfg: Config, cap: float | None, ref: Reference | None) -> list[tuple[str, str]]:
    q = urllib.parse.quote_plus(f"{want.query} vinyl")
    qq = urllib.parse.quote_plus(want.query)
    mp = int(cap) + 1 if cap else None
    links: list[tuple[str, str]] = []
    city = cfg.facebook_city or ""
    fb = f"https://www.facebook.com/marketplace/{city + '/' if city else ''}search/?query={q}"
    links.append(("FB Marketplace", fb + (f"&maxPrice={mp}" if mp else "")))
    if cfg.craigslist_site:
        cl = f"https://{cfg.craigslist_site}.craigslist.org/search/sss?query={q}"
        links.append(("Craigslist", cl + (f"&max_price={mp}" if mp else "")))
    links.append(("OfferUp", f"https://offerup.com/search?q={q}" + (f"&price_max={mp}" if mp else "")))
    links.append(("Mercari", f"https://www.mercari.com/search/?keyword={q}"))
    ebay_local = (f"https://www.ebay.com/sch/176985/i.html?_nkw={qq}&LH_PrefLoc=99&_stpos={cfg.home_zip}"
                  f"&_sadis={cfg.local_radius_miles}&LH_LPickup=1") if cfg.home_zip else None
    if ebay_local:
        links.append(("eBay local", ebay_local))
    links.append(("eBay sold", f"https://www.ebay.com/sch/176985/i.html?_nkw={qq}&LH_Sold=1&LH_Complete=1"))
    if ref and ref.release_id:
        links.append(("Discogs", f"https://www.discogs.com/sell/release/{ref.release_id}?sort=price%2Casc"))
    else:
        links.append(("Discogs", f"https://www.discogs.com/search/?q={qq}&type=all&format_exact=Vinyl"))
    return links


def build_guide(rows: list[tuple[WantItem, Reference | None]], cfg: Config) -> str:
    e = html.escape
    trs = []
    for want, ref in rows:
        cap = buy_under(want, ref, cfg)
        links = " ".join(f'<a href="{e(u)}" target="_blank" rel="noopener">{e(n)}</a>'
                         for n, u in search_links(want, cfg, cap, ref))
        fair = f"${ref.value:.0f}" if ref else "—"
        basis = e(ref.basis) if ref else "no price data"
        trs.append(
            f"<tr><td><b>{e(want.artist)}</b><br>{e(want.title)}"
            f"{'<br><small>' + e(want.notes) + '</small>' if want.notes else ''}</td>"
            f"<td class=num><span class=buy>{'$' + format(cap, '.0f') if cap else '—'}</span></td>"
            f"<td class=num>{fair}<br><small>{basis}</small></td>"
            f"<td class=links>{links}</td></tr>"
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Record Field Guide</title>
<style>
:root{{--bg:#fbfaf7;--fg:#1d1b18;--mut:#6b665e;--line:#e4e0d8;--acc:#0f7a4a;--chip:#efece6}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151412;--fg:#ece8e1;--mut:#9a948a;--line:#2c2a26;--acc:#4cc38a;--chip:#23211e}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.4 system-ui,sans-serif}}
main{{max-width:960px;margin:0 auto;padding:16px}}
h1{{font-size:22px;margin:0 0 4px}} p{{color:var(--mut);margin:0 0 12px}}
input{{width:100%;box-sizing:border-box;padding:10px 12px;font:inherit;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg);margin-bottom:12px}}
table{{width:100%;border-collapse:collapse}} td,th{{padding:10px 6px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}}
th{{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--mut)}}
.num{{white-space:nowrap}} .buy{{color:var(--acc);font-weight:700;font-size:18px}}
small{{color:var(--mut)}} .links a{{display:inline-block;margin:0 4px 6px 0;padding:3px 8px;border-radius:999px;background:var(--chip);color:var(--fg);text-decoration:none;font-size:13px}}
@media (max-width:640px){{thead{{display:none}} tr{{display:grid;grid-template-columns:1fr auto auto;gap:4px 12px;border-bottom:1px solid var(--line);padding:10px 0}} td{{border:0;padding:0}} td.links{{grid-column:1/-1}}}}
</style></head><body><main>
<h1>Record Field Guide</h1>
<p>Buy-under = the price (incl. shipping) at which it's a deal. Generated {date.today().isoformat()}.</p>
<input id=f placeholder="Filter…" oninput="for(const r of document.querySelectorAll('tbody tr'))r.style.display=r.textContent.toLowerCase().includes(this.value.toLowerCase())?'':'none'">
<table><thead><tr><th>Record</th><th>Buy under</th><th>Fair value</th><th>Search</th></tr></thead>
<tbody>{''.join(trs)}</tbody></table>
</main></body></html>"""
