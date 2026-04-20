"""Entry point. Run once per GitHub Actions tick."""
from __future__ import annotations

import logging
import sys

from . import craigslist_source, dedupe, filter, gmail_source, notify, parsers, score
from .model import Listing

log = logging.getLogger(__name__)


def run() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    dedupe.ensure_db()

    candidates: list[Listing] = []

    # Email: StreetEasy, Zillow, Trulia, Apartments, RentHop, Zumper, HotPads,
    # Listings Project, Leasebreak, NYBits, Citysnap, OpenIgloo, broker sites.
    try:
        for email in gmail_source.fetch_new_emails():
            for listing in parsers.parse_email(email):
                candidates.append(listing)
    except KeyError as e:
        log.error("missing gmail env var: %s", e)
    except Exception:
        log.exception("gmail ingest failed")

    # Craigslist RSS (public feeds).
    try:
        for listing in craigslist_source.fetch_craigslist():
            candidates.append(listing)
    except Exception:
        log.exception("craigslist ingest failed")

    log.info("ingested %d raw candidates", len(candidates))

    # Hard filters.
    passing = [l for l in candidates if filter.passes(l)]
    log.info("%d passed hard filters", len(passing))

    # Dedupe in-batch (same listing can appear in multiple emails / sources).
    by_fp: dict[str, Listing] = {}
    for l in passing:
        by_fp.setdefault(l.fingerprint(), l)
    fresh = dedupe.filter_new(list(by_fp.values()))
    log.info("%d new after dedupe", len(fresh))

    # Sort highest score first so Telegram top-of-feed has the best matches.
    fresh.sort(key=score.score, reverse=True)

    try:
        notify.send_listings(fresh)
    except KeyError as e:
        log.error("missing telegram env var: %s", e)
        return 2
    except Exception:
        log.exception("telegram send failed")
        return 3

    dedupe.mark_seen(fresh)
    return 0


if __name__ == "__main__":
    sys.exit(run())
