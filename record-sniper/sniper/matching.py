"""Decide whether a listing title is really the record you want."""
from __future__ import annotations

import difflib
import re
import unicodedata

from .models import WantItem

STOPWORDS = {"the", "a", "an", "and", "of", "lp", "vinyl", "record", "records", "album", "12", "12in", "ep", "s"}

# Listings that mention these are almost never the actual record.
DEFAULT_EXCLUDE = [
    "cd", "cds", "cassette", "tape", "8 track", "8track", "dvd", "blu ray", "bluray", "mp3", "digital download only",
    "poster", "shirt", "t shirt", "tshirt", "hoodie", "slipmat", "sticker", "patch", "pin badge", "flag",
    "sleeve only", "jacket only", "cover only", "empty sleeve", "empty jacket", "no vinyl", "no record",
    "sheet music", "songbook", "book only", "box only", "frame", "framed", "magazine", "test pressing sleeve",
]

# Grading scale (Goldmine), low → high.
GRADES = ["P", "F", "G", "G+", "VG-", "VG", "VG+", "NM", "M"]
_GRADE_ALIASES = {
    "poor": "P", "fair": "F", "good": "G", "good plus": "G+", "very good": "VG", "very good plus": "VG+",
    "near mint": "NM", "m-": "NM", "nm-": "NM", "nm/m-": "NM", "mint": "M", "sealed": "M", "vg++": "VG+",
    "ex": "VG+", "excellent": "VG+", "ex+": "NM",
}
_GRADE_RE = re.compile(
    r"(?<![A-Za-z])(NM/M-|NM-|NM|M-|VG\+\+|VG\+|VG-|VG|G\+|EX\+|EX)(?![A-Za-z+-])|"
    r"\b(near mint|very good plus|very good|good plus|excellent|sealed)\b",
    re.I,
)


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", " and ").replace("'", "")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(s: str) -> set[str]:
    return {t for t in normalize(s).split() if t not in STOPWORDS}


def _has(tok: str, pool: set[str]) -> bool:
    if tok in pool:
        return True
    if len(tok) >= 5:  # tolerate small typos in longer words ("coltrain" vs "coltrane")
        return bool(difflib.get_close_matches(tok, pool, n=1, cutoff=0.85))
    return False


def _coverage(want_toks: set[str], pool: set[str]) -> float:
    if not want_toks:
        return 1.0
    return sum(_has(t, pool) for t in want_toks) / len(want_toks)


def _contains_phrase(norm_text: str, phrase: str) -> bool:
    p = normalize(phrase)
    return bool(p) and re.search(rf"(?<![a-z0-9]){re.escape(p)}(?![a-z0-9])", norm_text) is not None


def match_score(want: WantItem, title: str) -> float:
    pool = tokens(title)
    return min(_coverage(tokens(want.artist), pool), _coverage(tokens(want.title), pool))


def parse_grade(text: str) -> str | None:
    """Return the best media grade mentioned in a listing, normalised to GRADES, or None."""
    found: list[str] = []
    for m in _GRADE_RE.finditer(text):
        g = (m.group(1) or m.group(2)).upper()
        g = _GRADE_ALIASES.get(g.lower(), g)
        if g in GRADES:
            found.append(g)
    if not found:
        return None
    # Sellers often write "VG+/NM" meaning media/sleeve; be conservative and take the lowest.
    return min(found, key=GRADES.index)


def grade_ok(listing_text: str, min_condition: str | None) -> bool:
    if not min_condition:
        return True
    want = _GRADE_ALIASES.get(min_condition.lower(), min_condition.upper())
    if want not in GRADES:
        return True
    got = parse_grade(listing_text)
    return got is None or GRADES.index(got) >= GRADES.index(want)


def is_match(want: WantItem, title: str, threshold: float = 0.8, extra_text: str = "") -> bool:
    norm = normalize(title)
    want_norm = normalize(want.query)
    for phrase in DEFAULT_EXCLUDE + want.exclude:
        # Don't exclude a word that is part of what you're looking for (an album called "Tape", say).
        if _contains_phrase(norm, phrase) and not _contains_phrase(want_norm, phrase):
            return False
    full = normalize(f"{title} {extra_text}")
    for phrase in want.must_include:
        if not _contains_phrase(full, phrase):
            return False
    if not grade_ok(f"{title} {extra_text}", want.min_condition):
        return False
    return match_score(want, title) >= threshold
