"""Search criteria for the apartment scraper."""
from __future__ import annotations

ROOMMATES = 4
PER_PERSON_BUDGET = 2000
MAX_TOTAL_RENT = ROOMMATES * PER_PERSON_BUDGET  # 8000
MIN_BEDROOMS = 3  # 4 people can share a 3BR or 4BR

# Priority order: lower number = higher priority. Used for ranking, not filtering.
NEIGHBORHOOD_PRIORITY: dict[str, int] = {
    "east village": 1,
    "lower east side": 2,
    "les": 2,
    "williamsburg": 3,
    "financial district": 4,
    "fidi": 4,
    "upper west side": 5,
    "uws": 5,
    "upper east side": 6,
    "ues": 6,
}

# Accepted Manhattan neighborhoods (anything in Manhattan except Harlem/Inwood/
# Washington Heights). Brooklyn accepted only for Williamsburg / Greenpoint edge.
MANHATTAN_ACCEPTED = {
    "east village", "lower east side", "les", "soho", "noho", "nolita",
    "west village", "greenwich village", "chelsea", "flatiron", "gramercy",
    "kips bay", "murray hill", "midtown", "midtown east", "midtown west",
    "hell's kitchen", "hells kitchen", "clinton", "tribeca", "financial district",
    "fidi", "battery park city", "chinatown", "two bridges", "upper west side",
    "uws", "upper east side", "ues", "stuyvesant town", "peter cooper village",
    "lincoln square", "yorkville", "roosevelt island", "downtown",
}
BROOKLYN_ACCEPTED = {"williamsburg", "greenpoint"}
ACCEPTED_NEIGHBORHOODS = MANHATTAN_ACCEPTED | BROOKLYN_ACCEPTED

# Explicit blocklist — anything that matches here is dropped.
BLOCKED_NEIGHBORHOODS = {
    "harlem", "east harlem", "central harlem", "west harlem", "hamilton heights",
    "morningside heights", "washington heights", "inwood", "marble hill",
    "bronx", "mott haven", "melrose", "port morris", "fordham", "riverdale",
    "staten island", "queens", "astoria", "long island city", "lic",
    "bushwick", "bedstuy", "bed-stuy", "bedford-stuyvesant", "crown heights",
    "park slope", "flatbush", "prospect heights", "sunset park", "red hook",
    "dumbo", "brooklyn heights", "fort greene", "clinton hill", "gowanus",
    "carroll gardens", "cobble hill",
}

# Craigslist RSS feeds (public, ToS-compliant).
CRAIGSLIST_FEEDS = [
    # Manhattan apartments, 3BR+, up to $8000
    "https://newyork.craigslist.org/search/mnh/apa?format=rss"
    "&min_bedrooms=3&max_price=8000&availabilityMode=0",
    # Brooklyn apartments, filtered further by neighborhood in code
    "https://newyork.craigslist.org/search/brk/apa?format=rss"
    "&min_bedrooms=3&max_price=8000&availabilityMode=0",
]

# Known senders we parse from the shared Gmail inbox. Any email whose From
# address contains one of these substrings is treated as a listing alert and
# routed to the per-sender parser in parsers.py. Non-matching mail is ignored.
#
# Note on the FARE Act (effective 2025-06-11): landlord-side brokers can no
# longer charge fees to tenants, so most "no-fee" filters are becoming moot
# in NYC. We still parse a fee_text field where present.
EMAIL_SENDERS = {
    # Aggregators
    "streeteasy.com",
    "mail.zillow.com",
    "zillow.com",
    "trulia.com",
    "apartments.com",
    "renthop.com",
    "zumper.com",
    "hotpads.com",
    "realtyhop.com",
    "padmapper.com",
    # NYC-specific
    "listingsproject.com",
    "leasebreak.com",
    "nybits.com",
    "citysnap.com",
    "openigloo.com",
    "localize.city",
    # Major NYC brokerages (saved-search emails)
    "corcoran.com",
    "elliman.com",             # Douglas Elliman
    "compass.com",
    "bhsusa.com",              # Brown Harris Stevens
    "halstead.com",
    "nestseekers.com",
    "realnyproperties.com",
    # Rentals.com / Rent.com (CoStar network, syndicated with Apartments.com)
    "rent.com",
    "rentals.com",
    "forrent.com",
    "rentcafe.com",
}
