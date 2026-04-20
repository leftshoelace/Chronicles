"""SQLite-backed seen-store. DB is committed back to the repo each run so
state persists across GitHub Actions invocations."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .model import Listing

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "seen.sqlite3"


def ensure_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS seen (
                fingerprint TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                source TEXT NOT NULL,
                price INTEGER,
                bedrooms REAL,
                neighborhood TEXT,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def filter_new(listings: list[Listing]) -> list[Listing]:
    if not listings:
        return []
    with _connect() as c:
        rows = c.execute("SELECT fingerprint FROM seen").fetchall()
        seen = {r[0] for r in rows}
    return [l for l in listings if l.fingerprint() not in seen]


def mark_seen(listings: list[Listing]) -> None:
    if not listings:
        return
    with _connect() as c:
        c.executemany(
            """
            INSERT OR IGNORE INTO seen
                (fingerprint, url, source, price, bedrooms, neighborhood)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    l.fingerprint(),
                    l.url,
                    l.source,
                    l.price,
                    l.bedrooms,
                    l.neighborhood,
                )
                for l in listings
            ],
        )


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
