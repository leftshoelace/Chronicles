"""Spotify: read your liked songs + top artists, work out which ALBUMS you love, suggest them as wants.

Uses Spotify's official Web API with the PKCE login flow (no client secret needed, nothing is
shared with anyone but Spotify). Read-only scopes: user-library-read, user-top-read.

One-time setup: create a free app at https://developer.spotify.com/dashboard and add this exact
Redirect URI:  http://127.0.0.1:8888/callback   (Spotify requires 127.0.0.1, not "localhost").
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from .http import HttpError, get_json, request
from .models import WantItem

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"
SCOPES = "user-library-read user-top-read"
DEFAULT_REDIRECT = "http://127.0.0.1:8888/callback"


# --- PKCE / auth ---------------------------------------------------------------------------

def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def new_verifier() -> str:
    return secrets.token_urlsafe(64)[:96]


def build_auth_url(client_id: str, redirect_uri: str, verifier: str, state: str) -> str:
    return AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id, "response_type": "code", "redirect_uri": redirect_uri,
        "scope": SCOPES, "code_challenge_method": "S256", "code_challenge": pkce_challenge(verifier),
        "state": state,
    })


def parse_callback(url_or_query: str, expected_state: str) -> str:
    """Extract the auth code from the redirect URL (or a pasted copy of it)."""
    q = urllib.parse.urlparse(url_or_query).query or url_or_query.lstrip("?")
    p = urllib.parse.parse_qs(q)
    if p.get("error"):
        raise RuntimeError(f"Spotify login failed: {p['error'][0]}")
    if p.get("state", [""])[0] != expected_state:
        raise RuntimeError("Spotify login failed: state mismatch (try again)")
    if not p.get("code"):
        raise RuntimeError("Spotify login failed: no code in redirect")
    return p["code"][0]


class _Callback(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.server.result = self.path  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("<h2>Connected to Record Sniper ✓</h2><p>You can close this tab.</p>".encode())

    def log_message(self, *a):  # silence
        pass


def _wait_for_redirect(redirect_uri: str, timeout: float = 180) -> str | None:
    u = urllib.parse.urlparse(redirect_uri)
    try:
        srv = HTTPServer((u.hostname or "127.0.0.1", u.port or 80), _Callback)
    except OSError:
        return None
    srv.timeout = timeout
    srv.result = None  # type: ignore[attr-defined]
    try:
        srv.handle_request()
    finally:
        srv.server_close()
    return srv.result  # type: ignore[attr-defined]


class SpotifyAuth:
    def __init__(self, client_id: str, token_path: Path, redirect_uri: str = DEFAULT_REDIRECT):
        self.client_id = client_id
        self.token_path = Path(token_path)
        self.redirect_uri = redirect_uri

    def _save(self, tok: dict, old_refresh: str | None = None) -> dict:
        tok = dict(tok)
        tok["refresh_token"] = tok.get("refresh_token") or old_refresh
        tok["expires_at"] = time.time() + int(tok.get("expires_in", 3600))
        fd = os.open(self.token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(tok, f)
        return tok

    def _token_request(self, form: dict) -> dict:
        raw = request(TOKEN_URL, method="POST", data=urllib.parse.urlencode(form),
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
        return json.loads(raw)

    def login(self, open_browser: bool = True) -> dict:
        verifier, state = new_verifier(), secrets.token_urlsafe(16)
        url = build_auth_url(self.client_id, self.redirect_uri, verifier, state)
        print("Log in to Spotify to let Record Sniper read your liked songs (read-only):\n  " + url)
        if open_browser:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        got = _wait_for_redirect(self.redirect_uri)
        if not got:
            got = input("\nCouldn't catch the redirect automatically. After approving, your browser will show an "
                        "error page — paste its full address bar URL here:\n> ").strip()
        code = parse_callback(got, state)
        tok = self._token_request({
            "grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri,
            "client_id": self.client_id, "code_verifier": verifier,
        })
        return self._save(tok)

    def access_token(self, open_browser: bool = True) -> str:
        tok = None
        if self.token_path.exists():
            try:
                tok = json.loads(self.token_path.read_text())
            except ValueError:
                tok = None
        if tok and tok.get("expires_at", 0) > time.time() + 60:
            return tok["access_token"]
        if tok and tok.get("refresh_token"):
            try:
                new = self._token_request({"grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
                                           "client_id": self.client_id})
                return self._save(new, tok["refresh_token"])["access_token"]
            except HttpError:
                pass  # refresh token revoked/expired → log in again
        return self.login(open_browser)["access_token"]


# --- fetching ------------------------------------------------------------------------------

class SpotifyClient:
    def __init__(self, token: str):
        self.headers = {"Authorization": f"Bearer {token}"}

    def _pages(self, url: str, params: dict | None = None):
        while url:
            data = get_json(url, params=params, headers=self.headers)
            yield from data.get("items", [])
            url, params = data.get("next"), None

    def saved_tracks(self) -> list[dict]:
        return [i["track"] for i in self._pages(f"{API}/me/tracks", {"limit": 50}) if i.get("track")]

    def top_artists(self, time_range: str = "long_term") -> list[str]:
        data = get_json(f"{API}/me/top/artists", params={"limit": 50, "time_range": time_range}, headers=self.headers)
        return [a["name"] for a in data.get("items", [])]


# --- analysis ------------------------------------------------------------------------------

_EDITION_WORDS = r"deluxe|remaster(?:ed)?|edition|expanded|anniversary|bonus|version|reissue|mono|stereo|legacy|super|explicit"
_PAREN = re.compile(rf"\s*[\(\[][^)\]]*\b(?:{_EDITION_WORDS})\b[^)\]]*[\)\]]", re.I)
_DASH = re.compile(rf"\s+[-–]\s+[^-–]*\b(?:{_EDITION_WORDS})\b.*$", re.I)


def clean_album_title(title: str) -> str:
    """'Rumours (Super Deluxe)' / 'Rumours - 2013 Remaster' → 'Rumours'."""
    t = _PAREN.sub("", title)
    t = _DASH.sub("", t)
    return t.strip() or title.strip()


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


@dataclass
class AlbumStat:
    artist: str
    title: str
    liked_tracks: set[str] = field(default_factory=set)
    total_tracks: int = 0
    year: str = ""
    artist_rank: int | None = None  # position in your top artists (0 = most listened)
    score: float = 0.0

    @property
    def liked(self) -> int:
        return len(self.liked_tracks)

    @property
    def fraction(self) -> float:
        return min(1.0, self.liked / self.total_tracks) if self.total_tracks else 0.0

    def reason(self) -> str:
        bits = [f"{self.liked} liked song{'s' if self.liked != 1 else ''}"]
        if self.total_tracks:
            bits[0] += f" of {self.total_tracks}"
        if self.artist_rank is not None:
            bits.append(f"#{self.artist_rank + 1} top artist")
        return ", ".join(bits)


def analyze(tracks: list[dict], top_artists: list[str] | None = None, min_liked: int = 2,
            min_fraction: float = 0.3) -> list[AlbumStat]:
    """Group liked tracks into albums and rank how much you love each one."""
    ranks = {_norm(a): i for i, a in enumerate(top_artists or [])}
    albums: dict[tuple[str, str], AlbumStat] = {}
    for t in tracks:
        alb = t.get("album") or {}
        artists = alb.get("artists") or t.get("artists") or []
        if not artists or not alb.get("name"):
            continue
        atype, total = alb.get("album_type", "album"), int(alb.get("total_tracks") or 0)
        if atype == "compilation" or (atype == "single" and total < 4):
            continue  # singles/comps aren't what you're hunting on vinyl
        artist = artists[0]["name"]
        title = clean_album_title(alb["name"])
        key = (_norm(artist), _norm(title))
        st = albums.setdefault(key, AlbumStat(artist=artist, title=title))
        st.liked_tracks.add(_norm(t.get("name", "")))  # dedupes the same song on standard + deluxe
        if total and (not st.total_tracks or total < st.total_tracks):
            st.total_tracks = total  # standard edition, not the 40-track deluxe
        st.year = st.year or (alb.get("release_date") or "")[:4]
        st.artist_rank = ranks.get(_norm(artist))

    out = []
    for st in albums.values():
        if st.liked < min_liked and st.fraction < min_fraction:
            continue
        boost = 3 * (1 - st.artist_rank / max(len(ranks), 1)) if st.artist_rank is not None else 0
        st.score = round(st.liked + 4 * st.fraction + boost, 2)
        out.append(st)
    return sorted(out, key=lambda s: s.score, reverse=True)


def to_wants(albums: list[AlbumStat]) -> list[WantItem]:
    return [WantItem(artist=a.artist, title=a.title, notes=f"Spotify: {a.reason()}") for a in albums]
