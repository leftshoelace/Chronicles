# Record Sniper

Watches the internet for records on your wantlist, works out what each one is actually worth, and pings your phone when a copy is listed cheap. It puts listings you can pick up locally first.

Pure Python 3.11+, no packages to install.

## What it does

| Where | How | Notes |
|---|---|---|
| **Discogs** | Official API | Sets the **fair value** for every record (VG+ price suggestion, or the lowest current listing). Also alerts when the cheapest Discogs copy is itself a deal. |
| **eBay** | Official Browse API | Searches nationwide **and** "local pickup within N miles of my zip". Includes shipping to your zip. Only alerts on auctions in their last few hours. |
| **Indie record shops** | Shopify's public search | Many shops run on Shopify. Add yours and mark the local ones. |
| **Any RSS search feed** | RSS/Atom | Works with classifieds or shop sites that offer a search feed. |
| **FB Marketplace, Craigslist, OfferUp, Mercari, flea markets** | Field guide + `check` | See below. These sites ban scraping and block bots, so the tool doesn't scrape them. |

A listing becomes a **DEAL** when the total price (including shipping) is:
- under your `max_price`, or
- at or below 60% of fair value, or
- low enough that reselling at fair value would make you at least $10 after fees (the arbitrage case).

It's a **STEAL** at 40% of fair value or less. All of these thresholds can be changed in `config.toml`.

Matching ignores CDs, cassettes, posters, empty sleeves and similar, tolerates typos, and can enforce a minimum grade (VG+, NM…) when a listing states one. You only get alerted once per listing, unless its price drops another 10%.

## Setup (5 minutes)

```bash
cd record-sniper
cp config.example.toml config.toml
cp wantlist.example.csv wantlist.csv
```

1. **Wantlist.** Edit `wantlist.csv`. Columns:
   - `artist`, `title`
   - `max_price`
   - `min_condition`
   - `discogs_id`: optional; pins an exact pressing
   - `fair_value`: optional manual override
   - `must_include` / `exclude`: `;`-separated phrases, such as `original;mono`
   - `notes`

   If you already keep a Discogs wantlist, import it with `python -m sniper import-discogs YOUR_USERNAME`.
2. **Discogs token** (free, and needed for fair values): https://www.discogs.com/settings/developers. Filling in your Discogs seller settings unlocks condition-based price suggestions.
3. **eBay keys** (free): https://developer.ebay.com/my/keys. Use the Production App ID and Cert ID.
4. **Phone alerts:** install the [ntfy](https://ntfy.sh) app, subscribe to a hard-to-guess topic, and put that topic in `ntfy_topic`. Discord webhooks and email digests are also supported.
5. Set `home_zip`, `facebook_city`, `craigslist_site`, and add any local shops under `[[shopify]]`.

You can put secrets in environment variables instead: `DISCOGS_TOKEN`, `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`, `NTFY_TOPIC`, `DISCORD_WEBHOOK`, `SMTP_PASSWORD`.

## Build your wantlist from Spotify

Instead of typing records in by hand, let your listening decide. This reads your **liked songs** and **top artists**, groups them by album, and ranks the albums you love most. Several liked songs from one album, or most of the album liked, put it near the top. Albums by your most-played artists get a boost. Singles and compilations are skipped, and deluxe, remaster and standard editions are merged into one album.

One-time setup (2 minutes, free):
1. Go to https://developer.spotify.com/dashboard and create an app.
2. Add this exact Redirect URI: `http://127.0.0.1:8888/callback`. It must be `127.0.0.1`, not `localhost`.
3. Copy the app's **Client ID** into `[spotify] client_id` in `config.toml`.

```bash
python -m sniper import-spotify            # log in, rank albums, save suggestions.csv for you to review
python -m sniper import-spotify --add      # ...and add them straight to wantlist.csv
```

- The first run opens a browser to log in. It's read-only (`user-library-read` and `user-top-read`). Your login is saved in `spotify_token.json`, readable only by you.
- On a machine with no browser, use `--no-browser` and paste the redirected address back in when asked.
- Albums already on your wantlist are skipped. Tune with `--min-liked` and `--min-fraction`.
- Suggestions have no `max_price`, so they're judged against the Discogs fair value (flagged at 60% or less). Set a `max_price` on the ones you care about.

## Use

```bash
python -m sniper scan --dry-run          # see what it finds, no alerts sent
python -m sniper scan                    # search once, send alerts
python -m sniper watch --every 30        # run forever, every 30 min
python -m sniper deals                   # what you've been alerted about
python -m sniper guide                   # build guide.html (see below)
python -m sniper check "Fleetwood Mac" "Rumours" 8          # is $8 in person a deal?
python -m sniper check "Radiohead" "OK Computer" 30 --shipping 6
```

To run it automatically, either keep `watch` running on an always-on machine, or add a cron job:

```bash
*/30 * * * * cd /path/to/record-sniper && python3 -m sniper scan >> sniper.log 2>&1
```

### Facebook Marketplace, Craigslist & flea markets

`python -m sniper guide` writes **`guide.html`**, a phone-friendly page you can search. For every record it shows:
- your **buy-under price**
- its fair value
- one-tap searches on FB Marketplace, Craigslist, OfferUp, Mercari, eBay local pickup, eBay sold listings and Discogs, already filtered to your area and max price

Take it to flea markets and record fairs, or use it to work through Marketplace quickly. For hands-off Marketplace alerts, save those searches in the Facebook app and turn on its notifications.

When you find a copy in person, `check` tells you whether the price is worth it.

## Tests

```bash
python -m unittest discover -s tests -v
```
