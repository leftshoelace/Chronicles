import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sniper.config import Config
from sniper.db import Store
from sniper.guide import build_guide
from sniper.matching import is_match, match_score, parse_grade
from sniper.models import Listing, Reference, WantItem
from sniper.notify import format_deal
from sniper.scoring import buy_under, evaluate
from sniper.sources.ebay import parse_items
from sniper.sources.rss import parse_feed
from sniper.sources.shopify import parse_suggest
from sniper.wantlist import load_wantlist, write_wantlist

FX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 9, 2, 0, tzinfo=timezone.utc)
KOB = WantItem("Miles Davis", "Kind of Blue", max_price=25, min_condition="VG+")


def L(price, **kw):
    return Listing(source="test", source_id=str(price), title="Miles Davis Kind of Blue", url="u", price=price, **kw)


class Matching(unittest.TestCase):
    def test_basic(self):
        self.assertTrue(is_match(KOB, "MILES DAVIS - Kind Of Blue LP 1959 Columbia"))
        self.assertTrue(is_match(KOB, "Kind of Blue / Miles Davis (vinyl)"))

    def test_rejects_other_formats_and_merch(self):
        self.assertFalse(is_match(KOB, "Miles Davis Kind of Blue CD"))
        self.assertFalse(is_match(KOB, "Miles Davis Kind of Blue poster 24x36"))
        self.assertFalse(is_match(KOB, "Miles Davis Kind of Blue empty jacket only"))

    def test_rejects_wrong_record(self):
        self.assertFalse(is_match(KOB, "Miles Davis Bitches Brew"))
        self.assertFalse(is_match(KOB, "Kind of Blue - Various Artists"))

    def test_typo_tolerance(self):
        w = WantItem("John Coltrane", "A Love Supreme")
        self.assertTrue(is_match(w, "John Coltrain - Love Supreme LP"))

    def test_exclude_word_in_want_is_not_excluded(self):
        w = WantItem("Some Band", "Cassette")
        self.assertTrue(is_match(w, "Some Band - Cassette LP"))

    def test_must_include_and_exclude(self):
        w = WantItem("Bill Evans Trio", "Sunday at the Village Vanguard", must_include=["riverside"], exclude=["reissue"])
        self.assertTrue(is_match(w, "Bill Evans Trio Sunday At The Village Vanguard Riverside RLP 376"))
        self.assertFalse(is_match(w, "Bill Evans Trio Sunday At The Village Vanguard"))
        self.assertFalse(is_match(w, "Bill Evans Trio Sunday At The Village Vanguard Riverside reissue"))

    def test_grades(self):
        self.assertEqual(parse_grade("Kind of Blue VG+/NM"), "VG+")
        self.assertEqual(parse_grade("near mint copy"), "NM")
        self.assertEqual(parse_grade("Exodus soundtrack"), None)
        self.assertFalse(is_match(KOB, "Miles Davis Kind of Blue VG- plays through"))
        self.assertTrue(is_match(KOB, "Miles Davis Kind of Blue NM"))

    def test_score(self):
        self.assertEqual(match_score(KOB, "miles davis kind of blue"), 1.0)


class Scoring(unittest.TestCase):
    def setUp(self):
        self.cfg = Config()

    def test_under_max(self):
        d = evaluate(KOB, L(10, shipping=4), None, self.cfg)
        self.assertIsNotNone(d)
        self.assertEqual(d.total, 14)
        self.assertEqual(d.tier, "STEAL")  # 14/25 = 0.56

    def test_over_max_no_ref(self):
        self.assertIsNone(evaluate(KOB, L(30, shipping=0), None, self.cfg))

    def test_ref_discount_without_max(self):
        w = WantItem("Miles Davis", "Kind of Blue")
        ref = Reference(50, "test")
        d = evaluate(w, L(15, shipping=0), ref, self.cfg)
        self.assertEqual(d.tier, "STEAL")
        self.assertIn("70% below", d.reasons[0])
        self.assertAlmostEqual(d.flip_profit, 50 * 0.85 - 15)

    def test_flip_only(self):
        w = WantItem("Miles Davis", "Kind of Blue")
        d = evaluate(w, L(30, shipping=0), Reference(50, "t"), self.cfg)  # 60% exactly = deal
        self.assertIsNotNone(d)
        self.assertIsNone(evaluate(w, L(40, shipping=0), Reference(50, "t"), self.cfg))

    def test_assumed_shipping_and_local(self):
        self.assertEqual(evaluate(KOB, L(10), None, self.cfg).total, 15)
        d = evaluate(KOB, L(10, local=True), None, self.cfg)
        self.assertEqual(d.total, 10)

    def test_auction_timing(self):
        soon = evaluate(KOB, L(5, shipping=0, is_auction=True, ends_at="2026-11-09T06:00:00Z"), None, self.cfg, now=NOW)
        late = evaluate(KOB, L(5, shipping=0, is_auction=True, ends_at="2026-11-14T06:00:00Z"), None, self.cfg, now=NOW)
        over = evaluate(KOB, L(5, shipping=0, is_auction=True, ends_at="2026-11-08T06:00:00Z"), None, self.cfg, now=NOW)
        self.assertIsNotNone(soon)
        self.assertAlmostEqual(soon.hours_left, 4)
        self.assertIsNone(late)
        self.assertIsNone(over)

    def test_currency_mismatch(self):
        self.assertIsNone(evaluate(KOB, L(5, currency="GBP"), None, self.cfg))

    def test_buy_under(self):
        self.assertEqual(buy_under(KOB, Reference(100, "t"), self.cfg), 60)
        self.assertEqual(buy_under(KOB, None, self.cfg), 25)


