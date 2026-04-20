# cwb-apartment-scraper

Aggregates NYC apartment listings from every major source into one Telegram
channel for 4 roommates. Runs on a GitHub Actions cron — no server required.

**Criteria:** 3BR+ up to $6,250/mo total. Manhattan (excluding Harlem / Inwood
/ Washington Heights) + Williamsburg / Greenpoint. Priority: East Village >
LES > Williamsburg > FiDi > UWS > UES > everything else.

## How it works

```
           +-----------------+       +-----------------+
           | cwbapartment@   |       | Craigslist RSS  |
           | gmail.com       |       | (Manhattan,     |
           | saved-search    |       |  Brooklyn apa)  |
           | alerts          |       +--------+--------+
           +--------+--------+                |
                    |                         |
                    v                         v
               IMAP fetch                feedparser
                    |                         |
                    +------------+------------+
                                 v
                         per-sender parsers
                                 v
                    filter (budget, beds, blocklist)
                                 v
                    SQLite dedupe (committed to repo)
                                 v
                    score (neighborhood priority)
                                 v
                         Telegram group chat
```

Why email and RSS instead of scraping? Because StreetEasy/Zillow/Apartments.com
actively block scrapers (Cloudflare, rate limits, ToS prohibitions), but all
of them will happily send you saved-search alerts for free. RSS and email are
the supported, stable, legal API surface. No Playwright, no proxies, no bans.

## Sources covered

| Source | Ingestion | Notes |
|---|---|---|
| StreetEasy | email | saved search → inbox |
| Zillow | email | saved search → inbox |
| Trulia | email | saved search → inbox (same backend as Zillow) |
| Apartments.com | email | saved search → inbox |
| RentHop | email | saved search → inbox |
| Zumper | email | saved search → inbox |
| HotPads | email | saved search → inbox |
| RealtyHop | email | saved search → inbox |
| Listings Project | email | weekly digest subscription |
| Leasebreak | email | saved search → inbox |
| NYBits | email | saved search → inbox |
| Citysnap | email | REBNY RLS listings |
| OpenIgloo | email | saved search → inbox |
| Localize | email | saved search → inbox |
| Corcoran / Elliman / Compass / BHS / Halstead / Nestseekers | email | broker saved searches |
| Craigslist | RSS | `mnh/apa` + `brk/apa` feeds |

## One-time setup

### 1. Gmail App Password

The shared inbox is `cwbapartment@gmail.com`. To let the scraper sign in via
IMAP, generate a Google App Password:

1. Turn on 2FA on the account: <https://myaccount.google.com/security>
2. Create an app password: <https://myaccount.google.com/apppasswords>
3. Label it "apartment-scraper" and save the 16-character password.

### 2. Saved-search email alerts on every source

For each of the sites in the table above:

1. Sign in (or create an account) using `cwbapartment@gmail.com`.
2. Configure a search: 3+ bedrooms, max rent $6,250, neighborhoods = East
   Village, LES, Williamsburg, FiDi, UWS, UES (add every Manhattan neighborhood
   that the site's filter UI allows).
3. Save the search and turn on "email me new listings" / "instant alerts".

Rough guide (exact menus change):

- **StreetEasy**: Search → bell icon → Save Search → frequency: *Instant*.
- **Zillow**: heart icon on search → Save Search → frequency: *As they happen*.
- **Trulia**: Save Search button → *As they happen*.
- **Apartments.com**: bell icon next to search → *Real-time*.
- **RentHop**: Save Search → *ASAP*.
- **Zumper**: Create Alert → *Instant*.
- **HotPads**: Save Search → *Real-time*.
- **Listings Project**: subscribe to the weekly email at
  <https://www.listingsproject.com>.
- **Leasebreak / NYBits / Citysnap / OpenIgloo / Localize**: account → email
  alerts → save your search.
- **Corcoran / Elliman / Compass / BHS / Halstead / Nestseekers**: make an
  account, save a search, opt into email alerts.

### 3. Telegram group + bot

1. Create a Telegram group with all 4 roommates.
2. Talk to [@BotFather](https://t.me/BotFather) → `/newbot` → follow prompts.
   Save the bot token.
3. Add the bot to the group. Send any message in the group, then visit
   `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser. Find the
   `chat.id` (it's a negative number for groups). Save it.

### 4. GitHub Actions secrets

On the repo: Settings → Secrets and variables → Actions → New secret. Add:

- `GMAIL_ADDRESS` = `cwbapartment@gmail.com`
- `GMAIL_APP_PASSWORD` = (from step 1)
- `TELEGRAM_BOT_TOKEN` = (from step 3)
- `TELEGRAM_CHAT_ID` = (from step 3, include the leading `-`)

### 5. Kick it off

`.github/workflows/scrape.yml` runs every 10 minutes on branch
`claude/apartment-search-scraper-8p5mH`. To trigger a manual run:

Actions tab → `apartment-scrape` → Run workflow.

## Local dev

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env           # fill in real values
export $(grep -v '^#' .env | xargs)
python -m src.main
```

## Tuning

All knobs live in `src/config.py`:

- `MAX_TOTAL_RENT`, `MIN_BEDROOMS` — hard filters
- `NEIGHBORHOOD_PRIORITY` — ranking weights
- `ACCEPTED_NEIGHBORHOODS` / `BLOCKED_NEIGHBORHOODS` — allow/deny lists
- `EMAIL_SENDERS` — add new sources by appending a domain substring
- `CRAIGSLIST_FEEDS` — adjust bedroom/price bounds in the URL querystring

## What we're not doing (and why)

- **Scraping StreetEasy/Zillow/Apartments.com directly.** Against ToS, blocked
  by Cloudflare, brittle, and not faster than saved-search email alerts.
- **Facebook Marketplace / Gypsy Housing.** Requires a logged-in session; FB's
  automation detection will nuke the account and it's not worth the maintenance.
- **PadMapper / Cozycozy.** They aggregate the same sources we already cover,
  so we'd just get duplicates.

## Legal note

Every source we ingest is either (a) a public RSS feed or (b) an email that
the source itself sends to our inbox based on a saved search we configured on
their site. We do not bypass any authentication, rate limit, or anti-bot
measure. If a source revokes alerts or sends a cease-and-desist, remove it.
