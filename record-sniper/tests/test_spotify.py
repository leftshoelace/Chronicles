import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sniper import cli, spotify
from sniper.wantlist import load_wantlist, write_wantlist


def track(name, album, artist="Fleetwood Mac", total=11, atype="album", date="1977-02-04"):
    return {"name": name, "artists": [{"name": artist}],
            "album": {"name": album, "album_type": atype, "total_tracks": total, "release_date": date,
                      "artists": [{"name": artist}]}}


TRACKS = [
    track("Dreams", "Rumours"), track("Go Your Own Way", "Rumours"), track("The Chain", "Rumours"),
    track("Dreams", "Rumours (Super Deluxe)", total=40),           # same song, deluxe edition
    track("Hey Jude", "Past Masters", artist="The Beatles", atype="compilation", total=30),
    track("One Hit", "Some Single", artist="X", atype="single", total=1),
    track("Idioteque", "Kid A", artist="Radiohead", total=10, date="2000-10-02"),
    track("Everything In Its Right Place", "Kid A", artist="Radiohead", total=10),
    track("Lonely", "Big Album", artist="Solo", total=14),          # only 1 of 14 → excluded
    track("Gem", "Tiny EP", artist="Small", atype="single", total=4),
    track("Gem2", "Tiny EP", artist="Small", atype="single", total=4),
]


class Spotify(unittest.TestCase):
    def test_pkce_rfc7636_vector(self):
        self.assertEqual(spotify.pkce_challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"),
                         "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")

    def test_verifier_length_valid(self):
        self.assertTrue(43 <= len(spotify.new_verifier()) <= 128)

    def test_auth_url_and_callback(self):
        u = spotify.build_auth_url("cid", spotify.DEFAULT_REDIRECT, "v" * 50, "st")
        self.assertIn("code_challenge_method=S256", u)
        self.assertIn("127.0.0.1%3A8888", u)
        self.assertEqual(spotify.parse_callback("/callback?code=abc&state=st", "st"), "abc")
        self.assertEqual(spotify.parse_callback("http://127.0.0.1:8888/callback?code=abc&state=st", "st"), "abc")
        with self.assertRaises(RuntimeError):
            spotify.parse_callback("/callback?code=abc&state=BAD", "st")
        with self.assertRaises(RuntimeError):
            spotify.parse_callback("/callback?error=access_denied&state=st", "st")

    def test_clean_title(self):
        c = spotify.clean_album_title
        self.assertEqual(c("Rumours (Super Deluxe)"), "Rumours")
        self.assertEqual(c("Rumours - 2013 Remaster"), "Rumours")
        self.assertEqual(c("Kid A [Remastered]"), "Kid A")
        self.assertEqual(c("Blue (Expanded Edition)"), "Blue")
        self.assertEqual(c("Remain in Light"), "Remain in Light")
        self.assertEqual(c("Deluxe"), "Deluxe")  # never returns empty

    def test_analyze(self):
        res = spotify.analyze(TRACKS, top_artists=["Radiohead", "Fleetwood Mac"])
        names = [(a.artist, a.title) for a in res]
        self.assertEqual(names[0], ("Radiohead", "Kid A"))           # 2/10 liked + #1 top artist
        self.assertIn(("Fleetwood Mac", "Rumours"), names)
        rum = next(a for a in res if a.title == "Rumours")
        self.assertEqual(rum.liked, 3)                                # deluxe dup not double counted
        self.assertEqual(rum.total_tracks, 11)                        # standard edition track count
        self.assertEqual(rum.year, "1977")
        self.assertNotIn("Past Masters", [a.title for a in res])      # compilation
        self.assertNotIn("Some Single", [a.title for a in res])
        self.assertNotIn("Big Album", [a.title for a in res])         # 1/14
        self.assertIn("Tiny EP", [a.title for a in res])              # 4-track EP, 2 liked

    def test_to_wants(self):
        w = spotify.to_wants(spotify.analyze(TRACKS))
        self.assertTrue(all(x.notes.startswith("Spotify:") for x in w))

    def test_token_file_private_and_refresh(self):
        with tempfile.TemporaryDirectory() as td:
            a = spotify.SpotifyAuth("cid", Path(td) / "t.json")
            a._save({"access_token": "A", "refresh_token": "R", "expires_in": 3600})
            self.assertEqual((Path(td) / "t.json").stat().st_mode & 0o777, 0o600)
            self.assertEqual(a.access_token(), "A")                    # still valid → no network
            a._save({"access_token": "OLD", "refresh_token": "R", "expires_in": 0})
            with mock.patch.object(a, "_token_request", return_value={"access_token": "NEW", "expires_in": 3600}) as m:
                self.assertEqual(a.access_token(), "NEW")
            self.assertEqual(m.call_args[0][0]["grant_type"], "refresh_token")
            self.assertEqual(a.access_token(), "NEW")                  # refresh token preserved on disk

    def test_command_end_to_end(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            from sniper.models import WantItem
            write_wantlist(td / "wantlist.csv", [WantItem("Radiohead", "Kid A")])  # already wanted
            from sniper.config import Config
            from sniper.db import Store
            cfg = Config(spotify_client_id="cid", base_dir=td)
            args = mock.Mock(min_liked=2, min_fraction=0.3, limit=50, add=True, no_browser=True,
                             output=str(td / "suggestions.csv"))
            with mock.patch.object(cli, "SpotifyAuth") as A, mock.patch.object(cli, "SpotifyClient") as C:
                A.return_value.access_token.return_value = "tok"
                C.return_value.saved_tracks.return_value = TRACKS
                C.return_value.top_artists.return_value = ["Radiohead"]
                self.assertEqual(cli.cmd_spotify(cfg, Store(td / "s.db"), args), 0)
            keys = [w.key for w in load_wantlist(td / "wantlist.csv")]
            self.assertEqual(keys.count("radiohead|kid a"), 1)         # not duplicated
            self.assertIn("fleetwood mac|rumours", keys)
            sug = [w.key for w in load_wantlist(td / "suggestions.csv")]
            self.assertNotIn("radiohead|kid a", sug)


if __name__ == "__main__":
    unittest.main()