class Parsers(unittest.TestCase):
    def test_ebay(self):
        items = parse_items(json.loads((FX / "ebay_search.json").read_text()))
        self.assertEqual(len(items), 4)
        a, cd, auc, nos = items
        self.assertEqual((a.price, a.shipping), (9.99, 4.5))
        self.assertTrue(auc.is_auction)
        self.assertEqual(auc.price, 6.0)  # current bid, not starting/BIN
        self.assertIsNone(nos.shipping)
        self.assertFalse(nos.is_auction)

    def test_ebay_local(self):
        items = parse_items(json.loads((FX / "ebay_search.json").read_text()), local=True)
        self.assertTrue(all(i.local for i in items))
        self.assertEqual(items[3].shipping, 0.0)

    def test_shopify(self):
        items = parse_suggest(json.loads((FX / "shopify_suggest.json").read_text()),
                              {"name": "Shop", "url": "https://shop.example/", "local": True})
        self.assertEqual(len(items), 1)  # sold-out one skipped
        self.assertEqual(items[0].url, "https://shop.example/products/kind-of-blue-used")
        self.assertEqual(items[0].price, 12.0)
        self.assertTrue(is_match(KOB, items[0].title))

    def test_rss(self):
        items = parse_feed((FX / "feed.xml").read_bytes(), {"name": "Feed", "local": True})
        self.assertEqual([i.price for i in items], [8.0, 12.5])
        self.assertTrue(items[0].local)


class Pipeline(unittest.TestCase):
    def test_end_to_end_ebay(self):
        cfg = Config()
        items = parse_items(json.loads((FX / "ebay_search.json").read_text()))
        deals = [evaluate(KOB, l, Reference(40, "Discogs VG+ suggestion"), cfg, now=NOW)
                 for l in items if is_match(KOB, l.title, extra_text=l.condition)]
        deals = [d for d in deals if d]
        self.assertEqual({d.listing.source_id for d in deals}, {"v1|111|0", "v1|333|0", "v1|444|0"})
        title, body = format_deal(deals[0])
        self.assertIn("Miles Davis", title)
        self.assertIn("https://www.ebay.com/itm/111", body)

    def test_store_realert(self):
        with tempfile.TemporaryDirectory() as td:
            s = Store(Path(td) / "t.db")
            d = evaluate(KOB, L(10, shipping=0), None, Config())
            self.assertTrue(s.should_alert(d.listing.key, 10, 10))
            s.record_alert(d)
            self.assertFalse(s.should_alert(d.listing.key, 10, 10))
            self.assertFalse(s.should_alert(d.listing.key, 9.5, 10))
            self.assertTrue(s.should_alert(d.listing.key, 8.5, 10))
            s.cache_set("k", {"a": 1})
            self.assertEqual(s.cache_get("k", 1), {"a": 1})
            s.close()

    def test_wantlist_roundtrip_and_guide(self):
        with tempfile.TemporaryDirectory() as td:
            items = load_wantlist(Path(__file__).parents[1] / "wantlist.example.csv")
            self.assertGreaterEqual(len(items), 5)
            p = Path(td) / "w.csv"
            write_wantlist(p, items)
            again = load_wantlist(p)
            self.assertEqual([i.key for i in again], [i.key for i in items])
            self.assertEqual(again[-2].must_include, ["original", "riverside"])
            cfg = Config(facebook_city="nyc", craigslist_site="newyork", home_zip="10001")
            html = build_guide([(w, None) for w in items], cfg)
            self.assertIn("facebook.com/marketplace/nyc/search", html)
            self.assertIn("newyork.craigslist.org", html)


if __name__ == "__main__":
    unittest.main()
